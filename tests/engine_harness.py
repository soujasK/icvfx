"""Shared harness for driving the real kinematic_engine binary from tests:
starts it, blocks until its stderr actually says "listening" (rather than a
fixed `sleep()`, which is a race condition under load - see
docs/TEST_REPORT.md "Fixed startup sleep" finding), and tears it down.
"""

from __future__ import annotations

import os
import selectors
import socket
import subprocess
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_BIN = os.path.join(REPO_ROOT, "cpp-core", "bin", "kinematic_engine")
GENERATOR_BIN = os.path.join(REPO_ROOT, "cpp-core", "bin", "packet_generator")


class EngineStartupError(RuntimeError):
    pass


class EngineHandle:
    def __init__(self, proc: subprocess.Popen, port: int, out_dir: str):
        self.proc = proc
        self.port = port
        self.out_dir = out_dir
        self._stderr_lines: list[str] = []

    def wait_and_collect(self, timeout: float = 5.0) -> str:
        """Waits for the process to exit (e.g. after its idle timeout) and
        returns all stderr captured (startup line + per-camera summary +
        TOTAL summary line)."""
        try:
            _, stderr = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            _, stderr = self.proc.communicate()
            raise EngineStartupError(f"engine did not exit within {timeout}s of idle timeout")
        text = "\n".join(self._stderr_lines) + (stderr or "")
        return text

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.communicate(timeout=2)


def start_engine(port: int, out_dir: str, hz: float = 120.0, idle_timeout_ms: int = 1000,
                  extra_args: list[str] | None = None, ready_timeout: float = 3.0) -> EngineHandle:
    """Starts kinematic_engine and blocks until it has actually bound the
    socket and is listening - determined by reading its own
    "[kinematic_engine] listening" stderr line, not by guessing a sleep
    duration. Raises EngineStartupError if it doesn't come up in time
    (e.g. the port is already taken by another process) or exits early
    (e.g. a validation error on bad args)."""
    os.makedirs(out_dir, exist_ok=True)
    args = [ENGINE_BIN, "--port", str(port), "--hz", str(hz),
            "--idle-timeout-ms", str(idle_timeout_ms), "--out-dir", out_dir]
    if extra_args:
        args.extend(extra_args)

    proc = subprocess.Popen(args, stderr=subprocess.PIPE, text=True, bufsize=1)
    handle = EngineHandle(proc, port, out_dir)

    sel = selectors.DefaultSelector()
    sel.register(proc.stderr, selectors.EVENT_READ)
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # Exited before announcing readiness - e.g. bad args or bind failure.
            remaining = proc.stderr.read()
            handle._stderr_lines.append(remaining)
            raise EngineStartupError(
                f"engine exited early (code {proc.returncode}) before signaling ready: {remaining!r}"
            )
        events = sel.select(timeout=max(0.0, deadline - time.monotonic()))
        if not events:
            continue
        line = proc.stderr.readline()
        if not line:
            continue
        handle._stderr_lines.append(line.rstrip("\n"))
        if "listening" in line:
            sel.close()
            return handle

    sel.close()
    handle.kill()
    raise EngineStartupError(f"engine did not signal ready within {ready_timeout}s")


def send_udp(port: int, payload: bytes, host: str = "127.0.0.1") -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.sendto(payload, (host, port))


def run_generator(port: int, scenario: str = "normal", hz: float = 120.0, duration: float = 3.0,
                   camera_id: int = 1, extra_args: list[str] | None = None,
                   expect_success: bool = True) -> subprocess.CompletedProcess:
    args = [GENERATOR_BIN, "--port", str(port), "--hz", str(hz), "--duration", str(duration),
            "--scenario", scenario, "--camera-id", str(camera_id)]
    if extra_args:
        args.extend(extra_args)
    result = subprocess.run(args, capture_output=True, text=True, timeout=duration + 10)
    if expect_success and result.returncode != 0:
        raise RuntimeError(f"generator exited {result.returncode}: {result.stderr}")
    return result
