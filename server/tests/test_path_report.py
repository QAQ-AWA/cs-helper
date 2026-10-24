"""走位解读的结构化解析：模型输出必须被收成稳定结构，名字要能对上名单。"""

import json

from app.path_report import build_prompt, parse_report

PROFILE = {
    "map": "de_dust2",
    "rounds": 19,
    "teamPlants": {"rounds": 12, "A": 8, "B": 4, "avgT": 53.0},
    "teamApproach": {"rounds": 15, "A": 10, "B": 5, "even": 0},
    "players": [
        {"steamId": "111", "name": "阿甲", "rounds": 12, "t": {"rounds": 8}},
        {"steamId": "222", "name": "阿乙", "rounds": 7, "t": {"rounds": 3}},
    ],
    "siteKnown": ["A", "B"],
}

ALLOWED = {"阿甲": ("111", "T"), "阿乙": ("222", "T")}

VALID = {
    "summary": "对面偏 A，节奏偏慢",
    "tempo": "偏慢，平均 53 秒",
    "sitePreference": "A 67% / B 33%",
    "players": [
        {
            "nickname": "阿甲",
            "side": "T",
            "habit": "T 8 回合里 6 次压 A",
            "likely": "开局 20 秒大概率在 A 大",
            "counter": "A 大第一身位架枪",
        },
        {
            "nickname": "查无此人",
            "habit": "编的",
        },
    ],
    "counters": ["A 大双架", "B 通道给火", "20 秒后补烟", "第四条会被截断"],
}


def test_prompt_carries_the_profile_and_side():
    prompt = build_prompt(PROFILE, "ct")
    assert "de_dust2" in prompt
    assert "阿甲" in prompt
    assert "我方是 CT" in prompt


def test_parse_keeps_only_known_players_and_attaches_steamid():
    report = parse_report(json.dumps(VALID, ensure_ascii=False), allowed_players=ALLOWED)
    assert report["summary"] == "对面偏 A，节奏偏慢"
    assert [p["nickname"] for p in report["players"]] == ["阿甲"]
    assert report["players"][0]["steamId"] == "111"
    assert report["players"][0]["side"] == "T"  # 以名单为准
    # 对策最多三条
    assert len(report["counters"]) == 3


def test_parse_survives_code_fences_and_prose():
    raw = "好的，结果如下：\n```json\n" + json.dumps(VALID, ensure_ascii=False) + "\n```\n"
    report = parse_report(raw, allowed_players=ALLOWED)
    assert report and report["players"]


def test_parse_returns_none_for_unusable_output():
    assert parse_report("模型什么都没说", allowed_players=ALLOWED) is None
    assert parse_report("", allowed_players=ALLOWED) is None
    assert parse_report('{"players": []}', allowed_players=ALLOWED) is None
