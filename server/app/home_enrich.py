"""Enrich the roster with 5E season data (`player/home`).

The desktop already fetches this for its own panels, but the relay cannot rely
on it: a report may arrive from an older client, or from a PC whose signature
already expired. Doing it server-side makes the AI evidence complete no matter
which client reported.

Failure is always soft. The signature key is embedded in 5E's own frontend and
rotates whenever they rebuild it, so a 401 is an expected state, not a bug: we
record a human-readable reason, keep the match usable, and let the phone show a
one-line notice.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger("cs-helper.home")

SIGNATURE_HINT = (
    "5E 签名已失效，赛季数据（ADR/RWS/KAST）这次没拿到，仅用本场数据。"
    "需要更新 5E 的签名密钥后才能恢复。"
)


@dataclass
class HomeOutcome:
    seasons: dict[str, dict[str, Any]] = field(default_factory=dict)
    failed: list[dict[str, str]] = field(default_factory=list)
    signature_failed: bool = False
    error: str | None = None


class HomeClient(Protocol):
    def fetch(self, players: list[dict[str, Any]]) -> HomeOutcome: ...


class SubprocessHomeClient:
    """Runs ``engine/home_runner.py``; a crash or hang cannot hurt the relay."""

    def __init__(
        self,
        engine_dir: Path | str | None = None,
        *,
        timeout: int = 90,
        python: str | None = None,
    ) -> None:
        self.engine_dir = Path(engine_dir) if engine_dir else None
        self.timeout = timeout
        self.python = python or sys.executable

    def fetch(self, players: list[dict[str, Any]]) -> HomeOutcome:
        targets = [
            {"domain": str(p.get("platformUserId") or "").strip(), "nickname": p.get("nickname")}
            for p in players
            if str(p.get("platformUserId") or "").strip()
        ]
        if not targets:
            return HomeOutcome()

        engine_dir = self.engine_dir
        if engine_dir is None:
            from . import settings

            engine_dir = settings.ENGINE_DIR

        env = dict(os.environ)
        env["PYTHONPATH"] = str(engine_dir)
        try:
            completed = subprocess.run(
                [self.python, str(Path(engine_dir) / "home_runner.py")],
                input=json.dumps({"players": targets}, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(engine_dir),
                env=env,
            )
        except subprocess.TimeoutExpired:
            return HomeOutcome(error="player/home 拉取超时")
        except OSError as exc:
            return HomeOutcome(error=f"player/home 启动失败: {exc}")

        outcome = HomeOutcome()
        for line in (completed.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "player" and isinstance(event.get("season"), dict):
                outcome.seasons[str(event.get("domain"))] = event["season"]
            elif event.get("type") == "done":
                outcome.failed = event.get("failed") or []
                outcome.signature_failed = bool(event.get("signatureFailed"))
            elif event.get("type") == "error":
                outcome.error = str(event.get("message") or "player/home 失败")[:200]

        if outcome.error is None and not outcome.seasons and completed.returncode != 0:
            tail = (completed.stderr or "").strip().splitlines()[-2:]
            outcome.error = "player/home 无有效数据" + (": " + " / ".join(tail) if tail else "")
        if outcome.signature_failed:
            outcome.error = SIGNATURE_HINT
        return outcome


def merge_season_stats(profiles: list[dict[str, Any]], seasons: dict[str, dict[str, Any]]) -> int:
    """Attach season numbers to each player's ``stats``.

    Only fills gaps: a value the client already reported is never overwritten,
    because the client had the same source and may be fresher. Season-only
    fields are namespaced so the evidence pack can tell them apart.
    """

    merged = 0
    for player in profiles:
        season = seasons.get(str(player.get("platformUserId") or ""))
        if not season:
            continue
        stats = player.get("stats")
        if not isinstance(stats, dict):
            stats = {}
            player["stats"] = stats

        mapping = {
            "seasonAdr": season.get("adr"),
            "seasonRws": season.get("rws"),
            "seasonKast": season.get("kast"),
            "seasonRating": season.get("rating"),
            "seasonImpact": season.get("impact"),
        }
        for key, value in mapping.items():
            if value is not None:
                stats[key] = value

        if not stats.get("matchesPlayed") and season.get("matches"):
            stats["matchesPlayed"] = int(season["matches"])
        if stats.get("rating") in (None, 0, 1) and season.get("avgRating"):
            # 1 is the desktop's "unknown" placeholder, not a real rating.
            stats["rating"] = season["avgRating"]
        if not stats.get("kd") and season.get("kd"):
            stats["kd"] = season["kd"]
        if not stats.get("headshotRate") and season.get("headshot"):
            stats["headshotRate"] = season["headshot"]
        if not stats.get("winRate") and season.get("winRate"):
            stats["winRate"] = season["winRate"]
        merged += 1
    return merged
