"""Assemble per-player JSON from parsed rounds + combat stats."""
import maps

def build(username, domain, steamid, map_name, rounds, combat):
    m = maps.load_map(map_name)
    out_rounds = []
    for r in rounds:
        # parse_demo already excludes dropped economy rounds.  Keep this final
        # guard so callers cannot accidentally publish a side-only/None round.
        if r.get("side") not in {"CT", "T"} or r.get("rtype") not in {"Pistol", "Buy"}:
            continue
        out_rounds.append({
            "side": r["side"], "rtype": r["rtype"], "round_id": r["official_num"],
            "path": r["path"], "grenades": r["grenades"],
            "death_t": r.get("death_t"),
            # Bomb site truth for the round (A/B + plant position), when it was
            # planted. Opening-position analysis needs this to name sites.
            "plant": r.get("plant"),
            # 回合所属的 5E 场次：服务端按 (match_code, round_id) 去重。
            "match_code": r.get("match_code"),
        })
    return {
        "username": username, "domain": domain, "steamid": str(steamid),
        "map": map_name, "transform": m["transform"], "radar": m["radar_rel"],
        "combat_stats": combat or {"kd": 0.0, "awp_rate": 0.0},
        "demos_found": 0,   # filled by pipeline
        "round_count": len(out_rounds),
        "rounds": out_rounds,
    }
