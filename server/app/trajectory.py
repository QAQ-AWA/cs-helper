"""Opening-behaviour profile built from parsed replay paths.

The replay already stores each player's first 20 seconds of every round
(``engine/config.py``: ``WINDOW_S = 20``). That window is what decides a CS2
round — where the CTs set up, which site the T side commits to, who throws the
first smoke — so it is the right raw material for a pre-match read.

Two rules keep this honest:

* Site letters come from ``bomb_planted`` (the only ground truth we have), never
  from guessing at coordinates.
* Anchors are accumulated per map across every demo ever parsed, because a
  single demo often only plants one site. Until both anchors exist we refuse to
  name sites and report ``unknown`` instead of inventing one.
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Any, Iterable

from . import settings

log = logging.getLogger("cs-helper.trajectory")

# CTs are in position by now on every active-duty map. The T side is not: on
# Mirage plants land at 30-40s, well past the 20s capture window, so T commits
# come from ``bomb_planted`` rather than from a position snapshot.
SETUP_T = 8.0
# Roughly the radius of a bombsite: a player inside it counts as "on site".
SITE_RADIUS = 600.0
# How many samples per site we keep for the anchor median.
ANCHOR_SAMPLES = 240


def anchor_path() -> Path:
    return settings.DATA_DIR / "anchors.json"


def load_anchor_samples() -> dict[str, dict[str, list[list[float]]]]:
    path = anchor_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_anchor_samples(data: dict[str, dict[str, list[list[float]]]]) -> None:
    path = anchor_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:  # anchors are an optimisation, never a hard failure
        log.warning("could not persist map anchors: %s", exc)


def _medians(samples: dict[str, list[list[float]]]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for site, points in samples.items():
        if not points:
            continue
        out[site] = [
            round(statistics.median(point[0] for point in points), 1),
            round(statistics.median(point[1] for point in points), 1),
        ]
    return out


def merge_anchors(
    map_name: str, plants: Iterable[dict[str, Any]]
) -> dict[str, list[float]]:
    """Fold this demo's plants into the per-map anchor history, return medians."""

    store = load_anchor_samples()
    per_map = store.setdefault(map_name, {})
    added = False
    for plant in plants:
        site = plant.get("site")
        if site not in {"A", "B"} or plant.get("x") is None or plant.get("y") is None:
            continue
        bucket = per_map.setdefault(site, [])
        bucket.append([float(plant["x"]), float(plant["y"])])
        if len(bucket) > ANCHOR_SAMPLES:
            del bucket[: len(bucket) - ANCHOR_SAMPLES]
        added = True
    if added:
        save_anchor_samples(store)
    return _medians(per_map)


def sample_at(path: list[list[float]], moment: float) -> tuple[float, float] | None:
    """Position at ``moment`` seconds, linearly interpolated between samples."""

    if not path:
        return None
    if moment <= path[0][0]:
        return float(path[0][1]), float(path[0][2])
    for index in range(1, len(path)):
        previous, current = path[index - 1], path[index]
        if current[0] >= moment:
            span = current[0] - previous[0]
            ratio = 0.0 if span <= 0 else (moment - previous[0]) / span
            return (
                previous[1] + (current[1] - previous[1]) * ratio,
                previous[2] + (current[2] - previous[2]) * ratio,
            )
    return float(path[-1][1]), float(path[-1][2])


def zone_of(
    position: tuple[float, float] | None, anchors: dict[str, list[float]]
) -> str:
    """Nearest site inside the radius, else ``other``; ``unknown`` without anchors."""

    if position is None:
        return "unknown"
    if not anchors:
        return "unknown"
    best_site, best_distance = None, None
    for site, (ax, ay) in anchors.items():
        distance = ((position[0] - ax) ** 2 + (position[1] - ay) ** 2) ** 0.5
        if best_distance is None or distance < best_distance:
            best_site, best_distance = site, distance
    if best_distance is None or best_distance > SITE_RADIUS:
        return "other"
    return best_site or "unknown"


def _tally(zones: Iterable[str], fallback: str) -> dict[str, int]:
    """Count A/B, plus a bucket for anything that is not a site."""

    counts = {"A": 0, "B": 0, fallback: 0, "unknown": 0}
    for zone in zones:
        if zone in {"A", "B"}:
            counts[zone] += 1
        elif zone == "unknown":
            counts["unknown"] += 1
        else:
            counts[fallback] += 1
    return {key: value for key, value in counts.items() if value}


def _player_profile(player: dict[str, Any], anchors: dict[str, list[float]]) -> dict[str, Any]:
    replay = player.get("replay") or {}
    rounds = [item for item in replay.get("rounds") or [] if item.get("path")]
    ct_zones: list[str] = []
    planted: list[str] = []
    plant_times: list[float] = []
    t_rounds = 0
    early_utility: dict[str, int] = {}
    opening_deaths = 0

    for item in rounds:
        side = item.get("side")
        path = item["path"]
        if side == "CT":
            # CTs are in position by 8s, so the snapshot is meaningful.
            ct_zones.append(zone_of(sample_at(path, SETUP_T), anchors))
        elif side == "T":
            t_rounds += 1
            plant = item.get("plant") or {}
            site = plant.get("site")
            # A 20s window cannot see a Mirage execute (plants land at 30-40s),
            # so the plant is the only honest source for "where did they go".
            if site in {"A", "B"}:
                planted.append(site)
                if isinstance(plant.get("t"), (int, float)):
                    plant_times.append(float(plant["t"]))
        death = item.get("death_t")
        if isinstance(death, (int, float)) and death <= 25:
            opening_deaths += 1
        for nade in item.get("grenades") or []:
            if (nade.get("throw_t") or 99) <= 12:
                kind = nade.get("type") or "unknown"
                early_utility[kind] = early_utility.get(kind, 0) + 1

    return {
        "steamId": str(player.get("steamId") or ""),
        "name": player.get("nickname") or player.get("username") or "Unknown",
        "rounds": len(rounds),
        "ct": {"rounds": len(ct_zones), "setup": _tally(ct_zones, "offsite")},
        "t": {
            "rounds": t_rounds,
            "planted": _tally(planted, "unknown"),
            # Rounds where the T side died before planting — not a site choice.
            "noPlant": t_rounds - len(planted),
            "avgPlantT": round(statistics.mean(plant_times), 1) if plant_times else None,
        },
        "openingDeaths": opening_deaths,
        "earlyUtility": early_utility,
    }


def build_profile(
    map_name: str, players: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Everything the model needs to talk about the opponents' opening habits."""

    players = list(players)
    plants: list[dict[str, Any]] = []
    for player in players:
        for item in (player.get("replay") or {}).get("rounds") or []:
            plant = item.get("plant")
            if plant:
                plants.append(plant)

    anchors = merge_anchors(map_name, plants)
    profiles = [_player_profile(player, anchors) for player in players]
    profiles = [item for item in profiles if item["rounds"]]
    total_rounds = sum(item["rounds"] for item in profiles)

    # 同一个下包会出现在每个被解析选手的回合里，横向相加会重复计数；
    # 队伍级的次数必须按 round_id 去重后再统计。
    team_plants: dict[int, dict[str, Any]] = {}
    for player in players:
        for item in (player.get("replay") or {}).get("rounds") or []:
            plant = item.get("plant") or {}
            round_id = item.get("round_id")
            if plant.get("site") in {"A", "B"} and round_id is not None:
                team_plants.setdefault(int(round_id), plant)

    sites = [plant.get("site") for plant in team_plants.values()]
    times = [
        float(plant["t"])
        for plant in team_plants.values()
        if isinstance(plant.get("t"), (int, float))
    ]

    return {
        "map": map_name,
        "rounds": total_rounds,
        "teamPlants": {
            "rounds": len(team_plants),
            "A": sites.count("A"),
            "B": sites.count("B"),
            "avgT": round(statistics.mean(times), 1) if times else None,
        },
        "players": profiles,
        "siteAnchors": anchors or None,
        "siteKnown": sorted(anchors) if anchors else [],
        "windowSeconds": 20,
    }
