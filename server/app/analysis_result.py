"""v3 结构化分析结果的解析与兜底。

客户端那套 prompt / 证据 / 校准已经删掉，但历史文档和界面仍按 v3 渲染。
现在由服务端直接产出这个结构：模型只负责判断，编号、截断、数值夹紧、枚举纠偏
都在这里做——少一个字段就让整页空白的代价太高。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger("cs-helper.analysis")

SCHEMA_VERSION = 3

DIMENSIONS = {"strength", "aim", "opening", "utility", "clutch", "map", "form", "party"}
SIGNAL_KINDS = {"carry", "anchor", "specialist", "weakLink", "volatile", "watch"}
SIDES = {"A", "B"}

MAX_FACTORS = 4
MAX_SIGNALS = 4
MAX_SIGNALS_PER_SIDE = 2
MAX_UNCERTAINTIES = 4
MAX_PLAN_ITEMS = 2

# 展示用的硬上限（汉字数）。模型偶尔会写长句，超了直接截断而不是整条丢弃。
HEADLINE_CHARS = 48
TITLE_CHARS = 18
SUMMARY_CHARS = 80
CLAIM_CHARS = 60
UNCERTAINTY_CHARS = 60

_FENCE = re.compile(r"```(?:json)?|```", re.IGNORECASE)


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _impact(value: Any) -> int:
    number = _number(value, 2)
    if number is None:
        return 2
    return max(1, min(3, int(round(number))))


def _side(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in SIDES else None


def _probability(raw: Any) -> dict[str, float]:
    block = raw if isinstance(raw, dict) else {}
    left = _number(block.get("A"), 50.0) or 0.0
    right = _number(block.get("B"), 50.0) or 0.0
    left = max(0.0, min(100.0, left))
    right = max(0.0, min(100.0, right))
    total = left + right
    if total <= 0:
        return {"A": 50.0, "B": 50.0}
    return {"A": round(left * 100 / total, 1), "B": round(right * 100 / total, 1)}


def _claims(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw[:MAX_PLAN_ITEMS]:
        text = item.get("text") if isinstance(item, dict) else item
        cleaned = _clean_text(text, CLAIM_CHARS)
        if cleaned:
            out.append({"text": cleaned, "evidence": []})
    return out


def _load_json(raw: str) -> dict[str, Any] | None:
    text = _FENCE.sub("", raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def parse_analysis_result(
    raw: str,
    *,
    allowed_players: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Turn the model's JSON into the exact shape the UI expects.

    ``allowed_players`` maps SteamID -> (nickname, side). Signals pointing at
    anyone else are dropped: a hallucinated player card is worse than none.
    """

    payload = _load_json(raw)
    if payload is None:
        return None

    allowed = allowed_players or {}
    model_probability = _probability(payload.get("modelWinProbability") or payload.get("winProbability"))
    winner = str(payload.get("predictedWinner") or "").strip()
    if winner not in {"A", "B", "Even", "Unknown"}:
        winner = "A" if model_probability["A"] > model_probability["B"] else "B"
        if abs(model_probability["A"] - model_probability["B"]) < 3:
            winner = "Even"

    factors: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("decisiveFactors") or []):
        if not isinstance(item, dict) or len(factors) >= MAX_FACTORS:
            continue
        title = _clean_text(item.get("title"), TITLE_CHARS)
        summary = _clean_text(item.get("summary"), SUMMARY_CHARS)
        if not title and not summary:
            continue
        dimension = str(item.get("dimension") or "").strip()
        advantage = _side(item.get("advantage")) or "Even"
        factors.append(
            {
                "id": str(item.get("id") or f"f{index + 1}")[:24],
                "dimension": dimension if dimension in DIMENSIONS else "strength",
                "advantage": advantage,
                "impact": _impact(item.get("impact")),
                "title": title or summary[:TITLE_CHARS],
                "summary": summary,
                "evidence": [],
            }
        )

    signals: list[dict[str, Any]] = []
    per_side = {"A": 0, "B": 0}
    for item in payload.get("playerSignals") or []:
        if not isinstance(item, dict) or len(signals) >= MAX_SIGNALS:
            continue
        steam_id = str(item.get("steamId") or "").strip()
        nickname, side = allowed.get(steam_id, ("", ""))
        if not side:
            # 允许模型只给昵称：按昵称反查一次，查不到就丢。
            wanted = str(item.get("nickname") or "").strip()
            match = next(
                ((sid, meta) for sid, meta in allowed.items() if meta[0] == wanted),
                None,
            )
            if match is None:
                continue
            steam_id, (nickname, side) = match[0], match[1]
        if per_side[side] >= MAX_SIGNALS_PER_SIDE:
            continue
        title = _clean_text(item.get("title"), TITLE_CHARS)
        summary = _clean_text(item.get("summary"), SUMMARY_CHARS)
        if not title and not summary:
            continue
        kind = str(item.get("kind") or "").strip()
        per_side[side] += 1
        signals.append(
            {
                "steamId": steam_id,
                "nickname": nickname,
                "side": side,
                "kind": kind if kind in SIGNAL_KINDS else "watch",
                "impact": _impact(item.get("impact")),
                "title": title or summary[:TITLE_CHARS],
                "summary": summary,
                "evidence": [],
                "source": "model",
            }
        )

    plans_raw = payload.get("teamPlans") if isinstance(payload.get("teamPlans"), dict) else {}
    plans = {
        side: {
            "winConditions": _claims((plans_raw.get(side) or {}).get("winConditions")),
            "risks": _claims((plans_raw.get(side) or {}).get("risks")),
        }
        for side in ("A", "B")
    }

    uncertainties = [
        text
        for text in (
            _clean_text(item, UNCERTAINTY_CHARS)
            for item in (payload.get("uncertainties") or [])[:MAX_UNCERTAINTIES]
        )
        if text
    ]

    headline = _clean_text(payload.get("headline"), HEADLINE_CHARS)
    if not headline:
        leader = "A" if model_probability["A"] >= model_probability["B"] else "B"
        headline = f"{leader} 队更被看好（{model_probability['A']:.0f}% 对 {model_probability['B']:.0f}%）"

    confidence = _number(payload.get("confidence"), 50.0) or 0.0
    coverage = _number(payload.get("dataCoverage"), 0.0) or 0.0
    if coverage > 1:
        coverage = coverage / 100

    return {
        "schemaVersion": SCHEMA_VERSION,
        "predictedWinner": winner,
        "modelWinProbability": model_probability,
        "winProbability": dict(model_probability),
        "confidence": int(max(0, min(100, round(confidence)))),
        "dataCoverage": round(max(0.0, min(1.0, coverage)), 2),
        "headline": headline,
        "decisiveFactors": factors,
        "playerSignals": signals,
        "teamPlans": plans,
        "uncertainties": uncertainties,
        "dataQuality": _clean_text(payload.get("dataQuality"), SUMMARY_CHARS),
    }


def render_markdown(result: dict[str, Any]) -> str:
    """手机端用的纯文本版：同一份结构，不额外调一次模型。"""

    probability = result.get("modelWinProbability") or {}
    lines = [
        "## 结论",
        f"{result.get('headline') or ''}（A {probability.get('A', 50):.0f}% / B {probability.get('B', 50):.0f}%，"
        f"可信度 {result.get('confidence', 0)}）",
    ]

    factors = result.get("decisiveFactors") or []
    if factors:
        lines += ["", "## 决定本局的因素"]
        for factor in factors:
            lines.append(f"- {factor['title']}：{factor['summary']}")

    signals = result.get("playerSignals") or []
    if signals:
        lines += ["", "## 玩家信号"]
        for signal in signals:
            lines.append(f"- {signal['nickname']}（{signal['side']}）：{signal['title']} — {signal['summary']}")

    plans = result.get("teamPlans") or {}
    if plans:
        lines += ["", "## 双方取胜路径"]
        for side in ("A", "B"):
            plan = plans.get(side) or {}
            wins = "；".join(item["text"] for item in plan.get("winConditions") or [])
            risks = "；".join(item["text"] for item in plan.get("risks") or [])
            if wins or risks:
                lines.append(f"- {side} 队：取胜条件 {wins or '—'}；隐患 {risks or '—'}")

    uncertainties = result.get("uncertainties") or []
    if uncertainties:
        lines += ["", "## 数据缺口"]
        lines += [f"- {item}" for item in uncertainties]

    return "\n".join(lines)
