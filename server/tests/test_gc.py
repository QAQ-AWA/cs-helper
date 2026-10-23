"""Housekeeping: rooms expire, memory stays bounded, history keeps the receipts."""

import os
import time

from fastapi.testclient import TestClient

from conftest import make_report

from app.main import create_app

DAY = 86400


def _app(tmp_path, **overrides):
    options = dict(
        secret="test-secret",
        persist_dir=tmp_path,
        room_mode="single",
        demo_runner=None,
        ai_client=None,
        gc_interval=None,
    )
    options.update(overrides)
    return create_app(**options)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _host(client):
    return client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]


def _report(client, token, **overrides):
    response = client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=make_report(**overrides),
        headers=_headers(token),
    )
    assert response.json()["code"] == 0, response.json()
    return response.json()["data"]


def _idle(app):
    app.state.hub.jobs.wait_idle(timeout=10)


def _age(path, seconds):
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def test_reap_drops_expired_room_and_idle_session(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)

        hub = app.state.hub
        room = hub.store.get_room("MAIN")
        session = hub.store.get_session(room.session_id)
        room.expires_at = time.time() - 1
        session.updated_at = time.time() - 2 * DAY

        result = hub.reap()

        assert result["rooms"] == 1
        assert result["sessions"] == 1
        assert hub.store.stats()["rooms"] == 0
        assert hub.store.stats()["sessions"] == 0
        # Evicted from memory, still on disk: reclamation is not data loss.
        assert hub.repository.count() == 1


def test_reap_never_drops_a_session_a_live_room_points_at(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)

        hub = app.state.hub
        room = hub.store.get_room("MAIN")
        session = hub.store.get_session(room.session_id)
        session.updated_at = time.time() - 30 * DAY

        result = hub.reap()

        assert result["sessions"] == 0
        assert hub.store.get_session(session.id) is not None


def test_session_memory_cap_keeps_the_newest_match(tmp_path):
    app = _app(tmp_path, session_memory_max=1)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)
        _report(client, host["token"], matchId="m-2")
        _idle(app)
        _report(client, host["token"], matchId="m-3")
        _idle(app)

        hub = app.state.hub
        result = hub.reap()

        assert result["sessions"] == 2
        remaining = hub.store.sessions()
        assert [item.match_id for item in remaining] == ["m-3"]
        assert hub.repository.count() == 3


def test_prune_removes_old_history_and_its_replay_blob(tmp_path):
    app = _app(tmp_path, history_days=1)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)

        hub = app.state.hub
        room = hub.store.get_room("MAIN")
        session = hub.store.get_session(room.session_id)
        artifact = hub.artifacts.put(b'{"players":[]}', parts={"76561198000000002": b'{"x":1}'})
        session.artifact_id = artifact.id
        hub.persist(session)

        for path in (tmp_path / "sessions").glob("*.json"):
            _age(path, 3 * DAY)
        for path in (tmp_path / "artifacts").iterdir():
            _age(path, 3 * DAY)

        result = hub.reap()

        assert result["history"] == 1
        assert result["artifacts"] == 2  # index + one player part
        assert list((tmp_path / "sessions").glob("*.json")) == []
        assert list((tmp_path / "artifacts").iterdir()) == []


def test_prune_leaves_fresh_history_alone(tmp_path):
    app = _app(tmp_path, history_days=7)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)

        result = app.state.hub.reap()

        assert result["history"] == 0
        assert len(list((tmp_path / "sessions").glob("*.json"))) == 1


def test_background_reaper_runs_without_a_request(tmp_path):
    app = _app(tmp_path, gc_interval=0.05)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)
        hub = app.state.hub
        room = hub.store.get_room("MAIN")
        hub.store.get_session(room.session_id).updated_at = time.time() - 2 * DAY
        room.expires_at = time.time() - 1

        deadline = time.time() + 5
        while time.time() < deadline and hub.store.stats()["rooms"]:
            time.sleep(0.05)

        assert hub.store.stats()["rooms"] == 0
        assert hub.last_reap is not None


def test_healthz_reports_the_ops_surface(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)
        app.state.hub.reap()

        health = client.get("/healthz").json()

    assert health["status"] == "ok"
    assert health["protocolVersion"] == 1
    assert health["rooms"] == 1
    assert health["sessions"] == 1
    assert health["persistence"] is True
    assert health["historyFiles"] == 1
    assert health["historyDays"] == 7
    assert health["dataDir"] == str(tmp_path)
    assert health["lastReap"]["rooms"] == 0
    assert health["artifactDiskBytes"] >= 0
