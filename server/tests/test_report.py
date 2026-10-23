from conftest import make_report


def report(client, room, **overrides):
    return client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(**overrides),
        headers={"Authorization": f"Bearer {room['token']}", "Idempotency-Key": "5e:2603212003001"},
    )


def test_report_binds_session_to_room(client, room):
    body = report(client, room).json()
    assert body["code"] == 0, body
    assert body["data"]["created"] is True

    snapshot = client.get(
        f"/api/v1/room/{room['roomCode']}/snapshot",
        headers={"Authorization": f"Bearer {room['token']}"},
    ).json()["data"]
    assert snapshot["match"]["matchId"] == "2603212003001"
    assert snapshot["match"]["teams"]["ct"][0]["nickname"] == "Alpha"


def test_same_match_in_two_rooms_shares_one_session(client, room):
    first = report(client, room).json()["data"]

    second_room = client.post("/api/v1/room/create", json={}).json()["data"]
    second = report(client, second_room).json()["data"]

    assert second["sessionId"] == first["sessionId"]
    assert second["created"] is False


def test_repeated_report_is_idempotent(client, room):
    first = report(client, room).json()["data"]
    second = report(client, room).json()["data"]
    assert second["sessionId"] == first["sessionId"]
    assert second["created"] is False


def test_invalid_steam_id_is_rejected(client, room):
    bad = make_report()
    bad["teams"]["ct"][0]["steamId"] = "12345"
    response = client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=bad,
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == 1005


def test_invalid_map_is_rejected(client, room):
    response = report(client, room, mapName="mirage")
    assert response.status_code == 422


def test_protocol_version_from_the_future_is_refused(client, room):
    response = report(client, room, protocolVersion=99)
    assert response.status_code == 409
    assert response.json()["code"] == 1006
