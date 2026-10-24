import json
import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.ai import build_prompt, iter_sse_deltas, iter_sse_events
from app.engine_runner import DemoOutcome
from app.main import create_app

# 分析这一轮要的是 v3 JSON，开局预判那一轮仍是 Markdown。
ANALYSIS_RESULT = {
    "schemaVersion": 3,
    "predictedWinner": "A",
    "modelWinProbability": {"A": 58, "B": 42},
    "confidence": 72,
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
            "summary": "Rating 1.18、K/D 1.25 都是全场最高",
        }
    ],
    "teamPlans": {
        "A": {"winConditions": [{"text": "先控中路"}], "risks": []},
        "B": {"winConditions": [], "risks": [{"text": "枪法吃亏"}]},
    },
    "uncertainties": ["样本偏少"],
}


class FakeAi:
    def __init__(self, chunks=("结论：A 队略优。\n", "建议：先控中路。"), reasons=(), analysis=None):
        self.chunks = chunks
        self.reasons = reasons
        self.analysis = analysis if analysis is not None else json.dumps(ANALYSIS_RESULT, ensure_ascii=False)
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def stream(self, prompt, on_reason=None, system=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        for thought in self.reasons:
            if on_reason is not None:
                on_reason(thought)
        if system and "只输出 JSON" in system and self.analysis:
            # 分两段吐，模拟真实流式，验证半截 JSON 不会被当成结果。
            half = len(self.analysis) // 2
            yield self.analysis[:half]
            yield self.analysis[half:]
            return
        for chunk in self.chunks:
            yield chunk


def _room(client):
    return client.post("/api/v1/room/create", json={}).json()["data"]


def _report(client, room):
    return client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(),
        headers={"Authorization": f"Bearer {room['token']}"},
    )


def _wait(client, room, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(
            f"/api/v1/room/{room['roomCode']}/snapshot",
            headers={"Authorization": f"Bearer {room['token']}"},
        ).json()["data"]
        if predicate(data["match"] or {}):
            return data
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


@pytest.fixture()
def ai_client():
    app = create_app(
        secret="test-secret",
        demo_runner=None,
        room_mode="multi",
        ai_client=FakeAi(),
    )
    with TestClient(app) as client:
        yield client


def test_ai_runs_once_after_profile_and_broadcasts(ai_client):
    room = _room(ai_client)
    with ai_client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()  # ROOM_STATE_SYNC
        _report(ai_client, room)

        seen: list[str] = []
        streamed = ""
        report = None
        for _ in range(14):
            message = ws.receive_json()
            seen.append(message["action"])
            if message["action"] == "AI_STREAM_CHUNK":
                # 生成过程中只推进度（chars），完整文本在最后一帧才给。
                streamed = message["payload"].get("accumulated", streamed)
            if message["action"] == "AI_REPORT_READY":
                report = message["payload"]
                break

    assert "PROFILE_READY" in seen
    assert "AI_REPORT_READY" in seen
    # 结构化结果的手机版是本地渲染的 Markdown，不是模型原文。
    assert streamed.strip().startswith("## 结论")
    assert report and report["report"] == streamed
    assert report["model"]
    assert report["result"]["schemaVersion"] == 3
    assert report["result"]["playerSignals"][0]["nickname"] == "Alpha"


def test_ai_text_is_kept_for_reconnects(ai_client):
    room = _room(ai_client)
    _report(ai_client, room)
    data = _wait(ai_client, room, lambda match: match.get("aiState") == "ready")
    assert "先控中路" in data["match"]["aiText"]


def test_ai_is_skipped_without_a_key():
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi", ai_client=None)
    with TestClient(app) as client:
        room = _room(client)
        _report(client, room)
        data = _wait(client, room, lambda match: match.get("aiState") == "skipped")
        assert data["match"]["aiText"] is None


def test_prompt_carries_map_and_rosters():
    prompt = build_prompt(
        "de_mirage",
        [
            {"nickname": "Alpha", "team": "ct", "stats": {"rating": 1.18, "kd": 1.25, "headshotRate": 48, "winRate": 54}},
            {"nickname": "Bravo", "team": "t", "stats": {"rating": 0.95}},
        ],
    )
    assert "de_mirage" in prompt
    assert "Alpha" in prompt and "Bravo" in prompt
    assert "1.18" in prompt
    assert "CT" in prompt and "T" in prompt


def test_prompt_is_an_evidence_pack_with_local_directions():
    prompt = build_prompt(
        "de_mirage",
        [
            {"nickname": "Alpha", "team": "ct", "stats": {"rating": 1.18, "kd": 1.25, "matchesPlayed": 120}},
            {"nickname": "Bravo", "team": "t", "stats": {"rating": 0.95, "kd": 0.8, "matchesPlayed": 4}},
        ],
        my_side="ct",
    )
    assert '"direction":"positive"' in prompt
    assert '"direction":"negative"' in prompt
    assert '"role":"我方"' in prompt and '"role":"对方"' in prompt
    assert '"lowSamplePlayers":["Bravo"]' in prompt
    assert "数据缺口" in prompt


def test_sse_parser_tolerates_noise_and_stops_on_done():
    lines = [
        "",
        ": keep-alive",
        'data: {"choices":[{"delta":{"content":"你"}}]}',
        'data: {"choices":[{"delta":{}}]}',
        "event: ping",
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"不应出现"}}]}',
    ]
    assert "".join(iter_sse_deltas(lines)) == "你好"


def test_reasoning_shows_as_progress_and_empty_body_is_reported():
    """A reasoning model can burn the whole budget on its scratchpad.

    The phone must see progress instead of a blank card, and the server must
    say why the answer is empty rather than 'AI 未返回内容'.
    """

    app = create_app(
        secret="test-secret",
        demo_runner=None,
        room_mode="multi",
        ai_client=FakeAi(chunks=(), reasons=("先看 CT 的 Rating 分布", "再看 T 的尖点"), analysis=""),
    )
    with TestClient(app) as client:
        room = _room(client)
        with client.websocket_connect(f"/ws?token={room['token']}") as ws:
            ws.receive_json()
            _report(client, room)

            phases: list[str] = []
            error = None
            for _ in range(16):
                message = ws.receive_json()
                if message["action"] == "AI_STREAM_CHUNK":
                    phases.append(message["payload"].get("phase"))
                if message["action"] == "ROOM_ERROR" and message["payload"].get("stage") == "ai":
                    error = message["payload"]
                    break

    assert "thinking" in phases
    assert error is not None and "推理" in error["message"]


def test_sse_events_separate_reasoning_from_content():
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"想一下"}}]}',
        'data: {"choices":[{"delta":{"content":"结论"}}]}',
        "data: [DONE]",
    ]
    events = list(iter_sse_events(lines))
    assert events == [("reason", "想一下"), ("content", "结论")]


class TacticsRunner:
    """One demo, five opponents, with real plants so sites can be named."""

    def __init__(self):
        self.calls = []

    def run(self, request, on_progress, *, session_id=None):
        self.calls.append(request)
        players = []
        for index in range(5):
            players.append(
                {
                    "username": f"opp{index}",
                    "steamId": f"7656119800000000{index}",
                    "rounds": 2,
                    "replay": {
                        "rounds": [
                            {
                                "side": "T",
                                "path": [[0, 0, 0], [10, 1000, 1000], [20, 1000, 1000]],
                                "plant": {"site": "A", "x": 1000, "y": 1000},
                            },
                            {
                                "side": "CT",
                                "path": [[0, -1000, -1000], [20, -1000, -1000]],
                            },
                        ]
                    },
                }
            )
        return DemoOutcome(players=players, failed=[])

    def cancel(self, session_id):
        return None


def test_tactics_pass_runs_after_the_trajectory_is_ready(tmp_path, monkeypatch):
    from app import settings as app_settings

    monkeypatch.setattr(app_settings, "maps_ready", lambda name: True)
    monkeypatch.setattr(app_settings, "job_dir", lambda session_id: tmp_path / session_id)
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path / "data")

    ai = FakeAi(chunks=("## 开局选点预判\n3 人 12 秒进 A。",))
    app = create_app(
        secret="test-secret",
        demo_runner=TacticsRunner(),
        room_mode="single",
        ai_client=ai,
    )
    with TestClient(app) as client:
        host = client.post("/api/v1/room/create", json={"creatorNickname": "房主"}).json()["data"]
        client.post(
            "/api/v1/match/report?roomCode=MAIN",
            json=make_report(mySide="ct"),
            headers={"Authorization": f"Bearer {host['token']}"},
        )
        deadline = time.time() + 8
        state = None
        while time.time() < deadline:
            snapshot = client.get(
                "/api/v1/room/MAIN/snapshot", headers={"Authorization": f"Bearer {host['token']}"}
            ).json()["data"]
            state = (snapshot["match"] or {}).get("tacticsState")
            if state in {"ready", "failed", "skipped"}:
                break
            time.sleep(0.02)

    assert state == "ready"
    # Two calls: the season-stats read, then the trajectory read.
    assert len(ai.systems) == 2
    assert "开局预判" in ai.systems[1]
    assert '"planted"' in ai.prompts[1]
    assert '"siteKnown":["A"]' in ai.prompts[1]


def test_switching_side_reruns_the_analysis(monkeypatch, tmp_path):
    """换边等于换视角：旧结论是按另一边写的，必须重算。"""

    from app import settings as app_settings

    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path / "data")
    ai = FakeAi()
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single", ai_client=ai)
    with TestClient(app) as client:
        host = client.post("/api/v1/room/create", json={"creatorNickname": "房主"}).json()["data"]
        headers = {"Authorization": f"Bearer {host['token']}"}
        client.post("/api/v1/match/report?roomCode=MAIN", json=make_report(), headers=headers)

        deadline = time.time() + 5
        while time.time() < deadline and len(ai.systems) < 1:
            time.sleep(0.02)
        assert len(ai.systems) == 1

        client.post("/api/v1/room/MAIN/analysis-side", json={"mySide": "t", "all": False}, headers=headers)

        deadline = time.time() + 5
        while time.time() < deadline and len(ai.systems) < 2:
            time.sleep(0.02)
        assert len(ai.systems) == 2
