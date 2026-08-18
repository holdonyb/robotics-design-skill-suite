"""Parent-side isolated execution for closed declarative policy artifacts."""
from __future__ import annotations

import math
import os
import signal
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
_CLEANUP_WAIT_S = 0.1
_WIN_CREATE_SUSPENDED = 0x00000004
_ACTION_FIELDS = {"linear_m_s", "angular_rad_s"}
_SCRIPT_ROOT = Path(__file__).resolve().parents[2]


class PolicyBackendError(ValueError):
    """A closed policy action could not be safely executed."""


class _WindowsKillOnCloseJob:
    """Windows Job Object whose close terminates every assigned descendant."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time_limit", ctypes.c_longlong),
                ("per_job_user_time_limit", ctypes.c_longlong),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set_size", ctypes.c_size_t),
                ("maximum_working_set_size", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("read_operation_count", ctypes.c_ulonglong),
                ("write_operation_count", ctypes.c_ulonglong),
                ("other_operation_count", ctypes.c_ulonglong),
                ("read_transfer_count", ctypes.c_ulonglong),
                ("write_transfer_count", ctypes.c_ulonglong),
                ("other_transfer_count", ctypes.c_ulonglong),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("basic_limit_information", _BasicLimitInformation),
                ("io_info", _IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateJobObjectW
        create.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        create.restype = wintypes.HANDLE
        configure = kernel32.SetInformationJobObject
        configure.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
        configure.restype = wintypes.BOOL
        assign = kernel32.AssignProcessToJobObject
        assign.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        assign.restype = wintypes.BOOL
        close = kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close.restype = wintypes.BOOL
        snapshot = kernel32.CreateToolhelp32Snapshot
        snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        snapshot.restype = wintypes.HANDLE
        open_thread = kernel32.OpenThread
        open_thread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_thread.restype = wintypes.HANDLE
        resume_thread = kernel32.ResumeThread
        resume_thread.argtypes = (wintypes.HANDLE,)
        resume_thread.restype = wintypes.DWORD

        class _ThreadEntry32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
            ]

        thread_first = kernel32.Thread32First
        thread_first.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
        thread_first.restype = wintypes.BOOL
        thread_next = kernel32.Thread32Next
        thread_next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32))
        thread_next.restype = wintypes.BOOL

        handle = create(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimitInformation()
        limits.basic_limit_information.limit_flags = self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not configure(
            handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            close(handle)
            raise ctypes.WinError(error)
        self._assign = assign
        self._close = close
        self._ctypes = ctypes
        self._handle = handle
        self._close_snapshot = close
        self._snapshot = snapshot
        self._open_thread = open_thread
        self._resume_thread = resume_thread
        self._thread_first = thread_first
        self._thread_next = thread_next
        self._thread_entry_type = _ThreadEntry32

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        if not self._assign(self._handle, process._handle):
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def close(self) -> None:
        if self._handle:
            self._close(self._handle)
            self._handle = None

    def resume_root(self, process: subprocess.Popen[bytes]) -> None:
        """Resume the suspended primary thread only after Job assignment."""

        deadline = time.monotonic() + _CLEANUP_WAIT_S
        invalid_handle = self._ctypes.c_void_p(-1).value
        while time.monotonic() < deadline:
            snapshot = self._snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
            if snapshot and snapshot != invalid_handle:
                try:
                    entry = self._thread_entry_type()
                    entry.dwSize = self._ctypes.sizeof(entry)
                    found = self._thread_first(snapshot, self._ctypes.byref(entry))
                    while found:
                        if entry.th32OwnerProcessID == process.pid:
                            thread = self._open_thread(0x0002, False, entry.th32ThreadID)
                            if thread:
                                try:
                                    if self._resume_thread(thread) != 0xFFFFFFFF:
                                        return
                                finally:
                                    self._close_snapshot(thread)
                        entry.dwSize = self._ctypes.sizeof(entry)
                        found = self._thread_next(snapshot, self._ctypes.byref(entry))
                finally:
                    self._close_snapshot(snapshot)
            time.sleep(0.001)
        raise self._ctypes.WinError(self._ctypes.get_last_error())


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

    def join(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _drain(self) -> None:
        try:
            while True:
                try:
                    chunk = self._stream.read(4096)
                except (OSError, ValueError):
                    return
                if not chunk:
                    return
                if len(self.data) + len(chunk) > self._limit:
                    self.overflow = True
                    return
                self.data.extend(chunk)
        finally:
            try:
                self._stream.close()
            except (OSError, ValueError):
                pass


def _write_input(stream: object, payload: bytes, errors: list[OSError]) -> None:
    try:
        stream.write(payload)
    except (OSError, ValueError) as exc:
        errors.append(exc)
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _close_pipe(stream: object) -> None:
    try:
        stream.close()
    except (OSError, ValueError):
        pass


def _stop_worker(
    process: subprocess.Popen[bytes], windows_job: _WindowsKillOnCloseJob | None
) -> None:
    if windows_job is not None:
        windows_job.close()
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
    elif process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=_CLEANUP_WAIT_S)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=_CLEANUP_WAIT_S)
        except subprocess.TimeoutExpired:
            pass


def _run_worker(
    command: list[str], request: bytes, *, cwd: str, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[bytes]:
    """Run one worker with bounded pipe retention and a hard wall-time limit."""

    windows_job = _WindowsKillOnCloseJob() if os.name == "nt" else None
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=_WIN_CREATE_SUSPENDED if os.name == "nt" else 0,
        )
        if windows_job is not None:
            windows_job.assign(process)
            windows_job.resume_root(process)
    except BaseException:
        if process is not None:
            _stop_worker(process, windows_job)
        elif windows_job is not None:
            windows_job.close()
        raise
    assert process is not None
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
        _stop_worker(process, windows_job)
        _close_pipe(process.stdin)
        _close_pipe(process.stdout)
        _close_pipe(process.stderr)
        writer.join(_CLEANUP_WAIT_S)
        stdout.join(_CLEANUP_WAIT_S)
        stderr.join(_CLEANUP_WAIT_S)
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
