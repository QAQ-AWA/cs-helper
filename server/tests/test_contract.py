import json
from pathlib import Path

from app.events import ALL_ACTIONS, PROTOCOL_VERSION
from app.security import JoinLimiter, TokenService

CONTRACT = Path(__file__).resolve().parents[2] / "contract" / "events.json"


def test_event_catalogue_matches_contract_file():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["protocolVersion"] == PROTOCOL_VERSION
    assert tuple(event["action"] for event in data["events"]) == ALL_ACTIONS


def test_token_roundtrip():
    tokens = TokenService("secret", ttl=60)
    token, expires_at = tokens.issue("ABCDEF", "member1", "队友", "mobile")
    payload = tokens.verify(token)
    assert payload is not None
    assert payload["r"] == "ABCDEF"
    assert payload["m"] == "member1"
    assert payload["e"] == expires_at


def test_tampered_token_is_rejected():
    tokens = TokenService("secret", ttl=60)
    token, _ = tokens.issue("ABCDEF", "member1", "队友", "mobile")
    body, signature = token.split(".", 1)
    forged = body[:-1] + ("A" if body[-1] != "A" else "B") + "." + signature
    assert tokens.verify(forged) is None


def test_expired_token_is_rejected():
    tokens = TokenService("secret", ttl=-1)
    token, _ = tokens.issue("ABCDEF", "member1", "队友", "mobile")
    assert tokens.verify(token) is None


def test_token_signed_with_other_secret_is_rejected():
    token, _ = TokenService("a", ttl=60).issue("ABCDEF", "m", "n", "pc")
    assert TokenService("b", ttl=60).verify(token) is None


def test_join_limiter_blocks_after_limit():
    limiter = JoinLimiter(limit=2, window=60)
    assert limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4")
    assert not limiter.allow("1.2.3.4")
    assert limiter.allow("5.6.7.8")


def test_lan_addresses_skip_proxy_tunnels_and_prefer_home_routers():
    from app.security import _is_usable_lan_ip, _lan_priority

    # Proxy TUN / link-local / loopback must never become the phone link.
    assert not _is_usable_lan_ip("198.18.0.1")
    assert not _is_usable_lan_ip("198.19.3.4")
    assert not _is_usable_lan_ip("127.0.0.1")
    assert not _is_usable_lan_ip("169.254.10.1")
    assert not _is_usable_lan_ip("100.64.1.2")

    assert _is_usable_lan_ip("192.168.3.46")
    assert _is_usable_lan_ip("10.0.0.8")
    assert _is_usable_lan_ip("172.20.1.5")

    # 192.168 beats 10.x beats 172.16-31.
    assert _lan_priority("192.168.3.46") < _lan_priority("10.0.0.8") < _lan_priority("172.20.1.5")


def test_lan_addresses_skip_proxy_tunnels_and_prefer_home_routers():
    from app.security import _is_usable_lan_ip, _lan_priority

    # Proxy TUN / link-local / loopback must never become the phone link.
    assert not _is_usable_lan_ip("198.18.0.1")
    assert not _is_usable_lan_ip("198.19.3.4")
    assert not _is_usable_lan_ip("127.0.0.1")
    assert not _is_usable_lan_ip("169.254.10.1")
    assert not _is_usable_lan_ip("100.64.1.2")

    assert _is_usable_lan_ip("192.168.3.46")
    assert _is_usable_lan_ip("10.0.0.8")
    assert _is_usable_lan_ip("172.20.1.5")

    # 192.168 beats 10.x beats 172.16-31.
    assert _lan_priority("192.168.3.46") < _lan_priority("10.0.0.8") < _lan_priority("172.20.1.5")


def test_ws_token_survives_a_server_restart(client):
    """重启后成员表是空的，旧 token 必须还能用（否则客户端 403 死循环）。"""
    import time

    host = client.post("/api/v1/room/create", json={"creatorNickname": "甲", "deviceType": "pc"}).json()["data"]
    token = host["token"]
    room_code = host["roomCode"]

    # 模拟重启：把成员表清空，token 仍在有效期内。
    hub = client.app.state.hub

    # 模拟重启：房间与成员都在内存里，全部丢失，token 仍在有效期内。
    hub.store._rooms.clear()

    payload = hub.tokens.verify(token)
    assert payload and payload["e"] > time.time()

    room2, member = hub.authenticate(token)
    assert room2.code == room_code
    assert member.nickname == "甲"
