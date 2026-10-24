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


def test_report_requires_the_key_when_configured(monkeypatch):
    """设了上报密钥就只认带密钥的客户端——房间码管看，密钥管写。"""

    from app import settings as app_settings

    app_settings.REPORT_KEY = "s3cret"
    try:
        app = create_app(secret="test-secret", demo_runner=None, room_mode="single")
        with TestClient(app) as client:
            token = client.post(
                "/api/v1/room/join",
                json={"roomCode": "MAIN", "nickname": "房主", "deviceType": "pc"},
            ).json()["data"]["token"]
            headers = {"Authorization": f"Bearer {token}"}
            body = {
                "protocolVersion": 1,
                "clientVersion": "test",
                "platform": "5e",
                "matchId": "g161-key-test",
                "mapName": "de_dust2",
                "phase": "ready",
                "teams": {"ct": [], "t": []},
            }

            missing = client.post("/api/v1/match/report?roomCode=MAIN", json=body, headers=headers)
            assert missing.status_code == 403
            assert missing.json()["code"] == 1005

            wrong = client.post(
                "/api/v1/match/report?roomCode=MAIN",
                json=body,
                headers={**headers, "X-CS-Report-Key": "nope"},
            )
            assert wrong.status_code == 403

            ok = client.post(
                "/api/v1/match/report?roomCode=MAIN",
                json=body,
                headers={**headers, "X-CS-Report-Key": "s3cret"},
            )
            assert ok.status_code == 200
            assert ok.json()["data"]["matchId"] == "g161-key-test"
    finally:
        app_settings.REPORT_KEY = ""


def test_unmapped_session_is_abandoned_after_the_timeout(monkeypatch):
    """准备阶段取消的对局永远等不到地图，别让轨迹页一直转圈。"""

    from app import hub as hub_mod, settings as app_settings

    monkeypatch.setattr(app_settings, "STALE_MAP_SECONDS", 60)
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single")
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/room/join",
            json={"roomCode": "MAIN", "nickname": "房主", "deviceType": "pc"},
        ).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/v1/match/report?roomCode=MAIN",
            json={
                "protocolVersion": 1,
                "clientVersion": "test",
                "platform": "5e",
                "matchId": "g161-never-started",
                "mapName": "de_unknown",
                "phase": "ready",
                "teams": {"ct": [], "t": []},
            },
            headers=headers,
        )

        hub = client.app.state.hub
        session = hub.store.get_session_by_key("5e:g161-never-started")
        assert session is not None
        # 没配 demo_runner 时不会进入 waiting，pending 也算「在等地图」
        assert session.demo_state in {"pending", "waiting"}

        # 时间没到：不动
        assert hub.abandon_stale_unmapped() == 0
        assert session.demo_state in {"pending", "waiting"}

        # 超过阈值：标成跳过
        session.created_at -= 120
        assert hub.abandon_stale_unmapped() == 1
        assert session.demo_state == "skipped"
        assert session.tactics_state == "skipped"
        # 幂等：再跑一次不重复计数
        assert hub.abandon_stale_unmapped() == 0


def test_unmapped_session_is_abandoned_after_the_timeout(monkeypatch):
    """准备阶段取消的对局永远等不到地图，别让轨迹页一直转圈。"""

    from app import hub as hub_mod, settings as app_settings

    monkeypatch.setattr(app_settings, "STALE_MAP_SECONDS", 60)
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single")
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/room/join",
            json={"roomCode": "MAIN", "nickname": "房主", "deviceType": "pc"},
        ).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/api/v1/match/report?roomCode=MAIN",
            json={
                "protocolVersion": 1,
                "clientVersion": "test",
                "platform": "5e",
                "matchId": "g161-never-started",
                "mapName": "de_unknown",
                "phase": "ready",
                "teams": {"ct": [], "t": []},
            },
            headers=headers,
        )

        hub = client.app.state.hub
        session = hub.store.get_session_by_key("5e:g161-never-started")
        assert session is not None
        # 没配 demo_runner 时不会进 waiting，pending 同样表示「在等地图」
        assert session.demo_state in {"pending", "waiting"}

        # 时间没到：不动
        assert hub.abandon_stale_unmapped() == 0
        assert session.demo_state in {"pending", "waiting"}

        # 超过阈值：标成跳过
        session.created_at -= 120
        assert hub.abandon_stale_unmapped() == 1
        assert session.demo_state == "skipped"
        assert session.tactics_state == "skipped"
        # 幂等：再跑一次不重复计数
        assert hub.abandon_stale_unmapped() == 0


def test_abandoned_session_rebinds_the_room_to_the_last_real_match(monkeypatch):
    """准备阶段取消的对局被放弃后，房间应该切回上一场真对局，而不是挂着空壳。"""

    from app import settings as app_settings

    monkeypatch.setattr(app_settings, "STALE_MAP_SECONDS", 60)
    app = create_app(secret="test-secret", demo_runner=None, room_mode="single")
    with TestClient(app) as client:
        token = client.post(
            "/api/v1/room/join",
            json={"roomCode": "MAIN", "nickname": "房主", "deviceType": "pc"},
        ).json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}

        def report(match_id, map_name):
            client.post(
                "/api/v1/match/report?roomCode=MAIN",
                json={
                    "protocolVersion": 1,
                    "clientVersion": "test",
                    "platform": "5e",
                    "matchId": match_id,
                    "mapName": map_name,
                    "phase": "ready",
                    "teams": {"ct": [], "t": []},
                },
                headers=headers,
            )

        report("g161-real", "de_mirage")
        hub = client.app.state.hub
        real = hub.store.get_session_by_key("5e:g161-real")
        real.updated_at -= 600  # 上一场，比幽灵对局旧

        report("g161-phantom", "de_unknown")
        phantom = hub.store.get_session_by_key("5e:g161-phantom")
        phantom.created_at -= 120

        assert hub.abandon_stale_unmapped() == 1
        assert phantom.demo_state == "skipped"

        snapshot = client.get("/api/v1/room/MAIN/snapshot", headers=headers).json()["data"]
        assert snapshot["match"]["matchId"] == "g161-real"
