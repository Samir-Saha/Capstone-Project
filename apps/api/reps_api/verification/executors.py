"""Where code actually runs.

LocalSubprocessExecutor  development and CI only. A separate Python process with
                         CPU, memory, file-size and process-count limits, an empty
                         environment, and a throwaway working directory. It does NOT
                         block network access, so it is not a security boundary for
                         untrusted code from the internet.
Judge0Executor           production. Sends the same harness to a Judge0 instance.

Both return the harness's JSON result, or an ExecutionResult describing why the run
never produced one (timeout, crash, service unavailable).
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx

HARNESS_PATH = Path(__file__).with_name("harness.py")
JS_HARNESS_PATH = Path(__file__).with_name("harness.js")
MARKER = "@@REPS_RESULT@@"


@dataclass
class ExecutionResult:
    status: str  # "ok" | "time_limit_exceeded" | "memory_limit_exceeded" | "crashed" | "unavailable"
    payload: dict[str, Any] = field(default_factory=dict)
    stderr: str = ""
    wall_ms: int = 0


class Executor(Protocol):
    name: str

    def run(self, job: dict[str, Any], cpu_seconds: int, memory_mb: int) -> ExecutionResult: ...


def _parse_marker(stdout: str) -> dict[str, Any] | None:
    lines = [line for line in stdout.splitlines() if line.startswith(MARKER)]
    if not lines:
        return None
    try:
        return json.loads(lines[-1][len(MARKER) :])
    except json.JSONDecodeError:
        return None


IS_WINDOWS = sys.platform == "win32"


def _posix_limits(cpu_seconds: int, memory_mb: int, cap_address_space: bool = True):
    import resource  # POSIX only

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        mem = memory_mb * 1024 * 1024
        if cap_address_space:  # V8 reserves far more address space than it uses; Node caps its heap itself
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.setsid()

    return apply


class LocalSubprocessExecutor:
    """On Linux/macOS: CPU, memory and file-size rlimits plus a wall-clock timeout.
    On Windows: wall-clock timeout only (no rlimits there), so memory isn't capped."""

    name = "local-subprocess"

    def __init__(self, enforce_limits: bool | None = None) -> None:
        self.enforce_limits = (not IS_WINDOWS) if enforce_limits is None else enforce_limits

    def run(self, job: dict[str, Any], cpu_seconds: int = 5, memory_mb: int = 512) -> ExecutionResult:
        env = {"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
        if IS_WINDOWS:
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        else:
            env["PATH"] = "/usr/bin:/bin"
        js = job.get("language") == "javascript"
        if js:
            node = shutil.which("node") or shutil.which("node.exe")
            if not node:
                return ExecutionResult(status="unavailable", stderr="Node.js was not found, so JavaScript can't run here.")
            cmd = [node, f"--max-old-space-size={memory_mb}", str(JS_HARNESS_PATH)]
            job = {**job, "cpu_seconds": cpu_seconds}
        else:
            cmd = [sys.executable, "-I", "-S", str(HARNESS_PATH)]
        extra: dict[str, Any] = {}
        if self.enforce_limits:
            extra["preexec_fn"] = _posix_limits(cpu_seconds, memory_mb, cap_address_space=not js)
        elif IS_WINDOWS:
            extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="reps-run-") as workdir:
            try:
                proc = subprocess.run(
                    cmd,
                    input=json.dumps(job),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=workdir,
                    env=env,
                    timeout=cpu_seconds * (3 if self.enforce_limits else 1) + 2,
                    **extra,
                )
            except subprocess.TimeoutExpired:
                return ExecutionResult(status="time_limit_exceeded", wall_ms=int((time.perf_counter() - started) * 1000))
        wall_ms = int((time.perf_counter() - started) * 1000)
        killed = {-getattr(signal, "SIGXCPU", 24), -getattr(signal, "SIGKILL", 9)}
        if proc.returncode in killed:
            return ExecutionResult(status="time_limit_exceeded", stderr=proc.stderr[-1000:], wall_ms=wall_ms)
        payload = _parse_marker(proc.stdout)
        if payload is None:
            if "MemoryError" in proc.stderr:
                return ExecutionResult(status="memory_limit_exceeded", stderr=proc.stderr[-1000:], wall_ms=wall_ms)
            return ExecutionResult(status="crashed", stderr=proc.stderr[-1000:], wall_ms=wall_ms)
        return ExecutionResult(status="ok", payload=payload, stderr=proc.stderr[-1000:], wall_ms=wall_ms)


class Judge0Executor:
    """Runs the harness on Judge0 (language 71 = Python 3 on the standard image).

    Untested against a live Judge0 instance until JUDGE0_URL is configured; the
    request and response handling is covered by unit tests with a mock transport.
    """

    name = "judge0"
    PYTHON_LANGUAGE_ID = 71

    def __init__(self, base_url: str, api_key: str | None = None, client: httpx.Client | None = None, poll_s: float = 0.5):
        self.base_url = base_url.rstrip("/")
        headers = {"X-Auth-Token": api_key} if api_key else {}
        self.client = client or httpx.Client(timeout=15, headers=headers)
        self.poll_s = poll_s

    def run(self, job: dict[str, Any], cpu_seconds: int = 5, memory_mb: int = 512) -> ExecutionResult:
        if job.get("language") == "javascript":
            return ExecutionResult(status="unavailable", stderr="JavaScript runs on the local runner only for now.")
        started = time.perf_counter()
        body = {
            "language_id": self.PYTHON_LANGUAGE_ID,
            "source_code": base64.b64encode(HARNESS_PATH.read_bytes()).decode(),
            "stdin": base64.b64encode(json.dumps(job).encode()).decode(),
            "cpu_time_limit": cpu_seconds,
            "wall_time_limit": cpu_seconds * 3,
            "memory_limit": memory_mb * 1024,
            "enable_network": False,
        }
        try:
            resp = self.client.post(f"{self.base_url}/submissions?base64_encoded=true&wait=false", json=body)
            resp.raise_for_status()
            token = resp.json()["token"]
            deadline = time.monotonic() + cpu_seconds * 3 + 30
            while True:
                r = self.client.get(f"{self.base_url}/submissions/{token}?base64_encoded=true")
                r.raise_for_status()
                data = r.json()
                status_id = data["status"]["id"]
                if status_id not in (1, 2):  # 1 In Queue, 2 Processing
                    break
                if time.monotonic() > deadline:
                    return ExecutionResult(status="time_limit_exceeded", wall_ms=int((time.perf_counter() - started) * 1000))
                time.sleep(self.poll_s)
        except (httpx.HTTPError, KeyError, ValueError) as err:
            return ExecutionResult(status="unavailable", stderr=f"{err.__class__.__name__}: {err}")

        wall_ms = int((time.perf_counter() - started) * 1000)
        stdout = base64.b64decode(data.get("stdout") or "").decode(errors="replace")
        stderr = base64.b64decode(data.get("stderr") or "").decode(errors="replace")[-1000:]
        if status_id == 5:
            return ExecutionResult(status="time_limit_exceeded", stderr=stderr, wall_ms=wall_ms)
        payload = _parse_marker(stdout)
        if payload is None:
            if "MemoryError" in stderr:
                return ExecutionResult(status="memory_limit_exceeded", stderr=stderr, wall_ms=wall_ms)
            return ExecutionResult(status="crashed", stderr=stderr, wall_ms=wall_ms)
        return ExecutionResult(status="ok", payload=payload, stderr=stderr, wall_ms=wall_ms)


def executor_from_env() -> Executor:
    url = os.environ.get("JUDGE0_URL")
    if url:
        return Judge0Executor(url, os.environ.get("JUDGE0_API_KEY"))
    if os.environ.get("REPS_ENV", "development") == "production":
        raise RuntimeError("JUDGE0_URL must be set in production; the local executor is not a sandbox")
    return LocalSubprocessExecutor()
