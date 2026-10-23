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
    profile_state: str = "pending"  # pending | running | ready | failed
    profiles: list[dict[str, Any]] | None = None

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
            "profileState": self.profile_state,
        }


class Store:
    def __init__(self, room_ttl: int = ROOM_TTL_SECONDS) -> None:
        self.room_ttl = room_ttl
        self._rooms: dict[str, Room] = {}
        self._sessions: dict[str, Session] = {}
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

    def set_online(self, room: Room, member_id: str, online: bool) -> bool:
        with self._lock:
            member = room.members.get(member_id)
            if member is None or member.is_online == online:
                return False
            member.is_online = online
            return True

    # -- sessions ------------------------------------------------------
    def upsert_session(self, report: dict[str, Any]) -> tuple[Session, bool]:
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
                )
                self._sessions[key] = session
                return session, True
            session.report = report
            session.map_name = report["mapName"]
            session.updated_at = now
            return session, False

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            for session in self._sessions.values():
                if session.id == session_id:
                    return session
            return None

    def bind(self, room: Room, session: Session) -> None:
        with self._lock:
            room.session_id = session.id

    def rooms_bound_to(self, session_id: str) -> list[Room]:
        with self._lock:
            return [room for room in self._rooms.values() if room.session_id == session_id]

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
    def purge_expired(self) -> list[str]:
        with self._lock:
            return self._purge_locked()

    def _purge_locked(self) -> list[str]:
        now = time.time()
        dead = [code for code, room in self._rooms.items() if room.expired(now)]
        for code in dead:
            self._rooms.pop(code, None)
        return dead

    @staticmethod
    def _normalise(code: str) -> str:
        return (code or "").strip().upper()
