import io
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "robotics-design" / "scripts"))

from assurance.hypothesis.canonical import canonical_bytes  # noqa: E402
from assurance.simulation.policy_artifact import load_policy_artifact  # noqa: E402
from assurance.simulation.policy_backend import (  # noqa: E402
    PolicyBackendError,
    execute_policy,
)
from assurance.simulation import policy_backend  # noqa: E402


class PolicyBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.artifact_path = Path(self.temporary.name) / "policy.json"
        self.artifact_path.write_bytes(
            canonical_bytes(
                {
                    "schema_version": 1,
                    "kind": "affine_tanh_v1",
                    "policy_id": "policy-worker-test",
                    "observation_order": ["joint-1", "wheel-rate"],
                    "linear": {"bias": 0.2, "weights": [0.5, -0.25]},
                    "angular": {"bias": -0.1, "weights": [0.1, 0.75]},
                }
            )
        )
        self.artifact = load_policy_artifact(self.artifact_path)
        self.observation = {"joint-1": 0.4, "wheel-rate": -0.2}

    def test_executes_reference_action_deterministically(self):
        first = execute_policy(self.artifact, self.observation, timeout_s=1.0)
        second = execute_policy(self.artifact, self.observation, timeout_s=1.0)

        self.assertEqual(first, second)
        self.assertEqual(
            {"linear_m_s", "angular_rad_s"}, set(first)
        )
        self.assertAlmostEqual(
            math.tanh(0.2 + 0.5 * 0.4 + -0.25 * -0.2), first["linear_m_s"]
        )
        self.assertAlmostEqual(
            math.tanh(-0.1 + 0.1 * 0.4 + 0.75 * -0.2), first["angular_rad_s"]
        )

    def test_rejects_wrong_observation_keys_and_values_before_launching_worker(self):
        cases = (
            ({"joint-1": 0.4}, "keys"),
            ({"joint-1": 0.4, "wheel-rate": -0.2, "extra": 0.0}, "keys"),
            ({"joint-1": True, "wheel-rate": -0.2}, "finite number"),
            ({"joint-1": "0.4", "wheel-rate": -0.2}, "finite number"),
            ({"joint-1": float("nan"), "wheel-rate": -0.2}, "finite number"),
            ({"joint-1": 0.4, "wheel-rate": float("inf")}, "finite number"),
            ({"joint-1": 1_000_001.0, "wheel-rate": -0.2}, "bounded"),
        )
        with mock.patch.object(policy_backend, "_run_worker") as launch:
            for observation, expected in cases:
                with self.subTest(observation=observation):
                    with self.assertRaisesRegex(PolicyBackendError, expected):
                        execute_policy(self.artifact, observation)
            self.assertFalse(launch.called)

    def test_rejects_artifact_whose_declared_fields_do_not_match_its_payload(self):
        forged = replace(self.artifact, linear_bias=self.artifact.linear_bias + 1.0)
        with mock.patch.object(policy_backend, "_run_worker") as launch:
            with self.assertRaisesRegex(PolicyBackendError, "artifact"):
                execute_policy(forged, self.observation)
            self.assertFalse(launch.called)

    def test_rejects_oversized_integer_observation_before_launching_worker(self):
        observation = {"joint-1": 1 << 10_000, "wheel-rate": -0.2}
        with mock.patch.object(policy_backend, "_run_worker") as launch:
            with self.assertRaisesRegex(PolicyBackendError, "observation.joint-1"):
                execute_policy(self.artifact, observation)
            self.assertFalse(launch.called)

    def test_worker_computes_closed_scalar_math(self):
        request = canonical_bytes(
            {"artifact": self.artifact.payload, "observation": self.observation}
        )
        with tempfile.TemporaryDirectory() as raw:
            completed = subprocess.run(
                policy_backend._worker_command(),
                input=request,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=raw,
                env=policy_backend._worker_environment(),
                check=False,
            )

        self.assertEqual(0, completed.returncode)
        self.assertEqual(b"", completed.stderr)
        response = policy_backend._parse_response(completed.stdout)
        self.assertAlmostEqual(
            math.tanh(0.2 + 0.5 * 0.4 + -0.25 * -0.2), response["linear_m_s"]
        )
        self.assertAlmostEqual(
            math.tanh(-0.1 + 0.1 * 0.4 + 0.75 * -0.2), response["angular_rad_s"]
        )

    def test_worker_rejects_malformed_extra_and_unsafe_requests(self):
        valid = canonical_bytes(
            {"artifact": self.artifact.payload, "observation": self.observation}
        )
        unsafe = canonical_bytes(
            {
                "artifact": self.artifact.payload,
                "observation": self.observation,
                "policy_path": "C:/untrusted-policy.py",
            }
        )
        boolean_observation = canonical_bytes(
            {
                "artifact": self.artifact.payload,
                "observation": {"joint-1": True, "wheel-rate": -0.2},
            }
        )
        cases = (
            b"",
            b"\n",
            b"not-json\n",
            valid[:-1] + b" \n",
            b'{"artifact":{},"artifact":{},"observation":{}}\n',
            valid + b"{}\n",
            unsafe,
            boolean_observation,
        )
        with tempfile.TemporaryDirectory() as raw:
            for request in cases:
                with self.subTest(request=request[:20]):
                    completed = subprocess.run(
                        policy_backend._worker_command(),
                        input=request,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=raw,
                        env=policy_backend._worker_environment(),
                        check=False,
                    )
                    self.assertNotEqual(0, completed.returncode)
                    self.assertEqual(b"", completed.stdout)
                    self.assertEqual(b"", completed.stderr)

    def test_worker_refuses_direct_script_execution(self):
        completed = subprocess.run(
            [sys.executable, Path(policy_backend.__file__).with_name("policy_worker.py")],
            input=b"",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertEqual(b"", completed.stdout)
        self.assertEqual(b"", completed.stderr)

    def test_parent_uses_empty_working_directory_and_scrubbed_environment(self):
        response = canonical_bytes({"linear_m_s": 0.1, "angular_rad_s": -0.2})
        completed = subprocess.CompletedProcess([], 0, response, b"")
        def inspect_launch(*arguments, **keyword):
            self.assertEqual([], list(Path(keyword["cwd"]).iterdir()))
            return completed

        with mock.patch.dict(
            policy_backend.os.environ,
            {"POLICY_BACKEND_TEST_SECRET": "must-not-reach-worker"},
            clear=False,
        ):
            with mock.patch.object(
                policy_backend, "_run_worker", side_effect=inspect_launch
            ) as launch:
                self.assertEqual(
                    {"linear_m_s": 0.1, "angular_rad_s": -0.2},
                    execute_policy(self.artifact, self.observation),
                )

        arguments, keyword = launch.call_args
        self.assertTrue(all(not item.startswith("PYTHON") for item in keyword["env"]))
        self.assertNotIn("POLICY_BACKEND_TEST_SECRET", keyword["env"])
        self.assertIn("-I", arguments[0])
        self.assertIn("assurance.simulation.policy_worker", arguments[0][-1])

    def test_parent_rejects_worker_protocol_violations(self):
        cases = (
            (0, canonical_bytes({"linear_m_s": 0.1, "angular_rad_s": 0.2}), b"noise", "stderr"),
            (0, canonical_bytes({"linear_m_s": 0.1, "angular_rad_s": 0.2}) + b"{}\n", b"", "response"),
            (0, b'{"linear_m_s":0.1,"angular_rad_s":0.2}\n', b"", "response"),
            (0, canonical_bytes({"linear_m_s": 2.0, "angular_rad_s": 0.2}), b"", "bounds"),
            (0, canonical_bytes({"linear_m_s": True, "angular_rad_s": 0.2}), b"", "finite number"),
            (0, b"x" * 1025, b"", "response"),
            (0, canonical_bytes({"linear_m_s": 0.1, "angular_rad_s": 0.2}), b"x" * 4097, "stderr"),
            (4, canonical_bytes({"linear_m_s": 0.1, "angular_rad_s": 0.2}), b"", "failed"),
        )
        for returncode, stdout, stderr, expected in cases:
            with self.subTest(expected=expected):
                completed = subprocess.CompletedProcess([], returncode, stdout, stderr)
                with mock.patch.object(policy_backend, "_run_worker", return_value=completed):
                    with self.assertRaisesRegex(PolicyBackendError, expected):
                        execute_policy(self.artifact, self.observation)

    def test_parent_normalizes_timeout_and_rejects_invalid_timeouts(self):
        with mock.patch.object(
            policy_backend,
            "_run_worker",
            side_effect=PolicyBackendError("policy worker timeout"),
        ):
            with self.assertRaisesRegex(PolicyBackendError, "timeout"):
                execute_policy(self.artifact, self.observation, timeout_s=0.01)

        for timeout in (True, 0.0, -1.0, float("nan"), float("inf"), 5.1):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(PolicyBackendError, "timeout"):
                    execute_policy(self.artifact, self.observation, timeout_s=timeout)

    def test_rejects_oversized_integer_timeout_before_launching_worker(self):
        with mock.patch.object(policy_backend, "_run_worker") as launch:
            with self.assertRaisesRegex(PolicyBackendError, "timeout"):
                execute_policy(self.artifact, self.observation, timeout_s=1 << 10_000)
            self.assertFalse(launch.called)

    def test_bounded_pipe_reader_marks_overflow_without_retaining_full_output(self):
        reader = policy_backend._BoundedPipeReader(io.BytesIO(b"x" * 64), 16)
        reader.start()
        reader.join()

        self.assertTrue(reader.overflow)
        self.assertLessEqual(len(reader.data), 16)

    def test_bounded_worker_runner_kills_excessive_output(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(PolicyBackendError, "excessive output"):
                policy_backend._run_worker(
                    [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*65536)"],
                    b"",
                    cwd=raw,
                    env=policy_backend._worker_environment(),
                    timeout=1.0,
                )

    def test_bounded_worker_runner_kills_timeout(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(PolicyBackendError, "timeout"):
                policy_backend._run_worker(
                    [sys.executable, "-c", "import time;time.sleep(1)"],
                    b"",
                    cwd=raw,
                    env=policy_backend._worker_environment(),
                    timeout=0.01,
                )

    def test_timeout_kills_inherited_pipe_descendants_without_delaying_cleanup(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        raw = Path(temporary.name)
        child_pid = raw / "child.pid"
        ready = raw / "ready"
        descendant = (
            "import os,pathlib,time;"
            f"pathlib.Path({str(child_pid)!r}).write_text(str(os.getpid()));"
            "time.sleep(1.2)"
        )
        root = (
            "import os,pathlib,subprocess,sys,time;"
            "[os.set_inheritable(stream.fileno(),True) for stream in (sys.stdout,sys.stderr)];"
            f"subprocess.Popen([sys.executable,'-c',{descendant!r}],"
            "stdout=sys.stdout,stderr=sys.stderr,close_fds=False);"
            f"[time.sleep(0.001) for _ in range(500) if not pathlib.Path({str(child_pid)!r}).exists()];"
            f"pathlib.Path({str(ready)!r}).write_text('ready');"
            "time.sleep(1)"
        )

        started = time.monotonic()
        with self.assertRaisesRegex(PolicyBackendError, "timeout"):
            policy_backend._run_worker(
                [sys.executable, "-c", root],
                b"",
                cwd=str(raw),
                env=policy_backend._worker_environment(),
                timeout=0.3,
            )
        elapsed = time.monotonic() - started

        self.assertTrue(ready.exists())
        self.assertTrue(child_pid.exists())
        self.assertLess(elapsed, 0.7)
        pid = int(child_pid.read_text(encoding="utf-8"))
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = (ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32)
            open_process.restype = ctypes.c_void_p
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (ctypes.c_void_p,)
            close_handle.restype = ctypes.c_bool
            deadline = time.monotonic() + policy_backend._CLEANUP_WAIT_S
            handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            while handle and time.monotonic() < deadline:
                close_handle(handle)
                time.sleep(0.005)
                handle = open_process(0x1000, False, pid)
            self.assertFalse(handle)
        else:
            deadline = time.monotonic() + policy_backend._CLEANUP_WAIT_S
            while True:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                stat = Path(f"/proc/{pid}/stat")
                if (
                    stat.exists()
                    and stat.read_text(encoding="utf-8")
                    .rsplit(")", 1)[1]
                    .lstrip()
                    .startswith("Z")
                ):
                    break
                if time.monotonic() >= deadline:
                    self.fail("descendant process remained alive after cleanup")
                time.sleep(0.005)
        temporary.cleanup()
        self.assertFalse(raw.exists())


if __name__ == "__main__":
    unittest.main()
