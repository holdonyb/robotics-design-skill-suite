"""Deterministic bounded hypothesis-space orchestration."""
from __future__ import annotations
import hashlib, json, tempfile
from pathlib import Path
from typing import Any
from .bundle import write_bundle
from .canonical import canonical_bytes, validate_integer
from .overlay import OverlayError, generate_candidates
from .schema import load_space
from .scheduler import HypothesisScheduler
from .objectives import extract_vector, pareto_fronts
from .uncertainty import ordered_cases, apply_case, search_counterexample, evaluate_sensitivity
from .overlay import ResolvedCandidate
from .repair import RepairError, repair, select_repair

class EngineError(ValueError): pass
def _base(space, source):
    record=space["base_contract"]; path=(source.parent/record["path"]).resolve()
    if not path.is_relative_to(source.parent.resolve()): raise EngineError("base contract path escapes hypothesis-space directory")
    try: raw=path.read_bytes(); data=json.loads(raw.decode("utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc: raise EngineError(f"cannot load base contract: {exc}") from None
    digest=hashlib.sha256(canonical_bytes(data)).hexdigest()
    if digest != record["sha256"]: raise EngineError(f"base contract SHA-256 mismatch: declared {record['sha256']}, observed {digest}")
    return path,data
def run_space(space_path, output, *, seed, force=False):
    source=Path(space_path); space,errors=load_space(source)
    if errors: raise EngineError("; ".join(errors))
    try: checked_seed=validate_integer(seed,"seed")
    except ValueError as exc: raise EngineError(str(exc)) from None
    base_path,base=_base(space,source)
    try: candidates=generate_candidates(space,base,seed=checked_seed)
    except OverlayError as exc: raise EngineError(str(exc)) from None
    scheduler=HypothesisScheduler(max_stage_evaluations=space["evaluation"]["max_stage_evaluations"],artifact_root=base_path.parent)
    files={}; lineage=[]; accepted=0; vectors={}
    with tempfile.TemporaryDirectory(prefix=".hypothesis-cache-",dir=Path(output).parent) as cache_raw:
      for candidate in candidates:
        contract=candidate.resolved_contract; cid=candidate.candidate_id
        files[f"candidates/{cid}/contract.json"]=contract
        if candidate.alias_of is None:
            stages=scheduler.evaluate(candidate,Path(cache_raw),stages=space["evaluation"]["stages"])
            stage_data=[stage.to_dict() for stage in stages]
            files[f"candidates/{cid}/stages.json"]=stage_data
            physical=next((stage for stage in stages if stage.name=="physical_v030"),None)
            report=None if physical is None else physical.to_dict()["output"].get("report")
            promotable=physical is not None and physical.status=="passed"
            if report is not None:
                vector=extract_vector(cid,contract,report,space["objectives"])
                vectors[cid]=vector
                files[f"candidates/{cid}/objectives.json"]=vector.to_dict()
            if space["uncertainties"] and physical is not None:
                remaining=(space["evaluation"]["max_stage_evaluations"]-scheduler.evaluation_count)//2
                if remaining < 1: raise EngineError("insufficient remaining evaluation budget for uncertainty cases")
                cases=ordered_cases(cid,contract,space["uncertainties"],seed=checked_seed,max_evaluations=remaining)
                outcomes={}
                def evaluate_case(case):
                    if case.case_id in outcomes: return outcomes[case.case_id]
                    if case.nominal:
                        nominal_report=physical.to_dict()["output"].get("report")
                        vector=extract_vector(cid,contract,nominal_report,space["objectives"])
                        outcomes[case.case_id]={"promotable":physical.status=="passed","diagnostic_codes":sorted({item["code"] for item in physical.to_dict()["diagnostics"]}),"objectives":dict(vector.values)}
                        return outcomes[case.case_id]
                    varied=apply_case(contract,case)
                    content={key:value for key,value in varied.items() if key!="candidate_id"}
                    varied_candidate=ResolvedCandidate(candidate.decision,varied,hashlib.sha256(canonical_bytes(content)).hexdigest(),candidate.contract_errors)
                    results=scheduler.evaluate(varied_candidate,Path(cache_raw),stages=("contract_v1","physical_v030"),uncertainty_case=case.to_dict())
                    stage=results[-1]; body=stage.to_dict()["output"].get("report")
                    vector=extract_vector(cid,varied,body,space["objectives"]) if body is not None else None
                    outcomes[case.case_id]={"promotable":stage.status=="passed","diagnostic_codes":sorted({item["code"] for item in stage.to_dict()["diagnostics"]}),"objectives":{} if vector is None else dict(vector.values)}
                    return outcomes[case.case_id]
                files[f"candidates/{cid}/cases.json"]=[case.to_dict() for case in cases]
                files[f"candidates/{cid}/counterexample.json"]=search_counterexample(cases,evaluate_case).to_dict()
                files[f"candidates/{cid}/sensitivity.json"]=[item.to_dict() for item in evaluate_sensitivity(cases,evaluate_case)]
            if physical is not None and physical.status in {"failed", "blocked", "indeterminate"} and space["repair_rules"] and len(candidates)+len([item for item in lineage if item.get("parent_id")]) < space["max_candidates"]:
                diagnostic_records=[dict(item,stage="physical_v030") for item in physical.to_dict()["diagnostics"]]
                try:
                    diagnostic, rule=select_repair(diagnostic_records,space["repair_rules"])
                    child,trace=repair(candidate,diagnostic,rule,seen_hashes={candidate.resolved_contract_sha256},failed_stage="physical_v030")
                    child_stages=scheduler.evaluate(child,Path(cache_raw),stages=trace.rerun_stages)
                    files[f"candidates/{child.candidate_id}/contract.json"]=child.resolved_contract
                    files[f"candidates/{child.candidate_id}/stages.json"]=[stage.to_dict() for stage in child_stages]
                    files[f"candidates/{child.candidate_id}/repair-trace.json"]=trace.to_dict()
                    child_physical=next((stage for stage in child_stages if stage.name=="physical_v030"),None)
                    child_ok=child_physical is not None and child_physical.status=="passed"; accepted+=int(child_ok)
                    lineage.append({"candidate_id":child.candidate_id,"parent_id":cid,"assignments":dict(child.decision.assignments),"repair_rule_id":rule["id"],"resolved_contract_sha256":child.resolved_contract_sha256,"status":"accepted" if child_ok else "rejected","alias_of":None})
                except RepairError:
                    pass
            accepted += int(promotable)
        else:
            stage_data=[]; promotable=False
        lineage.append({"candidate_id":cid,"parent_id":None,"assignments":dict(candidate.decision.assignments),"repair_rule_id":None,"resolved_contract_sha256":candidate.resolved_contract_sha256,"status":"alias" if candidate.alias_of else ("accepted" if promotable else "rejected"),"alias_of":candidate.alias_of})
    index={"schema_version":1,"space_id":space["space_id"],"seed":checked_seed,"candidate_count":len(lineage),"accepted_count":accepted,"candidates":lineage}
    directions={item["id"]:item["direction"] for item in space["objectives"]}
    files["index.json"]=index; files["pareto.json"]=(pareto_fronts(vectors,directions).to_dict() if directions else {"fronts":[]})
    write_bundle(output,files,force=force)
    return index
