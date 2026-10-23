import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.main import create_app

POST_REPORT = {
    "matchCode": "2603212003001",
    "mapName": "de_mirage",
    "roundTotal": 23,
    "scoreA": 13,
    "scoreB": 10,
    "winnerSide": "A",
    "halfScores": {"fhA": 7, "shA": 6, "fhB": 5, "shB": 5},
    "players": [
        {"uid": "1", "nickname": "Alpha", "teamSide": 1, "kill": 20, "death": 15,
         "assist": 5, "rating": 1.25, "adr": 88.5, "isMvp": True, "isSvp": False},
        {"uid": "2", "nickname": "Bravo", "teamSide": 2, "kill": 18, "death": 17,
         "assist": 3, "rating": 1.05, "adr": 80.1, "isMvp": False, "isSvp": True},
    ],
    "comparison": {"isCorrect": True, "headline": "AI 预测命中"},
}


@pytest.fixture()
def client():
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi")
    with TestClient(app) as test_client:
        yield test_client


def _room(client):
    return client.post("/api/v1/room/create", json={}).json()["data"]


def _headers(room):
    return {"Authorization": f"Bearer {room['token']}"}


def _report_match(client, room):
    return client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(),
        headers=_headers(room),
    )


def _post(client, room, **overrides):
    payload = {**POST_REPORT, **overrides}
    return client.post(
        f"/api/v1/match/post-report?roomCode={room['roomCode']}",
        json=payload,
        headers=_headers(room),
    )


def _snapshot(client, room):
    return client.get(
        f"/api/v1/room/{room['roomCode']}/snapshot", headers=_headers(room)
    ).json()["data"]


def test_post_match_is_stored_on_the_session(client):
    room = _room(client)
    _report_match(client, room)

    assert _post(client, room).json()["code"] == 0
    match = _snapshot(client, room)["match"]
    assert match["postReport"]["scoreA"] == 13
    assert match["postReport"]["players"][0]["nickname"] == "Alpha"


def test_post_match_is_broadcast(client):
    room = _room(client)
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        _report_match(client, room)
        # 让开局事件先排完，再插入战报
        while True:
            message = ws.receive_json()
            if message["action"] == "PROFILE_READY":
                break

        _post(client, room)
        for _ in range(6):
            message = ws.receive_json()
            if message["action"] == "POST_MATCH_READY":
                payload = message["payload"]
                assert payload["scoreA"] == 13
                assert payload["sessionId"]
                assert payload["comparison"]["isCorrect"] is True
                return
        raise AssertionError("POST_MATCH_READY not received")


def test_post_match_requires_an_existing_match(client):
    room = _room(client)
    response = _post(client, room)
    assert response.status_code == 409
    assert response.json()["code"] == 1009


def test_post_match_rejects_a_non_url_demo(client):
    room = _room(client)
    _report_match(client, room)
    response = _post(client, room, demoUrl="not-a-url")
    assert response.status_code == 422


def test_post_match_is_idempotent(client):
    room = _room(client)
    _report_match(client, room)
    assert _post(client, room).json()["code"] == 0
    assert _post(client, room, scoreA=13, scoreB=9).json()["code"] == 0
    # 后一次覆盖前一次，不会出现两份战报
    assert _snapshot(client, room)["match"]["postReport"]["scoreB"] == 9
