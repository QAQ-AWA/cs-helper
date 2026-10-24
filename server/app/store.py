"""In-process room and session state.

Deliberately dependency-free so the whole relay runs as one process for a
single team. The method surface mirrors what a Redis-backed implementation
needs, so swapping the backend later does not touch call sites.

Everything here is thread-safe: HTTP handlers, WebSocket pumps and job worker
threads all touch the same store.
"""

from __future__ import annotations

import secrets
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

ROOM_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ROOM_CODE_LENGTH = 6
ROOM_TTL_SECONDS = 4 * 60 * 60
EVENT_BUFFER = 200
SESSION_MEMORY_MAX = 50
SESSION_SCHEMA_VERSION = 1


def _new_room_code() -> str:
    return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


@dataclass
class Member:
    id: str
    nickname: str
    device_type: str
    joined_at: float
    is_online: bool = True

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nickname": self.nickname,
            "deviceType": self.device_type,
            "isOnline": self.is_online,
        }


@dataclass
class Room:
    code: str
    room_id: str
    created_at: float
    expires_at: float
    members: dict[str, Member] = field(default_factory=dict)
    session_id: str | None = None
    seq: int = 0
    buffer: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=EVENT_BUFFER))

    def expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    def to_wire(self) -> dict[str, Any]:
        return {
            "roomCode": self.code,
            "roomId": self.room_id,
            "expiresAt": int(self.expires_at),
            "members": [member.to_wire() for member in self.members.values()],
            "sessionId": self.session_id,
        }


@dataclass
class Session:
    """One real match, shared by every room that reports the same matchId."""

    id: str
    platform: str
    match_id: str
    map_name: str
    report: dict[str, Any]
    created_at: float
    updated_at: float
    # Which room reported it. Persisted so a restarted single-room server can
    # re-attach the last match instead of showing an empty room.
    room_code: str | None = None
    profile_state: str = "pending"  # pending | running | ready | failed
    profiles: list[dict[str, Any]] | None = None
    demo_state: str = "pending"  # pending | running | ready | skipped | failed
    artifact_id: str | None = None
    # 5E season enrichment (player/home). "signature" means the key rotated.
    home_state: str = "pending"  # pending | running | ready | partial | skipped | failed | signature
    home_error: str | None = None
    home_coverage: int = 0
    ai_state: str = "pending"  # pending | running | ready | skipped | failed
    ai_text: str | None = None
    # 结构化分析结果（v3）：客户端按卡片渲染，ai_text 是给手机看的纯文本版。
    ai_result: dict[str, Any] | None = None
    # 这份分析是基于什么输入算出来的（地图 + 名单 + 敌我）。变了就得重算。
    analysis_key: str | None = None
    # 还差什么才能开跑，给界面显示「等地图确认」这种话。
    ai_wait: list[str] | None = None
    # Second AI pass: opening habits read off the parsed trajectories.
    tactics_state: str = "pending"  # pending | running | ready | skipped | failed
    tactics_text: str | None = None
    trajectory: dict[str, Any] | None = None
    post_report: dict[str, Any] | None = None

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.match_id}"

    def to_wire(self) -> dict[str, Any]:
        return {
            "sessionId": self.id,
            "platform": self.platform,
            "matchId": self.match_id,
            "mapName": self.map_name,
            "teams": self.report.get("teams", {}),
            "phase": self.report.get("phase", "ready"),
            "countdownSeconds": self.report.get("countdownSeconds"),
            "mySide": self.report.get("mySide"),
            "profileState": self.profile_state,
            "demoState": self.demo_state,
            "homeState": self.home_state,
            "homeError": self.home_error,
            "homeCoverage": self.home_coverage,
            "artifactId": self.artifact_id,
            "aiState": self.ai_state,
            "aiText": self.ai_text,
            "aiResult": self.ai_result,
            "aiWait": self.ai_wait,
            "tacticsState": self.tactics_state,
            "tacticsText": self.tactics_text,
            "postReport": self.post_report,
            "createdAt": int(self.created_at * 1000),
            "updatedAt": int(self.updated_at * 1000),
        }

    # -- persistence ---------------------------------------------------
    def to_record(self) -> dict[str, Any]:
        return {
            "schemaVersion": SESSION_SCHEMA_VERSION,
            "id": self.id,
            "platform": self.platform,
            "matchId": self.match_id,
            "mapName": self.map_name,
            "roomCode": self.room_code,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "report": self.report,
            "profileState": self.profile_state,
            "profiles": self.profiles,
            "demoState": self.demo_state,
            "artifactId": self.artifact_id,
            "homeState": self.home_state,
            "homeError": self.home_error,
            "homeCoverage": self.home_coverage,
            "aiState": self.ai_state,
            "aiText": self.ai_text,
            "aiResult": self.ai_result,
            "analysisKey": self.analysis_key,
            "aiWait": self.ai_wait,
            "tacticsState": self.tactics_state,
            "tacticsText": self.tactics_text,
            "trajectory": self.trajectory,
            "postReport": self.post_report,
        }

    @classmethod
    def from_record(cls, data: dict[str, Any]) -> "Session | None":
        """Rebuild a session, or ``None`` if the record cannot be trusted."""

        try:
            session = cls(
                id=str(data["id"]),
                platform=str(data["platform"]),
                match_id=str(data["matchId"]),
                map_name=str(data.get("mapName") or ""),
                report=data.get("report") or {},
                created_at=float(data.get("createdAt") or 0.0),
                updated_at=float(data.get("updatedAt") or 0.0),
                room_code=(str(data["roomCode"]) if data.get("roomCode") else None),
                profile_state=str(data.get("profileState") or "pending"),
                profiles=data.get("profiles"),
                demo_state=str(data.get("demoState") or "pending"),
                artifact_id=(str(data["artifactId"]) if data.get("artifactId") else None),
                home_state=str(data.get("homeState") or "pending"),
                home_error=data.get("homeError"),
                home_coverage=int(data.get("homeCoverage") or 0),
                ai_state=str(data.get("aiState") or "pending"),
                ai_text=data.get("aiText"),
                ai_result=data.get("aiResult"),
                analysis_key=data.get("analysisKey"),
                ai_wait=data.get("aiWait"),
                tactics_state=str(data.get("tacticsState") or "pending"),
                tactics_text=data.get("tacticsText"),
                trajectory=data.get("trajectory"),
                post_report=data.get("postReport"),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if not isinstance(session.report, dict) or not session.report.get("teams"):
            return None
        # A job that was mid-flight when the process died will never finish.
        for attribute in ("profile_state", "demo_state", "ai_state", "tactics_state", "home_state"):
            if getattr(session, attribute) == "running":
                setattr(session, attribute, "failed")
        return session

    def summary(self) -> dict[str, Any]:
        """Compact row for the history list (no teams, no AI body)."""

        post = self.post_report or {}
        players = post.get("players") or []
        return {
            "sessionId": self.id,
            "platform": self.platform,
            "matchId": self.match_id,
            "mapName": self.map_name,
            "roomCode": self.room_code,
            "createdAt": int(self.created_at * 1000),
            "updatedAt": int(self.updated_at * 1000),
            "profileState": self.profile_state,
            "demoState": self.demo_state,
            "homeState": self.home_state,
            "aiState": self.ai_state,
            "tacticsState": self.tactics_state,
            "hasArtifact": bool(self.artifact_id),
            "scoreA": post.get("scoreA"),
            "scoreB": post.get("scoreB"),
            "playerCount": len(players),
            "aiExcerpt": (self.ai_text or "")[:120] or None,
        }


class Store:
    def __init__(
        self,
        room_ttl: int = ROOM_TTL_SECONDS,
        session_max: int = SESSION_MEMORY_MAX,
    ) -> None:
        self.room_ttl = room_ttl
        self.session_max = max(1, session_max)
        self._rooms: dict[str, Room] = {}
        self._sessions: dict[str, Session] = {}
        self._session_ids: dict[str, str] = {}
        self._lock = RLock()

    @property
    def lock(self) -> RLock:
        return self._lock

    # -- rooms ---------------------------------------------------------
    def create_room(self, nickname: str, device_type: str) -> tuple[Room, Member]:
        with self._lock:
            self._purge_locked()
            code = _new_room_code()
            while code in self._rooms:
                code = _new_room_code()
            now = time.time()
            room = Room(
                code=code,
                room_id=uuid.uuid4().hex,
                created_at=now,
                expires_at=now + self.room_ttl,
            )
            member = Member(
                id=uuid.uuid4().hex[:12],
                nickname=nickname,
                device_type=device_type,
                joined_at=now,
            )
            room.members[member.id] = member
            self._rooms[code] = room
            return room, member

    def get_room(self, code: str, *, touch: bool = True) -> Room | None:
        with self._lock:
            room = self._rooms.get(self._normalise(code))
            if room is None:
                return None
            if room.expired():
                self._rooms.pop(room.code, None)
                return None
            if touch:
                room.expires_at = time.time() + self.room_ttl
            return room

    def add_member(self, room: Room, nickname: str, device_type: str) -> Member:
        with self._lock:
            member = Member(
                id=uuid.uuid4().hex[:12],
                nickname=nickname,
                device_type=device_type,
                joined_at=time.time(),
            )
            room.members[member.id] = member
            return member

    def restore_member(
        self, room: Room, member_id: str, nickname: str, device_type: str
    ) -> Member:
        """Rebuild a member that only exists in a still-valid token.

        Members live in memory; the token does not. After a server restart every
        client holds a signed token whose member id is gone, and without this the
        socket is rejected forever (the client keeps retrying the same token).
        """

        with self._lock:
            existing = room.members.get(member_id)
            if existing is not None:
                return existing
            member = Member(
                id=member_id,
                nickname=nickname or "队友",
                device_type=device_type or "pc",
                joined_at=time.time(),
            )
            room.members[member.id] = member
            return member

    def get_or_create_room(self, code: str) -> Room:
        """Return the room, recreating it after a restart if needed.

        Rooms are in-memory too, so a valid token can outlive its room. Creating
        it on demand keeps the client's reconnect from failing forever.
        """

        with self._lock:
            self._purge_locked()
            normalised = self._normalise(code) or "MAIN"
            room = self._rooms.get(normalised)
            if room is None:
                now = time.time()
                room = Room(
                    code=normalised,
                    room_id=uuid.uuid4().hex,
                    created_at=now,
                    expires_at=now + self.room_ttl,
                )
                self._rooms[normalised] = room
                self._rebind_latest_locked(room)
            room.expires_at = time.time() + self.room_ttl
            return room

    def ensure_room(
        self, code: str, nickname: str, device_type: str
    ) -> tuple[Room, Member, bool]:
        """Single-room mode: one stable room, and one stable identity per device.

        Re-clicking "create room" or reopening the phone page must not pile up
        ghost members, so an existing (nickname, deviceType) pair is reused.
        """

        with self._lock:
            self._purge_locked()
            normalised = self._normalise(code) or "MAIN"
            room = self._rooms.get(normalised)
            if room is None:
                now = time.time()
                room = Room(
                    code=normalised,
                    room_id=uuid.uuid4().hex,
                    created_at=now,
                    expires_at=now + self.room_ttl,
                )
                self._rooms[normalised] = room
                # Restarted server: re-attach the most recent match that was
                # reported into this room, so the phone does not come back to
                # an empty room after every restart.
                self._rebind_latest_locked(room)
            room.expires_at = time.time() + self.room_ttl

            for member in room.members.values():
                if member.nickname == nickname and member.device_type == device_type:
                    return room, member, False

            member = Member(
                id=uuid.uuid4().hex[:12],
                nickname=nickname,
                device_type=device_type,
                joined_at=time.time(),
            )
            room.members[member.id] = member
            return room, member, True

    def set_online(self, room: Room, member_id: str, online: bool) -> bool:
        with self._lock:
            member = room.members.get(member_id)
            if member is None or member.is_online == online:
                return False
            member.is_online = online
            return True

    # -- sessions ------------------------------------------------------
    def upsert_session(
        self, report: dict[str, Any], room_code: str | None = None
    ) -> tuple[Session, bool]:
        platform = report["platform"]
        match_id = report["matchId"]
        key = f"{platform}:{match_id}"
        with self._lock:
            now = time.time()
            session = self._sessions.get(key)
            if session is None:
                session = Session(
                    id=uuid.uuid4().hex,
                    platform=platform,
                    match_id=match_id,
                    map_name=report["mapName"],
                    report=report,
                    created_at=now,
                    updated_at=now,
                    room_code=room_code,
                )
                self._sessions[key] = session
                self._session_ids[session.id] = key
                return session, True
            session.report = report
            session.map_name = report["mapName"]
            session.updated_at = now
            if room_code:
                session.room_code = room_code
            return session, False

    def restore_session(self, session: Session) -> bool:
        """Rehydrate one session from disk. Existing in-memory state wins."""

        with self._lock:
            if session.key in self._sessions:
                return False
            self._sessions[session.key] = session
            self._session_ids[session.id] = session.key
            return True

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            key = self._session_ids.get(session_id)
            return self._sessions.get(key) if key else None

    def get_session_by_key(self, key: str) -> Session | None:
        """Look a session up by ``platform:matchId``.

        A second room reporting the same match has no ``session_id`` bound yet,
        so looking it up by id alone would treat it as a brand-new match.
        """

        with self._lock:
            return self._sessions.get(key)

    def sessions(self) -> list[Session]:
        """Newest first, for the history endpoint when nothing is on disk."""

        with self._lock:
            return sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)

    def touch_session(self, session: Session) -> None:
        with self._lock:
            session.updated_at = time.time()

    def bind(self, room: Room, session: Session) -> None:
        with self._lock:
            room.session_id = session.id

    def rooms_bound_to(self, session_id: str) -> list[Room]:
        with self._lock:
            return [room for room in self._rooms.values() if room.session_id == session_id]

    def _rebind_latest_locked(self, room: Room) -> Session | None:
        now = time.time()
        candidates = [
            item
            for item in self._sessions.values()
            if item.room_code == room.code and now - item.updated_at <= self.room_ttl
        ]
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: item.updated_at)
        room.session_id = latest.id
        return latest

    # -- event bookkeeping --------------------------------------------
    def next_envelope(self, room: Room, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Assign the sequence number and remember the event for replay."""

        from .events import envelope

        with self._lock:
            room.seq += 1
            event = envelope(action, payload, room.seq)
            room.buffer.append(event)
            return event

    def events_since(self, room: Room, seq: int) -> list[dict[str, Any]]:
        with self._lock:
            return [event for event in room.buffer if event["seq"] > seq]

    def can_replay(self, room: Room, seq: int) -> bool:
        with self._lock:
            if not room.buffer:
                return seq >= room.seq
            return seq >= room.buffer[0]["seq"] - 1

    # -- housekeeping --------------------------------------------------
    def purge_expired(self) -> tuple[list[str], list[str]]:
        """Drop expired rooms, then sessions no room can still reach.

        Returns ``(room_codes, session_ids)``. The caller persists/keeps the
        dropped sessions on disk; this only decides what stays resident.
        """

        with self._lock:
            return self._purge_locked()

    def _purge_locked(self) -> tuple[list[str], list[str]]:
        now = time.time()
        dead = [code for code, room in self._rooms.items() if room.expired(now)]
        for code in dead:
            self._rooms.pop(code, None)
        return dead, self._drop_idle_sessions_locked(now)

    def _drop_idle_sessions_locked(self, now: float) -> list[str]:
        bound = {room.session_id for room in self._rooms.values() if room.session_id}
        dropped: list[str] = []

        for key, session in list(self._sessions.items()):
            if session.id in bound:
                continue
            if now - session.updated_at < self.room_ttl:
                continue
            self._forget_session_locked(key)
            dropped.append(session.id)

        # Hard cap: even a long-lived room accumulates one session per match.
        overflow = len(self._sessions) - self.session_max
        if overflow > 0:
            idle = sorted(
                (item for item in self._sessions.values() if item.id not in bound),
                key=lambda item: item.updated_at,
            )
            for session in idle[:overflow]:
                self._forget_session_locked(session.key)
                dropped.append(session.id)
        return dropped

    def _forget_session_locked(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is not None:
            self._session_ids.pop(session.id, None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "rooms": len(self._rooms),
                "sessions": len(self._sessions),
                "members": sum(len(room.members) for room in self._rooms.values()),
                "onlineMembers": sum(
                    1
                    for room in self._rooms.values()
                    for member in room.members.values()
                    if member.is_online
                ),
            }

    @staticmethod
    def _normalise(code: str) -> str:
        return (code or "").strip().upper()
