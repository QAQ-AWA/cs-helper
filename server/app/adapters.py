"""Translations between the desktop client's model and the parser engine."""

from __future__ import annotations

import re
from typing import Any

_DOMAIN_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_STEAM_RE = re.compile(r"765\d{14}\Z")


def normalise_players(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ``teams.ct/t`` into one list carrying an explicit team label."""

    teams = report.get("teams") or {}
    players: list[dict[str, Any]] = []
    for side in ("ct", "t"):
        for player in teams.get(side) or []:
            if not isinstance(player, dict):
                continue
            players.append(
                {
                    "steamId": player.get("steamId") or "",
                    "platformUserId": player.get("platformUserId") or "",
                    "nickname": player.get("nickname") or "Unknown",
                    "avatarUrl": player.get("avatarUrl"),
                    "isSelf": bool(player.get("isSelf")),
                    "partyTag": player.get("partyTag"),
                    "team": side,
                    "stats": player.get("stats"),
                }
            )
    return players


def build_profile_payload(session_id: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": session_id,
        "source": "client",
        "mapName": report.get("mapName"),
        "players": normalise_players(report),
    }


def to_engine_hints(report: dict[str, Any]) -> list[dict[str, str]] | None:
    """Build ``player_hints`` for ``pipeline.run``.

    The engine only knows how to discover 5E demos, and it needs a 5E ``domain``
    plus a SteamID64 per player. Anything incomplete is dropped so the pipeline
    falls back to its own search instead of failing the whole job.
    """

    if report.get("platform") != "5e":
        return None

    hints: list[dict[str, str]] = []
    for player in normalise_players(report):
        nickname = (player.get("nickname") or "").strip()
        domain = (player.get("platformUserId") or "").strip()
        steam_id = (player.get("steamId") or "").strip()
        if not nickname or not _DOMAIN_RE.match(domain) or not _STEAM_RE.match(steam_id):
            return None
        hints.append({"username": nickname, "domain": domain, "steamid": steam_id})
    return hints or None


def demo_job_targets(report: dict[str, Any]) -> list[str]:
    """Nicknames handed to the engine, in the same order as ``to_engine_hints``."""

    return [player["nickname"] for player in normalise_players(report)]


def nickname_index(report: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Map steamId and 5E domain back to the display nickname.

    The engine reports whatever ``username`` it was given, which is empty for
    synthesized or partially-matched jobs. The artifact index must still be
    readable on the phone, so we re-attach the nickname from the roster here.
    """

    by_steam: dict[str, str] = {}
    by_domain: dict[str, str] = {}
    for player in normalise_players(report):
        nickname = (player.get("nickname") or "").strip()
        if not nickname:
            continue
        steam_id = (player.get("steamId") or "").strip()
        domain = (player.get("platformUserId") or "").strip()
        if steam_id:
            by_steam.setdefault(steam_id, nickname)
        if domain:
            by_domain.setdefault(domain, nickname)
    return by_steam, by_domain
