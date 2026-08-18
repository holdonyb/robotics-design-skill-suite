"""One-request declarative policy worker, executable only as a package module."""
from __future__ import annotations

import math
import sys
from collections.abc import Mapping

if __name__ == "__main__" and __package__ != "assurance.simulation":
    raise SystemExit(2)

from assurance.hypothesis.canonical import canonical_bytes
from assurance.simulation.policy_artifact import (
    PolicyArtifact,
    PolicyArtifactError,
    _closed_object,
    _load_canonical_json,
    _parse_policy_artifact_payload,
)


_MAX_REQUEST_BYTES = 80 * 1024
_MAX_ABSOLUTE_OBSERVATION = 1_000_000.0
_REQUEST_FIELDS = {"artifact", "observation"}


class PolicyWorkerError(ValueError):
    """The one-request policy protocol is invalid."""


def _finite_observation(value: object, path: str) -> float:
    if type(value) not in (int, float):
        raise PolicyWorkerError(f"{path} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise PolicyWorkerError(f"{path} must be a finite number")
    if abs(result) > _MAX_ABSOLUTE_OBSERVATION:
        raise PolicyWorkerError(f"{path} must be bounded")
    return result


def _validated_observations(artifact: PolicyArtifact, value: object) -> tuple[float, ...]:
    if not isinstance(value, Mapping):
        raise PolicyWorkerError("observation must be an object")
    if set(value) != set(artifact.observation_order):
        raise PolicyWorkerError("observation keys do not match the policy artifact")
    return tuple(
        _finite_observation(value[name], f"observation.{name}")
        for name in artifact.observation_order
    )


def _action(artifact: PolicyArtifact, observations: tuple[float, ...]) -> dict[str, float]:
    linear = math.tanh(
        artifact.linear_bias
        + sum(weight * value for weight, value in zip(artifact.linear_weights, observations))
    )
    angular = math.tanh(
        artifact.angular_bias
        + sum(weight * value for weight, value in zip(artifact.angular_weights, observations))
    )
    if not math.isfinite(linear) or not math.isfinite(angular):
        raise PolicyWorkerError("policy action is not finite")
    return {"angular_rad_s": angular, "linear_m_s": linear}


def execute_request(payload: bytes) -> dict[str, float]:
    """Evaluate exactly one canonical request payload without filesystem access."""

    try:
        request = _load_canonical_json(payload)
        root = _closed_object(request, _REQUEST_FIELDS, "request")
        artifact_payload = canonical_bytes(root["artifact"])
        artifact = _parse_policy_artifact_payload(artifact_payload)
    except (PolicyArtifactError, TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise PolicyWorkerError("policy request is invalid") from exc
    return _action(artifact, _validated_observations(artifact, root["observation"]))


def _read_single_request() -> bytes:
    payload = sys.stdin.buffer.readline(_MAX_REQUEST_BYTES + 1)
    if not payload or len(payload) > _MAX_REQUEST_BYTES or not payload.endswith(b"\n"):
        raise PolicyWorkerError("policy request is invalid")
    if sys.stdin.buffer.read(1):
        raise PolicyWorkerError("policy request is invalid")
    return payload


def main() -> int:
    """Run the closed protocol and never emit diagnostics on standard error."""

    if __package__ != "assurance.simulation":
        return 2
    try:
        response = execute_request(_read_single_request())
        encoded = canonical_bytes(response)
    except (PolicyWorkerError, ValueError, OverflowError, UnicodeError):
        return 2
    sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
