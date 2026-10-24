"""Choosing our roster halves the downloads: only the opposing five are fetched."""

import time

import pytest
from fastapi.testclient import TestClient

from app import settings as app_settings
from app.adapters import demo_targets, resolve_my_side
from app.engine_runner import DemoOutcome
from app.main import create_app


def _roster(prefix: str, side: str) -> list[dict]:
    return [
        {
            "steamId": f"7656119800000{n:04d}",
            "platformUserId": f"{prefix}{n}",
            "nickname": f"{prefix}{n}",
            "stats": {"rating": 1.0, "kd": 1.0},
        }
        for n in range(1, 6)
    ]


def _report(**overrides):
    report = {
        "protocolVersion": 1,
        "platform": "5e",
        "matchId": "2603231500002",
        "mapName": "de_mirage",
        "phase": "ready",
        "teams": {"ct": _roster("ct", "ct"), "t": _roster("t", "t")},
    }
    report.update(overrides)
    return report


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list = []
        self.cancelled: list[str] = []

    def run(self, request, on_progress, *, session_id=None):
        self.calls.append(request)
        on_progress(0, len(request.usernames), request.usernames[0], 4, "解析")
        return DemoOutcome(players=[], failed=[{"username": "x", "reason": "无录像"}])

    def cancel(self, session_id):
        self.cancelled.append(session_id)


@pytest.fixture()
def demo_client(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "maps_ready", lambda name: True)
    monkeypatch.setattr(app_settings, "job_dir", lambda session_id: tmp_path / session_id)
    runner = FakeRunner()
    app = create_app(secret="test-secret", demo_runner=runner, room_mode="single", ai_client=None)
    with TestClient(app) as client:
        yield client, runner, app


def _host(client):
    return client.post(
        "/api/v1/room/create", json={"creatorNickname": "房主", "deviceType": "pc"}
    ).json()["data"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _wait_calls(app, count, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(app.state.hub.jobs._futures) == 0 and _runner_calls(app) >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"expected {count} demo runs")


def _runner_calls(app):
    return len(app.state.hub.jobs._demo_runner.calls)


# -- pure resolution ---------------------------------------------------


def test_explicit_side_wins():
    report = _report(mySide="ct")
    assert resolve_my_side(report) == "ct"
    assert {p["team"] for p in demo_targets(report)} == {"t"}


def test_self_flag_is_used_when_nothing_is_chosen():
    report = _report()
    report["teams"]["t"][0]["isSelf"] = True
    assert resolve_my_side(report) == "t"
    assert {p["team"] for p in demo_targets(report)} == {"ct"}


def test_party_tag_is_the_last_resort():
    report = _report()
    report["teams"]["ct"][2]["partyTag"] = "team-1"
    report["teams"]["ct"][3]["partyTag"] = "team-1"
    assert resolve_my_side(report) == "ct"


def test_a_single_party_tag_is_not_enough():
    report = _report()
    report["teams"]["ct"][2]["partyTag"] = "team-1"
    assert resolve_my_side(report) is None


def test_party_tags_on_both_sides_are_ambiguous():
    report = _report()
    report["teams"]["ct"][0]["partyTag"] = "1"
    report["teams"]["ct"][1]["partyTag"] = "1"
    report["teams"]["t"][0]["partyTag"] = "2"
    report["teams"]["t"][1]["partyTag"] = "2"
    assert resolve_my_side(report) is None


def test_ambiguous_report_keeps_all_ten():
    report = _report()
    assert resolve_my_side(report) is None
    assert len(demo_targets(report)) == 10


def test_lopsided_report_never_skips_the_job():
    report = _report(mySide="ct", teams={"ct": _roster("ct", "ct"), "t": []})
    assert len(demo_targets(report)) == 5


# -- end to end --------------------------------------------------------


def test_demo_job_only_downloads_the_opposing_five(demo_client):
    client, runner, app = demo_client
    host = _host(client)
    response = client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(mySide="ct"),
        headers=_headers(host["token"]),
    )
    assert response.json()["code"] == 0
    _wait_calls(app, 1)

    assert len(runner.calls) == 1
    assert sorted(runner.calls[0].usernames) == [f"t{n}" for n in range(1, 6)]


def test_switching_side_reruns_for_the_other_five(demo_client):
    client, runner, app = demo_client
    host = _host(client)
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(mySide="ct"),
        headers=_headers(host["token"]),
    )
    _wait_calls(app, 1)

    response = client.post(
        "/api/v1/room/MAIN/analysis-side",
        json={"mySide": "t"},
        headers=_headers(host["token"]),
    )
    body = response.json()
    assert body["code"] == 0, body
    assert body["data"]["mySide"] == "t"
    assert body["data"]["targets"] == 5

    _wait_calls(app, 2)
    assert sorted(runner.calls[-1].usernames) == [f"ct{n}" for n in range(1, 6)]
    # The first job already finished, so nothing needed cancelling — and a stray
    # cancel would poison the next run in SubprocessDemoRunner.
    assert runner.cancelled == []


def test_clearing_the_side_returns_to_all_ten(demo_client):
    client, runner, app = demo_client
    host = _host(client)
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(mySide="ct"),
        headers=_headers(host["token"]),
    )
    _wait_calls(app, 1)

    client.post(
        "/api/v1/room/MAIN/analysis-side",
        json={"mySide": None},
        headers=_headers(host["token"]),
    )
    _wait_calls(app, 2)
    assert len(runner.calls[-1].usernames) == 10


def test_re_report_keeps_the_side_already_chosen(demo_client):
    client, runner, app = demo_client
    host = _host(client)
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(mySide="ct"),
        headers=_headers(host["token"]),
    )
    _wait_calls(app, 1)

    # A second PC re-reports the same match without a side.
    client.post(
        "/api/v1/match/report?roomCode=MAIN",
        json=_report(),
        headers=_headers(host["token"]),
    )
    session = app.state.store.sessions()[0]
    assert session.report["mySide"] == "ct"


def test_side_endpoint_needs_a_match(demo_client):
    client, _runner, _app = demo_client
    host = _host(client)
    response = client.post(
        "/api/v1/room/MAIN/analysis-side",
        json={"mySide": "ct"},
        headers=_headers(host["token"]),
    )
    assert response.status_code == 409
    assert response.json()["code"] == 1009


def test_self_marker_decides_the_side():
    """客户端标出的 isSelf 比任何推断都直接：只有对面五个需要下载。"""
    report = _report()
    report["teams"]["ct"][2]["isSelf"] = True

    assert resolve_my_side(report) == "ct"
    assert {p["team"] for p in demo_targets(report)} == {"t"}
    assert len(demo_targets(report)) == 5


def test_self_marker_beats_a_stale_library():
    """以前同队的人这局可能在对面，身份库不该盖过「我在这边」。"""
    report = _report()
    report["teams"]["ct"][0]["isSelf"] = True

    assert resolve_my_side(report, library_side="t") == "ct"
    assert {p["team"] for p in demo_targets(report, "t")} == {"t"}


def test_no_marker_at_all_still_falls_back_to_all_ten():
    """没有 isSelf、也没有身份库时，只能全都分析——这是安全失败，不是错。"""
    report = _report()

    assert resolve_my_side(report) is None
    assert len(demo_targets(report)) == 10


def test_steam_id_never_passes_as_a_5e_domain():
    """没有 domain 时客户端拿 steamId 顶上，19 位数字也能过正则。

    真机事故：5 个对手的 hint 全带 steamId 当 domain，引擎拿它查 5E
    → Arena API error: None，五个人一起失败，一局白跑。
    """
    from app.adapters import to_engine_hints

    report = _report()
    for side in ("ct", "t"):
        for player in report["teams"][side]:
            player["platformUserId"] = player["steamId"]

    assert to_engine_hints(report, "ct") is None


def test_real_domains_still_become_hints():
    from app.adapters import to_engine_hints

    hints = to_engine_hints(_report(), "ct")
    assert hints is not None
    assert len(hints) == 5
    assert {h["domain"] for h in hints} == {f"t{n}" for n in range(1, 6)}
