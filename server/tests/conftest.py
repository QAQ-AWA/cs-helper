import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.main import create_app  # noqa: E402


@pytest.fixture()
def app():
    # demo_runner=None keeps the suite off the subprocess/egress path; the demo
    # job has its own tests with a fake runner.
    return create_app(secret="test-secret", room_ttl=600, demo_runner=None, room_mode="multi")


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def make_report(**overrides):
    report = {
        "protocolVersion": 1,
        "clientVersion": "4.0.0",
        "platform": "5e",
        "matchId": "2603212003001",
        "mapName": "de_mirage",
        "phase": "ready",
        "countdownSeconds": 58,
        "teams": {
            "ct": [
                {
                    "steamId": "76561198000000002",
                    "platformUserId": "player_a",
                    "nickname": "Alpha",
                    "stats": {"rating": 1.18, "kd": 1.25},
                }
            ],
            "t": [
                {
                    "steamId": "76561198000000003",
                    "platformUserId": "player_b",
                    "nickname": "Bravo",
                    "stats": {"rating": 0.95, "kd": 0.88},
                }
            ],
        },
    }
    report.update(overrides)
    return report


@pytest.fixture()
def room(client):
    response = client.post("/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"})
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]
