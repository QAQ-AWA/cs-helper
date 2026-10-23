# server — 房间与分发服务（P2）

替代上游 `demo/server/web_server.py`。Flask 版本是全局单例状态机（一个进程同时只能跑一个分析，`/api/analyze` 直接 409），无法承载多房间；这里改成 FastAPI + 每房间独立序号与事件环形缓冲。

**已完成**：房间、对局上报、画像广播、WebSocket 增量与断线补齐；Demo 解析任务接入引擎（子进程隔离、进度流、不可变 artifact）。
**未完成**：AI 编排（P4）、按房间配额、Redis 化。

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
| GET | `/api/v1/config` | — | 房间模式与默认房间码，手机端据此决定要不要让用户填码 |
| POST | `/api/v1/room/create` | — | 建房，返回 `roomCode` + `token` |
| POST | `/api/v1/room/join` | — | 加房（按 IP 限流，防房号爆破） |
| GET | `/api/v1/room/network/info` | — | 局域网 IP，供电脑端生成手机链接 |
| GET | `/api/v1/room/{code}/snapshot` | Bearer | 全量状态（成员/对局/画像/latestSeq） |
| POST | `/api/v1/match/report?roomCode=` | Bearer | 上报对局，`platform:matchId` 幂等 |
| GET | `/api/v1/artifacts/{id}` | Bearer | 回放索引（小）；内容寻址、ETag、gzip |
| GET | `/api/v1/artifacts/{id}/players/{steamId}` | Bearer | **单个玩家的回放**，手机按需拉取 |
| WS | `/ws?token=&lastSeq=` | token | 增量事件；断线按 `lastSeq` 补发 |

## 单房间模式（默认）

自用/小队场景不需要多房间，默认只有一个房间 `MAIN`：

- `create` 幂等：重复调用返回同一个房间，按 `(昵称, 设备类型)` 复用成员，重启客户端不会堆积幽灵成员。
- `join` 可以不带房间码。
- 手机端从 `/api/v1/config` 拿到 `roomCode`，用户只需输昵称。

要恢复多房间码系统：`CS_HELPER_ROOM_MODE=multi`（代码路径完整保留，有测试覆盖）。单房间码可用 `CS_HELPER_SINGLE_ROOM_CODE` 改名。

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
cd server && python -m pytest tests -q     # 45 passed（含 node 无头渲染测试）
```

另外跑过一次真实 uvicorn 实例的端到端冒烟：建房 → 手机加入 → 上报 → WS 收到 `MATCH_DETECTED/JOB_PROGRESS/PROFILE_READY` → 快照含 3 名选手。
Demo 任务用真实 `engine/job_runner.py` 验证过子进程链路（进度行、失败原因、退出码）。

## Demo 任务

上报后自动触发，按 `platform:matchId` 全局去重：同一场比赛无论几个房间上报，只解析一次。

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `CS_HELPER_DEMO` | `1` | 设为 `0` 关闭解析任务 |
| `CS_HELPER_DEMO_MAX_DEMOS` | `6` | 每个对手取几场 Demo（1–10） |
| `CS_HELPER_DEMO_MODE` | `normal` | `normal` / `fast`（fast 走进程池并发） |
| `CS_HELPER_WORK_DIR` | `.cache/jobs` | 每个任务独立的输出目录 |
| `CS_HELPER_DEMO_DIR` | `engine/demos_opponents` | Demo 缓存（跨任务共享，用于去重） |
| `CS_HELPER_MAPS_DIR` | `engine/data/maps` | 需先运行 `engine/setup_maps.py` |

流程：`JOB_PROGRESS(stage=demo)` 逐个玩家推进 → 完成后发出 `TACTICAL_PATHS_READY{artifactId}` → 客户端先拉索引，再按需拉 `.../players/{steamId}`（单人回放约 150KB，整队约 750KB）。
地图资源缺失时返回 `ROOM_ERROR{code:2002}`，平台不是 5E 时任务标记 `skipped`。

## 手机端（PWA）

`static/` 下是一个免构建的多文件 PWA，由服务端直接托管（`/` + `/static/*`）：

| 文件 | 职责 |
| --- | --- |
| `mobile.html` | 两个视图：房间（阵容/轨迹列表/AI）与选手详情（回放画布） |
| `mobile.js` | 连接、事件分发、按玩家拉取回放 |
| `mobile.css` | 深色移动端样式 |
| `replay-core.js` | **回放渲染核**：雷达底图 + 路径 + 投掷物，框架无关，桌面端可复用 |
| `manifest.webmanifest` / `sw.js` / `icon.svg` | 可安装、可离线打开外壳（API 永不缓存） |

回放交互：播放/暂停、1x/2x/4x、按阵营过滤、进度条拖动。
渲染依赖 `GET /maps/{map}/radar.png`（从 `engine/data/maps` 提供）；缺失时画网格占位并提示，不会白屏。

### 地图资源（回放的前置条件）

```bash
# A. 官方雷达图（awpy 的 CDN 偶尔返回 403，失败就用 B）
pip install -r engine/requirements-maps.txt
engine/.venv/Scripts/awpy get maps      # 或在已激活的环境里直接 awpy get maps
cd engine && python setup_maps.py

# B. 离线：已有 resource/overviews 的 png+txt（可从 pak01.vpk 解包）
cd engine && python import_radar.py --from-dir D:/overviews
```

没有 `data/maps/<map>/{radar.png,meta.json}` 时，解析任务会在开始时返回 `ROOM_ERROR 2002`，不会跑一半才失败；手机端回放会画网格占位而不是白屏。

## 为什么解析跑子进程

`engine/config.py` 在 **import 时**就从环境变量绑定 `OUTPUT_DIR`，多房间并发会互相覆盖 `player_{domain}.json`。
与其把目录参数穿过 1615 行 pipeline，不如每个任务起一个进程、用环境变量注入目录：同时获得可靠取消（`terminate()`）与崩溃隔离。
