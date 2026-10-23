"""The evidence pack is where judgement is made locally, not by the model."""

from app.evidence import build_evidence, direction_for, reliability_for


def _player(name, side, **stats):
    return {"nickname": name, "team": side, "stats": stats}


def test_direction_is_measured_against_the_lobby_median():
    players = [
        _player("Alpha", "ct", rating=1.18, kd=1.25, headshotRate=48, winRate=54, matchesPlayed=120),
        _player("Bravo", "t", rating=0.95, kd=0.80, headshotRate=40, winRate=44, matchesPlayed=90),
    ]
    pack = build_evidence("de_mirage", players, my_side="ct")

    by_name = {row["name"]: row for row in pack["players"]}
    assert by_name["Alpha"]["metrics"]["rating"] == {"value": 1.18, "direction": "positive"}
    assert by_name["Bravo"]["metrics"]["rating"] == {"value": 0.95, "direction": "negative"}
    assert by_name["Alpha"]["role"] == "我方"
    assert by_name["Bravo"]["role"] == "对方"
    assert pack["match"]["opponentSide"] == "t"


def test_small_differences_are_neutral_not_signal():
    assert direction_for(1.01, 1.0, 0.03) == "neutral"
    assert direction_for(1.04, 1.0, 0.03) == "positive"
    assert direction_for(None, 1.0, 0.03) == "unknown"


def test_reliability_follows_sample_size():
    assert reliability_for(120) == "high"
    assert reliability_for(30) == "high"
    assert reliability_for(29) == "medium"
    assert reliability_for(3) == "low"
    assert reliability_for(None) == "unknown"


def test_low_sample_players_are_flagged_for_the_model():
    players = [
        _player("Alpha", "ct", rating=1.4, matchesPlayed=3),
        _player("Bravo", "t", rating=0.9, matchesPlayed=80),
    ]
    pack = build_evidence("de_mirage", players)
    assert pack["dataQuality"]["lowSamplePlayers"] == ["Alpha"]
    assert "Alpha" in pack["teams"][0]["lowSample"]


def test_missing_metrics_are_declared_instead_of_invented():
    pack = build_evidence("de_dust2", [_player("Alpha", "ct"), _player("Bravo", "t")])
    assert pack["dataQuality"]["available"] is None or pack["dataQuality"]["available"] == []
    assert set(pack["dataQuality"]["missing"]) == {"Rating", "K/D", "爆头率", "胜率"}
    assert pack["players"][0]["metrics"]["rating"]["direction"] == "unknown"


def test_without_a_chosen_side_nothing_is_called_ours():
    pack = build_evidence("de_inferno", [_player("Alpha", "ct", rating=1.1)])
    assert pack["match"]["mySide"] is None
    assert pack["players"][0]["role"] == "CT 方"
    assert pack["teams"][0]["role"] == "CT 方"


def test_map_hint_is_carried_through():
    pack = build_evidence("de_nuke", [_player("Alpha", "ct", rating=1.0)])
    assert "垂直" in pack["match"]["mapFit"]
