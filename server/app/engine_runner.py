"""Bridge between the relay's job manager and the parsing engine.

The engine runs in a child process (see ``engine/job_runner.py``) so each job
gets its own output directory, cancellation is a ``terminate()``, and a parser
crash cannot take the relay down.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

ENGINE_DIR = Path(__file__).resolve().parents[2] / "engine"
JOB_TIMEOUT_SECONDS = 20 * 60
STDERR_TAIL_LINES = 20

ProgressCallback = Callable[[int, int, str, int, str], None]


@dataclass
class DemoRequest:
    usernames: list[str]
    map_name: str
    max_demos: int
    hints: list[dict[str, str]] | None
    output_dir: str
    demo_dir: str
    maps_dir: str
    mode: str = "normal"


@dataclass
class DemoOutcome:
    players: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, str]] = field(default_factory=list)
    cancelled: bool = False
    error: str | None = None


class DemoRunner(Protocol):
    def run(
        self,
        request: DemoRequest,
        on_progress: ProgressCallback,
        *,
        session_id: str | None = None,
    ) -> DemoOutcome: ...

    def cancel(self, session_id: str) -> None: ...


class SubprocessDemoRunner:
    def __init__(
        self,
        engine_dir: Path | None = None,
        *,
        timeout: int = JOB_TIMEOUT_SECONDS,
        python: str | None = None,
    ) -> None:
        self.engine_dir = Path(engine_dir or ENGINE_DIR)
        self.timeout = timeout
        self.python = python or sys.executable
        self._procs: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def cancel(self, session_id: str) -> None:
        with self._lock:
            self._cancelled.add(session_id)
            proc = self._procs.get(session_id)
        if proc and proc.poll() is None:
            proc.terminate()

    def run(
        self,
        request: DemoRequest,
        on_progress: ProgressCallback,
        *,
        session_id: str | None = None,
    ) -> DemoOutcome:
        key = session_id or request.output_dir
        payload = {
            "usernames": request.usernames,
            "mapName": request.map_name,
            "maxDemos": request.max_demos,
            "hints": request.hints,
            "mode": request.mode,
            "outputDir": request.output_dir,
            "demoDir": request.demo_dir,
            "mapsDir": request.maps_dir,
        }

        proc = self._spawn(payload)
        with self._lock:
            # A cancel that arrived before the child existed is stale: the caller
            # cancels only to restart, so honouring it here would fail the new run.
            self._cancelled.discard(key)
            self._procs[key] = proc
        try:
            return self._consume(proc, key, request, on_progress)
        finally:
            with self._lock:
                self._procs.pop(key, None)
                cancelled = key in self._cancelled
                self._cancelled.discard(key)
            if proc.poll() is None:
                proc.kill()
            if cancelled:
                pass

    # -- internals ------------------------------------------------------
    def _spawn(self, payload: dict[str, Any]) -> subprocess.Popen:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            [self.python, str(self.engine_dir / "job_runner.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(self.engine_dir),
            creationflags=flags,
        )
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(payload, ensure_ascii=False))
        proc.stdin.close()
        return proc

    def _consume(
        self,
        proc: subprocess.Popen,
        key: str,
        request: DemoRequest,
        on_progress: ProgressCallback,
    ) -> DemoOutcome:
        lines: queue.Queue[str | None] = queue.Queue()
        stderr_tail: list[str] = []

        def pump(stream, sink: queue.Queue | None = None) -> None:
            try:
                for line in stream:
                    if sink is not None:
                        sink.put(line)
                    else:
                        stderr_tail.append(line.rstrip())
                        del stderr_tail[:-STDERR_TAIL_LINES]
            finally:
                if sink is not None:
                    sink.put(None)

        assert proc.stdout is not None and proc.stderr is not None
        threading.Thread(target=pump, args=(proc.stdout, lines), daemon=True).start()
        threading.Thread(target=pump, args=(proc.stderr,), daemon=True).start()

        deadline = time.monotonic() + self.timeout
        done: dict[str, Any] | None = None
        error: str | None = None

        while True:
            if self._is_cancelled(key):
                proc.kill()
                return DemoOutcome(cancelled=True, failed=[{"username": "*", "reason": "已取消"}])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                proc.kill()
                return DemoOutcome(error="解析超时")
            try:
                line = lines.get(timeout=min(1.0, remaining))
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = message.get("type")
            if kind == "progress":
                on_progress(
                    int(message.get("i", 0)),
                    int(message.get("total", 0)),
                    str(message.get("name", "")),
                    int(message.get("step", 0)),
                    str(message.get("msg", "")),
                )
            elif kind == "done":
                done = message
            elif kind == "error":
                error = str(message.get("message", "解析失败"))

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

        if error:
            return DemoOutcome(error=error)
        if done is None:
            tail = " | ".join(stderr_tail[-3:])
            return DemoOutcome(error=f"引擎未返回结果{(': ' + tail) if tail else ''}")

        return self._collect(done, request.output_dir)

    def _is_cancelled(self, key: str) -> bool:
        with self._lock:
            return key in self._cancelled

    @staticmethod
    def _collect(done: dict[str, Any], output_dir: str) -> DemoOutcome:
        players: list[dict[str, Any]] = []
        failed = [dict(item) for item in done.get("failed") or []]

        for result in done.get("results") or []:
            name = str(result.get("player_json") or "")
            if not name:
                continue
            path = Path(output_dir) / Path(name).name
            try:
                replay = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                failed.append({"username": str(result.get("username", "")), "reason": f"读取回放失败: {exc}"})
                continue
            players.append(
                {
                    "username": result.get("username"),
                    "domain": result.get("domain"),
                    "steamId": replay.get("steamid"),
                    "rounds": replay.get("round_count", 0),
                    "bytes": path.stat().st_size,
                    "replay": replay,
                }
            )

        return DemoOutcome(players=players, failed=failed)
