"""v3 结构化结果：模型输出不可控，兜底逻辑必须可测。"""

import json

from app.analysis_result import parse_analysis_result, render_markdown

ALLOWED = {
    "76561198000000002": ("Alpha", "A"),
    "76561198000000003": ("Bravo", "B"),
}


def _payload(**overrides):
    base = {
        "schemaVersion": 3,
        "predictedWinner": "A",
        "modelWinProbability": {"A": 62, "B": 38},
        "confidence": 71,
        "headline": "A 队更被看好",
        "decisiveFactors": [
            {
                "dimension": "strength",
                "advantage": "A",
                "impact": 3,
                "title": "整体更强",
                "summary": "Alpha 的 Rating 1.18 高于 Bravo 的 0.95",
            }
        ],
        "playerSignals": [
            {
                "steamId": "76561198000000002",
                "side": "A",
                "kind": "carry",
                "impact": 2,
                "title": "强点",
                "summary": "Rating 1.18 全场最高",
            }
        ],
        "teamPlans": {
            "A": {"winConditions": [{"text": "先控中路"}], "risks": []},
            "B": {"winConditions": [], "risks": [{"text": "枪法吃亏"}]},
        },
        "uncertainties": ["Bravo 只打了 3 场"],
    }
    base.update(overrides)
    return base


def test_parses_a_clean_payload():
    result = parse_analysis_result(json.dumps(_payload(), ensure_ascii=False), allowed_players=ALLOWED)

    assert result is not None
    assert result["schemaVersion"] == 3
    assert result["predictedWinner"] == "A"
    assert result["modelWinProbability"] == {"A": 62.0, "B": 38.0}
    assert result["winProbability"] == {"A": 62.0, "B": 38.0}
    assert result["decisiveFactors"][0]["evidence"] == []
    assert result["playerSignals"][0]["nickname"] == "Alpha"
    assert result["teamPlans"]["A"]["winConditions"][0]["text"] == "先控中路"


def test_strips_code_fences_and_surrounding_prose():
    raw = "好的，分析如下：\n```json\n" + json.dumps(_payload(), ensure_ascii=False) + "\n```\n希望有帮助。"
    result = parse_analysis_result(raw, allowed_players=ALLOWED)

    assert result is not None
    assert result["headline"] == "A 队更被看好"


def test_returns_none_for_garbage():
    assert parse_analysis_result("完全不是 JSON", allowed_players=ALLOWED) is None
    assert parse_analysis_result("", allowed_players=ALLOWED) is None


def test_drops_signals_for_unknown_players():
    payload = _payload(
        playerSignals=[
            {"steamId": "999", "side": "A", "kind": "carry", "title": "编造的", "summary": "x"},
            {"steamId": "76561198000000003", "side": "B", "kind": "weakLink", "title": "短板", "summary": "K/D 0.88"},
        ]
    )
    result = parse_analysis_result(json.dumps(payload, ensure_ascii=False), allowed_players=ALLOWED)

    assert result is not None
    assert [signal["nickname"] for signal in result["playerSignals"]] == ["Bravo"]


def test_caps_two_signals_per_side():
    payload = _payload(
        playerSignals=[
            {"steamId": "76561198000000002", "kind": "carry", "title": "a", "summary": "1"},
            {"steamId": "76561198000000002", "kind": "anchor", "title": "b", "summary": "2"},
            {"steamId": "76561198000000002", "kind": "specialist", "title": "c", "summary": "3"},
        ]
    )
    result = parse_analysis_result(json.dumps(payload, ensure_ascii=False), allowed_players=ALLOWED)

    assert result is not None
    assert len(result["playerSignals"]) == 2


def test_normalises_probabilities_and_clamps_confidence():
    payload = _payload(modelWinProbability={"A": 70, "B": 60}, confidence=180)
    result = parse_analysis_result(json.dumps(payload, ensure_ascii=False), allowed_players=ALLOWED)

    assert result is not None
    assert result["modelWinProbability"]["A"] + result["modelWinProbability"]["B"] == 100
    assert result["confidence"] == 100


def test_fills_defaults_when_fields_are_missing():
    result = parse_analysis_result(json.dumps({"modelWinProbability": {"A": 40, "B": 60}}), allowed_players=ALLOWED)

    assert result is not None
    assert result["predictedWinner"] == "B"
    assert result["headline"]
    assert result["decisiveFactors"] == []
    assert result["playerSignals"] == []
    assert result["teamPlans"]["A"]["risks"] == []


def test_render_markdown_keeps_the_four_sections():
    result = parse_analysis_result(json.dumps(_payload(), ensure_ascii=False), allowed_players=ALLOWED)
    text = render_markdown(result)

    assert text.startswith("## 结论")
    assert "## 决定本局的因素" in text
    assert "## 玩家信号" in text
    assert "## 双方取胜路径" in text
    assert "## 数据缺口" in text
    assert "先控中路" in text
