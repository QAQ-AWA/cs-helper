"""End-to-end smoke test against a real uvicorn instance (not TestClient)."""

import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://127.0.0.1:8799"
WS = "ws://127.0.0.1:8799/ws"

REPORT = {
    "protocolVersion": 1,
    "clientVersion": "4.0.0",
    "platform": "5e",
    "matchId": "2603212003001",
    "mapName": "de_mirage",
    "phase": "ready",
    "countdownSeconds": 58,
    "teams": {
        "ct": [
            {"steamId": "76561198000000002", "platformUserId": "player_a", "nickname": "Alpha",
             "stats": {"rating": 1.18, "kd": 1.25}},
            {"steamId": "76561198000000004", "platformUserId": "player_c", "nickname": "Charlie"},
        ],
        "t": [
            {"steamId": "76561198000000003", "platformUserId": "player_b", "nickname": "Bravo",
             "stats": {"rating": 0.95, "kd": 0.88}},
        ],
    },
}


async def main() -> int:
    async with httpx.AsyncClient(timeout=10) as http:
        health = (await http.get(f"{BASE}/healthz")).json()
        print("healthz:", health)

        page = await http.get(f"{BASE}/")
        assert page.status_code == 200 and "CS Helper" in page.text
        print("mobile page bytes:", len(page.text))

        config = (await http.get(f"{BASE}/api/v1/config")).json()["data"]
        print("config:", config)
        assert config["mode"] == "single"

        created = (await http.post(f"{BASE}/api/v1/room/create", json={"creatorNickname": "房主"})).json()
        assert created["code"] == 0, created
        room = created["data"]
        print("room:", room["roomCode"], "joinUrl:", room["joinUrl"])
        assert room["roomCode"] == config["roomCode"]

        joined = (
            await http.post(
                f"{BASE}/api/v1/room/join",
                json={"nickname": "手机队友", "deviceType": "mobile"},  # no code in single mode
            )
        ).json()
        assert joined["code"] == 0, joined

        async with websockets.connect(f"{WS}?token={joined['data']['token']}", open_timeout=5) as ws:
            state = json.loads(await asyncio.wait_for(ws.recv(), 5))
            assert state["action"] == "ROOM_STATE_SYNC", state
            print("ws state members:", [m["nickname"] for m in state["payload"]["members"]])

            report = await http.post(
                f"{BASE}/api/v1/match/report?roomCode={room['roomCode']}",
                json=REPORT,
                headers={"Authorization": f"Bearer {room['token']}"},
            )
            assert report.json()["code"] == 0, report.text

            seen = []
            for _ in range(8):
                msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
                seen.append(f"{msg['seq']}:{msg['action']}")
                if msg["action"] == "PROFILE_READY":
                    players = msg["payload"]["players"]
                    print("profile players:", [(p["nickname"], p["team"]) for p in players])
                    break
            print("ws events:", seen)

            snapshot = await http.get(
                f"{BASE}/api/v1/room/{room['roomCode']}/snapshot",
                headers={"Authorization": f"Bearer {room['token']}"},
            )
            data = snapshot.json()["data"]
            print("snapshot seq:", data["latestSeq"], "match:", data["match"]["matchId"])

            assert any(s.endswith("PROFILE_READY") for s in seen), seen
            assert len(data["profiles"]) == 3

    print("E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
