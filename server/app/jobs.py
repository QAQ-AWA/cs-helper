"""Background job execution.

Two job kinds today:

* ``profile`` — derived from the uploaded report, finishes in microseconds.
* ``demo``    — hands the roster to the parsing engine in a child process,
  streams progress, then publishes one immutable artifact.

Everything runs off the request thread; ``JOB_PROGRESS`` is emitted from worker
threads, which is why the WebSocket layer accepts cross-thread publishing.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable, Iterator, Protocol

from . import adapters, settings
from .ai import TACTICS_SYSTEM_PROMPT, build_prompt, build_tactics_prompt
from .artifacts import ArtifactStore
from .engine_runner import DemoRequest, DemoRunner
from .events import Action
from .home_enrich import HomeClient, merge_season_stats
from .store import Session
from .trajectory import build_profile

log = logging.getLogger("cs-helper.jobs")

EmitSession = Callable[[Session, str, dict[str, Any]], None]
STREAM_EMIT_INTERVAL = 0.12
THINKING_EMIT_INTERVAL = 0.8


class AiClient(Protocol):
    def stream(self, prompt: str) -> Iterator[str]: ...

_STEP_LABELS = {
    0: "识别玩家",
    1: "获取 Demo 列表",
    2: "确认身份",
    3: "下载 Demo",
    4: "解析 Demo",
    5: "生成回放",
    6: "收尾",
}


class JobManager:
    def __init__(
        self,
        emit_session: EmitSession,
        artifacts: ArtifactStore,
        demo_runner: DemoRunner | None = None,
        ai_client: AiClient | None = None,
        max_workers: int = 4,
        on_change: Callable[[Session], None] | None = None,
        side_resolver: Callable[[Session], str | None] | None = None,
        home_client: HomeClient | None = None,
    ) -> None:
        self._emit_session = emit_session
        self._artifacts = artifacts
        self._demo_runner = demo_runner
        self._ai_client = ai_client
        self._on_change = on_change
        self._side_resolver = side_resolver
        self._home_client = home_client
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._futures: set[Future] = set()
        self._lock = Lock()

    def _side(self, session: Session) -> str | None:
        """Our side as the hub resolves it (explicit pick, ID library, markers)."""

        if self._side_resolver is not None:
            return self._side_resolver(session)
        return adapters.resolve_my_side(session.report)

    # -- public API ----------------------------------------------------
    @property
    def demo_enabled(self) -> bool:
        return self._demo_runner is not None

    def submit(
        self,
        kind: str,
        session: Session,
        work: Callable[[Session], None],
        *,
        total: int = 1,
    ) -> Future:
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

    def submit_demo(self, session: Session) -> Future | None:
        if self._demo_runner is None:
            return None
        with self._lock:
            if session.demo_state in {"running", "ready"}:
                return None
            session.demo_state = "running"
        # Only the opposing five when the report (or the ID library) says which
        # side is ours.
        total = len(adapters.demo_targets(session.report, self._side(session)))
        return self.submit("demo", session, self._demo_work, total=max(total, 1))

    def cancel(self, session_id: str) -> None:
        if self._demo_runner is not None:
            self._demo_runner.cancel(session_id)

    def wait_idle(self, timeout: float = 30.0) -> None:
        with self._lock:
            pending = list(self._futures)
        for future in pending:
            try:
                future.result(timeout=timeout)
            except Exception:  # already surfaced through the event stream
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
            elif kind == "demo":
                session.demo_state = "failed"
        finally:
            # Every terminal transition lands on disk, whatever the outcome.
            if self._on_change is not None:
                try:
                    self._on_change(session)
                except Exception:
                    log.exception("could not persist session %s", session.id)

    def _profile_work(self, session: Session) -> None:
        payload = adapters.build_profile_payload(session.id, session.report)
        session.profiles = payload["players"]
        session.profile_state = "ready"
        self._emit_session(session, Action.PROFILE_READY, payload)
        # Season data enriches the same rows, so it runs before the AI pass.
        self.submit_home(session)

    # -- 5E season enrichment ------------------------------------------
    def submit_home(self, session: Session) -> Future | None:
        if self._home_client is None:
            if session.home_state == "pending":
                session.home_state = "skipped"
            return self.submit_ai(session)
        if session.home_state in {"running", "ready", "partial", "signature"}:
            return self.submit_ai(session)
        session.home_state = "running"
        return self.submit("home", session, self._home_work)

    def _home_work(self, session: Session) -> None:
        assert self._home_client is not None
        players = session.profiles or adapters.normalise_players(session.report)

        # The desktop uploads its own season sheet. When it is complete the
        # gateway call is pure duplication, so skip it.
        already = sum(
            1
            for player in players
            if isinstance(player.get("stats"), dict)
            and player["stats"].get("seasonAdr") is not None
        )
        if players and already >= len(players):
            session.home_state = "ready"
            session.home_coverage = already
            session.home_error = None
            self.submit_ai(session)
            return

        outcome = self._home_client.fetch(players)

        if not outcome.seasons:
            # A rotated key is an expected state, not a crash: say so once and
            # keep the rest of the pipeline running on client-reported stats.
            session.home_state = "signature" if outcome.signature_failed else "failed"
            session.home_error = outcome.error or "player/home 没有返回任何赛季数据"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2007 if outcome.signature_failed else 2008,
                    "message": session.home_error,
                    "retryable": False,
                    "stage": "home",
                },
            )
            self.submit_ai(session)
            return

        merged = merge_season_stats(players, outcome.seasons)
        session.profiles = players
        session.home_coverage = merged
        session.home_state = "ready" if merged >= len(players) else "partial"
        session.home_error = outcome.error
        self._emit_session(
            session,
            Action.PROFILE_READY,
            {
                "sessionId": session.id,
                "source": "client+season",
                "mapName": session.map_name,
                "players": players,
            },
        )
        self.submit_ai(session)

    # -- ai ------------------------------------------------------------
    def submit_ai(self, session: Session) -> Future | None:
        if self._ai_client is None:
            if session.ai_state == "pending":
                session.ai_state = "skipped"
            return None
        with self._lock:
            if session.ai_state in {"running", "ready"}:
                return None
            session.ai_state = "running"
        return self.submit("ai", session, self._ai_work)

    def _ai_work(self, session: Session) -> None:
        assert self._ai_client is not None
        players = session.profiles or adapters.normalise_players(session.report)
        prompt = build_prompt(
            session.map_name,
            players,
            self._side(session),
        )

        accumulated = ""
        last_emit = 0.0
        # Reasoning models emit a hidden scratchpad first. Surface its size as a
        # progress hint, otherwise the phone stares at an empty card for ~10s.
        reason_chars = 0
        last_reason_emit = 0.0

        def on_reason(text: str) -> None:
            nonlocal reason_chars, last_reason_emit
            reason_chars += len(text)
            now = time.monotonic()
            if now - last_reason_emit >= THINKING_EMIT_INTERVAL:
                last_reason_emit = now
                self._emit_session(
                    session,
                    Action.AI_STREAM_CHUNK,
                    {"sessionId": session.id, "phase": "thinking", "chars": reason_chars},
                )

        for chunk in self._ai_client.stream(prompt, on_reason=on_reason):
            if not chunk:
                continue
            accumulated += chunk
            now = time.monotonic()
            if now - last_emit >= STREAM_EMIT_INTERVAL:
                last_emit = now
                self._emit_session(
                    session,
                    Action.AI_STREAM_CHUNK,
                    {"sessionId": session.id, "phase": "writing", "accumulated": accumulated},
                )

        if not accumulated.strip():
            session.ai_state = "failed"
            detail = "模型只输出了推理过程，没有正文，可调大 CS_HELPER_AI_MAX_TOKENS"
            if reason_chars:
                detail = f"{detail}（本次推理 {reason_chars} 字）"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {"code": 2005, "message": detail, "retryable": True, "stage": "ai"},
            )
            return

        session.ai_text = accumulated
        session.ai_state = "ready"
        self._emit_session(
            session,
            Action.AI_STREAM_CHUNK,
            {"sessionId": session.id, "phase": "writing", "accumulated": accumulated},
        )
        self._emit_session(
            session,
            Action.AI_REPORT_READY,
            {"sessionId": session.id, "report": accumulated, "model": settings.AI_MODEL},
        )

    # -- demo ----------------------------------------------------------
    def _demo_work(self, session: Session) -> None:
        report = session.report
        job_id = f"demo-{session.id[:8]}"

        if report.get("platform") != "5e":
            session.demo_state = "skipped"
            self._emit_session(
                session,
                Action.JOB_PROGRESS,
                {"jobId": job_id, "stage": "demo", "done": 0, "total": 0,
                 "etaSec": None, "skipped": "该平台暂不支持 Demo 检索"},
            )
            return

        if not settings.maps_ready(session.map_name):
            session.demo_state = "skipped"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2002,
                    "message": f"引擎缺少 {session.map_name} 的地图资源",
                    "retryable": False,
                    "stage": "demo",
                    "detail": "在 engine/ 下运行 setup_maps.py",
                },
            )
            return

        request = DemoRequest(
            usernames=adapters.demo_job_targets(report, self._side(session)),
            map_name=session.map_name,
            max_demos=settings.DEMO_MAX_DEMOS,
            hints=adapters.to_engine_hints(report, self._side(session)),
            output_dir=str(settings.job_dir(session.id)),
            demo_dir=str(settings.DEMO_DIR),
            maps_dir=str(settings.MAPS_DIR),
            mode=settings.DEMO_MODE,
        )

        def on_progress(index: int, total: int, name: str, step: int, message: str) -> None:
            self._emit_session(
                session,
                Action.JOB_PROGRESS,
                {
                    "jobId": job_id,
                    "stage": "demo",
                    "player": name,
                    "step": step,
                    "label": _STEP_LABELS.get(step, "处理中"),
                    "message": message,
                    "done": index,
                    "total": max(total, 1),
                    "etaSec": None,
                },
            )

        assert self._demo_runner is not None
        outcome = self._demo_runner.run(request, on_progress, session_id=session.id)

        if outcome.cancelled:
            session.demo_state = "failed"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {"code": 2003, "message": "解析已取消", "retryable": True, "stage": "demo"},
            )
            return

        if outcome.error:
            session.demo_state = "failed"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2001,
                    "message": "Demo 解析失败",
                    "retryable": True,
                    "stage": "demo",
                    "detail": outcome.error[:300],
                },
            )
            return

        # "No error" is not the same as "has data": when every player fails the
        # pipeline still exits cleanly. Publishing an empty TACTICAL_PATHS_READY
        # would show the phone a ready-but-blank path list with no explanation.
        if not outcome.players:
            session.demo_state = "failed"
            reasons = "；".join(
                f"{item.get('username') or '?'}: {item.get('reason') or '无可用录像'}"
                for item in (outcome.failed or [])[:3]
            )
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2006,
                    "message": "没有解析出任何轨迹",
                    "retryable": True,
                    "stage": "demo",
                    "detail": reasons[:300],
                },
            )
            return

        nick_by_steam, nick_by_domain = adapters.nickname_index(session.report)

        def display_name(item: dict[str, Any]) -> str:
            steam_id = str(item.get("steamId") or "")
            domain = str(item.get("domain") or "")
            return (
                nick_by_steam.get(steam_id)
                or nick_by_domain.get(domain)
                or (item.get("username") or "")
                or steam_id
            )

        players = [
            {
                "steamId": item.get("steamId"),
                "username": item.get("username"),
                "nickname": display_name(item),
                "domain": item.get("domain"),
                "rounds": item.get("rounds", 0),
                "bytes": item.get("bytes", 0),
            }
            for item in outcome.players
        ]
        # Heavy replay payloads go into per-player parts: the phone picks one
        # player at a time instead of downloading the whole roster.
        parts: dict[str, bytes] = {}
        for item in outcome.players:
            steam_id = item.get("steamId")
            if not steam_id:
                continue
            parts[str(steam_id)] = json.dumps(
                {
                    "steamId": steam_id,
                    "username": item.get("username"),
                    "nickname": display_name(item),
                    "domain": item.get("domain"),
                    "replay": item.get("replay"),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

        bundle = {
            "sessionId": session.id,
            "map": session.map_name,
            "generatedAt": int(time.time() * 1000),
            "players": players,
            "failed": outcome.failed,
        }
        try:
            artifact = self._artifacts.put(
                json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                parts=parts,
            )
        except ValueError as exc:
            session.demo_state = "failed"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {"code": 2004, "message": "回放数据过大", "retryable": False,
                 "stage": "demo", "detail": str(exc)[:200]},
            )
            return

        session.artifact_id = artifact.id
        session.demo_state = "ready"
        self._emit_session(
            session,
            Action.TACTICAL_PATHS_READY,
            {
                "sessionId": session.id,
                "artifactId": artifact.id,
                "map": session.map_name,
                "players": players,
                "failed": outcome.failed,
                "bytes": artifact.size,
            },
        )
        # Opening habits can only be read once the paths exist, so the tactics
        # pass chains here rather than running next to the profile analysis.
        session.trajectory = build_profile(session.map_name, outcome.players)
        # 轨迹重建了，开局预判就得重算：切换阵营或补下载之后，旧结论已经过期。
        if session.tactics_state != "running":
            session.tactics_state = "pending"
        self.submit_tactics(session)

    # -- tactics (second AI pass) --------------------------------------
    def submit_tactics(self, session: Session) -> Future | None:
        if self._ai_client is None:
            if session.tactics_state == "pending":
                session.tactics_state = "skipped"
            return None
        if not (session.trajectory or {}).get("players"):
            if session.tactics_state == "pending":
                session.tactics_state = "skipped"
            return None
        with self._lock:
            if session.tactics_state in {"running", "ready"}:
                return None
            session.tactics_state = "running"
        return self.submit("tactics", session, self._tactics_work)

    def _tactics_work(self, session: Session) -> None:
        assert self._ai_client is not None
        assert session.trajectory is not None
        prompt = build_tactics_prompt(session.trajectory)

        accumulated = ""
        last_emit = 0.0
        reason_chars = 0
        last_reason_emit = 0.0

        def on_reason(text: str) -> None:
            nonlocal reason_chars, last_reason_emit
            reason_chars += len(text)
            now = time.monotonic()
            if now - last_reason_emit >= THINKING_EMIT_INTERVAL:
                last_reason_emit = now
                self._emit_session(
                    session,
                    Action.AI_TACTICS_CHUNK,
                    {"sessionId": session.id, "phase": "thinking", "chars": reason_chars},
                )

        for chunk in self._ai_client.stream(
            prompt, on_reason=on_reason, system=TACTICS_SYSTEM_PROMPT
        ):
            if not chunk:
                continue
            accumulated += chunk
            now = time.monotonic()
            if now - last_emit >= STREAM_EMIT_INTERVAL:
                last_emit = now
                self._emit_session(
                    session,
                    Action.AI_TACTICS_CHUNK,
                    {"sessionId": session.id, "phase": "writing", "accumulated": accumulated},
                )

        if not accumulated.strip():
            session.tactics_state = "failed"
            self._emit_session(
                session,
                Action.ROOM_ERROR,
                {
                    "code": 2005,
                    "message": "开局预判没有正文输出，可调大 CS_HELPER_AI_MAX_TOKENS",
                    "retryable": True,
                    "stage": "tactics",
                    "detail": f"推理 {reason_chars} 字" if reason_chars else None,
                },
            )
            return

        session.tactics_text = accumulated
        session.tactics_state = "ready"
        self._emit_session(
            session,
            Action.AI_TACTICS_CHUNK,
            {"sessionId": session.id, "phase": "writing", "accumulated": accumulated},
        )
        self._emit_session(
            session,
            Action.AI_TACTICS_READY,
            {"sessionId": session.id, "report": accumulated, "model": settings.AI_MODEL},
        )
