# server — 房间与分发服务（P1）

替代 `demo/server/web_server.py`。Flask 版本是全局单例状态机（一个进程同时只能跑一个分析，`/api/analyze` 直接 409），无法承载多房间；这里改成 FastAPI + 每房间独立序号与事件环形缓冲。

**P1 只做"能连上、能同步"**：房间、对局上报、画像广播、WebSocket 增量与断线补齐。Demo 解析与 AI 编排在 P2 接入（`RoomHub.report_match` 是挂载点）。

## 快速开始

```bash
# 仓库根目录
python -m venv .venv
.venv/Scripts/activate            # Windows；Linux/macOS 用 source .venv/bin/activate
pip install -r server/requirements.txt

export CS_HELPER_SERVER_SECRET='换成随机串'   # 不设置则进程重启后所有 token 失效
python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --app-dir server
```

打开：
- 手机/浏览器：`http://<局域网IP>:8787/?room=<6位房间码>`
- 健康检查：`/healthz`

桌面端的 `TeamSyncSettingsSection` 里把服务端地址填成 `http://<IP>:8787` 即可。

## 目录

```
server/
├── app/
│   ├── main.py       # 路由、WebSocket 端点、错误信封
│   ├── models.py     # Pydantic DTO（HTTP 契约）
│   ├── events.py     # 事件目录 + 信封（与 contract/events.json 同步）
│   ├── hub.py        # 房间编排；唯一分配 seq 的地方
│   ├── store.py      # 进程内状态：房间/成员/会话/环形缓冲
│   ├── jobs.py       # 线程池 + JOB_PROGRESS；P2 挂 Demo 任务
│   ├── adapters.py   # MatchReport → 画像 / engine player_hints
│   ├── security.py   # HMAC token、加入限流、局域网 IP
│   └── ws.py         # 每连接队列 + 发送协程，跨线程安全发布
├── static/mobile.html  # P1 手机端（P3 由 Vue PWA 取代）
└── tests/              # 26 个用例
```

## 接口

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/room/create` | — | 建房，返回 `roomCode` + `token` |
| POST | `/api/v1/room/join` | — | 加房（按 IP 限流，防房号爆破） |
| GET | `/api/v1/room/network/info` | — | 局域网 IP，供电脑端生成手机链接 |
| GET | `/api/v1/room/{code}/snapshot` | Bearer | 全量状态（成员/对局/画像/latestSeq） |
| POST | `/api/v1/match/report?roomCode=` | Bearer | 上报对局，`platform:matchId` 幂等 |
| WS | `/ws?token=&lastSeq=` | token | 增量事件；断线按 `lastSeq` 补发 |

错误统一为 `{"code": 1000+, "message": "..."}`，与客户端 `if (json.code !== 0)` 的判断一致。

## 事件

`{protocolVersion, seq, ts, action, payload}`，`action` 名称保持不变以兼容现有 `sync-client.ts`。

`ROOM_STATE_SYNC` / `ROOM_MEMBERS_CHANGED` / `MATCH_DETECTED` / `PROFILE_READY` / `JOB_PROGRESS` / `TACTICAL_PATHS_READY` / `AI_STREAM_CHUNK` / `AI_REPORT_READY` / `POST_MATCH_READY` / `ROOM_ERROR`

目录镜像在 `contract/events.json`，`tests/test_contract.py` 会在两边漂移时失败。

## 三个关键设计

1. **seq 在 `hub.emit` 内分配，且与发布同处一把锁**。这样即使 Demo 解析线程和 HTTP 线程同时发事件，客户端看到的顺序也一致。
2. **重连先补事件、再发快照**。快照永远最后发，并携带 `latestSeq`，客户端据此重置本地序号；快照里已包含 `profiles`，中途进房不依赖历史重放。
3. **每连接独立队列**。慢手机只会丢自己的旧事件（记 warning），不会阻塞其它成员或生产者线程。

## 已验证

```bash
cd server && python -m pytest tests -q     # 26 passed
```

另外跑过一次真实 uvicorn 实例的端到端冒烟：建房 → 手机加入 → 上报 → WS 收到 `MATCH_DETECTED/JOB_PROGRESS/PROFILE_READY` → 快照含 3 名选手。

## P2 待办

- `jobs.py` 接入 `engine/`：`pipeline.run(..., player_hints=adapters.to_engine_hints(report))`。
- `artifacts.py`：大对象存储 + ETag + 按玩家懒加载（WS 只发 `artifactId`）。
- 会话按 `platform:matchId` 全局去重后，仍需按房间做解析配额与取消。
- `store.py` 换 Redis（接口已按可替换的方式设计，但尚未抽出 Protocol）。
- 服务端画像补全：目前 `PROFILE_READY.source = "client"`，需接入平台接口后标记为 `"server"`。
