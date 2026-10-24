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


def test_team_plant_totals_are_deduplicated_by_round():
    """同一个下包会出现在每个选手的回合里，横向相加会翻倍。"""
    shared = {"site": "B", "x": -1000, "y": -1000, "t": 40.0}
    players = [
        _player("a", [{"side": "T", "round_id": 7, "path": _path((0, 0, 0), (20, 0, 0)), "plant": shared}]),
        _player("b", [{"side": "T", "round_id": 7, "path": _path((0, 0, 0), (20, 0, 0)), "plant": shared}]),
        _player("c", [
            {"side": "T", "round_id": 7, "path": _path((0, 0, 0), (20, 0, 0)), "plant": shared},
            {"side": "T", "round_id": 8, "path": _path((0, 0, 0), (20, 0, 0)),
             "plant": {"site": "A", "x": 1000, "y": 1000, "t": 44.0}},
        ]),
    ]
    profile = build_profile("de_mirage", players)
    assert profile["teamPlants"]["rounds"] == 2
    assert profile["teamPlants"]["B"] == 1
    assert profile["teamPlants"]["A"] == 1
    assert profile["teamPlants"]["avgT"] == 42.0


def _t_round(round_id, path, plant=None, match_code="m1"):
    item = {"side": "T", "round_id": round_id, "path": path, "match_code": match_code}
    if plant:
        item["plant"] = plant
    return item


def test_team_approach_reads_direction_from_movement():
    """20 秒窗口里看不到落包，但看得到朝哪个包点压。"""
    to_a = _path((0, 0, 0), (20, 900, 900))
    to_b = _path((0, 0, 0), (20, -900, -900))
    rounds = [
        # 两发下包先把 A/B 的锚点立起来
        _t_round(1, to_a, {"site": "A", "x": 1000, "y": 1000, "t": 45.0}),
        _t_round(2, to_b, {"site": "B", "x": -1000, "y": -1000, "t": 40.0}),
        _t_round(3, to_a),
        _t_round(4, to_a),
        _t_round(5, to_b),
    ]
    profile = build_profile("de_dust2", [_player("p", rounds)])

    assert profile["teamApproach"]["rounds"] == 5
    assert profile["teamApproach"]["A"] == 3
    assert profile["teamApproach"]["B"] == 2
    assert profile["players"][0]["t"]["approach"] == {"A": 3, "B": 2}


def test_approach_ignores_players_who_stay_put():
    still = _path((0, 0, 0), (20, 20, 20))
    rounds = [
        _t_round(1, still, {"site": "A", "x": 1000, "y": 1000, "t": 45.0}),
        _t_round(2, still, {"site": "B", "x": -1000, "y": -1000, "t": 40.0}),
    ]
    profile = build_profile("de_dust2", [_player("p", rounds)])

    assert profile["teamApproach"]["rounds"] == 0
    assert profile["players"][0]["t"]["approach"] == {}


def test_same_round_number_in_two_matches_is_not_collapsed():
    """五个人五场，round_id 都从 0 开始；按回合去重必须带 match_code。"""
    to_a = _path((0, 0, 0), (20, 900, 900))
    players = [
        _player("p1", [_t_round(0, to_a, {"site": "A", "x": 1000, "y": 1000, "t": 45.0}, "m1")]),
        _player("p2", [_t_round(0, to_a, {"site": "A", "x": 1000, "y": 1000, "t": 45.0}, "m2")]),
    ]
    profile = build_profile("de_dust2", players)

    assert profile["teamPlants"]["rounds"] == 2
    assert profile["teamPlants"]["A"] == 2
    assert profile["teamApproach"]["rounds"] == 2
