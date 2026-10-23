"""The ID library: recognise our side without asking, ask when it cannot tell."""

import time

import pytest
from fastapi.testclient import TestClient

from app import settings as app_settings
from app.engine_runner import DemoOutcome
from app.identity import IdentityStore
from app.main import create_app


def _player(name, side, index):
    return {
        "steamId": f"7656119800000{index:04d}",
        "platformUserId": f"{side}{index}",
        "nickname": f"{name}{index}",
        "stats": {"rating": 1.0, "matchesPlayed": 50},
    }


def _report(my_side=None):
    report = {
        "protocolVersion": 1,
        "platform": "5e",
        "matchId": "2603231500003",
        "mapName": "de_mirage",
        "phase": "ready",
        "teams": {
            "ct": [_player("ct", "ct", n) for n in range(1, 6)],
            "t": [_player("t", "t", n) for n in range(6, 11)],
        },
    }
    if my_side:
        report["mySide"] = my_side
    return report


# -- store -------------------------------------------------------------


def test_empty_library_never_guesses(tmp_path):
    store = IdentityStore(tmp_path / "identity.json")
    assert store.match("MAIN", _report()) is None


def test_two_hits_on_one_side_are_enough(tmp_path):
    store = IdentityStore(tmp_path / "identity.json")
    players = _report()["teams"]["ct"][:2]
    store.add("MAIN", players)
    assert store.match("MAIN", _report()) == "ct"


def test_one_hit_is_deliberately_not_enough(tmp_path):
    """A former teammate you now face must not flip the analysis."""
    store = IdentityStore(tmp_path / "identity.json")
    store.add("MAIN", [_report()["teams"]["t"][0]])
    assert store.match("MAIN", _report()) is None


def test_hits_on_both_sides_are_ambiguous(tmp_path):
    store = IdentityStore(tmp_path / "identity.json")
    store.add("MAIN", _report()["teams"]["ct"][:2])
    store.add("MAIN", _report()["teams"]["t"][:2])
    assert store.match("MAIN", _report()) is None


def test_library_survives_a_restart(tmp_path):
    path = tmp_path / "identity.json"
    IdentityStore(path).add("MAIN", _report()["teams"]["t"][:3])

    reloaded = IdentityStore(path)
    assert reloaded.match("MAIN", _report()) == "t"
    assert reloaded.summary("MAIN")["count"] == 3


def test_rooms_do_not_inherit_each_other(tmp_path):
    store = IdentityStore(tmp_path / "identity.json")
    store.add("MAIN", _report()["teams"]["ct"][:2])
    assert store.match("OTHER", _report()) is None


def test_clear_empties_the_room(tmp_path):
    store = IdentityStore(tmp_path / "identity.json")
    store.add("MAIN", _report()["teams"]["ct"][:2])
    assert store.clear("MAIN") == 2
    assert store.match("MAIN", _report()) is None


# -- end to end --------------------------------------------------------


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, request, on_progress, *, session_id=None):
        self.calls.append(request)
        return DemoOutcome(players=[], failed=[{"username": "x", "reason": "无录像"}])

    def cancel(self, session_id):
        return None


@pytest.fixture()
def demo_client(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "maps_ready", lambda name: True)
    monkeypatch.setattr(app_settings, "job_dir", lambda session_id: tmp_path / session_id)
    runner = FakeRunner()
    app = create_app(
        secret="test-secret",
        demo_runner=runner,
        room_mode="single",
        ai_client=None,
        persist_dir=tmp_path,
    )
    with TestClient(app) as client:
        yield client, runner, app


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _host(client):
    return client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]


def _wait_calls(app, count, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(app.state.hub.jobs._futures) == 0 and len(app.state.hub.jobs._demo_runner.calls) >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"expected {count} demo runs")


def test_learn_then_next_report_needs_no_picker(demo_client):
    client, runner, app = demo_client
    host = _host(client)
    token = host["token"]

    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(my_side="ct"),
        headers=_headers(token),
    )
    _wait_calls(app, 1)

    learned = client.post(
        "/api/v1/identity/learn?roomCode=MAIN",
        json={"side": "ct"},
        headers=_headers(token),
    ).json()["data"]
    assert learned["added"] == 5
    assert learned["count"] == 5

    # A brand new match, reported with no side at all.
    second = _report()
    second["matchId"] = "2603231500004"
    client.post("/api/v1/match/report?roomCode=MAIN", json=second, headers=_headers(token))
    _wait_calls(app, 2)

    snapshot = client.get("/api/v1/room/MAIN/snapshot", headers=_headers(token)).json()["data"]
    assert snapshot["match"]["mySide"] == "ct"
    assert snapshot["match"]["mySideSource"] == "library"
    # Only the opposing five were requested.
    assert len(runner.calls[-1].usernames) == 5


def test_analyze_all_beats_the_library(demo_client):
    """Choosing "both sides" must not be silently undone by a library hit."""

    client, runner, app = demo_client
    host = _host(client)
    token = host["token"]
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(my_side="ct"),
        headers=_headers(token),
    )
    _wait_calls(app, 1)
    client.post(
        "/api/v1/identity/learn?roomCode=MAIN", json={"side": "ct"}, headers=_headers(token)
    )

    body = client.post(
        "/api/v1/room/MAIN/analysis-side",
        json={"mySide": None, "all": True},
        headers=_headers(token),
    ).json()["data"]

    assert body["mySide"] is None
    assert body["mySideSource"] == "explicit-all"
    assert body["targets"] == 10
    _wait_calls(app, 2)
    assert len(runner.calls[-1].usernames) == 10


def test_identity_endpoints_need_a_room_token(demo_client):
    client, _runner, _app = demo_client
    assert client.get("/api/v1/identity?roomCode=MAIN").status_code == 401


def test_learn_without_a_match_is_rejected(demo_client):
    client, _runner, _app = demo_client
    host = _host(client)
    response = client.post(
        "/api/v1/identity/learn?roomCode=MAIN",
        json={"side": "ct"},
        headers=_headers(host["token"]),
    )
    assert response.status_code == 409
    assert response.json()["code"] == 1009


def test_clear_endpoint_empties_the_library(demo_client):
    client, _runner, app = demo_client
    host = _host(client)
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(my_side="ct"),
        headers=_headers(host["token"]),
    )
    _wait_calls(app, 1)
    client.post(
        "/api/v1/identity/learn?roomCode=MAIN",
        json={"side": "ct"},
        headers=_headers(host["token"]),
    )
    removed = client.delete(
        "/api/v1/identity?roomCode=MAIN", headers=_headers(host["token"])
    ).json()["data"]
    assert removed["removed"] == 5
