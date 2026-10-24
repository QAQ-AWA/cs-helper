"""Known-good player IDs, so "which side is ours" can be answered without asking.

A library of SteamIDs and 5E domains you have confirmed as your own team. On a
new report we look for them before touching the UI: two or more hits on one side
means that side is ours.

Why two and not one: a former teammate you now play *against* would otherwise
match on the opposing side and silently flip the whole analysis to the wrong
team. A duo or a five-stack still auto-detects; a solo player falls back to the
manual picker, which is the safe failure.

The store lives beside the match history so it survives restarts, and it is
keyed by room code so two groups sharing one relay never inherit each other's
rosters.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from .persistence import atomic_write

log = logging.getLogger("cs-helper.identity")

SCHEMA_VERSION = 1
# Two hits on one side and none on the other is the smallest confident signal.
MIN_MATCHES = 2
MAX_IDS_PER_ROOM = 200


def _clean(values: Iterable[Any]) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


_STEAM_LIKE = re.compile(r"765\d{14}\Z")


def _clean_domains(values: Iterable[Any]) -> list[str]:
    """5E domains only — a SteamID here is the client's fallback, not a domain."""

    return [value for value in _clean(values) if not _STEAM_LIKE.fullmatch(value)]


class IdentityStore:
    def __init__(self, path: str | Path | None = None, min_matches: int = MIN_MATCHES) -> None:
        self.path = Path(path) if path else None
        self.min_matches = max(1, min_matches)
        self._lock = RLock()

    # -- storage -------------------------------------------------------
    def _read(self) -> dict[str, Any]:
        if self.path is None:
            return {"version": SCHEMA_VERSION, "rooms": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"version": SCHEMA_VERSION, "rooms": {}}
        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            return {"version": SCHEMA_VERSION, "rooms": {}}
        rooms = raw.get("rooms")
        return raw if isinstance(rooms, dict) else {"version": SCHEMA_VERSION, "rooms": {}}

    def _write(self, data: dict[str, Any]) -> None:
        if self.path is None:
            return
        try:
            atomic_write(
                self.path,
                json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            )
        except OSError as exc:
            log.warning("could not persist identity library: %s", exc)

    # -- queries -------------------------------------------------------
    def entries(self, room_code: str) -> dict[str, list[str]]:
        with self._lock:
            room = self._read()["rooms"].get(room_code.upper()) or {}
        return {
            "steamIds": _clean(room.get("steamIds") or []),
            "domains": _clean_domains(room.get("domains") or []),
        }

    def summary(self, room_code: str) -> dict[str, Any]:
        entries = self.entries(room_code)
        return {
            "roomCode": room_code.upper(),
            "count": len(entries["steamIds"]),
            "steamIds": entries["steamIds"],
            "domains": entries["domains"],
            "minMatches": self.min_matches,
        }

    def match(self, room_code: str, report: dict[str, Any]) -> str | None:
        """Which side the library recognises, or ``None`` when it cannot tell."""

        entries = self.entries(room_code)
        if not entries["steamIds"] and not entries["domains"]:
            return None
        teams = report.get("teams") or {}
        hits = {"ct": 0, "t": 0}
        for side in ("ct", "t"):
            for player in teams.get(side) or []:
                if not isinstance(player, dict):
                    continue
                if (
                    str(player.get("steamId") or "") in entries["steamIds"]
                    or str(player.get("platformUserId") or "") in entries["domains"]
                ):
                    hits[side] += 1
        if hits["ct"] >= self.min_matches and hits["t"] == 0:
            return "ct"
        if hits["t"] >= self.min_matches and hits["ct"] == 0:
            return "t"
        return None

    # -- mutations -----------------------------------------------------
    def add(self, room_code: str, players: Iterable[dict[str, Any]]) -> int:
        with self._lock:
            data = self._read()
            room = data["rooms"].setdefault(
                room_code.upper(), {"steamIds": [], "domains": []}
            )
            steam_ids = _clean([*room.get("steamIds", []), *[p.get("steamId") for p in players]])
            domains = _clean_domains(
                [*room.get("domains", []), *[p.get("platformUserId") for p in players]]
            )
            before = (len(room.get("steamIds") or []), len(room.get("domains") or []))
            room["steamIds"] = steam_ids[-MAX_IDS_PER_ROOM:]
            room["domains"] = domains[-MAX_IDS_PER_ROOM:]
            self._write(data)
            return len(steam_ids) - before[0]

    def clear(self, room_code: str) -> int:
        with self._lock:
            data = self._read()
            removed = data["rooms"].pop(room_code.upper(), None)
            self._write(data)
            if not removed:
                return 0
            return len(removed.get("steamIds") or [])
