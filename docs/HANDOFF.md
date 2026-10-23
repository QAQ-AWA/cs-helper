# 开发交接文档（2026-10-23）

> 本文件供下一个 AI / 新的开发会话快速接手。精炼版约定见 `.workbuddy/memory/MEMORY.md`（会话开始时自动注入），实测明细见 `.workbuddy/memory/2026-10-23.md`。

## 一句话项目

CS2 开黑辅助：**PC 客户端**侦测对局并上报阵容 → **服务端**聚合房间、拉取并解析对手历史 Demo、跑 AI 战术分析 → **手机 PWA** 实时展示十人画像、习惯轨迹与赛后复盘。只做**赛前历史数据**（合规红线：不读内存、不注入、不做局内实时敌人位置）。

## 仓库

- 主仓库：`QAQ-AWA/cs-helper`（remote 名 `helper`），单一 main 分支
- 构建仓库：`QAQ-AWA/cs-test`（remote 名 `test`），push 即触发 GitHub Actions 出 Windows exe 到 `latest-build` 预发布；打 `v*` tag 发正式版
- 注意：本地 main 上游是 `test/main`，`git push` 默认推构建仓库；推主仓库要显式 `git push helper main`
- 只读禁区：`I:\code项目\CS`（旧桌面项目）、`I:\code项目\demo`（engine 上游），不要改

## 架构

```
桌面 desktop/（Tauri2+Rust+Vue3）
  ├─ Rust 侦测层（5E CDP/WS、完美世界）── 上报 MatchRecord
  ├─ src/core/sync/report-builder.ts ── MatchRecord→MatchReport（Perfect assigned 过滤、幂等键 platform:matchId）
  └─ src/core/sync/sync-client.ts ──── lastSeq 续传 / snapshot 补齐 / 赛后战报上报
服务端 server/（FastAPI）
  ├─ hub.py ──── 房间编排，唯一分配 seq 的地方（同锁内分配+发布）
  ├─ store.py ── 房间/会话/环形缓冲（内存，重启即清空）
  ├─ ws.py ────── 每连接有界队列；重连先补事件、快照最后发
  ├─ jobs.py ──── 画像(秒级) → AI(流式) → Demo 任务；按 platform:matchId 全局去重
  ├─ engine_runner.py ── 子进程管理（见"为什么跑子进程"）
  ├─ artifacts.py ────── 内容寻址存储：索引(~1KB) + 按玩家 parts(~150KB)
  └─ devtools.py ─────── DEV=1 时的合成轨迹与本地 .dem 直通解析
引擎 engine/（纯 Python，CS-Scout 2.0 抽离）
  ├─ job_runner.py ── 5E 链路子进程入口（检索→下载→解析）
  ├─ parse_local.py ── 本地 .dem 直通（一次 open 解析多人）
  └─ config/maps/parse/player_json/combat/api_client/pipeline/vpk
契约 contract/events.json ── 与 server/app/events.py 互为镜像，漂移即测试失败
```

手机端在 `server/static/`（mobile.html/css/js + replay-core.js + sw.js），同一渲染核经 vite `@shared` 别名被桌面端复用。

## 开发历程（提交序）

| commit | 内容 |
| --- | --- |
| `5f4aabf` | 合集仓库初始化（engine+server+contract+docs，不含桌面端） |
| `cfc4a82` | 并入 desktop/ 完整代码树；旧 CS/demo 仓库已还原为只读 |
| `cd25932` | P2：解析引擎接入（子进程隔离 + artifact 分发），server 33 tests |
| `318f428` | 单房间模式（默认 MAIN，开关切 multi）+ 轨迹按玩家懒加载 |
| `5be3d21` | P3：手机端 PWA（replay-core 渲染核、选手详情、可安装外壳） |
| `2eb6a83` | 从本机 CS2 的 pak01.vpk 读地图变换（awpy CDN 被 Cloudflare 403） |
| `4488820` | 服务端 AI 编排（流式、一局一次、结果入会话） |
| `c417609` | 赛后战报端到端（客户端上报，手机显示比分/十人数据/AI 命中） |
| `d60081a` | 桌面端习惯轨迹面板（复用同一渲染核） |
| `24d80d4` | 联调脚手架 + **修 artifact 响应信封 bug**（裸 JSON 导致手机永远不显示轨迹） |
| `49e2622` | 仓库根 CI（Windows 出 exe，6.14MB） |
| `2b2e214` | 真机截图验收修复：昵称回退（引擎 username 为 null 时按 steamId/domain 回查阵容）、宽屏 max-width、详情页顶栏去重、WS 4401 死循环、SW 改 network-first |
| `1641556` | 桌面端设置里过期的 localhost:3000 文案 → 8787 |
| `ac2437c` | AI 适配 DeepSeek 推理模型 + 本地 .dem 直通解析接口 |
| `d300c35` | **默认每人只下 1 个 Demo**（原 6 会下 4-5GB 跑不完）；轨迹 K/D 标注"该场" |

## 关键决策及依据（都有实测，别凭感觉推翻）

1. **解析跑子进程，不改 1615 行 pipeline**：`engine/config.py` 在 import 时绑定 OUTPUT_DIR，多房间并发会互相覆盖；子进程注入环境变量解决，附带可靠 cancel 与崩溃隔离。
2. **双档交付是物理必需**：画像/AI 秒级，轨迹分钟级。单人解析仅 2.4s，但下载 130–230MB/人 ≈ 18s+；10 人首次 1–3 分钟（看带宽）。只有缓存命中（同一对手第二次）才能 30s 内出图。`DEMO_MAX_DEMOS` 默认 1。
3. **AI 默认关思考**：`deepseek-flash` 是推理模型，先吐 `reasoning_content` 再吐 `content`。开思考首字 10.5s、关思考 0.8s，正文质量无差异。`max_tokens` 必须 ≥3000（思考也占预算，700 会空正文且 HTTP 200）。
4. **地图资源不入库**：Valve 素材。`import_radar.py --from-vpk` 从本机 CS2 的 pak01_dir.vpk 读变换（`engine/vpk.py` 最小只读实现），雷达图 png 来自旧项目素材。de_mirage 变换 -3230/1713/5.0 已核对。
5. **服务端不重复抓赛后战报**：桌面端 `post-match.ts` 已成熟，取回后上报，服务端只归档广播。

## 实测性能基线

| 项 | 数据 |
| --- | --- |
| 单人解析（231MB / 22 回合） | 2.4s |
| 10 人共享 parser 全量 | 26–30s，产出 1.8MB |
| 单人首次（含 5E 下载） | ~21s |
| 4 人经服务端（缓存命中） | 49.5s 含 583 字 AI |
| AI（deepseek-flash 关思考） | 首字 0.5s，全文 3s |
| 5E 公开接口（搜索/列表） | 1s 内，免登录 |
| exe（GitHub Actions） | 6.14MB，冷构建 17min → 有缓存 ~5min |

坐标校验：mirage 3520 点 / dust2 2240 点，**0 越界**。

## 环境复现

```bash
# venv（已装好：fastapi/demoparser2/pandas/awpy…）
I:/workbuddy/cn-code/cs-helper/.venv/Scripts/python.exe -m uvicorn app.main:app \
  --host 0.0.0.0 --port 8787 --app-dir server

# 常用环境变量
CS_HELPER_SERVER_SECRET=...        # 必配
CS_HELPER_AI_KEY=...               # DeepSeek key，只走环境变量
CS_HELPER_AI_MODEL=deepseek-flash  # 可用模型仅 deepseek-flash / deepseek-v4-pro
CS_HELPER_DEV=1                    # 开 /api/v1/dev/*（seed-paths / parse-local）
CS_HELPER_LOCAL_DEMO_DIR=...       # dev 解析允许读取 .dem 的目录
CS_HELPER_DEMO_MAX_DEMOS=1         # 每人 demo 数，调大线性增加下载时间

# 测试
cd server && pytest tests -q    # 62
cd engine && pytest tests -q    # 104 passed, 10 skipped（需 328MB 集成 demo）
cd desktop && npx vitest run    # 284
```

## 已踩过的坑（修过，勿再犯）

- artifact 响应必须是 `{code,message,data}` 信封，前端按此解析（`2b2e214` 前是裸 JSON，手机静默不显示轨迹）。
- 引擎返回的 `username` 可能为 null（缓存命中/合成任务），轨迹索引必须按 steamId/domain 回查阵容昵称写 `nickname`。
- `combat.parse_combat_stats_from_context(parser, events, steamid, classified)` 参数顺序易错（steamid 在第三）。
- WS 4401 = 服务端重启后 token 验签过但成员不存在；客户端必须清 localStorage token 回昵称页，不能无限重连。
- SW cache-first 会让手机一直跑旧 JS；network-first + 每次 `registration.update()`。
- 全部玩家解析失败要回 `ROOM_ERROR 2006`，不能发 `TACTICAL_PATHS_READY{players:0}`（空白且无提示）。
- 推理模型"只思考没正文"要报 2005 并说明推理字数，不能笼统说"未返回内容"。

## 未做 / 待验证

- **P5 运维**：历史归档、指标、按房间配额、Redis 化、房间回收（数据目前全内存，重启即丢）。
- **历史习惯聚合**：现在是单场轨迹回放；"习惯"应聚合对手多场 demo（数据已能拉，缺聚合视图与文案）。
- 真机视觉：手机渲染逻辑有无头断言保证不崩，但配色/缩放/手感未做真机走查。
- 桌面端 AI 面板未订阅服务端 `phase:"thinking"`（ thinking 事件被安全忽略）。
- `desktop/.github` 已删，CI 统一在仓库根；旧 `cs-helper-exe` 仓库未同步桌面端新改动（report-builder/sync-client）。
- 328MB 集成 demo 缺失，engine 有 10 个用例 skip。

## 建议下一步

1. P5 运维（真正多人使用前必须做房间回收 + 持久化，否则服务端重启即丢）。
2. 习惯聚合视图：多人多场 demo 的点位热力/开局路线对比。
3. 发布桌面端：latest-build 已可用，打 `v1.0.0` 发正式版并更新根 README 下载链接。
4. 真机走查手机端轨迹页（唯一没有视觉验证的页面）。
