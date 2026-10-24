"""Room orchestration: the only place that assigns sequence numbers."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from . import settings
from .adapters import normalise_players
from .artifacts import ArtifactStore
from .engine_runner import DemoRunner
from .events import Action
from .identity import IdentityStore
from .jobs import JobManager
from .persistence import SessionRepository
from .security import TokenService
from .store import Member, Room, Session, Store
from .ws import ConnectionManager

log = logging.getLogger("cs-helper.hub")


class RoomNotFound(LookupError):
    pass


class RoomHub:
    def __init__(
        self,
        store: Store,
        tokens: TokenService,
        ws: ConnectionManager,
        artifacts: ArtifactStore | None = None,
        demo_runner: DemoRunner | None = None,
        room_mode: str | None = None,
        single_room_code: str | None = None,
        ai_client: object | None = None,
        repository: SessionRepository | None = None,
        history_days: int | None = None,
        identity: IdentityStore | None = None,
        home_client: object | None = None,
    ) -> None:
        self.store = store
        self.tokens = tokens
        self.ws = ws
        self.artifacts = artifacts or ArtifactStore()
        self.repository = repository
        self.history_days = history_days if history_days is not None else settings.HISTORY_DAYS
        self.identity = identity or IdentityStore()
        self.last_reap: dict[str, Any] | None = None
        self.jobs = JobManager(  # type: ignore[arg-type]
            self.emit_session,
            self.artifacts,
            demo_runner,
            ai_client,
            on_change=self.persist,
            side_resolver=self.resolved_side,
            home_client=home_client,  # type: ignore[arg-type]
        )
        self.room_mode = room_mode or settings.ROOM_MODE
        self.single_room_code = single_room_code or settings.SINGLE_ROOM_CODE

    # -- events --------------------------------------------------------
    def emit(self, room: Room, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Sequence assignment and publish happen under one lock so every client
        # observes the same order even when job threads emit concurrently.
        with self.store.lock:
            event = self.store.next_envelope(room, action, payload)
            self.ws.publish(room.code, event)
        return event

    def emit_session(self, session: Session, action: str, payload: dict[str, Any]) -> None:
        for room in self.store.rooms_bound_to(session.id):
            self.emit(room, action, payload)

    def room_state(self, room: Room) -> dict[str, Any]:
        session = self.store.get_session(room.session_id) if room.session_id else None
        return {
            "roomCode": room.code,
            "members": [member.to_wire() for member in room.members.values()],
            "match": self.session_view(session) if session else None,
            # A client joining mid-match must not depend on replaying history.
            "profiles": session.profiles if session else None,
            "latestSeq": room.seq,
        }

    # -- identity ------------------------------------------------------
    def resolved_side(self, session: Session) -> str | None:
        """The side we treat as ours, including the ID library's opinion."""

        from .adapters import resolve_my_side

        library_side = self.identity.match(session.room_code or "", session.report)
        return resolve_my_side(session.report, library_side)

    def session_view(self, session: Session) -> dict[str, Any]:
        """``to_wire`` plus the resolved side and where it came from."""

        from .adapters import resolve_side

        view = session.to_wire()
        library_side = self.identity.match(session.room_code or "", session.report)
        side, source = resolve_side(session.report, library_side)
        view["mySide"] = side
        view["mySideSource"] = source
        return view

    def learn_identity(self, room: Room, side: str) -> int:
        """Remember one roster block as ours, so the next match needs no picker."""

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)
        players = [p for p in normalise_players(session.report) if p.get("team") == side]
        return self.identity.add(room.code, players)

    # -- lifecycle -----------------------------------------------------
    @property
    def is_single_room(self) -> bool:
        return self.room_mode == "single"

    def _members_payload(self, room: Room) -> dict[str, Any]:
        return {"members": [member.to_wire() for member in room.members.values()]}

    def create_room(self, nickname: str, device_type: str) -> tuple[Room, Member, str, int]:
        if self.is_single_room:
            room, member, created = self.store.ensure_room(
                self.single_room_code, nickname, device_type
            )
            if created:
                self.emit(room, Action.ROOM_MEMBERS_CHANGED, self._members_payload(room))
        else:
            room, member = self.store.create_room(nickname, device_type)
        token, expires_at = self.tokens.issue(room.code, member.id, member.nickname, member.device_type)
        return room, member, token, expires_at

    def join_room(self, code: str, nickname: str, device_type: str) -> tuple[Room, Member, str, int]:
        if self.is_single_room:
            room, member, created = self.store.ensure_room(
                self.single_room_code, nickname, device_type
            )
            if created:
                self.emit(room, Action.ROOM_MEMBERS_CHANGED, self._members_payload(room))
        else:
            room = self.store.get_room(code)
            if room is None:
                raise RoomNotFound(code)
            member = self.store.add_member(room, nickname, device_type)
            self.emit(room, Action.ROOM_MEMBERS_CHANGED, self._members_payload(room))
        token, expires_at = self.tokens.issue(room.code, member.id, member.nickname, member.device_type)
        return room, member, token, expires_at

    def authenticate(self, token: str) -> tuple[Room, Member]:
        payload = self.tokens.verify(token)
        if not payload:
            raise RoomNotFound("token")
        code = str(payload.get("r", ""))
        room = self.store.get_room(code)
        if room is None:
            # 房间也在内存里，重启后同样会消失；token 有效就按需重建。
            room = self.store.get_or_create_room(code)
        member_id = str(payload.get("m", ""))
        member = room.members.get(member_id)
        if member is None:
            # 服务端重启后内存里的成员表丢了，但 token 签名与有效期都还在。
            # 直接按 token 里的身份重建，否则客户端会拿着旧 token 无限重试 403。
            member = self.store.restore_member(
                room,
                member_id,
                str(payload.get("n", "")),
                str(payload.get("d", "pc")),
            )
        return room, member

    def on_connect(self, room: Room, member: Member) -> None:
        if self.store.set_online(room, member.id, True):
            self.emit(room, Action.ROOM_MEMBERS_CHANGED, {"members": [m.to_wire() for m in room.members.values()]})

    def on_disconnect(self, room_code: str, member: Member) -> None:
        if self.ws.has_member_connection(room_code, member.id):
            return
        room = self.store.get_room(room_code, touch=False)
        if room is None:
            return
        if self.store.set_online(room, member.id, False):
            self.emit(room, Action.ROOM_MEMBERS_CHANGED, {"members": [m.to_wire() for m in room.members.values()]})

    # -- match ---------------------------------------------------------
    def report_match(self, room: Room, report: dict[str, Any]) -> tuple[Session, bool]:
        existing = self.store.get_session(room.session_id) if room.session_id else None
        if existing is None:
            # 另一个房间报了同一局：房间里还没绑定会话，但会话本身已经存在。
            existing = self.store.get_session_by_key(
                f"{report.get('platform')}:{report.get('matchId')}"
            )
        if (
            existing is not None
            and existing.match_id == report.get("matchId")
            and not report.get("mySide")
            and existing.report.get("mySide")
        ):
            # A second PC re-reporting the same match must not wipe the side
            # someone already picked; that would silently re-download all ten.
            report = {**report, "mySide": existing.report["mySide"]}
        previous_map = existing.map_name if existing is not None else None
        session, created = self.store.upsert_session(report, room_code=room.code)
        self.store.bind(room, session)
        # 地图常常是「先 de_unknown、后补上」：第一次上报时 demo 会被跳过，
        # 等真地图到了必须重跑，否则轨迹永远不出来。
        if not created and session.map_name != previous_map:
            session.demo_state = "pending"
            session.tactics_state = "pending"
        self.emit_session(session, Action.MATCH_DETECTED, self.session_view(session))
        self.persist(session)
        self.jobs.submit_profile(session)
        self.jobs.submit_demo(session)
        return session, created

    def set_analysis_side(
        self, room: Room, my_side: str | None, analyze_all: bool = False
    ) -> Session:
        """Change which roster we treat as ours and re-run the demo job.

        Downloads are cached per player on disk, so switching after the fact
        only pays for players never fetched before.
        """

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)
        session.report["mySide"] = my_side
        session.report["analyzeAll"] = bool(analyze_all and my_side is None)
        session.updated_at = time.time()
        if my_side in ("ct", "t"):
            # 手动选过一次边就该记住：下一局不用再点，也不会再把自己算成对手。
            try:
                self.learn_identity(room, my_side)
            except RoomNotFound:
                pass
            # A/B 换了边，旧的分析是按错的敌我写的，必须重算而不是留着。
            if session.ai_state != "running":
                session.ai_state = "pending"
                session.ai_result = None
                session.ai_text = None
        self.persist(session)
        self.emit_session(session, Action.MATCH_DETECTED, self.session_view(session))
        if self.jobs.demo_enabled:
            if session.demo_state == "running":
                self.jobs.cancel(session.id)
            session.demo_state = "pending"
            self.jobs.submit_demo(session)
        # 换边等于换视角：旧分析是按另一边写的，必须重算。
        if session.ai_state != "running":
            session.ai_state = "pending"
            self.jobs.submit_ai(session)
        return session

    def rerun_analysis(self, room: Room) -> Session:
        """Force a fresh AI pass; the analysis panel's 重新分析 button."""

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)
        if session.ai_state == "running":
            return session
        session.ai_state = "pending"
        session.updated_at = time.time()
        self.persist(session)
        self.emit_session(session, Action.MATCH_DETECTED, self.session_view(session))
        self.jobs.submit_ai(session)
        return session

    def report_post_match(self, room: Room, report: dict[str, Any]) -> Session:
        """赛后面板的数据由客户端取回，服务端只负责归档与广播。"""

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)
        session.post_report = report
        self.persist(session)
        self.emit_session(
            session,
            Action.POST_MATCH_READY,
            {"sessionId": session.id, **report},
        )
        return session

    # -- durability ----------------------------------------------------
    def persist(self, session: Session) -> None:
        """Write-through one session. Never raises: a full disk must not kill a job."""

        if self.repository is None:
            return
        with self.store.lock:
            session.updated_at = time.time()
            record = session.to_record()
        try:
            self.repository.save(record)
        except OSError:
            log.exception("could not persist session %s", session.id)

    def load_history(self) -> int:
        """Rehydrate the most recent matches after a restart."""

        if self.repository is None:
            return 0
        loaded = 0
        for record in self.repository.load_all(limit=self.store.session_max):
            session = Session.from_record(record)
            if session is None:
                continue
            # The replay blob may have been swept by retention; claiming
            # "ready" would make the phone request a 404.
            if session.artifact_id and not self.artifacts.has(session.artifact_id):
                session.artifact_id = None
                if session.demo_state == "ready":
                    session.demo_state = "failed"
            if self.store.restore_session(session):
                loaded += 1
        if loaded:
            log.info("restored %d match(es) from %s", loaded, self.repository.root)
        return loaded

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        if self.repository is not None:
            rows: list[dict[str, Any]] = []
            for record in self.repository.load_all(limit=limit):
                session = Session.from_record(record)
                if session is not None:
                    rows.append(session.summary())
            return rows
        return [session.summary() for session in self.store.sessions()[:limit]]

    def reap(self) -> dict[str, int]:
        """One housekeeping pass: expired rooms, idle sessions, old history."""

        rooms, sessions = self.store.purge_expired()
        result = {"rooms": len(rooms), "sessions": len(sessions), "history": 0, "artifacts": 0}
        if self.repository is not None:
            window = self.history_days * 86400
            dropped = self.repository.prune(window)
            result["history"] = len(dropped)
            if dropped:
                # Only a deleted match can orphan a blob, so the (relatively
                # expensive) directory scan is gated on that.
                result["artifacts"] = self.artifacts.prune_orphans(
                    self.repository.referenced_artifacts(), window
                )
        self.last_reap = {**result, "at": int(time.time())}
        if any(result.values()):
            log.info(
                "reaped rooms=%d sessions=%d history=%d artifacts=%d",
                result["rooms"],
                result["sessions"],
                result["history"],
                result["artifacts"],
            )
        return result

    def metrics(self) -> dict[str, Any]:
        stats: dict[str, Any] = dict(self.store.stats())
        stats.update(
            {
                "artifacts": self.artifacts.item_count,
                "artifactBytes": self.artifacts.total_bytes,
                "artifactDiskBytes": self.artifacts.disk_bytes(),
                "persistence": self.repository is not None,
                "historyFiles": self.repository.count() if self.repository else 0,
                "dataDir": str(self.repository.root) if self.repository else None,
                "historyDays": self.history_days,
                "lastReap": self.last_reap,
            }
        )
        return stats

    def shutdown(self) -> None:
        self.jobs.shutdown()

    # -- dev only ------------------------------------------------------
    def seed_dev_paths(self, room: Room):
        """合成一条轨迹产物，用于没有 CS2/5E 时验证回放（需 CS_HELPER_DEV=1）。"""

        from .devtools import build_synthetic_artifact

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)

        players = session.profiles or normalise_players(session.report)
        bundle, parts = build_synthetic_artifact(session, players)
        artifact = self.artifacts.put(
            json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            parts=parts,
        )
        session.artifact_id = artifact.id
        session.demo_state = "ready"
        self.persist(session)
        self.emit_session(
            session,
            Action.TACTICAL_PATHS_READY,
            {
                "sessionId": session.id,
                "artifactId": artifact.id,
                "map": session.map_name,
                "players": bundle["players"],
                "failed": [],
                "synthetic": True,
            },
        )
        return artifact

    def parse_dev_demo(self, room: Room, demo_name: str):
        """真实解析一份本机 .dem，跳过 5E 检索与下载（需 CS_HELPER_DEV=1）。"""

        from .devtools import parse_local_demo, resolve_local_demo

        session = self.store.get_session(room.session_id) if room.session_id else None
        if session is None:
            raise RoomNotFound(room.code)

        demo_path = resolve_local_demo(demo_name)
        roster = session.profiles or normalise_players(session.report)
        players = [
            {"steamid": str(p.get("steamId") or ""), "username": p.get("nickname") or ""}
            for p in roster
            if p.get("steamId")
        ]
        if not players:
            raise ValueError("当前对局没有可解析的选手")

        session.demo_state = "running"
        self.emit_session(
            session, Action.JOB_PROGRESS, {"sessionId": session.id, "stage": "demo", "step": 1, "total": 6}
        )
        try:
            bundle, parts = parse_local_demo(demo_path, players, settings.job_dir(session.id))
        except Exception:
            session.demo_state = "failed"
            raise

        artifact = self.artifacts.put(
            json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            parts=parts,
        )
        session.artifact_id = artifact.id
        session.demo_state = "ready"
        session.trajectory = self._profile_from_parts(bundle, parts)
        self.persist(session)
        self.emit_session(
            session,
            Action.TACTICAL_PATHS_READY,
            {
                "sessionId": session.id,
                "artifactId": artifact.id,
                "map": session.map_name,
                "players": bundle["players"],
                "failed": bundle.get("failed") or [],
                "synthetic": False,
            },
        )
        self.jobs.submit_tactics(session)
        return artifact, bundle

    @staticmethod
    def _profile_from_parts(bundle: dict[str, Any], parts: dict[str, bytes]) -> dict[str, Any]:
        """Opening habits for the dev path, which has no engine outcome object."""

        from .trajectory import build_profile

        players = []
        for steam_id, body in parts.items():
            try:
                payload = json.loads(body)
            except (ValueError, TypeError):
                continue
            players.append(
                {
                    "steamId": steam_id,
                    "nickname": payload.get("nickname"),
                    "replay": payload.get("replay"),
                }
            )
        return build_profile(bundle.get("map") or "", players)
