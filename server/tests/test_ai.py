import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.ai import build_prompt, iter_sse_deltas
from app.main import create_app


class FakeAi:
    def __init__(self, chunks=("结论：A 队略优。\n", "建议：先控中路。")):
        self.chunks = chunks
        self.prompts: list[str] = []

    def stream(self, prompt):
        self.prompts.append(prompt)
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
                streamed = message["payload"]["accumulated"]
            if message["action"] == "AI_REPORT_READY":
                report = message["payload"]
                break

    assert "PROFILE_READY" in seen
    assert "AI_REPORT_READY" in seen
    assert streamed.strip().startswith("结论")
    assert report and report["report"] == streamed
    assert report["model"]


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
