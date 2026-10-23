"""WebSocket event catalogue and envelope.

The envelope keeps the historical ``action``/``payload`` field names so the
existing desktop client (``src/core/sync/sync-client.ts``) keeps working
without changes. ``seq`` and ``protocolVersion`` are additive.
"""

from __future__ import annotations

import time
from typing import Any, Final

PROTOCOL_VERSION: Final = 1


class Action:
    """Event names. Mirrored by ``contract/events.json``."""

    ROOM_STATE_SYNC = "ROOM_STATE_SYNC"
    ROOM_MEMBERS_CHANGED = "ROOM_MEMBERS_CHANGED"
    MATCH_DETECTED = "MATCH_DETECTED"
    PROFILE_READY = "PROFILE_READY"
    JOB_PROGRESS = "JOB_PROGRESS"
    TACTICAL_PATHS_READY = "TACTICAL_PATHS_READY"
    AI_STREAM_CHUNK = "AI_STREAM_CHUNK"
    AI_REPORT_READY = "AI_REPORT_READY"
    AI_TACTICS_CHUNK = "AI_TACTICS_CHUNK"
    AI_TACTICS_READY = "AI_TACTICS_READY"
    POST_MATCH_READY = "POST_MATCH_READY"
    ROOM_ERROR = "ROOM_ERROR"


ALL_ACTIONS: Final[tuple[str, ...]] = (
    Action.ROOM_STATE_SYNC,
    Action.ROOM_MEMBERS_CHANGED,
    Action.MATCH_DETECTED,
    Action.PROFILE_READY,
    Action.JOB_PROGRESS,
    Action.TACTICAL_PATHS_READY,
    Action.AI_STREAM_CHUNK,
    Action.AI_REPORT_READY,
    Action.AI_TACTICS_CHUNK,
    Action.AI_TACTICS_READY,
    Action.POST_MATCH_READY,
    Action.ROOM_ERROR,
)


def envelope(action: str, payload: dict[str, Any], seq: int, now: float | None = None) -> dict[str, Any]:
    """Build the wire message. ``now`` is injectable for deterministic tests."""

    if action not in ALL_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "seq": seq,
        "ts": int((now if now is not None else time.time()) * 1000),
        "action": action,
        "payload": payload,
    }
