"""开发辅助：造一份合成轨迹，用来在没有 CS2/5E 的情况下验证回放链路。

只在 `CS_HELPER_DEV=1` 时由 `/api/v1/dev/seed-paths` 调用，生产环境不可达。
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
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


def list_local_demos() -> tuple[Path, list[dict[str, Any]]]:
    """Inventory the dev-only demo folder."""

    root = Path(settings.LOCAL_DEMO_DIR).resolve()
    if not settings.LOCAL_DEMO_DIR or not root.is_dir():
        raise FileNotFoundError("CS_HELPER_LOCAL_DEMO_DIR 未配置或不存在")
    items = []
    for entry in sorted(root.glob("*.dem")):
        items.append({"name": entry.name, "bytes": entry.stat().st_size})
    return root, items


def resolve_local_demo(name: str) -> Path:
    """Resolve a demo name inside the configured folder, rejecting escapes."""

    root, _ = list_local_demos()
    candidate = (root / Path(name).name).resolve()
    if candidate.parent != root or candidate.suffix.lower() != ".dem":
        raise FileNotFoundError(name)
    if not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate


def parse_local_demo(demo_path, players, output_dir) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Run ``engine/parse_local.py`` and convert its output into an artifact.

    Mirrors what ``jobs._demo_work`` produces, minus the 5E search/download.
    Returns ``(bundle, parts)`` ready for ``ArtifactStore.put``.
    """

    import os
    import subprocess
    import sys

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "demoPath": str(demo_path),
        "outputDir": str(output_dir),
        "players": players,
    }
    env = dict(os.environ)
    env["PYTHONPATH"] = str(settings.ENGINE_DIR)
    completed = subprocess.run(
        [sys.executable, str(Path(settings.ENGINE_DIR) / "parse_local.py")],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(settings.ENGINE_DIR),
        env=env,
    )
    results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    map_name = ""
    for line in (completed.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "player":
            results.append(event)
        elif event.get("type") == "done":
            results = event.get("results") or results
            failed = event.get("failed") or []
            map_name = event.get("map") or ""
        elif event.get("type") == "error":
            raise RuntimeError(event.get("message") or "解析失败")

    if not results:
        tail = (completed.stderr or "").strip().splitlines()[-3:]
        raise RuntimeError("没有解析出任何回放" + (": " + " / ".join(tail) if tail else ""))

    parts: dict[str, bytes] = {}
    meta_players: list[dict[str, Any]] = []
    for item in results:
        steam_id = str(item.get("steamid") or "")
        if not steam_id:
            continue
        payload_path = output_dir / Path(str(item.get("player_json") or "")).name
        replay = json.loads(payload_path.read_text(encoding="utf-8"))
        body = json.dumps(
            {
                "steamId": steam_id,
                "username": item.get("username"),
                "nickname": item.get("username"),
                "domain": item.get("domain") or "local",
                "replay": replay,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        parts[steam_id] = body
        meta_players.append(
            {
                "steamId": steam_id,
                "username": item.get("username"),
                "nickname": item.get("username"),
                "domain": item.get("domain") or "local",
                "rounds": item.get("rounds", 0),
                "bytes": item.get("bytes", len(body)),
            }
        )

    bundle = {
        "map": map_name,
        "generatedAt": int(time.time() * 1000),
        "players": meta_players,
        "failed": failed,
        "synthetic": False,
        "source": "local-demo",
    }
    return bundle, parts
