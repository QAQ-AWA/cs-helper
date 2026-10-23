from conftest import make_report

import pytest


def drain(ws, until, limit=12):
    actions = []
    for _ in range(limit):
        message = ws.receive_json()
        actions.append(message["action"])
        if message["action"] == until:
            return message, actions
    raise AssertionError(f"{until} not received, got {actions}")


def report(client, room, **overrides):
    return client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(**overrides),
        headers={"Authorization": f"Bearer {room['token']}"},
    )


def test_connection_starts_with_room_state(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        first = ws.receive_json()
        assert first["action"] == "ROOM_STATE_SYNC"
        assert first["protocolVersion"] == 1
        assert first["payload"]["roomCode"] == room["roomCode"]
        assert len(first["payload"]["members"]) == 1


def test_report_streams_detected_then_profile(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        report(client, room)
        profile, actions = drain(ws, "PROFILE_READY")
        assert "MATCH_DETECTED" in actions
        assert "JOB_PROGRESS" in actions
        assert profile["payload"]["source"] == "client"
        assert {p["nickname"] for p in profile["payload"]["players"]} == {"Alpha", "Bravo"}


def test_new_member_notifies_existing_connections(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        client.post(
            "/api/v1/room/join",
            json={"roomCode": room["roomCode"], "nickname": "手机", "deviceType": "mobile"},
        )
        message = ws.receive_json()
        assert message["action"] == "ROOM_MEMBERS_CHANGED"
        assert {m["nickname"] for m in message["payload"]["members"]} == {"房主", "手机"}


def test_reconnect_resumes_after_last_seen_sequence(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        report(client, room)
        _, actions = drain(ws, "PROFILE_READY")
        first_seq = 1  # MATCH_DETECTED
        assert actions[0] == "MATCH_DETECTED"

    with client.websocket_connect(f"/ws?token={room['token']}&lastSeq={first_seq}") as ws:
        replayed = ws.receive_json()
        assert replayed["seq"] == first_seq + 1
        assert replayed["action"] == "JOB_PROGRESS"


def test_fresh_connection_receives_profiles_in_snapshot(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        report(client, room)
        drain(ws, "PROFILE_READY")

    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        state = ws.receive_json()
        assert state["action"] == "ROOM_STATE_SYNC"
        assert state["payload"]["match"]["matchId"] == "2603212003001"
        assert {p["nickname"] for p in state["payload"]["profiles"]} == {"Alpha", "Bravo"}


def test_sequence_numbers_are_monotonic(client, room):
    with client.websocket_connect(f"/ws?token={room['token']}") as ws:
        ws.receive_json()
        report(client, room)
        _, actions = drain(ws, "PROFILE_READY")

    with client.websocket_connect(f"/ws?token={room['token']}&lastSeq=1") as ws:
        seen = []
        for _ in range(len(actions) - 1):
            seen.append(ws.receive_json()["seq"])
        assert seen == sorted(seen)
        assert len(set(seen)) == len(seen)


def test_bad_token_is_closed(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?token=nope") as ws:
            ws.receive_json()
