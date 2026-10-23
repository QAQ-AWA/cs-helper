"""5E 签名与赛季解析：签名必须与 Rust 侧逐字节一致。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import home_client  # noqa: E402


def test_signature_matches_the_rust_known_answer():
    """向量来自 desktop/src-tauri/.../platform_5e_gate_sign.rs 的单元测试。"""

    headers = home_client.build_signed_headers(
        "GET",
        "/cranenew/http/api/data/v3/player/home",
        {"uuid": "ed954be0-7222-11ee-9ce2-ec0d9a495494"},
    )
    assert headers["x-ca-signature"] == "V+81D/A51CzX6Azk0HbElYwxZfLiquWykkaT6k+Z8Io="
    assert headers["x-ca-signature-headers"] == "Accept-Language,Authorization"
    assert headers["x-ca-key"] == "5eplay"


def test_signature_changes_with_the_query():
    first = home_client.build_signed_headers("GET", "/x", {"uuid": "a"})
    second = home_client.build_signed_headers("GET", "/x", {"uuid": "b"})
    assert first["x-ca-signature"] != second["x-ca-signature"]


def test_query_keys_are_sorted_like_btreemap():
    a = home_client.build_signed_headers("GET", "/x", {"b": "2", "a": "1"})
    b = home_client.build_signed_headers("GET", "/x", {"a": "1", "b": "2"})
    assert a["x-ca-signature"] == b["x-ca-signature"]


def test_parse_season_converts_fractions_to_percent():
    body = {
        "code": 0,
        "data": {
            "season_data": {
                "rating": 1.02,
                "avg_rating": 1.087,
                "adr": 78.49,
                "rws": 9.77,
                "kast": 0.66,
                "per_headshot": 0.35,
                "per_win_match": 0.4,
                "match_total": 53,
                "kill": 1200,
                "death": 1290,
            }
        },
    }
    season = home_client.parse_season(body)
    assert season["kast"] == 66.0
    assert season["headshot"] == 35.0
    assert season["winRate"] == 40.0
    assert season["matches"] == 53
    assert season["kd"] == 0.93


def test_parse_season_drops_missing_fields():
    season = home_client.parse_season({"data": {"season_data": {"rating": 1.0}}})
    assert season == {"rating": 1.0}


def test_signature_failure_is_flagged_not_swallowed(monkeypatch):
    def boom(uuid):
        raise home_client.GateSignatureError("HTTP 403")

    monkeypatch.setattr(home_client, "fetch_home", boom)
    seasons, failures, signature_failed = home_client.fetch_seasons(
        ["a", "b"], {"a": "uuid-a", "b": "uuid-b"}
    )
    assert seasons == {}
    assert signature_failed is True
    assert len(failures) == 2


def test_missing_uuid_is_reported_per_player(monkeypatch):
    monkeypatch.setattr(home_client, "fetch_home", lambda uuid: {"data": {"season_data": {}}})
    seasons, failures, signature_failed = home_client.fetch_seasons(["a"], {})
    assert seasons == {}
    assert signature_failed is False
    assert failures[0]["reason"].startswith("找不到")
