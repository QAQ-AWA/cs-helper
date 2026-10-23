import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app import settings as app_settings
from app.artifacts import ArtifactStore
from app.engine_runner import DemoOutcome
from app.main import create_app


class FakeRunner:
    def __init__(self, outcome: DemoOutcome | None = None) -> None:
        self.outcome = outcome or DemoOutcome(
            players=[
                {
                    "username": "Alpha",
                    "domain": "player_a",
                    "steamId": "76561198000000002",
                    "rounds": 2,
                    "bytes": 120,
                    "replay": {
                        "username": "Alpha",
                        "steamid": "76561198000000002",
                        "map": "de_mirage",
                        "round_count": 2,
                        "rounds": [{"side": "CT", "rtype": "Buy", "round_id": 1, "path": [[0, 0, 0]]}],
                    },
                }
            ],
            failed=[{"username": "Bravo", "reason": "无 de_mirage demo 可用"}],
        )
        self.calls: list[tuple] = []
        self.cancelled: list[str] = []

    def run(self, request, on_progress, *, session_id=None):
        self.calls.append((request, session_id))
        on_progress(0, 1, "Alpha", 3, "下载 Demo 1/2")
        on_progress(0, 1, "Alpha", 4, "解析 Demo 1/2")
        return self.outcome

    def cancel(self, session_id):
        self.cancelled.append(session_id)


@pytest.fixture()
def demo_client(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "maps_ready", lambda name: True)
    monkeypatch.setattr(app_settings, "job_dir", lambda session_id: tmp_path / session_id)
    runner = FakeRunner()
    app = create_app(secret="test-secret", room_ttl=600, demo_runner=runner, room_mode="multi")
    with TestClient(app) as client:
        yield client, runner


def _room(client):
    return client.post("/api/v1/room/create", json={}).json()["data"]


def _report(client, room):
    return client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=make_report(),
        headers={"Authorization": f"Bearer {room['token']}"},
    )


def _wait(client, room, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(
            f"/api/v1/room/{room['roomCode']}/snapshot",
            headers={"Authorization": f"Bearer {room['token']}"},
        ).json()["data"]
        if predicate(data["match"] or {}):
            return data
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_demo_job_publishes_artifact_ref(demo_client):
    client, runner = demo_client
    room = _room(client)
    assert _report(client, room).json()["code"] == 0

    data = _wait(client, room, lambda match: match.get("demoState") == "ready")
    assert data["match"]["artifactId"]
    assert len(runner.calls) == 1
    request, session_id = runner.calls[0]
    assert request.map_name == "de_mirage"
    assert request.usernames == ["Alpha", "Bravo"]

    artifact = client.get(
        f"/api/v1/artifacts/{data['match']['artifactId']}",
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert artifact.status_code == 200
    bundle = artifact.json()["data"]
    assert bundle["map"] == "de_mirage"
    # The index stays small: replay payloads live in per-player parts.
    assert bundle["players"][0]["steamId"] == "76561198000000002"
    assert "replay" not in bundle["players"][0]
    assert bundle["failed"][0]["username"] == "Bravo"

    player = client.get(
        f"/api/v1/artifacts/{data['match']['artifactId']}/players/76561198000000002",
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert player.status_code == 200
    assert player.json()["data"]["replay"]["round_count"] == 2

    missing = client.get(
        f"/api/v1/artifacts/{data['match']['artifactId']}/players/76561198000000009",
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    assert missing.status_code == 404


def test_demo_runs_once_per_match_across_rooms(demo_client):
    client, runner = demo_client
    first = _room(client)
    _report(client, first)
    _wait(client, first, lambda match: match.get("demoState") == "ready")

    second = _room(client)
    _report(client, second)
    _wait(client, second, lambda match: match.get("demoState") == "ready")

    assert len(runner.calls) == 1


def test_demo_skipped_for_other_platforms(demo_client):
    client, runner = demo_client
    room = _room(client)
    payload = make_report(platform="perfect")
    client.post(
        f"/api/v1/match/report?roomCode={room['roomCode']}",
        json=payload,
        headers={"Authorization": f"Bearer {room['token']}"},
    )
    data = _wait(client, room, lambda match: match.get("demoState") == "skipped")
    assert data["match"]["artifactId"] is None
    assert runner.calls == []


def test_artifact_requires_token_and_supports_etag(demo_client):
    client, _runner = demo_client
    room = _room(client)
    _report(client, room)
    data = _wait(client, room, lambda match: match.get("demoState") == "ready")
    url = f"/api/v1/artifacts/{data['match']['artifactId']}"

    assert client.get(url).status_code == 401

    first = client.get(url, headers={"Authorization": f"Bearer {room['token']}"})
    etag = first.headers["etag"]
    assert first.headers["content-type"].startswith("application/json")

    cached = client.get(
        url,
        headers={"Authorization": f"Bearer {room['token']}", "If-None-Match": etag},
    )
    assert cached.status_code == 304

    compressed = client.get(
        url,
        headers={"Authorization": f"Bearer {room['token']}", "Accept-Encoding": "gzip"},
    )
    assert compressed.headers.get("content-encoding") == "gzip"


def test_missing_map_assets_report_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "maps_ready", lambda name: False)
    monkeypatch.setattr(app_settings, "job_dir", lambda session_id: tmp_path / session_id)
    app = create_app(secret="test-secret", demo_runner=FakeRunner())
    with TestClient(app) as client:
        room = _room(client)
        with client.websocket_connect(f"/ws?token={room['token']}") as ws:
            ws.receive_json()
            _report(client, room)
            for _ in range(8):
                message = ws.receive_json()
                if message["action"] == "ROOM_ERROR":
                    assert message["payload"]["code"] == 2002
                    assert message["payload"]["retryable"] is False
                    return
        raise AssertionError("expected a ROOM_ERROR about missing map assets")


def test_artifact_store_is_content_addressed_and_evicts():
    store = ArtifactStore(max_items=2)
    first = store.put(b'{"a":1}')
    again = store.put(b'{"a":1}')
    assert first.id == again.id
    assert first.etag.startswith('"')

    store.put(b'{"b":2}')
    store.put(b'{"c":3}')
    assert store.get(first.id) is None  # evicted, oldest first
    assert store.get(store.put(b'{"c":3}').id) is not None


FAKE_JOB_RUNNER = """
import json, sys
payload = json.loads(sys.stdin.read())
assert payload["mapName"] == "de_mirage"
print(json.dumps({"type": "progress", "i": 0, "total": 1, "name": "A", "step": 3, "msg": "dl"}), flush=True)
print(json.dumps({"type": "progress", "i": 0, "total": 1, "name": "A", "step": 4, "msg": "parse"}), flush=True)
print(json.dumps({"type": "done", "results": [{"username": "A", "domain": "p", "player_json": "/output/player_p.json"}], "failed": []}), flush=True)
"""


def test_subprocess_runner_parses_child_stream(tmp_path):
    import json
    import sys

    from app.engine_runner import DemoRequest, SubprocessDemoRunner

    engine = tmp_path / "engine"
    engine.mkdir()
    (engine / "job_runner.py").write_text(FAKE_JOB_RUNNER, encoding="utf-8")

    output = tmp_path / "out"
    output.mkdir()
    (output / "player_p.json").write_text(
        json.dumps({"steamid": "76561198000000002", "round_count": 2, "rounds": []}),
        encoding="utf-8",
    )

    runner = SubprocessDemoRunner(engine_dir=engine, python=sys.executable, timeout=60)
    seen: list[tuple] = []
    outcome = runner.run(
        DemoRequest(
            usernames=["A"],
            map_name="de_mirage",
            max_demos=1,
            hints=None,
            output_dir=str(output),
            demo_dir=str(tmp_path),
            maps_dir=str(tmp_path),
        ),
        lambda *args: seen.append(args),
        session_id="s1",
    )

    assert [item[3] for item in seen] == [3, 4]
    assert outcome.error is None
    assert outcome.players[0]["rounds"] == 2
    assert outcome.players[0]["replay"]["steamid"] == "76561198000000002"
