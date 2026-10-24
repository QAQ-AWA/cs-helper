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


def test_parse_demo_retries_by_nickname_when_the_steamid_is_wrong(monkeypatch):
    """5E 的 demo 列表可能给出和录像不一致的 steamId，按昵称再认一次。"""

    import parse

    calls: list[str] = []

    def fake_context(path, steamid):
        calls.append(str(steamid))
        if str(steamid) == "wrong":
            return [], None, {}, []
        return [{"side": "CT", "rtype": "Pistol", "path": []}], None, {}, []

    monkeypatch.setattr(parse, "parse_demo_with_context", fake_context)
    monkeypatch.setattr(parse, "resolve_steamid_by_name", lambda path, name: "right")

    records = parse.parse_demo("demo.dem", "wrong", "KILLER8号")

    assert calls == ["wrong", "right"]
    assert len(records) == 1


def test_parse_demo_does_not_retry_without_a_nickname(monkeypatch):
    import parse

    calls: list[str] = []
    monkeypatch.setattr(
        parse, "parse_demo_with_context", lambda path, sid: (calls.append(sid) or ([], None, {}, []))
    )
    monkeypatch.setattr(parse, "resolve_steamid_by_name", lambda path, name: "right")

    assert parse.parse_demo("demo.dem", "wrong") == []
    assert calls == ["wrong"]
