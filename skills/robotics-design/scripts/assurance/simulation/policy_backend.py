"""Parent-side isolated execution for closed declarative policy artifacts."""
from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from assurance.hypothesis.canonical import canonical_bytes
from assurance.simulation.policy_artifact import (
    PolicyArtifact,
    PolicyArtifactError,
    _closed_object,
    _load_canonical_json,
    _parse_policy_artifact_payload,
)


DEFAULT_TIMEOUT_S = 1.0
MAX_TIMEOUT_S = 5.0
_MAX_REQUEST_BYTES = 80 * 1024
_MAX_STDOUT_BYTES = 1024
_MAX_STDERR_BYTES = 4096
_MAX_ABSOLUTE_OBSERVATION = 1_000_000.0
_MAX_LINEAR_M_S = 1.0
_MAX_ANGULAR_RAD_S = 2.0
_ACTION_FIELDS = {"linear_m_s", "angular_rad_s"}
_SCRIPT_ROOT = Path(__file__).resolve().parents[2]


class PolicyBackendError(ValueError):
    """A closed policy action could not be safely executed."""


class _BoundedPipeReader:
    """Drain one pipe while retaining no more than its protocol limit."""

    def __init__(self, stream: object, limit: int):
        self._stream = stream
        self._limit = limit
        self.data = bytearray()
        self.overflow = False
        self._thread = threading.Thread(target=self._drain, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self) -> None:
        self._thread.join()

    def _drain(self) -> None:
        try:
            while chunk := self._stream.read(4096):
                if len(self.data) + len(chunk) > self._limit:
                    self.overflow = True
                    return
                self.data.extend(chunk)
        finally:
            self._stream.close()


def _write_input(stream: object, payload: bytes, errors: list[OSError]) -> None:
    try:
        stream.write(payload)
    except OSError as exc:
        errors.append(exc)
    finally:
        stream.close()


def _stop_worker(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait()
    except OSError:
        pass


def _run_worker(
    command: list[str], request: bytes, *, cwd: str, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    """Run one worker with bounded pipe retention and a hard wall-time limit."""

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        shell=False,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    stdout = _BoundedPipeReader(process.stdout, _MAX_STDOUT_BYTES)
    stderr = _BoundedPipeReader(process.stderr, _MAX_STDERR_BYTES)
    writer_errors: list[OSError] = []
    writer = threading.Thread(
        target=_write_input,
        args=(process.stdin, request, writer_errors),
        daemon=True,
    )
    stdout.start()
    stderr.start()
    writer.start()
    deadline = time.monotonic() + timeout
    failure: PolicyBackendError | None = None
    try:
        while process.poll() is None:
            if stdout.overflow or stderr.overflow:
                failure = PolicyBackendError("policy worker emitted excessive output")
                break
            if time.monotonic() >= deadline:
                failure = PolicyBackendError("policy worker timeout")
                break
            time.sleep(0.005)
    finally:
        _stop_worker(process)
        writer.join()
        stdout.join()
        stderr.join()
    if failure is not None:
        raise failure
    if stdout.overflow or stderr.overflow:
        raise PolicyBackendError("policy worker emitted excessive output")
    if writer_errors:
        raise PolicyBackendError("policy worker failed")
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        bytes(stdout.data),
        bytes(stderr.data),
    )


def _worker_command() -> list[str]:
    """Return a fixed isolated interpreter command that runs the package module."""

    launcher = (
        "import runpy,sys;"
        f"sys.path.insert(0,{str(_SCRIPT_ROOT)!r});"
        "runpy.run_module('assurance.simulation.policy_worker',run_name='__main__')"
    )
    return [sys.executable, "-I", "-c", launcher]


def _worker_environment() -> dict[str, str]:
    """Keep only Windows loader variables needed to start the fixed interpreter."""

    environment: dict[str, str] = {}
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR"):
            value = os.environ.get(name)
            if value:
                environment[name] = value
    return environment


def _timeout(value: object) -> float:
    if type(value) not in (int, float):
        raise PolicyBackendError("timeout must be a finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise PolicyBackendError("timeout must be a finite number") from None
    if not math.isfinite(result) or result <= 0 or result > MAX_TIMEOUT_S:
        raise PolicyBackendError(
            f"timeout must be greater than zero and at most {MAX_TIMEOUT_S:g} seconds"
        )
    return result


def _finite_observation(value: object, path: str) -> float:
    if type(value) not in (int, float):
        raise PolicyBackendError(f"{path} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise PolicyBackendError(f"{path} must be a finite number") from None
    if not math.isfinite(result):
        raise PolicyBackendError(f"{path} must be a finite number")
    if abs(result) > _MAX_ABSOLUTE_OBSERVATION:
        raise PolicyBackendError(f"{path} must be bounded")
    return result


def _validated_observation(
    artifact: PolicyArtifact, observation: Mapping[str, object]
) -> dict[str, float]:
    if not isinstance(artifact, PolicyArtifact):
        raise PolicyBackendError("artifact must be a loaded PolicyArtifact")
    if not isinstance(observation, Mapping):
        raise PolicyBackendError("observation must be a mapping")
    if set(observation) != set(artifact.observation_order):
        raise PolicyBackendError("observation keys do not match the policy artifact")
    return {
        name: _finite_observation(observation[name], f"observation.{name}")
        for name in artifact.observation_order
    }


def _validated_artifact(artifact: object) -> PolicyArtifact:
    if not isinstance(artifact, PolicyArtifact):
        raise PolicyBackendError("artifact must be a loaded PolicyArtifact")
    try:
        checked = _parse_policy_artifact_payload(canonical_bytes(artifact.payload))
    except (PolicyArtifactError, TypeError, ValueError, OverflowError, UnicodeError):
        raise PolicyBackendError("artifact cannot be verified") from None
    declared = (
        artifact.policy_id,
        artifact.sha256,
        artifact.observation_order,
        artifact.linear_bias,
        artifact.linear_weights,
        artifact.angular_bias,
        artifact.angular_weights,
    )
    rebuilt = (
        checked.policy_id,
        checked.sha256,
        checked.observation_order,
        checked.linear_bias,
        checked.linear_weights,
        checked.angular_bias,
        checked.angular_weights,
    )
    if declared != rebuilt:
        raise PolicyBackendError("artifact fields do not match its canonical payload")
    return checked


def _request_bytes(artifact: PolicyArtifact, observation: Mapping[str, object]) -> bytes:
    artifact = _validated_artifact(artifact)
    checked_observation = _validated_observation(artifact, observation)
    try:
        request = canonical_bytes(
            {"artifact": artifact.payload, "observation": checked_observation}
        )
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise PolicyBackendError("policy request cannot be encoded") from exc
    if len(request) > _MAX_REQUEST_BYTES:
        raise PolicyBackendError("policy request exceeds the maximum size")
    return request


def _finite_action(value: object, name: str, bound: float) -> float:
    if type(value) not in (int, float):
        raise PolicyBackendError(f"policy response {name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise PolicyBackendError(f"policy response {name} must be a finite number")
    if abs(result) > bound:
        raise PolicyBackendError(f"policy response {name} exceeds physical bounds")
    return result


def _parse_response(stdout: bytes) -> dict[str, float]:
    if not isinstance(stdout, bytes) or len(stdout) > _MAX_STDOUT_BYTES:
        raise PolicyBackendError("policy worker response is malformed")
    try:
        response = _load_canonical_json(stdout)
        root = _closed_object(response, _ACTION_FIELDS, "response")
    except (PolicyArtifactError, TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise PolicyBackendError("policy worker response is malformed") from exc
    return {
        "linear_m_s": _finite_action(
            root["linear_m_s"], "linear_m_s", _MAX_LINEAR_M_S
        ),
        "angular_rad_s": _finite_action(
            root["angular_rad_s"], "angular_rad_s", _MAX_ANGULAR_RAD_S
        ),
    }


def execute_policy(
    artifact: PolicyArtifact,
    observation: Mapping[str, object],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, float]:
    """Evaluate one loaded artifact in a fresh isolated stdlib worker process."""

    timeout = _timeout(timeout_s)
    request = _request_bytes(artifact, observation)
    try:
        with tempfile.TemporaryDirectory(prefix="policy-worker-") as worker_cwd:
            completed = _run_worker(
                _worker_command(),
                request,
                cwd=worker_cwd,
                env=_worker_environment(),
                timeout=timeout,
            )
    except PolicyBackendError:
        raise
    except (OSError, ValueError):
        raise PolicyBackendError("policy worker could not be started") from None
    if completed.returncode != 0:
        raise PolicyBackendError("policy worker failed")
    if (
        not isinstance(completed.stderr, bytes)
        or len(completed.stderr) > _MAX_STDERR_BYTES
        or completed.stderr
    ):
        raise PolicyBackendError("policy worker emitted stderr")
    return _parse_response(completed.stdout)
