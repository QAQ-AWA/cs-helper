import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def single_client():
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single")
    with TestClient(app) as client:
        yield client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_config_does_not_leak_the_room_code(single_client):
    """服务端可能挂在公网，匿名接口不能把房间码贴出去。"""

    data = single_client.get("/api/v1/config").json()["data"]
    assert data["mode"] == "single"
    assert "roomCode" not in data
    assert data["protocolVersion"] == 1


def test_create_is_idempotent_and_reuses_identity(single_client):
    first = single_client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]
    second = single_client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]

    assert first["roomCode"] == second["roomCode"] == "MAIN"

    snapshot = single_client.get(
        "/api/v1/room/MAIN/snapshot", headers=_headers(second["token"])
    ).json()["data"]
    assert len(snapshot["members"]) == 1  # restarting the client leaves no ghost


def test_join_requires_the_single_room_code(single_client):
    """房间码是公网部署下唯一的门禁，报错码不能放进来。"""

    wrong = single_client.post(
        "/api/v1/room/join", json={"roomCode": "WRONG1", "nickname": "路人", "deviceType": "mobile"}
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == 1002

    body = single_client.post(
        "/api/v1/room/join",
        json={"roomCode": "MAIN", "nickname": "手机", "deviceType": "mobile"},
    ).json()
    assert body["code"] == 0
    assert body["data"]["roomCode"] == "MAIN"


def test_single_room_still_isolates_members(single_client):
    host = single_client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]
    single_client.post(
        "/api/v1/room/join",
        json={"roomCode": "MAIN", "nickname": "手机", "deviceType": "mobile"},
    )

    snapshot = single_client.get(
        "/api/v1/room/MAIN/snapshot", headers=_headers(host["token"])
    ).json()["data"]
    assert {m["nickname"] for m in snapshot["members"]} == {"房主", "手机"}


def test_multi_mode_still_requires_a_code():
    app = create_app(secret="test-secret", demo_runner=None, room_mode="multi")
    with TestClient(app) as client:
        response = client.post("/api/v1/room/join", json={"nickname": "x"})
        assert response.status_code == 400
        assert response.json()["code"] == 1002
