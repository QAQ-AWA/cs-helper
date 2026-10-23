# CS Helper · 对局情报系统

CS2 的「端 · 云 · 多端」一体化项目：**桌面探针采集 → 云端聚合解析 → 队友手机查看**。

本仓库是完整项目，三端都在里面；桌面模块也可脱离云端单独运行。

## 目录

| 目录 | 内容 | 技术栈 | 状态 |
| --- | --- | --- | --- |
| [`desktop/`](desktop/) | 桌面客户端：本机侦测、本地展示、对局上报、习惯轨迹 | Tauri v2 · Rust · Vue 3 · TS | ✅ 可用（284 tests） |
| [`server/`](server/) | 房间与分发服务：上报幂等、画像广播、解析编排、轨迹按需下发 | FastAPI · WebSocket | ✅ 可用（55 tests） |
| [`server/static/`](server/static/) | 手机端 PWA：房间、阵容、选手详情、轨迹回放 | 原生 ESM · Canvas | ✅ P3 |
| [`engine/`](engine/) | Demo 检索、下载、解析引擎 | Python · demoparser2 | ✅ 可用（104 tests） |
| [`contract/`](contract/) | 端云事件契约 | JSON Schema | ✅ v1 |
| [`tools/`](tools/) | 端到端冒烟脚本 | Python | ✅ |
| [`docs/`](docs/) | 架构与路线图 | Markdown | ✅ |

> `desktop/` 来自原来的独立桌面项目 [cs-helper-exe](https://github.com/QAQ-AWA/cs-helper-exe)。
> 那个仓库是**上一代单独发布的桌面版**，可以独立安装使用；本仓库里的 `desktop/` 是纳入统一架构后继续演进的版本，两者不要混为一谈。

## 架构

```
┌── desktop/ ──────────────────────────────────────────────┐
│ 5E CDP 侦测 · 完美世界日志解密 · 就绪倒计时 · 本地展示      │
│ 只上报「看到了什么」，不上报结论                            │
└──────────────┬───────────────────────────────────────────┘
               │ HTTPS 上报（幂等键 platform:matchId）· WSS 订阅
┌──────────────▼──── server/ ──────────────────────────────┐
│ 房间中心 · 任务编排（按 matchId 去重）· 分发（事件+大对象）  │
│ 计算：engine/ 解析 Demo（异步）· AI 编排（可选）              │
└──────────────┬───────────────────────────────────────────┘
               │ WSS
        📱 队友手机（PWA ✅）：房间 · 阵容 · 轨迹回放 · AI
```

服务端是房间状态的唯一权威，PC 与手机看到的内容始终一致。
完整取舍见 [docs/architecture.md](docs/architecture.md)。

## 快速开始

### 服务端

```bash
python -m venv .venv
.venv/Scripts/activate           # Linux/macOS: source .venv/bin/activate
pip install -r server/requirements.txt

export CS_HELPER_SERVER_SECRET='换成随机串'   # 不设则重启后 token 全部失效
python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --app-dir server
```

- 手机/浏览器：`http://<局域网IP>:8787/`（默认单房间，只需输昵称；带 `?room=` 亦可）
- 健康检查：`/healthz`

默认是**单房间模式**，适合自用与固定车队。需要多房间码时设 `CS_HELPER_ROOM_MODE=multi`。

### 桌面客户端

```bash
cd desktop
npm ci
npm run dev          # 开发
npm run build:exe    # 出单文件 exe（src-tauri/target/release/）
```

在客户端的同步设置里把服务端地址填成 `http://<IP>:8787` 即可接入房间。

### 地图资源（回放必需）

```bash
cd engine && python import_radar.py --from-vpk "<CS2>/game" --png-dir <1024px 雷达图目录>
```

变换直接读 CS2 的 `pak01_dir.vpk`；`awpy get maps` 的 CDN 当前被 Cloudflare 拦截。详见 [engine/README.md](engine/README.md)。

### 解析引擎（独立使用）

```bash
pip install -r engine/requirements.txt
cd engine && python -m pytest tests -q
```

## 验证现状

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 服务端 | `cd server && pytest tests -q` | 55 passed |
| 引擎 | `cd engine && pytest tests -q` | 104 passed, 10 skipped（缺 328MB 集成样本） |
| 桌面端 | `cd desktop && npm test` | 284 passed |
| 端到端 | `python tools/smoke_e2e.py`（先启动 8787） | 建房 → 加入 → 上报 → 收到画像 |

## 事件契约

`{protocolVersion, seq, ts, action, payload}`，目录见 [`contract/events.json`](contract/events.json)，与 `server/app/events.py` 互为镜像，漂移时测试失败。

## 许可证与致谢

MIT，见 [LICENSE](LICENSE)；第三方依赖见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

- 桌面客户端衍生自 [qianjiachun/cs-match-helper](https://github.com/qianjiachun/cs-match-helper)，由 [QAQ-AWA](https://github.com/QAQ-AWA) 维护。
- Demo 解析引擎来自 **CS-Scout 2.0**（EytleBB）。

## 免责声明

仅用于赛前情报与赛后复盘。**不读取游戏内存、不注入进程、不提供局内实时敌人位置**；请勿用于破坏平台公平性的用途。
