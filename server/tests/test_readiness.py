"""5E 是分段落数据的：先 matchId，再名单，再地图。作业要按段位放行。"""

import json
import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.main import create_app
from app.readiness import analysis_key, map_ready, missing_for_analysis, roster_note

ANALYSIS = {
    "predictedWinner": "A",
    "modelWinProbability": {"A": 55, "B": 45},
    "confidence": 60,
    "headline": "A 队略优",
    "decisiveFactors": [],
    "playerSignals": [],
    "teamPlans": {"A": {"winConditions": [], "risks": []}, "B": {"winConditions": [], "risks": []}},
    "uncertainties": [],
}


class CountingAi:
    def __init__(self) -> None:
        self.calls = 0

    def stream(self, prompt, on_reason=None, system=None):
        self.calls += 1
        yield json.dumps(ANALYSIS, ensure_ascii=False)


def test_map_ready_rejects_the_placeholders_5e_sends_before_picking():
    for name in ("", "de_unknown", "UNKNOWN", "de_workshop"):
        assert map_ready(name) is False
    assert map_ready("de_dust2") is True


def test_analysis_key_only_tracks_map_roster_and_side():
    report = make_report()
    first = analysis_key("de_dust2", report, "ct")
    assert first == analysis_key("de_dust2", report, "ct")
    assert first != analysis_key("de_mirage", report, "ct")
    assert first != analysis_key("de_dust2", report, "t")
    changed = make_report()
    changed["teams"]["ct"][0]["steamId"] = "76561198000000009"
    assert first != analysis_key("de_dust2", changed, "ct")


def test_missing_for_analysis_only_blocks_on_the_map():
    report = make_report()
    assert missing_for_analysis("de_unknown", report, None) == ["等地图确认"]
    # 敌我未定照样能算，只是按 CT/T 说，不再冒充「我方/对方」。
    assert missing_for_analysis("de_dust2", report, None) == []
    assert roster_note(report) == "名单 2/10"


@pytest.fixture()
def staged_client():
    ai = CountingAi()
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single", ai_client=ai)
    with TestClient(app) as client:
        host = client.post("/api/v1/room/create", json={"creatorNickname": "房主"}).json()["data"]
        yield client, host, ai


def _report(client, host, **overrides):
    return client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=make_report(**overrides),
        headers={"Authorization": f"Bearer {host['token']}"},
    )


def _wait(client, host, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(
            "/api/v1/room/MAIN/snapshot",
            headers={"Authorization": f"Bearer {host['token']}"},
        ).json()["data"]
        if predicate(data["match"] or {}):
            return data["match"]
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_analysis_waits_for_the_map_and_runs_once_it_arrives(staged_client):
    client, host, ai = staged_client

    _report(client, host, mapName="de_unknown")
    match = _wait(client, host, lambda m: m.get("aiState") == "waiting")
    assert match["aiWait"] == ["等地图确认"]
    assert ai.calls == 0

    _report(client, host, mapName="de_dust2")
    _wait(client, host, lambda m: m.get("aiState") == "ready")
    assert ai.calls == 1


def test_identical_report_does_not_rerun_the_analysis(staged_client):
    client, host, ai = staged_client
    _report(client, host, mapName="de_dust2")
    _wait(client, host, lambda m: m.get("aiState") == "ready")

    _report(client, host, mapName="de_dust2")
    time.sleep(0.3)
    assert ai.calls == 1


def test_roster_change_invalidates_the_old_analysis(staged_client):
    """名单补齐属于「输入变了」：旧结论要作废重算，而不是留着第一份半成品。"""

    client, host, ai = staged_client
    _report(client, host, mapName="de_dust2")
    _wait(client, host, lambda m: m.get("aiState") == "ready")
    assert ai.calls == 1

    report = make_report(mapName="de_dust2")
    report["teams"]["t"].append(
        {"steamId": "76561198000000010", "platformUserId": "late", "nickname": "Late", "stats": {}}
    )
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=report,
        headers={"Authorization": f"Bearer {host['token']}"},
    )
    _wait(client, host, lambda m: m.get("aiState") == "ready" and ai.calls == 2)
    assert ai.calls == 2
