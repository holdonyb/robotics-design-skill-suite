"""Deterministic staged evaluation with a content-addressed local cache."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..engine import evaluate_contract
from ..model import Report
from .canonical import canonical_bytes, canonical_value
from .model import StageResult, StageSpec
from .overlay import ResolvedCandidate


KNOWN_STAGE_ORDER = (
    "contract_v1",
    "physical_v030",
    "uncertainty_v1",
    "counterexample_v1",
    "objectives_v1",
)
_KNOWN_STAGES = frozenset(KNOWN_STAGE_ORDER)
_BLOCKING_STATUSES = frozenset({"failed", "blocked", "indeterminate"})
_CACHE_SCHEMA_VERSION = 1
_MAX_CACHE_BYTES = 16 * 1024 * 1024


class SchedulerError(ValueError):
    """Raised when a stage graph, budget, or evaluation request is invalid."""


def default_registry() -> dict[str, StageSpec]:
    """Return a fresh registry containing exactly the five v0.4 stages."""

    return {
        "contract_v1": StageSpec("contract_v1", "1", (), 1_000_000),
        "physical_v030": StageSpec("physical_v030", "0.3.0", ("contract_v1",), 1_000_000),
        "uncertainty_v1": StageSpec("uncertainty_v1", "1", ("physical_v030",), 1_000_000),
        "counterexample_v1": StageSpec("counterexample_v1", "1", ("uncertainty_v1",), 1_000_000),
        "objectives_v1": StageSpec("objectives_v1", "1", ("physical_v030",), 1_000_000),
    }


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _validate_registry(registry: object) -> dict[str, StageSpec]:
    if not isinstance(registry, Mapping):
        raise SchedulerError("registry must be a mapping")
    if set(registry) != _KNOWN_STAGES:
        missing = sorted(_KNOWN_STAGES - set(registry))
        extra = sorted(set(registry) - _KNOWN_STAGES)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise SchedulerError("registry must contain exactly five known stages: " + "; ".join(details))
    checked: dict[str, StageSpec] = {}
    for name in KNOWN_STAGE_ORDER:
        spec = registry[name]
        if not isinstance(spec, StageSpec):
            raise SchedulerError(f"registry[{name}] must be a StageSpec")
        if spec.name != name:
            raise SchedulerError(f"registry key {name} does not match StageSpec name {spec.name}")
        unknown = sorted(set(spec.dependencies) - _KNOWN_STAGES)
        if unknown:
            raise SchedulerError(f"stage {name} has unknown dependencies: {', '.join(unknown)}")
        checked[name] = spec

    state: dict[str, int] = {}

    def visit(name: str, trail: tuple[str, ...]) -> None:
        current = state.get(name, 0)
        if current == 1:
            raise SchedulerError("stage dependency cycle: " + " -> ".join((*trail, name)))
        if current == 2:
            return
        state[name] = 1
        for dependency in checked[name].dependencies:
            visit(dependency, (*trail, name))
        state[name] = 2

    for name in KNOWN_STAGE_ORDER:
        visit(name, ())
    return checked


def _stage_from_dict(value: object) -> StageResult | None:
    if not isinstance(value, dict) or set(value) != {
        "name", "version", "status", "cache_key", "input_hash", "output", "diagnostics"
    }:
        return None
    try:
        diagnostics = value["diagnostics"]
        if not isinstance(diagnostics, list):
            return None
        return StageResult(
            name=value["name"],
            version=value["version"],
            status=value["status"],
            cache_key=value["cache_key"],
            input_hash=value["input_hash"],
            output=value["output"],
            diagnostics=tuple(diagnostics),
        )
    except (TypeError, ValueError):
        return None


class HypothesisScheduler:
    """Run a closed stage graph under one cumulative evaluation budget."""

    def __init__(
        self,
        *,
        registry: Mapping[str, StageSpec] | None = None,
        gate: Callable[[Path], tuple[Report | None, list[str]]] = evaluate_contract,
        tool_versions: Mapping[str, str] | None = None,
        artifact_root: Path | str | None = None,
        max_stage_evaluations: int = 1_000_000,
        handlers: Mapping[str, Callable[..., object]] | None = None,
    ) -> None:
        self.registry = _validate_registry(default_registry() if registry is None else registry)
        if not callable(gate):
            raise SchedulerError("gate must be callable")
        self.gate = gate
        versions = {"assurance_kernel": "0.3.0", "hypothesis_scheduler": "1"}
        if tool_versions is not None:
            if not isinstance(tool_versions, Mapping) or any(
                not isinstance(key, str) or not key or not isinstance(value, str) or not value
                for key, value in tool_versions.items()
            ):
                raise SchedulerError("tool_versions must map non-empty strings to non-empty strings")
            versions.update(tool_versions)
        self.tool_versions = dict(sorted(versions.items()))
        self.artifact_root = Path.cwd() if artifact_root is None else Path(artifact_root)
        if isinstance(max_stage_evaluations, bool) or not isinstance(max_stage_evaluations, int) or not 1 <= max_stage_evaluations <= 1_000_000:
            raise SchedulerError("max_stage_evaluations must be an integer from 1 through 1000000")
        self.max_stage_evaluations = max_stage_evaluations
        self.evaluation_count = 0
        self.stage_evaluation_counts = {name: 0 for name in KNOWN_STAGE_ORDER}
        self.handlers = dict(handlers or {})
        unknown_handlers = sorted(set(self.handlers) - _KNOWN_STAGES)
        if unknown_handlers:
            raise SchedulerError("handlers contains unknown stages: " + ", ".join(unknown_handlers))

    def order(self, stages: Iterable[str]) -> tuple[str, ...]:
        if isinstance(stages, (str, bytes)):
            raise SchedulerError("stages must be an iterable of stage names")
        try:
            requested = tuple(stages)
        except TypeError as exc:
            raise SchedulerError("stages must be an iterable of stage names") from exc
        if not requested:
            raise SchedulerError("stages must not be empty")
        if any(not isinstance(name, str) or name not in _KNOWN_STAGES for name in requested):
            unknown = sorted({str(name) for name in requested if name not in _KNOWN_STAGES})
            raise SchedulerError("unknown stage: " + ", ".join(unknown))
        if len(set(requested)) != len(requested):
            raise SchedulerError("stages must not contain duplicates")
        selected = set(requested)
        for name in requested:
            missing = sorted(set(self.registry[name].dependencies) - selected)
            if missing:
                raise SchedulerError(f"stage {name} requires dependency: {', '.join(missing)}")

        indegree = {name: 0 for name in selected}
        consumers = {name: [] for name in selected}
        for name in selected:
            for dependency in self.registry[name].dependencies:
                indegree[name] += 1
                consumers[dependency].append(name)
        priority = {name: index for index, name in enumerate(KNOWN_STAGE_ORDER)}
        ready = sorted((name for name, degree in indegree.items() if degree == 0), key=priority.get)
        result = []
        while ready:
            name = ready.pop(0)
            result.append(name)
            for consumer in sorted(consumers[name], key=priority.get):
                indegree[consumer] -= 1
                if indegree[consumer] == 0:
                    ready.append(consumer)
                    ready.sort(key=priority.get)
        if len(result) != len(selected):
            raise SchedulerError("stage dependency cycle")
        return tuple(result)

    def evaluate(
        self,
        candidate: ResolvedCandidate,
        cache_dir: Path | str,
        *,
        stages: Iterable[str] = ("contract_v1", "physical_v030"),
        uncertainty_case: object = None,
    ) -> tuple[StageResult, ...]:
        if not isinstance(candidate, ResolvedCandidate):
            raise SchedulerError("candidate must be a ResolvedCandidate")
        ordered = self.order(stages)
        try:
            uncertainty = canonical_value(uncertainty_case, "uncertainty_case")
        except ValueError as exc:
            raise SchedulerError(str(exc)) from None
        contract = candidate.resolved_contract
        content = {key: value for key, value in contract.items() if key != "candidate_id"}
        try:
            observed_content_sha256 = _digest(content)
        except ValueError as exc:
            raise SchedulerError(f"candidate content cannot be hashed: {exc}") from None
        if observed_content_sha256 != candidate.resolved_contract_sha256:
            raise SchedulerError(
                "candidate content SHA-256 mismatch: "
                f"declared {candidate.resolved_contract_sha256}, observed {observed_content_sha256}"
            )
        cache_path = Path(cache_dir)
        results: dict[str, StageResult] = {}
        emitted: list[StageResult] = []
        for name in ordered:
            dependencies = tuple(results[item] for item in self.registry[name].dependencies)
            if any(item.status in _BLOCKING_STATUSES for item in dependencies):
                break
            self._consume_budget(name)
            result = self._evaluate_stage(candidate, cache_path, name, dependencies, uncertainty)
            results[name] = result
            emitted.append(result)
            if result.status in _BLOCKING_STATUSES:
                break
        return tuple(emitted)

    def _consume_budget(self, name: str) -> None:
        if self.evaluation_count + 1 > self.max_stage_evaluations:
            raise SchedulerError(
                f"max_stage_evaluations {self.max_stage_evaluations} would be exceeded "
                f"by stage {name} at count {self.evaluation_count}"
            )
        if self.stage_evaluation_counts[name] + 1 > self.registry[name].max_evaluations:
            raise SchedulerError(
                f"stage {name} max_evaluations {self.registry[name].max_evaluations} "
                f"would be exceeded at count {self.stage_evaluation_counts[name]}"
            )
        self.evaluation_count += 1
        self.stage_evaluation_counts[name] += 1

    def _evaluate_stage(
        self,
        candidate: ResolvedCandidate,
        cache_dir: Path,
        name: str,
        dependencies: tuple[StageResult, ...],
        uncertainty_case: object,
    ) -> StageResult:
        spec = self.registry[name]
        dependency_hashes = {
            item.name: _digest(item.to_dict()) for item in sorted(dependencies, key=lambda item: item.name)
        }
        key_payload = {
            "candidate_id": candidate.candidate_id,
            "candidate_content_sha256": candidate.resolved_contract_sha256,
            "stage": name,
            "stage_version": spec.version,
            "dependency_report_sha256": dependency_hashes,
            "uncertainty_case": uncertainty_case,
            "tool_versions": dict(sorted(self.tool_versions.items())),
        }
        input_hash = _digest(key_payload)
        cache_key = input_hash
        cached = self._read_cache(cache_dir, cache_key, spec)
        if cached is not None:
            return cached

        if name == "contract_v1":
            result = self._contract_stage(candidate, spec, cache_key, input_hash)
        elif name == "physical_v030":
            result = self._physical_stage(candidate, spec, cache_key, input_hash)
        else:
            handler = self.handlers.get(name)
            if handler is None:
                output = {
                    "dependency_report_sha256": dependency_hashes,
                    "uncertainty_case": uncertainty_case,
                }
                result = StageResult(name, spec.version, "passed", cache_key, input_hash, output)
            else:
                handled = handler(candidate, dependencies, uncertainty_case)
                if not isinstance(handled, StageResult):
                    raise SchedulerError(f"handler for {name} must return a StageResult")
                if handled.name != name or handled.version != spec.version or handled.cache_key != cache_key or handled.input_hash != input_hash:
                    raise SchedulerError(f"handler for {name} returned mismatched stage identity")
                result = handled
        self._write_cache(cache_dir, result)
        return result

    @staticmethod
    def _contract_stage(candidate: ResolvedCandidate, spec: StageSpec, cache_key: str, input_hash: str) -> StageResult:
        errors = list(candidate.contract_errors)
        diagnostics = tuple(
            {
                "code": "HYP.CONTRACT.INVALID",
                "severity": "error",
                "path": "contract",
                "message": error,
                "evidence_ids": [],
            }
            for error in errors
        )
        return StageResult(
            spec.name,
            spec.version,
            "blocked" if errors else "passed",
            cache_key,
            input_hash,
            {
                "candidate_id": candidate.candidate_id,
                "resolved_contract_sha256": candidate.resolved_contract_sha256,
                "schema_errors": errors,
            },
            diagnostics,
        )

    def _physical_stage(self, candidate: ResolvedCandidate, spec: StageSpec, cache_key: str, input_hash: str) -> StageResult:
        try:
            root = self.artifact_root.resolve()
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SchedulerError(f"physical_v030 artifact root failed: {exc}") from exc
        temporary = root / f".hypothesis-contract-{uuid.uuid4().hex}.tmp"
        try:
            data = canonical_bytes(candidate.resolved_contract)
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            report, schema_errors = self.gate(temporary)
        except OSError as exc:
            raise SchedulerError(f"physical_v030 temporary contract failed: {exc}") from exc
        except Exception as exc:
            raise SchedulerError(f"physical_v030 gate failed: {exc}") from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if report is not None and not isinstance(report, Report) and not callable(getattr(report, "to_dict", None)):
            raise SchedulerError("physical_v030 gate returned an invalid report")
        if not isinstance(schema_errors, list) or any(not isinstance(item, str) for item in schema_errors):
            raise SchedulerError("physical_v030 gate returned invalid schema errors")
        report_dict = None if report is None else report.to_dict()
        if report_dict is not None and not isinstance(report_dict, dict):
            raise SchedulerError("physical_v030 gate returned an invalid report payload")
        report_diagnostics = () if report_dict is None else report_dict.get("diagnostics", ())
        if not isinstance(report_diagnostics, list):
            raise SchedulerError("physical_v030 report contains invalid diagnostics")
        if any(not isinstance(item, dict) for item in report_diagnostics):
            raise SchedulerError("physical_v030 report contains invalid diagnostics")
        diagnostics = tuple(report_diagnostics)
        if schema_errors:
            diagnostics = diagnostics + tuple(
                {
                    "code": "HYP.PHYSICAL.SCHEMA",
                    "severity": "indeterminate",
                    "path": "contract",
                    "message": error,
                    "evidence_ids": [],
                }
                for error in schema_errors
            )
        if schema_errors or report_dict is None:
            status = "indeterminate"
        else:
            status = "passed" if report_dict.get("promotable") is True else "failed"
        return StageResult(
            spec.name,
            spec.version,
            status,
            cache_key,
            input_hash,
            {"report": report_dict, "schema_errors": list(schema_errors)},
            diagnostics,
        )

    @staticmethod
    def _read_cache(cache_dir: Path, cache_key: str, spec: StageSpec) -> StageResult | None:
        entry = cache_dir / f"{cache_key}.json"
        try:
            if entry.stat().st_size > _MAX_CACHE_BYTES:
                return None
            raw = entry.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
            return None
        expected = {"schema_version", "cache_key", "result", "result_sha256", "payload_sha256"}
        if not isinstance(payload, dict) or set(payload) != expected:
            return None
        if payload.get("schema_version") != _CACHE_SCHEMA_VERSION or payload.get("cache_key") != cache_key:
            return None
        body = dict(payload)
        declared_payload_hash = body.pop("payload_sha256", None)
        try:
            if declared_payload_hash != _digest(body):
                return None
            if payload.get("result_sha256") != _digest(payload.get("result")):
                return None
        except ValueError:
            return None
        result = _stage_from_dict(payload.get("result"))
        if (
            result is None
            or result.name != spec.name
            or result.version != spec.version
            or result.cache_key != cache_key
            or result.input_hash != cache_key
        ):
            return None
        return result

    @staticmethod
    def _write_cache(cache_dir: Path, result: StageResult) -> None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            result_dict = result.to_dict()
            body = {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "cache_key": result.cache_key,
                "result": result_dict,
                "result_sha256": _digest(result_dict),
            }
            payload = dict(body)
            payload["payload_sha256"] = _digest(body)
            data = canonical_bytes(payload)
            temporary = cache_dir / f".{result.cache_key}.{uuid.uuid4().hex}.tmp"
            try:
                with temporary.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(cache_dir / f"{result.cache_key}.json")
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as exc:
            raise SchedulerError(f"cannot write cache entry {result.cache_key}: {exc}") from exc


Scheduler = HypothesisScheduler


__all__ = [
    "HypothesisScheduler",
    "KNOWN_STAGE_ORDER",
    "Scheduler",
    "SchedulerError",
    "default_registry",
]
