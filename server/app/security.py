"""Room tokens and lightweight abuse limits."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import time
from threading import Lock

DEFAULT_TTL_SECONDS = 4 * 60 * 60
JOIN_ATTEMPTS_PER_MINUTE = 20


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class TokenService:
    """Compact HMAC tokens: ``base64(payload).base64(signature)``.

    Avoids a JWT dependency while keeping tamper detection and expiry.
    """

    def __init__(self, secret: str | None = None, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        configured = (secret if secret is not None else os.getenv("CS_HELPER_SERVER_SECRET", "")).strip()
        self._ephemeral = not configured
        self._secret = (configured or secrets.token_hex(32)).encode("utf-8")
        self.ttl = ttl

    @property
    def ephemeral(self) -> bool:
        return self._ephemeral

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._secret, body.encode("utf-8"), hashlib.sha256).digest())

    def issue(self, room_code: str, member_id: str, nickname: str, device_type: str) -> tuple[str, int]:
        expires_at = int(time.time()) + self.ttl
        payload = {
            "r": room_code,
            "m": member_id,
            "n": nickname,
            "d": device_type,
            "e": expires_at,
        }
        body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        return f"{body}.{self._sign(body)}", expires_at

    def verify(self, token: str) -> dict | None:
        if not token or token.count(".") != 1:
            return None
        body, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, self._sign(body)):
            return None
        try:
            payload = json.loads(_unb64(body))
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or int(payload.get("e", 0)) < int(time.time()):
            return None
        return payload


class JoinLimiter:
    """Per-IP join attempts, to blunt room-code brute force."""

    def __init__(self, limit: int = JOIN_ATTEMPTS_PER_MINUTE, window: float = 60.0) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


def lan_addresses() -> list[str]:
    """Best-effort LAN IPv4 list so the PC can render a scannable phone URL."""

    found: list[str] = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    unique: list[str] = []
    for ip in found:
        if ip.startswith(("127.", "169.254.")) or ip in unique:
            continue
        unique.append(ip)
    return unique
