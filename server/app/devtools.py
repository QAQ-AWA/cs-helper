"""开发辅助：造一份合成轨迹，用来在没有 CS2/5E 的情况下验证回放链路。

只在 `CS_HELPER_DEV=1` 时由 `/api/v1/dev/seed-paths` 调用，生产环境不可达。
"""

from __future__ import annotations

import json
import math
import time
from typing import Any

from . import settings

FALLBACK_TRANSFORM = {"pos_x": -3230.0, "pos_y": 1713.0, "scale": 5.0}
ROUNDS_PER_PLAYER = 6
SAMPLES = 60


def load_transform(map_name: str) -> dict[str, float]:
    path = settings.MAPS_DIR / map_name / "meta.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["transform"]
    except (OSError, KeyError, json.JSONDecodeError):
        return dict(FALLBACK_TRANSFORM)


def _to_game(transform: dict[str, float], px: float, py: float) -> tuple[float, float]:
    """雷达像素坐标 → 游戏世界坐标（renderer 的反函数）。"""

    return px * transform["scale"] + transform["pos_x"], transform["pos_y"] - py * transform["scale"]


def _path(transform: dict[str, float], start: tuple[float, float], end: tuple[float, float], bend: float) -> list[list[float]]:
    points: list[list[float]] = []
    for step in range(SAMPLES):
        ratio = step / (SAMPLES - 1)
        px = start[0] + (end[0] - start[0]) * ratio
        py = start[1] + (end[1] - start[1]) * ratio + bend * math.sin(ratio * math.pi)
        gx, gy = _to_game(transform, px, py)
        points.append([round(ratio * 20, 2), round(gx, 1), round(gy, 1)])
    return points


def build_synthetic_artifact(session: Any, players: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, bytes]]:
    transform = load_transform(session.map_name)
    radar = f"/maps/{session.map_name}/radar.png"
    parts: dict[str, bytes] = {}
    meta_players: list[dict[str, Any]] = []

    for index, player in enumerate(players):
        steam_id = str(player.get("steamId") or f"dev{index}")
        display = player.get("nickname") or player.get("username") or steam_id
        rounds: list[dict[str, Any]] = []
        for number in range(ROUNDS_PER_PLAYER):
            side = "CT" if number < ROUNDS_PER_PLAYER // 2 else "T"
            if side == "CT":
                start = (300 + index * 18, 780)
                end = (520 + index * 6, 470)
            else:
                start = (700, 240 + index * 12)
                end = (430, 540)
            rounds.append(
                {
                    "side": side,
                    "rtype": "Pistol" if number in (0, ROUNDS_PER_PLAYER // 2) else "Buy",
                    "round_id": 1000 * (index + 1) + number,
                    "path": _path(transform, start, end, bend=50 + index * 8),
                    "grenades": [],
                    "death_t": None,
                }
            )

        replay = {
            "username": display,
            "domain": player.get("domain") or f"dev{index}",
            "steamid": steam_id,
            "map": session.map_name,
            "transform": transform,
            "radar": radar,
            "combat_stats": {"kd": round(1.0 + index * 0.05, 2), "awp_rate": 20.0 + index},
            "round_count": len(rounds),
            "rounds": rounds,
        }
        body = json.dumps(
            {
                "steamId": steam_id,
                "username": display,
                "nickname": display,
                "domain": player.get("domain"),
                "replay": replay,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        parts[steam_id] = body
        meta_players.append(
            {
                "steamId": steam_id,
                "username": display,
                "nickname": display,
                "domain": player.get("domain"),
                "rounds": len(rounds),
                "bytes": len(body),
            }
        )

    bundle = {
        "sessionId": session.id,
        "map": session.map_name,
        "generatedAt": int(time.time() * 1000),
        "players": meta_players,
        "failed": [],
        "synthetic": True,
    }
    return bundle, parts
