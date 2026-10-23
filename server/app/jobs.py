"""Background job execution.

P1 only runs the profile job (it is derived from the uploaded report and takes
microseconds). The same executor is the hook for the demo pipeline in P2, and
it already emits ``JOB_PROGRESS`` from a worker thread, which is the part that
is easy to get wrong later.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

from . import adapters
from .events import Action
from .store import Session

log = logging.getLogger("cs-helper.jobs")

EmitSession = Callable[[Session, str, dict[str, Any]], None]


class JobManager:
    def __init__(self, emit_session: EmitSession, max_workers: int = 4) -> None:
        self._emit_session = emit_session
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._futures: set[Future] = set()
        self._lock = Lock()

    # -- public API ----------------------------------------------------
    def submit(
        self,
        kind: str,
        session: Session,
        work: Callable[[Session], None],
        *,
        total: int = 1,
    ) -> Future:
        """Queue ``work`` and report progress. Safe to call from any thread."""

        job_id = f"{kind}-{uuid.uuid4().hex[:8]}"
        future = self._pool.submit(self._run, job_id, kind, session, work, total)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._forget)
        return future

    def submit_profile(self, session: Session) -> Future | None:
        with self._lock:
            if session.profile_state in {"running", "ready"}:
                return None
            session.profile_state = "running"
        return self.submit("profile", session, self._profile_work)

    def wait_idle(self, timeout: float = 10.0) -> None:
        with self._lock:
            pending = list(self._futures)
        for future in pending:
            try:
                future.result(timeout=timeout)
            except Exception:  # already surfaced through the room event stream
                pass

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- internals -----------------------------------------------------
    def _forget(self, future: Future) -> None:
        with self._lock:
            self._futures.discard(future)

    def _run(
        self,
        job_id: str,
        kind: str,
        session: Session,
        work: Callable[[Session], None],
        total: int,
    ) -> None:
        self._emit_session(
            session,
            Action.JOB_PROGRESS,
            {"jobId": job_id, "stage": kind, "done": 0, "total": total, "etaSec": None},
        )
        try:
            work(session)
        except Exception as exc:  # never let one job kill the pool
            log.exception("job %s failed", job_id)
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2001,
                    "message": f"{kind} 任务失败",
                    "retryable": True,
                    "stage": kind,
                    "detail": str(exc)[:200],
                },
            )
            if kind == "profile":
                session.profile_state = "failed"

    def _profile_work(self, session: Session) -> None:
        payload = adapters.build_profile_payload(session.id, session.report)
        session.profiles = payload["players"]
        session.profile_state = "ready"
        self._emit_session(session, Action.PROFILE_READY, payload)
