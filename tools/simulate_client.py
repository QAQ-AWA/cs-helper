"""模拟 PC 客户端：没有 CS2/5E 时也能把房间跑起来，用于验证手机 UI。

    python tools/simulate_client.py --server http://127.0.0.1:8787 --seed-paths --post-after 20 --tail

做的事：建房（或复用）→ 上报一场 10 人对局 →（可选）塞一条合成轨迹 →
（可选）等 N 秒上报赛后战报 →（可选）保持 WebSocket 打印事件。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import requests

CT = [
    ("Alpha", "player_alpha", 1.18, 1.25, 48.0, 54.0),
    ("Bravo", "player_bravo", 1.05, 1.12, 44.0, 51.0),
    ("Charlie", "player_charlie", 0.98, 0.96, 41.0, 48.0),
    ("Delta", "player_delta", 0.92, 0.88, 39.0, 46.0),
    ("Echo", "player_echo", 1.24, 1.31, 52.0, 57.0),
]
T = [
    ("Foxtrot", "player_foxtrot", 1.15, 1.20, 46.0, 53.0),
    ("Golf", "player_golf", 1.02, 1.08, 43.0, 50.0),
    ("Hotel", "player_hotel", 0.95, 0.92, 40.0, 47.0),
    ("India", "player_india", 1.21, 1.28, 50.0, 55.0),
    ("Juliet", "player_juliet", 0.89, 0.85, 38.0, 45.0),
]


def player(index: int, row: tuple, team: str) -> dict:
    name, domain, rating, kd, hs, win = row
    return {
        "steamId": f"7656119800000{index:04d}",
        "platformUserId": domain,
        "nickname": name,
        "isSelf": index == 0,
        "stats": {
            "rating": rating,
            "kd": kd,
            "headshotRate": hs,
            "winRate": win,
            "matchesPlayed": 120 + index * 7,
        },
        "team": team,
    }


def build_report(map_name: str, match_id: str, platform: str = "5e") -> dict:
    return {
        "protocolVersion": 1,
        "clientVersion": "sim",
        "platform": platform,
        "matchId": match_id,
        "mapName": map_name,
        "phase": "ready",
        "countdownSeconds": 58,
        "teams": {
            "ct": [player(i, row, "ct") for i, row in enumerate(CT)],
            "t": [player(i + 5, row, "t") for i, row in enumerate(T)],
        },
    }


def build_post_match(match_id: str, map_name: str) -> dict:
    players = []
    for index, row in enumerate(CT + T):
        name = row[0]
        team_side = 1 if index < 5 else 2
        players.append(
            {
                "uid": f"u{index}",
                "nickname": name,
                "teamSide": team_side,
                "kill": 24 - index,
                "death": 14 + index // 2,
                "assist": 4 + index % 3,
                "rating": round(1.3 - index * 0.03, 2),
                "adr": round(92 - index * 2.1, 1),
                "isMvp": index == 0,
                "isSvp": index == 5,
            }
        )
    return {
        "matchCode": match_id,
        "mapName": map_name,
        "roundTotal": 23,
        "scoreA": 13,
        "scoreB": 10,
        "winnerSide": "A",
        "halfScores": {"fhA": 7, "shA": 6, "fhB": 5, "shB": 5},
        "players": players,
        "comparison": {"isCorrect": True, "headline": "AI 赛前看好的 A 队获胜，预测命中"},
        "isFinished": True,
    }


async def tail(ws_url: str, seconds: float) -> None:
    import websockets

    print(f"[ws] {ws_url}")
    async with websockets.connect(ws_url, open_timeout=10) as ws:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.5, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            message = json.loads(raw)
            print(f"[event] {message['seq']:>3} {message['action']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="模拟 PC 客户端")
    parser.add_argument("--server", default="http://127.0.0.1:8787")
    parser.add_argument("--room", default="", help="已有房间码；留空则建房")
    parser.add_argument("--map", default="de_mirage")
    parser.add_argument(
        "--platform",
        default="5e",
        choices=["5e", "perfect"],
        help="perfect 会跳过 Demo 检索，适合纯 UI 演示",
    )
    parser.add_argument("--match-id", default=f"sim{int(time.time())}")
    parser.add_argument("--seed-paths", action="store_true", help="调用 /api/v1/dev/seed-paths")
    parser.add_argument("--post-after", type=float, default=0, help="N 秒后上报赛后战报")
    parser.add_argument("--tail", action="store_true", help="保持连接并打印事件")
    parser.add_argument("--tail-seconds", type=float, default=120)
    args = parser.parse_args()

    base = args.server.rstrip("/")
    config = requests.get(f"{base}/api/v1/config", timeout=10).json()["data"]
    print("[config]", config)

    code = args.room or config.get("roomCode")
    if code:
        joined = requests.post(
            f"{base}/api/v1/room/join",
            json={"roomCode": code, "nickname": "PC 房主", "deviceType": "pc"},
            timeout=10,
        ).json()
        if joined["code"] != 0:
            raise SystemExit(f"加入房间失败: {joined}")
        room, token = joined["data"], joined["data"]["token"]
    else:
        created = requests.post(
            f"{base}/api/v1/room/create",
            json={"creatorNickname": "PC 房主", "deviceType": "pc"},
            timeout=10,
        ).json()
        if created["code"] != 0:
            raise SystemExit(f"建房失败: {created}")
        room, token = created["data"], created["data"]["token"]

    code = room["roomCode"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"[room] {code}")

    report = requests.post(
        f"{base}/api/v1/match/report",
        params={"roomCode": code},
        json=build_report(args.map, args.match_id, args.platform),
        headers={**headers, "Idempotency-Key": f"5e:{args.match_id}"},
        timeout=15,
    ).json()
    print("[report]", report.get("code"), report.get("data", {}).get("sessionId"))

    if args.seed_paths:
        seeded = requests.post(
            f"{base}/api/v1/dev/seed-paths", params={"roomCode": code}, headers=headers, timeout=30
        ).json()
        print("[seed]", seeded.get("code"), seeded.get("data") or seeded.get("message"))

    if args.post_after > 0:
        print(f"[wait] {args.post_after}s 后上报赛后战报…")
        time.sleep(args.post_after)
        posted = requests.post(
            f"{base}/api/v1/match/post-report",
            params={"roomCode": code},
            json=build_post_match(args.match_id, args.map),
            headers=headers,
            timeout=15,
        ).json()
        print("[post-match]", posted.get("code"))

    print(f"\n手机打开: {base}/?room={code}\n")
    if args.tail:
        ws_url = base.replace("http", "ws", 1) + f"/ws?token={token}&lastSeq=0"
        try:
            asyncio.run(tail(ws_url, args.tail_seconds))
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
