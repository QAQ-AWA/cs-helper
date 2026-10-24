"""Durable history: a restart must not lose the match, the AI report or the replay."""

import json
import time

from fastapi.testclient import TestClient

from conftest import make_report

from app import settings
from app.main import create_app
from app.persistence import SessionRepository


def _app(tmp_path, **overrides):
    options = dict(
        secret="test-secret",
        persist_dir=tmp_path,
        room_mode="single",
        demo_runner=None,
        ai_client=None,
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


def test_match_survives_restart(tmp_path):
    first = _app(tmp_path)
    with TestClient(first) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(first)
        client.post(
            "/api/v1/match/post-report?roomCode=MAIN",
            json={"matchCode": "2603212003001", "mapName": "de_mirage", "scoreA": 13, "scoreB": 10},
            headers=_headers(host["token"]),
        )

    second = _app(tmp_path)
    with TestClient(second) as client:
        phone = client.post("/api/v1/room/join", json={"roomCode": "MAIN", "nickname": "手机"}).json()["data"]
        snapshot = client.get("/api/v1/room/MAIN/snapshot", headers=_headers(phone["token"])).json()["data"]

    match = snapshot["match"]
    assert match["matchId"] == "2603212003001"
    assert match["profileState"] == "ready"
    assert match["aiState"] == "skipped"  # no key configured, but the verdict survives
    assert match["postReport"]["scoreA"] == 13
    assert [player["nickname"] for player in snapshot["profiles"]] == ["Alpha", "Bravo"]


def test_replay_artifact_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", True)
    first = _app(tmp_path)
    with TestClient(first) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(first)
        seeded = client.post("/api/v1/dev/seed-paths?roomCode=MAIN", headers=_headers(host["token"])).json()
        artifact_id = seeded["data"]["artifactId"]

    second = _app(tmp_path)
    with TestClient(second) as client:
        phone = client.post("/api/v1/room/join", json={"roomCode": "MAIN", "nickname": "手机"}).json()["data"]
        headers = _headers(phone["token"])
        snapshot = client.get("/api/v1/room/MAIN/snapshot", headers=headers).json()["data"]
        assert snapshot["match"]["artifactId"] == artifact_id

        index = client.get(f"/api/v1/artifacts/{artifact_id}", headers=headers)
        assert index.status_code == 200, index.text
        bundle = index.json()["data"]
        steam_id = bundle["players"][0]["steamId"]

        part = client.get(f"/api/v1/artifacts/{artifact_id}/players/{steam_id}", headers=headers)
        assert part.status_code == 200
        assert part.json()["data"]["replay"]["rounds"]


def test_missing_blob_downgrades_the_session(tmp_path):
    repo = SessionRepository(tmp_path)
    repo.save(
        {
            "schemaVersion": 1,
            "id": "gone",
            "platform": "5e",
            "matchId": "2603212003001",
            "mapName": "de_mirage",
            "roomCode": "MAIN",
            "createdAt": time.time(),
            "updatedAt": time.time(),
            "report": {"teams": {"ct": [], "t": []}},
            "demoState": "ready",
            "artifactId": "0" * 32,
        }
    )
    app = _app(tmp_path)
    session = app.state.store.get_session("gone")
    assert session is not None
    # Claiming "ready" would send the phone to a 404 it cannot explain.
    assert session.artifact_id is None
    assert session.demo_state == "failed"


def test_interrupted_job_is_not_reported_as_running(tmp_path):
    repo = SessionRepository(tmp_path)
    repo.save(
        {
            "schemaVersion": 1,
            "id": "half",
            "platform": "5e",
            "matchId": "m-half",
            "mapName": "de_mirage",
            "createdAt": 1,
            "updatedAt": 1,
            "report": {"teams": {"ct": [], "t": []}},
            "profileState": "running",
            "demoState": "running",
            "aiState": "running",
        }
    )
    app = _app(tmp_path)
    session = app.state.store.get_session("half")
    assert session is not None
    assert (session.profile_state, session.demo_state, session.ai_state) == (
        "failed",
        "failed",
        "failed",
    )


def test_corrupt_history_file_is_skipped_not_fatal(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "broken.json").write_text("{ this is not json", encoding="utf-8")
    (sessions / "future.json").write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")

    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert app.state.store.stats()["sessions"] == 0


def test_history_lists_matches_newest_first(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        host = _host(client)
        _report(client, host["token"])
        _idle(app)
        _report(client, host["token"], matchId="2603212003002", mapName="de_dust2")
        _idle(app)

        body = client.get("/api/v1/history/sessions", headers=_headers(host["token"])).json()
        rows = body["data"]["sessions"]

    assert [row["matchId"] for row in rows] == ["2603212003002", "2603212003001"]
    assert rows[0]["mapName"] == "de_dust2"
    assert rows[0]["profileState"] == "ready"
    assert rows[0]["hasArtifact"] is False


def test_history_requires_a_room_token(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/history/sessions")
    assert response.status_code == 401
    assert response.json()["code"] == 1001


def test_persistence_is_off_unless_asked():
    app = create_app(secret="test-secret", demo_runner=None, ai_client=None, room_mode="multi")
    with TestClient(app) as client:
        health = client.get("/healthz").json()
    assert health["persistence"] is False
    assert health["historyFiles"] == 0
