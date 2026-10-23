"""Turn a match report into a compact, self-describing evidence pack.

Adapted from the desktop project's ``analysis-v3``: the model is never asked to
eyeball raw numbers. Direction (better/worse) is computed locally against the
lobby median, sample size decides how much a number may be trusted, and the
prompt forbids quoting anything that is not in the pack.

Why bother: a bare table of ten Ratings invites the model to invent ADR, RWS
and clutch stats it was never given. Marking what is missing, and pre-computing
who is above or below the lobby, keeps the output anchored to real data.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable

# Per-map character. Helps the model weight map-specific traits instead of
# giving generic advice; ported from the desktop project's MAP_FIT_HINTS.
MAP_FIT_HINTS: dict[str, str] = {
    "de_dust2": "长枪线、中路/A 大控制、狙击与首杀权重高",
    "de_mirage": "中路控图、道具协同、默认战术执行",
    "de_inferno": "香蕉道道具、近点交火、补枪与残局",
    "de_nuke": "垂直协同、外场控制、道具与残局",
    "de_ancient": "中路争夺、道具压制、信息战",
    "de_vertigo": "近距离交火、首杀与补枪",
    "de_overpass": "道具、信息、长枪与狙击",
    "de_anubis": "水道与中路控制、道具交换、转点速度",
    "de_train": "长枪线、道具封锁、狙击点位",
}

# Metrics the client can actually supply, with the tolerance below which a
# difference is noise rather than signal.
METRIC_SPECS: dict[str, dict[str, Any]] = {
    "rating": {"label": "Rating", "tolerance": 0.03, "digits": 2},
    "kd": {"label": "K/D", "tolerance": 0.03, "digits": 2},
    "headshotRate": {"label": "爆头率", "tolerance": 2.0, "digits": 1},
    "winRate": {"label": "胜率", "tolerance": 2.0, "digits": 1},
}

# Reference points for "is this number good", independent of the lobby.
BASELINES = (
    "Rating 1.00 为分界，>=1.10 偏强，<0.95 偏弱；"
    "K/D 1.00 为分界，>=1.15 稳定正贡献，<0.90 偏弱；"
    "爆头率 45-55% 属正常区间；"
    "胜率 50% 为分界，样本少于 30 场时波动极大"
)

RELIABILITY_BANDS = ((30, "high"), (10, "medium"), (0, "low"))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def reliability_for(matches: Any) -> str:
    count = _num(matches)
    if count is None:
        return "unknown"
    for floor, label in RELIABILITY_BANDS:
        if count >= floor:
            return label
    return "low"


def direction_for(value: float | None, reference: float | None, tolerance: float) -> str:
    """``positive`` / ``negative`` / ``neutral`` — never left to the model."""

    if value is None or reference is None:
        return "unknown"
    delta = value - reference
    if abs(delta) <= tolerance:
        return "neutral"
    return "positive" if delta > 0 else "negative"


def _median(values: Iterable[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return median(clean) if clean else None


def _players(report: dict[str, Any], profiles: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if profiles:
        return profiles
    from .adapters import normalise_players

    return normalise_players(report)


def build_evidence(
    map_name: str,
    players: list[dict[str, Any]],
    my_side: str | None = None,
) -> dict[str, Any]:
    """The exact payload the model sees, minus the prose rules."""

    opponent = "t" if my_side == "ct" else "ct" if my_side == "t" else None

    def role_for(side: str) -> str:
        if my_side is None:
            return f"{side.upper()} 方"
        return "我方" if side == my_side else "对方"

    rows: list[dict[str, Any]] = []
    for index, player in enumerate(players, start=1):
        stats = player.get("stats") or {}
        rows.append(
            {
                "id": f"p{index}",
                "name": player.get("nickname") or "Unknown",
                "side": player.get("team") or "",
                "role": role_for(player.get("team") or ""),
                "matches": _num(stats.get("matchesPlayed")),
                "rank": stats.get("rankLevel"),
                "reliability": reliability_for(stats.get("matchesPlayed")),
                "_raw": {key: _num(stats.get(key)) for key in METRIC_SPECS},
            }
        )

    lobby = {key: _median(row["_raw"][key] for row in rows) for key in METRIC_SPECS}

    for row in rows:
        metrics: dict[str, Any] = {}
        for key, spec in METRIC_SPECS.items():
            value = row["_raw"][key]
            metrics[key] = {
                "value": _round(value, spec["digits"]),
                "direction": direction_for(value, lobby[key], spec["tolerance"]),
            }
        row["metrics"] = metrics
        del row["_raw"]

    teams: list[dict[str, Any]] = []
    for side in ("ct", "t"):
        members = [row for row in rows if row["side"] == side]
        if not members:
            continue
        teams.append(
            {
                "side": side,
                "role": role_for(side),
                "size": len(members),
                "avg": {
                    key: _round(
                        _median(member["metrics"][key]["value"] for member in members),
                        METRIC_SPECS[key]["digits"],
                    )
                    for key in METRIC_SPECS
                },
                "lowSample": [m["name"] for m in members if m["reliability"] in {"low", "unknown"}],
            }
        )

    missing = [spec["label"] for key, spec in METRIC_SPECS.items() if lobby[key] is None]
    low_sample = [row["name"] for row in rows if row["reliability"] in {"low", "unknown"}]

    return {
        "match": {
            "map": map_name,
            "mapFit": MAP_FIT_HINTS.get(map_name, "通用地图，无额外倾向"),
            "mySide": my_side,
            "opponentSide": opponent,
            "perspective": "我方/对方" if my_side else "未指定，按 CT/T 表述",
        },
        "dataQuality": {
            "source": "队友电脑端读取的平台公开赛季数据（非 demo 解析）",
            "available": [spec["label"] for key, spec in METRIC_SPECS.items() if lobby[key] is not None],
            "missing": missing or None,
            "lowSamplePlayers": low_sample or None,
            "note": "direction 已按全场中位数本地计算，正负可直接采信，不要重算",
        },
        "baselines": BASELINES,
        "teams": teams,
        "players": rows,
    }
