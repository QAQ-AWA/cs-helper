"""bomb_planted.site 是地图内的实体索引，每张图都不一样。"""

import parse


def test_known_map_uses_the_table():
    assert parse._site_labels([326, 327]) == {326: "A", 327: "B"}


def test_unknown_indices_fall_back_to_ascending_order():
    # de_dust2 实测 313=A（雷达右侧）、314=B。
    assert parse._site_labels([314, 313, 313]) == {313: "A", 314: "B"}


def test_single_index_is_not_guessed():
    assert parse._site_labels([314]) == {}


def test_no_sites_at_all():
    assert parse._site_labels([]) == {}
