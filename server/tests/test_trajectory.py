"""Opening habits come from paths + bomb sites, never from guesswork."""

import pytest

from app import settings as app_settings
from app.trajectory import build_profile, merge_anchors, sample_at, zone_of


@pytest.fixture(autouse=True)
def isolated_anchors(monkeypatch, tmp_path):
    monkeypatch.setattr(app_settings, "DATA_DIR", tmp_path)


def _path(*points):
    return [[float(t), float(x), float(y)] for t, x, y in points]


def _player(name, rounds):
    return {"steamId": name, "nickname": name, "replay": {"rounds": rounds}}


def test_sample_at_interpolates_between_samples():
    path = _path((0, 0, 0), (10, 100, -100))
    assert sample_at(path, 5) == (50.0, -50.0)
    assert sample_at(path, 0) == (0.0, 0.0)
    assert sample_at(path, 99) == (100.0, -100.0)
    assert sample_at([], 3) is None


def test_zone_of_uses_radius_and_falls_back_to_other():
    anchors = {"A": [1000.0, 1000.0], "B": [-1000.0, -1000.0]}
    assert zone_of((1100, 1100), anchors) == "A"
    assert zone_of((-900, -900), anchors) == "B"
    assert zone_of((0, 0), anchors) == "other"
    assert zone_of((0, 0), {}) == "unknown"
    assert zone_of(None, anchors) == "unknown"


def test_anchors_accumulate_across_demos_and_use_medians():
    first = merge_anchors("de_mirage", [{"site": "A", "x": 1000, "y": 1000}])
    assert first == {"A": [1000.0, 1000.0]}

    second = merge_anchors(
        "de_mirage",
        [{"site": "A", "x": 1200, "y": 800}, {"site": "B", "x": -1000, "y": -1000}],
    )
    # Median of (1000,1000), (1200,800) — a single demo rarely plants both sites.
    assert second["A"] == [1100.0, 900.0]
    assert second["B"] == [-1000.0, -1000.0]


def test_profile_reads_ct_setup_and_t_plants():
    ct = _player(
        "ct1",
        [
            {"side": "CT", "path": _path((0, 1000, 1000), (20, 1000, 1000))},
            {"side": "CT", "path": _path((0, -1000, -1000), (20, -1000, -1000))},
            {"side": "CT", "path": _path((0, 0, 0), (20, 0, 0))},
        ],
    )
    t_side = _player(
        "t1",
        [
            {
                "side": "T",
                "path": _path((0, 0, 0), (20, 1000, 1000)),
                "plant": {"site": "A", "x": 1000, "y": 1000, "t": 31.0},
            },
            {
                "side": "T",
                "path": _path((0, 0, 0), (20, -1000, -1000)),
                "plant": {"site": "B", "x": -1000, "y": -1000, "t": 35.0},
            },
            {"side": "T", "path": _path((0, 0, 0), (20, 0, 0))},
        ],
    )
    profile = build_profile("de_mirage", [ct, t_side])

    by_name = {row["name"]: row for row in profile["players"]}
    assert by_name["ct1"]["ct"]["setup"] == {"A": 1, "B": 1, "offsite": 1}
    assert by_name["t1"]["t"]["planted"] == {"A": 1, "B": 1}
    assert by_name["t1"]["t"]["noPlant"] == 1
    assert by_name["t1"]["t"]["avgPlantT"] == 33.0
    assert profile["siteKnown"] == ["A", "B"]


def test_profile_refuses_to_name_sites_without_a_plant():
    player = _player("t1", [{"side": "T", "path": _path((0, 0, 0), (20, 500, 500))}])
    profile = build_profile("de_mirage", [player])
    assert profile["siteKnown"] == []
    assert profile["players"][0]["t"]["planted"] == {}
    assert profile["players"][0]["t"]["noPlant"] == 1


def test_opening_deaths_and_early_utility_are_counted():
    player = _player(
        "t1",
        [
            {
                "side": "T",
                "path": _path((0, 0, 0), (20, 0, 0)),
                "death_t": 12.5,
                "grenades": [
                    {"type": "smoke", "throw_t": 3.0},
                    {"type": "flash", "throw_t": 5.0},
                    {"type": "he", "throw_t": 18.0},
                ],
            },
            {"side": "T", "path": _path((0, 0, 0), (20, 0, 0)), "death_t": 40.0},
        ],
    )
    profile = build_profile("de_mirage", [player])
    row = profile["players"][0]
    assert row["openingDeaths"] == 1
    assert row["earlyUtility"] == {"smoke": 1, "flash": 1}
