"""5E season enrichment: best-effort, never blocking, always explained."""

import time

import pytest
from fastapi.testclient import TestClient

from conftest import make_report
from app.evidence import build_evidence
from app.home_enrich import HomeOutcome, SIGNATURE_HINT, merge_season_stats
from app.main import create_app

SEASONS = {
    "player_a": {
        "rating": 1.12,
        "avgRating": 1.18,
        "adr": 86.4,
        "rws": 10.2,
        "kast": 72.5,
        "matches": 61,
        "winRate": 58.0,
        "headshot": 51.0,
    },
    "player_b": {
        "rating": 0.94,
        "avgRating": 0.91,
        "adr": 68.1,
        "rws": 6.8,
        "kast": 64.0,
        "matches": 44,
        "winRate": 41.0,
    },
}


class FakeHome:
    def __init__(self, seasons=None, signature=False, error=None):
        self.seasons = seasons if seasons is not None else dict(SEASONS)
        self.signature = signature
        self.error = error
        self.calls = 0

    def fetch(self, players):
        self.calls += 1
        if self.signature:
            return HomeOutcome(signature_failed=True, error=SIGNATURE_HINT)
        return HomeOutcome(seasons=dict(self.seasons), error=self.error)


def _client(home):
    app = create_app(
        secret="test-secret",
        demo_runner=None,
        room_mode="multi",
        ai_client=None,
        home_client=home,
    )
    return app, TestClient(app)


def _wait(client, room, predicate, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(
            f"/api/v1/room/{room['roomCode']}/snapshot",
            headers={"Authorization": f"Bearer {room['token']}"},
        ).json()["data"]
        if predicate(data):
            return data
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


# -- merge rules -------------------------------------------------------


def test_season_fields_are_attached_without_overwriting_the_client():
    profiles = [
        {
            "platformUserId": "player_a",
            "stats": {"rating": 1.3, "kd": 1.4, "matchesPlayed": 120},
        }
    ]
    merged = merge_season_stats(profiles, SEASONS)
    stats = profiles[0]["stats"]
    assert merged == 1
    # Client values win; season values fill the gaps and add namespaced extras.
    assert stats["rating"] == 1.3
    assert stats["matchesPlayed"] == 120
    assert stats["seasonAdr"] == 86.4
    assert stats["seasonKast"] == 72.5


def test_placeholder_values_are_replaced_by_season_data():
    profiles = [
        {
            "platformUserId": "player_b",
            "stats": {"rating": 1, "kd": 1, "matchesPlayed": 0, "winRate": 50},
        }
    ]
    merge_season_stats(profiles, SEASONS)
    stats = profiles[0]["stats"]
    # 1 / 0 / 50 are the desktop's "unknown" placeholders, not real values.
    assert stats["rating"] == 0.91
    assert stats["matchesPlayed"] == 44
    assert stats["winRate"] == 50  # a plausible 50% is left alone


def test_evidence_uses_the_new_metrics():
    pack = build_evidence(
        "de_mirage",
        [
            {"nickname": "Alpha", "team": "ct", "stats": {"rating": 1.1, "seasonAdr": 86.4, "seasonRws": 10.2}},
            {"nickname": "Bravo", "team": "t", "stats": {"rating": 0.9, "seasonAdr": 68.1, "seasonRws": 6.8}},
        ],
    )
    assert "ADR" in pack["dataQuality"]["available"]
    assert "KAST" in pack["dataQuality"]["missing"]
    by_name = {row["name"]: row for row in pack["players"]}
    assert by_name["Alpha"]["metrics"]["seasonAdr"]["direction"] == "positive"
    assert by_name["Bravo"]["metrics"]["seasonAdr"]["direction"] == "negative"


# -- end to end --------------------------------------------------------


def test_profiles_are_enriched_before_the_ai_pass():
    home = FakeHome()
    app, client = _client(home)
    with client:
        room = client.post("/api/v1/room/create", json={}).json()["data"]
        client.post(
            f"/api/v1/match/report?roomCode={room['roomCode']}",
            json=make_report(),
            headers={"Authorization": f"Bearer {room['token']}"},
        )
        data = _wait(client, room, lambda snap: (snap["match"] or {}).get("homeState") == "ready")

    assert home.calls == 1
    assert data["match"]["homeCoverage"] == 2
    assert data["match"]["homeError"] is None
    stats = {p["nickname"]: p["stats"] for p in data["profiles"]}
    assert stats["Alpha"]["seasonAdr"] == 86.4
    assert stats["Bravo"]["seasonRws"] == 6.8


def test_rotated_signature_is_explained_and_never_blocks():
    home = FakeHome(signature=True)
    app, client = _client(home)
    with client:
        room = client.post("/api/v1/room/create", json={}).json()["data"]
        with client.websocket_connect(f"/ws?token={room['token']}") as ws:
            ws.receive_json()
            client.post(
                f"/api/v1/match/report?roomCode={room['roomCode']}",
                json=make_report(),
                headers={"Authorization": f"Bearer {room['token']}"},
            )
            error = None
            for _ in range(12):
                message = ws.receive_json()
                if message["action"] == "ROOM_ERROR" and message["payload"].get("stage") == "home":
                    error = message["payload"]
                    break

        data = _wait(client, room, lambda snap: (snap["match"] or {}).get("homeState") == "signature")

    assert error is not None and error["code"] == 2007
    assert "签名" in error["message"]
    # The rest of the pipeline still ran on client-reported stats.
    assert data["match"]["profileState"] == "ready"
    assert data["match"]["homeError"] == SIGNATURE_HINT


def test_complete_client_upload_skips_the_gateway():
    """The desktop already sends its season sheet; refetching it is pure waste."""

    home = FakeHome()
    app, client = _client(home)
    report = make_report()
    for team in report["teams"].values():
        for player in team:
            player["stats"] = {"rating": 1.1, "kd": 1.0, "seasonAdr": 80.0, "matchesPlayed": 40}
    with client:
        room = client.post("/api/v1/room/create", json={}).json()["data"]
        client.post(
            f"/api/v1/match/report?roomCode={room['roomCode']}",
            json=report,
            headers={"Authorization": f"Bearer {room['token']}"},
        )
        data = _wait(client, room, lambda snap: (snap["match"] or {}).get("homeState") == "ready")

    assert home.calls == 0
    assert data["match"]["homeCoverage"] == 2


def test_home_can_be_switched_off():
    app = create_app(
        secret="test-secret", demo_runner=None, room_mode="multi", ai_client=None, home_client=None
    )
    with TestClient(app) as client:
        room = client.post("/api/v1/room/create", json={}).json()["data"]
        client.post(
            f"/api/v1/match/report?roomCode={room['roomCode']}",
            json=make_report(),
            headers={"Authorization": f"Bearer {room['token']}"},
        )
        data = _wait(client, room, lambda snap: (snap["match"] or {}).get("homeState") == "skipped")
    assert data["match"]["homeCoverage"] == 0


def test_season_average_replaces_the_duplicated_client_rating():
    """客户端拿不到场均时会用本图生涯 Rating 顶上，结果和 seasonRating 一模一样。"""

    from app.home_enrich import merge_season_stats

    profiles = [
        {"platformUserId": "p1", "stats": {"rating": 0.97, "seasonRating": 0.97}},
    ]
    seasons = {"p1": {"rating": 0.97, "avgRating": 1.065}}
    merge_season_stats(profiles, seasons)

    stats = profiles[0]["stats"]
    assert stats["seasonRating"] == 0.97
    assert stats["rating"] == 1.065


def test_a_genuinely_different_client_rating_is_kept():
    from app.home_enrich import merge_season_stats

    profiles = [
        {"platformUserId": "p1", "stats": {"rating": 1.20, "seasonRating": 0.97}},
    ]
    seasons = {"p1": {"rating": 0.97, "avgRating": 1.065}}
    merge_season_stats(profiles, seasons)

    # 客户端报的是独立来源（近几场），不该被赛季场均盖掉。
    assert profiles[0]["stats"]["rating"] == 1.20


def test_duplicate_detection_uses_the_clients_own_season_rating():
    """客户端报的 1.14 是它自己的赛季值，服务端把它更新成 1.15 之后
    仍然要认出「近期」那一列是复制品，否则两列还是一样。"""

    from app.home_enrich import merge_season_stats

    profiles = [{"platformUserId": "p1", "stats": {"rating": 1.14, "seasonRating": 1.14}}]
    merge_season_stats(profiles, {"p1": {"rating": 1.15, "avgRating": 1.087}})

    stats = profiles[0]["stats"]
    assert stats["seasonRating"] == 1.15
    assert stats["rating"] == 1.087
