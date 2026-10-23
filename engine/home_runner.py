"""Fetch 5E season data (`player/home`) in a child process.

Same contract style as ``job_runner.py``: JSON in on stdin, JSON lines out on
stdout. Kept in a subprocess for two reasons — a signature failure must not take
the relay down, and the relay's request threads should never block on 5E.

    stdin   {"players": [{"domain": "1204gmjzkzoj", "nickname": "半团空气"}]}
    stdout  {"type":"player","domain":...,"season":{...}}
            {"type":"done","resolved":n,"failed":[...],"signatureFailed":bool}
            {"type":"error","message":...}
    exit    0 when at least one player resolved, 1 otherwise
"""

from __future__ import annotations

import json
import sys


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        _emit({"type": "error", "message": f"invalid home payload: {exc}"})
        return 1

    players = payload.get("players") or []
    domains = [str(p.get("domain") or "").strip() for p in players if isinstance(p, dict)]
    domains = [d for d in dict.fromkeys(domains) if d]
    if not domains:
        _emit({"type": "done", "resolved": 0, "failed": [], "signatureFailed": False})
        return 0

    try:
        import home_client
    except Exception as exc:  # noqa: BLE001
        _emit({"type": "error", "message": f"cannot import home_client: {exc}"})
        return 1

    try:
        uuid_by_domain = home_client.resolve_uuids(domains)
    except Exception as exc:  # noqa: BLE001 - uuid 解析失败按整体失败处理
        _emit({"type": "error", "message": f"uuid bootstrap failed: {exc}"})
        return 1

    seasons, failures, signature_failed = home_client.fetch_seasons(domains, uuid_by_domain)
    for domain, season in seasons.items():
        _emit({"type": "player", "domain": domain, "season": season})

    _emit(
        {
            "type": "done",
            "resolved": len(seasons),
            "requested": len(domains),
            "failed": failures,
            "signatureFailed": signature_failed,
        }
    )
    return 0 if seasons else 1


if __name__ == "__main__":
    sys.exit(main())
