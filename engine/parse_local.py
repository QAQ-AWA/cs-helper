"""Parse a local .dem once and emit one replay per player.

The server normally downloads demos through ``pipeline.run``. During
development the demos are already on disk, so this entry point skips search,
download and the 5E API entirely and reuses a single ``DemoParser`` for the
whole roster (one file open, one event pass).

Protocol (same shape as ``job_runner.py``):

    stdin    {"demoPath": "...", "players": [{"steamid": "...", "username": "..."}],
              "outputDir": "..."}
    stdout   {"type": "progress", "index": 1, "total": 10, "username": "..."}
             {"type": "player", "steamid": "...", "username": "...", "rounds": 18,
              "bytes": 179000, "player_json": "7656....json"}
             {"type": "done", "results": [...], "failed": [...]}
    stderr   human readable logs
"""

from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    raw = sys.stdin.read()
    try:
        job = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        _emit({"type": "error", "message": f"invalid job payload: {exc}"})
        return 1

    demo_path = str(job.get("demoPath") or "")
    players = job.get("players") or []
    output_dir = str(job.get("outputDir") or "")
    if not demo_path or not output_dir or not players:
        _emit({"type": "error", "message": "demoPath, outputDir and players are required"})
        return 1
    if not os.path.isfile(demo_path):
        _emit({"type": "error", "message": f"demo not found: {demo_path}"})
        return 1

    os.makedirs(output_dir, exist_ok=True)

    import combat
    import parse
    import player_json
    from demoparser2 import DemoParser

    try:
        parser = DemoParser(demo_path)
        header = parser.parse_header()
        map_name = str(header.get("map_name") or "")
        events = dict(
            parser.parse_events(
                ["round_freeze_end", "round_announce_match_start", "round_end", "player_death"],
                other=["tick"],
            )
        )
        round_table = parse.get_round_table(events)
    except Exception as exc:  # noqa: BLE001 - report, never crash the parent
        _emit({"type": "error", "message": f"cannot open demo: {exc}"})
        return 1

    if not round_table:
        _emit({"type": "error", "message": "demo 里没有可用的回合记录"})
        return 1

    results: list[dict] = []
    failed: list[dict] = []
    for index, player in enumerate(players, 1):
        steamid = str(player.get("steamid") or "").strip()
        username = str(player.get("username") or steamid)
        _emit({"type": "progress", "index": index, "total": len(players), "username": username})
        if not steamid:
            failed.append({"username": username, "reason": "缺少 steamid"})
            continue
        try:
            classified = parse.classify_rounds(parser, round_table, {steamid})
            positions = parse.parse_positions(parser, classified, steamid)
            nades = parse.parse_grenades_for_rounds(parser, classified, steamid)
            deaths = parse.parse_deaths_for_rounds(events, classified, steamid)
            records = [
                {
                    "side": row["side"],
                    "rtype": row["rtype"],
                    "official_num": row["official_num"],
                    "path": row["path"],
                    "grenades": nades.get(row["official_num"], []),
                    "death_t": deaths.get(row["official_num"]),
                }
                for row in positions
            ]
            stats = combat.parse_combat_stats_from_context(parser, events, steamid, classified)
            payload = player_json.build(username, "local", steamid, map_name, records, stats)
        except Exception as exc:  # noqa: BLE001 - one bad player must not stop the rest
            traceback.print_exc(file=sys.stderr)
            failed.append({"username": username, "reason": str(exc)[:200]})
            continue

        name = f"{steamid}.json"
        path = os.path.join(output_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        item = {
            "type": "player",
            "steamid": steamid,
            "username": username,
            "domain": "local",
            "rounds": payload["round_count"],
            "bytes": os.path.getsize(path),
            "player_json": name,
        }
        results.append(item)
        _emit(item)

    _emit({"type": "done", "results": results, "failed": failed, "map": map_name})
    return 0


if __name__ == "__main__":
    sys.exit(main())
