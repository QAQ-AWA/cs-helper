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


def resolve_side(
    report: dict[str, Any], library_side: str | None = None
) -> tuple[str | None, str | None]:
    """Which roster block is ours, and how we know.

    Precedence: an explicit pick beats everything (the user just told us), then
    the ID library (we have seen these people on our side before), then the
    client's own markers. Anything ambiguous returns ``(None, None)`` so we fall
    back to analysing all ten rather than guessing wrong.
    """

    explicit = report.get("mySide")
    if explicit in ("ct", "t"):
        return explicit, "explicit"
    if report.get("analyzeAll") is True:
        # "Analyze both" must beat the library, otherwise the choice is a no-op.
        return None, "explicit-all"
    if library_side in ("ct", "t"):
        return library_side, "library"

    teams = report.get("teams") or {}
    for side in ("ct", "t"):
        if any(player.get("isSelf") for player in teams.get(side) or []):
            return side, "self"

    # A party tag is only evidence when it is unambiguous: at least two players
    # share it and none of them sit on the other side. Lobbies that hand every
    # player the same troop id must not silently pick a side.
    tagged = {
        side: [p for p in teams.get(side) or [] if p.get("partyTag")]
        for side in ("ct", "t")
    }
    sides_with_tags = [side for side, members in tagged.items() if members]
    if len(sides_with_tags) == 1 and len(tagged[sides_with_tags[0]]) >= 2:
        return sides_with_tags[0], "party"
    return None, None


def resolve_my_side(report: dict[str, Any], library_side: str | None = None) -> str | None:
    return resolve_side(report, library_side)[0]


def opponent_side(side: str | None) -> str | None:
    if side == "ct":
        return "t"
    if side == "t":
        return "ct"
    return None


def demo_targets(
    report: dict[str, Any], library_side: str | None = None
) -> list[dict[str, Any]]:
    """Players whose demos we actually need.

    With a known side this is the opposing five: half the downloads, half the
    wait, and the only side whose habits matter before the match.
    """

    players = normalise_players(report)
    my_side = resolve_my_side(report, library_side)
    if my_side is None:
        return players
    opponents = [player for player in players if player["team"] != my_side]
    # A lopsided report (only our side filled in) must not silently skip the job.
    return opponents or players


def to_engine_hints(
    report: dict[str, Any], library_side: str | None = None
) -> list[dict[str, str]] | None:
    """Build ``player_hints`` for ``pipeline.run``.

    The engine only knows how to discover 5E demos, and it needs a 5E ``domain``
    plus a SteamID64 per player. Anything incomplete is dropped so the pipeline
    falls back to its own search instead of failing the whole job.
    """

    if report.get("platform") != "5e":
        return None

    hints: list[dict[str, str]] = []
    for player in demo_targets(report, library_side):
        nickname = (player.get("nickname") or "").strip()
        domain = (player.get("platformUserId") or "").strip()
        steam_id = (player.get("steamId") or "").strip()
        if not nickname or not _DOMAIN_RE.match(domain) or not _STEAM_RE.match(steam_id):
            return None
        hints.append({"username": nickname, "domain": domain, "steamid": steam_id})
    return hints or None


def demo_job_targets(
    report: dict[str, Any], library_side: str | None = None
) -> list[str]:
    """Nicknames handed to the engine, in the same order as ``to_engine_hints``."""

    return [player["nickname"] for player in demo_targets(report, library_side)]


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
