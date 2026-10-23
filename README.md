# CS Helper · 对局情报合集

CS2 的「端 · 云 · 多端」系统：**桌面探针采集 → 云端聚合解析 → 队友手机查看**。

本仓库是**合集**，只放与具体客户端无关的部分；桌面客户端是独立子项目，不在此重复。

| 目录 | 内容 | 状态 |
| --- | --- | --- |
| [`engine/`](engine/) | Demo 检索、下载、解析引擎（Python） | ✅ 可用（97 tests） |
| [`server/`](server/) | 房间与分发服务（FastAPI + WebSocket） | ✅ P1 可用（26 tests） |
| [`contract/`](contract/) | 端云事件契约 | ✅ v1 |
| [`tools/`](tools/) | 端到端冒烟脚本 | ✅ |
| [`docs/`](docs/) | 架构与实施方案 | ✅ |
| `mobile/` | 队友手机端（PWA） | 🚧 P3 |
| `ai-worker/` | 服务端 AI 编排 | 🚧 P4 |

桌面客户端：**[QAQ-AWA/cs-helper-exe](https://github.com/QAQ-AWA/cs-helper-exe)**（Tauri v2 + Vue 3）。
它只负责本机侦测（5E CDP / 完美世界日志）、本地展示与上报，不含解析与分发。

## 为什么拆成两个仓库

- **发版节奏不同**：桌面端跟着安装包走，云端按服务发布，绑在一起会互相阻塞。
- **职责边界清晰**：客户端不解析 Demo（避免占用游戏机 CPU），服务端不接触玩家本机进程与凭据。
- **对齐方式是契约，不是代码**：两端共享 `contract/events.json` 与 `protocolVersion`，客户端升级不会强制服务端同步发版。

> 客户端代码**不复制**到本仓库。需要联调时，克隆两个仓库并让客户端的服务端地址指向本机运行的 `server/`。

## 架构一句话

```
PC 客户端（cs-helper-exe）──上报对局──▶ server（房间/编排/分发）──▶ 队友手机
                                          │
                                          ├─ engine：Demo 下载解析（异步、分钟级）
                                          └─ 画像 / AI（一次调用，多端共享）
```

完整设计与取舍见 [docs/architecture.md](docs/architecture.md)：包含模块归属、事件契约、时延双档、分阶段验收与风险登记。

## 快速开始（服务端）

```bash
python -m venv .venv
.venv/Scripts/activate           # Linux/macOS: source .venv/bin/activate
pip install -r server/requirements.txt

export CS_HELPER_SERVER_SECRET='换成随机串'   # 不设则进程重启后 token 全部失效
python -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --app-dir server
```

- 手机/浏览器：`http://<局域网IP>:8787/?room=<6位房间码>`
- 健康检查：`/healthz`
- 客户端里把同步服务端地址填成 `http://<IP>:8787`

引擎单独运行需要更重的依赖（pandas / demoparser2）：

```bash
pip install -r engine/requirements.txt
cd engine && python -m pytest tests -q
```

## 验证现状

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 服务端 | `cd server && pytest tests -q` | 26 passed |
| 引擎 | `cd engine && pytest tests -q` | 97 passed, 10 skipped（缺 328MB 集成样本） |
| 端到端 | `python tools/smoke_e2e.py`（需先启动 8787 上的实例） | 建房 → 加入 → 上报 → 收到画像 |

## 事件契约

`{protocolVersion, seq, ts, action, payload}`，目录见 [`contract/events.json`](contract/events.json)，与 `server/app/events.py` 互为镜像，漂移时测试会失败。

## 许可证与致谢

MIT。本项目聚合了两份上游代码，版权声明见 [LICENSE](LICENSE)、第三方依赖见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

- 桌面客户端衍生自 [qianjiachun/cs-match-helper](https://github.com/qianjiachun/cs-match-helper)，由 [QAQ-AWA](https://github.com/QAQ-AWA) 维护。
- Demo 解析引擎来自 **CS-Scout 2.0**（EytleBB）。

## 免责声明

仅用于赛前情报与赛后复盘。**不读取游戏内存、不注入进程、不提供局内实时敌人位置**；请勿用于破坏平台公平性的用途。
