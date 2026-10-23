"""Run one parsing job in an isolated child process.

Why a process instead of a thread: ``config.py`` binds ``OUTPUT_DIR`` /
``DEMO_DIR`` / ``MAPS_DIR`` at import time from environment variables. Giving
each job its own process means per-job output directories without threading a
new parameter through 1600 lines of pipeline code. It also makes cancellation a
``terminate()`` and keeps a parser crash from taking the relay down.

Contract with the parent (`server/app/engine_runner.py`):

    stdin   one JSON object: {usernames, mapName, maxDemos, hints, mode,
                              outputDir, demoDir, mapsDir}
    stdout  JSON lines: {"type":"progress"|"done"|"error", ...}
    exit    0 on success, 1 on failure
"""

from __future__ import annotations

import json
import os
import sys


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        _emit({"type": "error", "message": f"invalid job payload: {exc}"})
        return 1

    missing = [key for key in ("outputDir", "demoDir", "mapsDir", "usernames", "mapName") if key not in payload]
    if missing:
        _emit({"type": "error", "message": f"job payload missing: {', '.join(missing)}"})
        return 1

    # Must happen before importing the engine: config reads these at import time.
    os.environ["CS_SCOUT_OUTPUT_DIR"] = payload["outputDir"]
    os.environ["CS_SCOUT_DEMO_DIR"] = payload["demoDir"]
    os.environ["CS_SCOUT_MAPS_DIR"] = payload["mapsDir"]

    import pipeline  # noqa: E402  (import order is the point)

    def progress_cb(index, total, name, step, message):
        _emit(
            {
                "type": "progress",
                "i": index,
                "total": total,
                "name": name,
                "step": step,
                "msg": str(message)[:200],
            }
        )

    runner = pipeline.run_fast if payload.get("mode") == "fast" else pipeline.run
    try:
        results, failed = runner(
            payload["usernames"],
            payload["mapName"],
            max_demos=int(payload.get("maxDemos") or 6),
            progress_cb=progress_cb,
            player_hints=payload.get("hints") or None,
        )
    except Exception as exc:  # surfaced to the parent as a job failure
        _emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"[:500]})
        return 1

    _emit({"type": "done", "results": results, "failed": failed})
    return 0


if __name__ == "__main__":
    sys.exit(main())
