"""Bounded deterministic velocity-scale calibration."""
from __future__ import annotations
import json, math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from ..hypothesis.canonical import canonical_value, validate_identifier, validate_sha256

class CalibrationError(ValueError): pass

@dataclass(frozen=True)
class CalibrationResult:
    parameters: MappingProxyType
    train_rmse: float
    evaluation_rmse: float
    evidence_level: str
    pipeline_test_only: bool

def _finite(v,n):
    if type(v) not in (int,float) or not math.isfinite(float(v)): raise CalibrationError(f"{n} must be finite")
    return float(v)

def load_calibration_dataset(path):
    try:
        raw=Path(path).read_bytes()
        if len(raw)>5*1024*1024: raise CalibrationError("dataset exceeds maximum size")
        value=canonical_value(json.loads(raw.decode('utf-8'), object_pairs_hook=lambda p: _pairs(p)),"calibration dataset")
    except CalibrationError: raise
    except Exception as e: raise CalibrationError(f"cannot load calibration dataset: {e}") from None
    if not isinstance(value,dict): raise CalibrationError("dataset root must be object")
    return value
def _pairs(pairs):
    d={}
    for k,v in pairs:
        if k in d: raise CalibrationError(f"duplicate JSON key: {k}")
        d[k]=v
    return d

def fit_calibration(data):
    try: d=canonical_value(data,"calibration dataset")
    except Exception as e: raise CalibrationError(f"dataset invalid: {e}") from None
    fields={"schema_version","dataset_id","artifact_sha256","evidence_level","pipeline_test_only","parameter_bounds","samples"}
    if not isinstance(d,dict) or set(d)!=fields: raise CalibrationError("dataset has unknown or missing fields")
    if d["schema_version"]!=1 or type(d["schema_version"]) is not int: raise CalibrationError("schema_version must be integer 1")
    validate_identifier(d["dataset_id"],"dataset_id")
    try: validate_sha256(d["artifact_sha256"],"artifact_sha256")
    except ValueError as e: raise CalibrationError(str(e)) from None
    level=d["evidence_level"]
    if level not in {"simulated","bench_tested","integrated_hardware_tested"}: raise CalibrationError("evidence_level is invalid")
    if type(d["pipeline_test_only"]) is not bool or d["pipeline_test_only"] != (level=="simulated"): raise CalibrationError("pipeline_test_only is inconsistent")
    b=d["parameter_bounds"]
    if not isinstance(b,dict) or set(b)!={"velocity_scale"} or not isinstance(b["velocity_scale"],dict) or set(b["velocity_scale"])!={"lower","upper"}: raise CalibrationError("bounds are invalid")
    lo,hi=_finite(b["velocity_scale"]["lower"],"lower"),_finite(b["velocity_scale"]["upper"],"upper")
    if not 0<lo<hi: raise CalibrationError("bounds are invalid")
    s=d["samples"]
    if not isinstance(s,list) or not 4<=len(s)<=10000: raise CalibrationError("samples are invalid")
    seen=set(); train=[]; ev=[]
    for i,x in enumerate(s):
        if not isinstance(x,dict) or set(x)!={"sample_id","command_m_s","observed_m_s","split"}: raise CalibrationError("sample fields are invalid")
        ident=validate_identifier(x["sample_id"],"sample_id")
        if ident in seen: raise CalibrationError("duplicate sample_id")
        seen.add(ident); a,y=_finite(x["command_m_s"],"command_m_s"),_finite(x["observed_m_s"],"observed_m_s")
        if x["split"] not in {"train","evaluation"}: raise CalibrationError("sample split is invalid")
        (train if x["split"]=="train" else ev).append((a,y))
    if len(train)<2 or len(ev)<2: raise CalibrationError("train and evaluation samples each require at least two records")
    denom=sum(a*a for a,_ in train)
    if denom<=0 or len({a for a,_ in train})<2: raise CalibrationError("training input is singular")
    scale=min(hi,max(lo,sum(a*y for a,y in train)/denom))
    unconstrained=sum(a*y for a,y in train)/denom
    if not lo <= unconstrained <= hi: raise CalibrationError("fit falls outside parameter bounds")
    rmse=lambda group: math.sqrt(sum((scale*a-y)**2 for a,y in group)/len(group))
    tr,er=rmse(train),rmse(ev)
    if er>0.05: raise CalibrationError("evaluation residual exceeds bounded threshold")
    return CalibrationResult(MappingProxyType({"velocity_scale":scale}),tr,er,"simulated" if level=="simulated" else "calibrated_simulation",level=="simulated")
