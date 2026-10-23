from conftest import make_report


def test_create_room_returns_scannable_code(client):
    body = client.post("/api/v1/room/create", json={"creatorNickname": "房主"}).json()
    assert body["code"] == 0
    data = body["data"]
    assert len(data["roomCode"]) == 6
    assert data["roomCode"].isalnum() and data["roomCode"].isupper()
    assert not set(data["roomCode"]) & set("01IO")
    assert data["token"]
    assert data["joinUrl"].endswith(data["roomCode"])


def test_join_room_issues_independent_token(client, room):
    body = client.post(
        "/api/v1/room/join",
        json={"roomCode": room["roomCode"].lower(), "nickname": "队友", "deviceType": "mobile"},
    ).json()
    assert body["code"] == 0, body
    assert body["data"]["token"] != room["token"]
    assert body["data"]["roomCode"] == room["roomCode"]


def test_join_unknown_room_is_rejected(client):
    response = client.post("/api/v1/room/join", json={"roomCode": "ZZZZZZ", "nickname": "x"})
    assert response.status_code == 404
    assert response.json()["code"] == 1002


def test_snapshot_requires_token(client, room):
    response = client.get(f"/api/v1/room/{room['roomCode']}/snapshot")
    assert response.status_code == 401
    assert response.json()["code"] == 1001


def test_snapshot_rejects_token_for_other_room(client, room):
    other = client.post("/api/v1/room/create", json={}).json()["data"]
    response = client.get(
        f"/api/v1/room/{other['roomCode']}/snapshot",
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert response.status_code == 403


def test_network_info_offers_lan_addresses(client):
    body = client.get("/api/v1/room/network/info").json()
    assert body["code"] == 0
    assert isinstance(body["data"]["ips"], list)
    assert all(not ip.startswith("127.") for ip in body["data"]["ips"])


def test_report_requires_matching_room_token(client, room):
    response = client.post(
        "/api/v1/match/report?roomCode=XXXXXX",
        json=make_report(),
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == 1001
