import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.main import create_app


@pytest.fixture()
def dev_client(monkeypatch):
    from app import settings

    monkeypatch.setattr(settings, "DEV_MODE", True)
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi")
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def prod_client(monkeypatch):
    from app import settings

    monkeypatch.setattr(settings, "DEV_MODE", False)
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi")
    with TestClient(app) as client:
        yield client


def _room_with_match(client):
    room = client.post("/api/v1/room/create", json={}).json()["data"]
    client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(),
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    return room


def test_seed_paths_publishes_a_synthetic_artifact(dev_client):
    room = _room_with_match(dev_client)
    headers = {"Authorization": f"Bearer {room['token']}"}

    response = dev_client.post(
        f"/api/v1/dev/seed-paths?roomCode={room['roomCode']}", headers=headers
    )
    assert response.json()["code"] == 0
    artifact_id = response.json()["data"]["artifactId"]

    time.sleep(0.05)
    snapshot = dev_client.get(
        f"/api/v1/room/{room['roomCode']}/snapshot", headers=headers
    ).json()["data"]
    assert snapshot["match"]["demoState"] == "ready"

    index = dev_client.get(f"/api/v1/artifacts/{artifact_id}", headers=headers).json()["data"]
    assert index["synthetic"] is True
    assert len(index["players"]) == 2

    steam_id = index["players"][0]["steamId"]
    detail = dev_client.get(
        f"/api/v1/artifacts/{artifact_id}/players/{steam_id}", headers=headers
    ).json()["data"]
    assert len(detail["replay"]["rounds"]) == 6
    assert detail["replay"]["radar"].startswith("/maps/")


def test_seed_paths_is_unavailable_without_dev_mode(prod_client):
    room = _room_with_match(prod_client)
    response = prod_client.post(
        f"/api/v1/dev/seed-paths?roomCode={room['roomCode']}",
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == 1010


def test_local_demo_endpoints_need_dev_mode(prod_client):
    assert prod_client.get("/api/v1/dev/demos").status_code == 404


def test_local_demo_rejects_path_escape(dev_client, tmp_path, monkeypatch):
    """`name` must resolve inside CS_HELPER_LOCAL_DEMO_DIR, not anywhere on disk."""

    from app import settings as app_settings

    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "real.dem").write_bytes(b"x")
    monkeypatch.setattr(app_settings, "LOCAL_DEMO_DIR", str(inside))

    listing = dev_client.get("/api/v1/dev/demos").json()["data"]["demos"]
    assert [item["name"] for item in listing] == ["real.dem"]

    room = _room_with_match(dev_client)
    headers = {"Authorization": f"Bearer {room['token']}"}
    escaped = dev_client.post(
        f"/api/v1/dev/parse-local?roomCode={room['roomCode']}",
        json={"name": "../../secret.dem"},
        headers=headers,
    )
    assert escaped.status_code in (404, 500)
    assert "secret" in escaped.json()["message"] or escaped.json()["code"] in (1011, 2001)
