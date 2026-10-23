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
