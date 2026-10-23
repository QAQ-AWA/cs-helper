"""Room orchestration: the only place that assigns sequence numbers."""

from __future__ import annotations

from typing import Any

from . import settings
from .artifacts import ArtifactStore
from .engine_runner import DemoRunner
from .events import Action
from .jobs import JobManager
from .security import TokenService
from .store import Member, Room, Session, Store
from .ws import ConnectionManager


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
    ) -> None:
        self.store = store
        self.tokens = tokens
        self.ws = ws
        self.artifacts = artifacts or ArtifactStore()
        self.jobs = JobManager(self.emit_session, self.artifacts, demo_runner)
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
            "match": session.to_wire() if session else None,
            # A client joining mid-match must not depend on replaying history.
            "profiles": session.profiles if session else None,
            "latestSeq": room.seq,
        }

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
        room = self.store.get_room(str(payload.get("r", "")))
        if room is None:
            raise RoomNotFound("room")
        member = room.members.get(str(payload.get("m", "")))
        if member is None:
            raise RoomNotFound("member")
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
        session, created = self.store.upsert_session(report)
        self.store.bind(room, session)
        self.emit_session(session, Action.MATCH_DETECTED, session.to_wire())
        self.jobs.submit_profile(session)
        self.jobs.submit_demo(session)
        return session, created

    def shutdown(self) -> None:
        self.jobs.shutdown()
