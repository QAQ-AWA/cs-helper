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
  ├─ store.py ── 房间/会话/环形缓冲（内存，重启后从磁盘恢复最近 N 局）
  ├─ persistence.py ── 一局一个 JSON，原子写；历史列表与保留期清理
  ├─ evidence.py ───── 赛前证据包：本地算 direction/reliability/dataQuality
  ├─ home_enrich.py ── 调 engine 拉 5E 赛季数据（player/home），失败可降级
  ├─ trajectory.py ─── 开局画像：CT 站位、T 下包分布、道具与开局死亡
  ├─ ws.py ────── 每连接有界队列；重连先补事件、快照最后发
  ├─ jobs.py ──── 画像(秒级) → AI(流式) → Demo 任务；按 platform:matchId 全局去重
  ├─ engine_runner.py ── 子进程管理（见"为什么跑子进程"）
  ├─ artifacts.py ────── 内容寻址存储：索引(~1KB) + 按玩家 parts(~150KB)，写穿到磁盘
  └─ devtools.py ─────── DEV=1 时的合成轨迹与本地 .dem 直通解析
引擎 engine/（纯 Python，CS-Scout 2.0 抽离）
  ├─ job_runner.py ── 5E 链路子进程入口（检索→下载→解析）
  ├─ home_runner.py ── 赛季数据子进程入口（签名网关 player/home）
  ├─ home_client.py ── 网关 HMAC 签名 + 赛季字段归一
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
| `6929899` | 交接文档 |
| `e2d4f42` | **P5 运维**：会话与轨迹落盘、启动恢复、MAIN 自动重绑、后台回收、历史接口 |
| *本轮* | **功能深化**：我方阵营选择（只下对面 5 人）、证据化 AI 输入、轨迹开局预判 |

## 关键决策及依据（都有实测，别凭感觉推翻）

1. **解析跑子进程，不改 1615 行 pipeline**：`engine/config.py` 在 import 时绑定 OUTPUT_DIR，多房间并发会互相覆盖；子进程注入环境变量解决，附带可靠 cancel 与崩溃隔离。
2. **双档交付是物理必需**：画像/AI 秒级，轨迹分钟级。单人解析仅 2.4s，但下载 130–230MB/人 ≈ 18s+；10 人首次 1–3 分钟（看带宽）。只有缓存命中（同一对手第二次）才能 30s 内出图。`DEMO_MAX_DEMOS` 默认 1。
3. **AI 默认关思考**：`deepseek-flash` 是推理模型，先吐 `reasoning_content` 再吐 `content`。开思考首字 10.5s、关思考 0.8s，正文质量无差异。`max_tokens` 必须 ≥3000（思考也占预算，700 会空正文且 HTTP 200）。
4. **地图资源不入库**：Valve 素材。`import_radar.py --from-vpk` 从本机 CS2 的 pak01_dir.vpk 读变换（`engine/vpk.py` 最小只读实现），雷达图 png 来自旧项目素材。de_mirage 变换 -3230/1713/5.0 已核对。
5. **服务端不重复抓赛后战报**：桌面端 `post-match.ts` 已成熟，取回后上报，服务端只归档广播。
6. **持久化用「一局一个 JSON」而不是数据库**：局域网规模下几百个小文件启动扫描是瞬时的，`rm -rf .cache/data` 就是彻底重置；`persistence.SessionRepository` 是唯一需要替换的面。写盘用 `tmp + os.replace`（中途掉电不会留下半截 JSON），坏文件跳过而不是让进程起不来。
7. **重启后自动重绑最近一局**（限 4 小时内，即 `ROOM_TTL`）：否则持久化只有存档意义，手机回到房间仍是空的。`mobile.js:115` 本来就会用快照里的 `artifactId` 恢复轨迹，所以手机端零改动。
8. **轨迹产物必须一起落盘**：只存会话会导致 `demoState=ready` 但拉轨迹 404；启动时若 blob 已不在，会话降级为 `demoState=failed` 并清空 `artifactId`。

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
CS_HELPER_HOME=0                   # 关闭 5E 赛季数据补全（player/home 签名网关）

# 运维（P5）
CS_HELPER_DATA_DIR=...             # 历史根目录，默认 .cache/data
CS_HELPER_ROOM_TTL=14400           # 房间无访问多久回收（秒）
CS_HELPER_GC_INTERVAL=60           # 后台回收周期（秒），0 关闭
CS_HELPER_HISTORY_DAYS=7           # 历史保留天数，到期连轨迹一起删
CS_HELPER_SESSION_MEMORY_MAX=50    # 内存里最多常驻多少局

# 测试
cd server && pytest tests -q    # 123
cd engine && pytest tests -q    # 111 passed, 10 skipped（需 328MB 集成 demo）
cd desktop && npx vitest run    # 286
```

## 已踩过的坑（修过，勿再犯）

- artifact 响应必须是 `{code,message,data}` 信封，前端按此解析（`2b2e214` 前是裸 JSON，手机静默不显示轨迹）。
- 引擎返回的 `username` 可能为 null（缓存命中/合成任务），轨迹索引必须按 steamId/domain 回查阵容昵称写 `nickname`。
- `combat.parse_combat_stats_from_context(parser, events, steamid, classified)` 参数顺序易错（steamid 在第三）。
- WS 4401 = 服务端重启后 token 验签过但成员不存在；客户端必须清 localStorage token 回昵称页，不能无限重连。
- SW cache-first 会让手机一直跑旧 JS；network-first + 每次 `registration.update()`。
- 全部玩家解析失败要回 `ROOM_ERROR 2006`，不能发 `TACTICAL_PATHS_READY{players:0}`（空白且无提示）。
- 推理模型"只思考没正文"要报 2005 并说明推理字数，不能笼统说"未返回内容"。

## P5 运维：房间回收 + 历史持久化（本轮）

服务端原先全内存，重启即丢，且过期房间只 pop 房间不 pop 会话（会话永久累积）。现已改为「内存是缓存、磁盘是账本」。

**落盘布局**（`CS_HELPER_DATA_DIR`，默认 `.cache/data`，已 gitignore）：

```
.cache/data/
  sessions/5e_2603231500001-1949da3d.json      # 一局一个，~2.5KB，原子写
  artifacts/018e9b33….json                     # 轨迹索引，~660B
  artifacts/018e9b33….76561199352425025.json   # 按玩家分片，130–200KB
```

- `persistence.SessionRepository`：`tmp + os.replace` 原子写；坏文件/未知 schema 只跳过不致命；保留期按 mtime 清理。
- 写盘时机：上报时一次 + 每个任务终态一次（`JobManager._run` 的 `finally` 统一挂钩），一局约 4 次。
- `ArtifactStore` 加磁盘层：`put` 写穿、`get` 未命中懒加载、LRU 仍在（内存 96MB 上限），磁盘副本只由保留期回收。
- `Store` 级联回收：过期房间 → 无房间绑定且空闲超 `ROOM_TTL` 的会话 → 超 `SESSION_MEMORY_MAX` 时按最旧淘汰；**被房间指向的会话永不淘汰**。淘汰只影响内存，历史仍在磁盘。
- `hub.reap()` 由 lifespan 里的 asyncio 任务每 `GC_INTERVAL` 秒执行（`asyncio.to_thread`，不阻塞事件循环）；只有删过历史才去扫孤儿轨迹，避免每分钟全目录扫描。
- 重启体验：`ensure_room` 新建房间时自动重绑 4 小时内最近一局（`Session.room_code` 落盘支撑），手机靠快照里的 `artifactId` 直接恢复轨迹，手机端零改动。
- 新接口：`GET /api/v1/history/sessions?limit=20`（需房间 token），返回 matchId/地图/时间/三态/比分/是否有轨迹/AI 摘要，为下一步习惯聚合铺路。
- `healthz` 扩为运维面：`rooms/sessions/members/onlineMembers/artifacts/artifactBytes/artifactDiskBytes/persistence/historyFiles/dataDir/historyDays/lastReap`，原有 `status/rooms/protocolVersion` 保留。

**实测（真实 5E 四人一局）**：4 人 mirage 轨迹 20/13/13/16 回合，产物 635KB；session JSON 2.5KB。`kill` 后重启 → `restored 1 match(es)` → 重进 MAIN 快照直接有 match + artifactId，索引与单人分片均 200；`lastReap` 每 15s 前进一次（GC_INTERVAL=15 时）。

## 功能深化（本轮）

### 0.1 数据上报：修掉"从来没上传过统计"

`desktop/src/core/sync/report-builder.ts` 读的是 `player.stats.rating` / `player.steamId64` / `player.platformUserId`——这些字段在 `MatchPlayer` 上**根本不存在**（真实字段是 `player.rating` / `player.steamId` / `player.platformBoardId`）。`if (player.stats)` 恒为 false，所以 **`payload.stats` 从来没有被设置过**，服务端一直只收到昵称和 steamid。

为什么没被发现：`vite build` 走 esbuild，不做类型检查；单测用的假数据也照着错字段写，所以测试是绿的。`npx tsc --noEmit` 能直接看到十几条 `Property 'stats' does not exist on type 'MatchPlayer'`。

修复后上报的是完整统计（有就带，没有就不带）：

| 分组 | 字段 |
| --- | --- |
| 核心 | `rating` `kd` `headshotRate` `winRate` `matchesPlayed` `rankLevel` |
| 赛季 | `seasonRating` `seasonAdr` `seasonRws` `seasonKast` |
| 首杀/残局/补枪 | `firstKillRate` `clutchWinRate` `entryKillRatio` `tradeFragRate` |
| 状态 | `recentWinRate` `recentResults`(WWLWL) `recentRatings` `continuedWins` |
| 当前地图 | `mapWinRate` `mapMatches` `mapSampleLow` |
| 身份 | `elo` `eloChange` `rankNum` `rankDesc` |
| 原始计数 | `kills` `deaths` `assists` `mvpCount` |

- `platformUserId` 现在取 `platformBoardId`（5E domain），引擎可以跳过昵称搜索直接命中，不再每次回退到模糊查找。
- `partyTag` 取 `troopTeamId`，但 **0 表示"无组队"**，不能当标签用。
- **百分比只在边界转换一次**：5E 解析器给的是 0-1 小数（`hsRate`/`seasonWinRate`/`kast`），UI 显示的是 48%，服务端基准线也按百分数写。混在一份 JSON 里模型必然读错，所以在 `pct()` 里统一——不是"为了统一而统一"，是同一个量纲才能比较。

服务端对应收紧：`partyTag` 推断要求**同一侧 ≥2 人且另一侧 0 人**，否则整桌同一个 troop id 会把边判反。

### 0.2 服务端统一分析，桌面端只负责展示

- `useTeamSync` 现在维护 `serverMatch`（aiText / tacticsText / mySide / 三态）与 `serverProfiles`，并暴露 `setAnalysisSide()`。
- 新增 `ServerAnalysisPanel.vue`：状态胶囊（画像/赛季/轨迹/战术/开局）+ 我方阵营切换 + 战术分析 + 开局预判 + 赛季缺口提示。
- `MatchFeaturedPanel` 的「分析」标签从客户端 `AiAnalysisPanel` 换成 `ServerAnalysisPanel`——**AI 只在服务端跑**，桌面端看到的是同一份结果。
- 客户端原有的本地 AI 代码仍在（`src/core/ai/*`、`useAiAnalysis`），保留给离线/独立使用；要彻底删掉需要先做一轮真机视觉验收，见"未做"。

**为什么之前"看不到分析页"**：桌面端主界面由**本地侦测到的对局**驱动（`matches[0]`），没侦测到就停在 `MatchEmptyState`，服务端房间里的会话根本不会渲染——分析存在，但没有地方显示。现在补了两层：

- `ServerRoomPanel.vue`：本地还没对局、但服务端房间已有会话时，直接显示服务端阵容 + 分析（含恢复的历史对局，带时间戳）。
- 等待页新增一行服务端状态（`已连接服务端房间 MAIN` / `未连接`），"等待中"不再对同步状态含糊。

### 0.2.1 5E 启动链路（不要动）

用户明确要求保留，实际也没动过（`git diff` 可证）：

```
（无平台选择页）启动即 P5eLaunchView
  · 探测并校验 5E 客户端路径（持久化，下次自动带出）
  · 拉起 5E（CDP 9222）→ 等 hook
  └─ emit('ready') → completeP5eSetup() → phase='main'
       MatchAssistantView：本地 matches 为空 → MatchEmptyState（等待）
       └─ 5E 开始匹配 → CDP/WS 截获 → injectMatch → MatchFeaturedPanel（标签页）
```

涉及文件：`useAppSession.ts`（已改成只有 `p5e-launch | main`）、`P5eLaunchView.vue`、`useP5eCdp.ts`、`MatchEmptyState.vue`、`src-tauri/src/platform/*`。

### 0.2.2 移除完美世界（只做 5E）

已删（用户可见面全部清掉）：

- `PlatformSelectView.vue`、`PerfectAuthView.vue`、`usePerfectAuth.ts`（+测试）
- `PerfectAccountSettingsSection.vue`、`PerfectApiDebugPanel.vue`
- 设置页「登录管理」页签、标题栏完美账号状态、调试面板「完美 API」标签
- `useAppSession` 去掉 `select-platform` / `perfect-auth` 两个阶段

**仍保留**（被共享代码引用，删不掉）：

- `src/platforms/perfect/*`：被客户端 AI（`core/ai/analysis-v3.ts`、`prompt.ts`）和队伍表格（`team-table-shared.ts`）引用
- `useLogWatcher.ts`：完美世界的日志侦测器，`autoInit: false`，5E 下不启动
- `src-tauri/src/platform/perfect_*.rs`：5 个模块 + `lib.rs` 的命令注册

要彻底删干净，得先做「删掉客户端 AI 栈」这一刀（`src/core/ai/*` 约 4000 行 + `useAiAnalysis` + `AiAnalysisPanel` + `P5ePostMatchPanel` 的 AI 部分），再改 `team-table-shared` 的段位显示。这是一次独立重构，别和别的改动混在一起做。

### 0.3 数据从哪来（签名网关）

| 数据 | 来源 | 谁在抓 |
| --- | --- | --- |
| 选手赛季数据（Rating/K/D/爆头率/胜率/场次） | 桌面端已打开的 5E 比赛详情接口（`field-mapper.ts` 的 `userData` / `seasonBlock`），随上报带给服务端 | 桌面端 |
| **赛季 ADR/RWS/KAST（补充）** | **服务端自己调 5E 签名网关 `player/home`**（`engine/home_client.py`） | 服务端 |
| demo 列表与下载地址 | 5E **公开**接口：`arena/api/search` + `gate` 分页（`engine/api_client.py`） | 引擎 |
| 轨迹、下包点、道具、死亡 | 自己的 `demoparser2` 解析 | 引擎 |

签名网关已经搬过来了（从 `desktop/src-tauri/src/platform/platform_5e_gate_sign.rs` 移植到 Python）：

- **算法**：阿里云网关 HMAC-SHA256。canonical = `METHOD\n*/*\n\n\n\n<accept-language:zh-cn\nauthorization:>\n<path?query>`，query 按 key 升序，签名 base64 放 `x-ca-signature`。
- **正确性**：Rust 侧有单元测试向量（uuid `ed954be0-…` → `V+81D/A51CzX6Azk0HbElYwxZfLiquWykkaT6k+Z8Io=`），Python 实现逐字节对齐，`engine/tests/test_home_client.py` 锁住它。
- **UUID**：`home_client.resolve_uuids()` 用一份 match detail 解析整队（详情里有十个玩家），不是一人一次请求。
- **单位**：5E 的 `kast` / `per_headshot` / `per_win_match` 是 0-1 小数，`parse_season()` 统一乘 100，与客户端上报的百分数量纲一致。
- **失效处理**：401/403 抛 `GateSignatureError` → `homeState=signature` + `ROOM_ERROR 2007 (stage=home)` + 手机端阵容卡一行黄字；**不阻塞**画像、轨迹和 AI。
- **开关**：`CS_HELPER_HOME=0` 关闭。`create_app(home_client=None)` 默认关（测试不许联网），`app.main:app` 显式开。

已知维护点：密钥硬编码在 5E 前端产物里（与桌面端同源），5E 改版就会失效——所以这条链路的所有失败都必须是可降级的。

**副作用要记住**：桌面端签名失效时 `matchesPlayed` 会报 0。`evidence.reliability_for()` 因此把 `<=0` 判成 `unknown` 而不是 `low`——"不知道"和"打得少"是两件事。

### 1. 我方阵营：只下对面 5 人

下载是唯一瓶颈（单人 130–230MB / ~21s），十人全下就是十份等待，而赛前真正要研究的只有对面。

- `MatchReport.mySide: "ct"|"t"|null`；解析顺序 **显式选择 > 「都看」覆盖 > ID 库 > `isSelf` > `partyTag` > 不确定**（不确定就退回十人，绝不猜）。
- `adapters.demo_targets()` 一处过滤，`to_engine_hints` / `demo_job_targets` / 进度总数全部走它。
- `POST /api/v1/room/{code}/analysis-side` 改边重跑：demo 按 domain 缓存在磁盘，切换只补没下过的人。
- 手机端「我们在哪边」三档（CT / T / 都看），改完立刻显示目标人数。
- 重复上报同一局且没带 `mySide` 时，保留已有选择（否则第二台 PC 一上报就白下十人）。

**ID 库（`identity.py`）**：把确认过的 SteamID / 5E domain 记进 `DATA_DIR/identity.json`（按房间码隔离，重启不丢）。下一局上报时先查库，**同一侧命中 ≥2 人且另一侧 0 人**才自动判定——只命中 1 人不够，否则你撞见前队友时会被判到对面去。判不出来就回落到手动选择，这是安全的失败方向。

- `GET /api/v1/identity?roomCode=` 看库；`POST /api/v1/identity/learn {side}` 记住当前对局的某一侧；`DELETE` 清空。
- 手机端选完边会出现「把我方这 5 人记进 ID 库」，成功后提示「已记住 N 个 ID」。
- **「都看」必须能压过 ID 库**：`POST analysis-side {mySide:null, all:true}` 会写 `report.analyzeAll=true`，否则库里一命中，用户点的「都看」立刻被打回去，看起来像坏了。

**踩到的坑**：`SubprocessDemoRunner.cancel()` 会把 session 记进 `_cancelled`，紧接着提交的新任务一启动就判自己"已取消" → demo 直接 failed。修法：只在 `demo_state == "running"` 时才 cancel，且 `run()` 启动时丢弃过期的取消标记。

### 2. AI 输入改成证据包（学旧项目 analysis-v3）

旧项目 `src/core/ai/analysis-v3.ts` 的核心不是提示词写得多好，而是**判断在本地做完了**：方向按全场中位数算、可信度按样本量分级、模型只能引用证据 ID。我们原来只给一张十人 Rating 表，等于让模型自己瞎猜强弱。

- 新增 `server/app/evidence.py`：`direction`（positive/negative/neutral，按全场中位数 ± 容差）、`reliability`（high ≥30 场 / medium ≥10 / low）、`dataQuality`（哪些指标有、哪些缺、谁样本不足）、`mapFit`（每张图的性格）、`role`（我方/对方）。
- 提示词硬规则：只能引用包里的数值、不得推翻 direction、low/unknown 只能写进「数据缺口」。输出仍是 Markdown（手机已能渲染），不改成 JSON，省掉一次 UI 重写。
- 保留了旧项目的 `MAP_FIT_HINTS` 与指标基准线（Rating 1.00 / K/D 1.00 / 爆头率 45–55% / 胜率 50%）。

### 3. 轨迹开局预判（第二段 AI）

- **引擎**：`parse.py` 新增 `parse_plants()`，从 `bomb_planted` 取包点编号 + 下包人坐标，按 tick 落到回合，写进每回合的 `plant: {site, x, y, t, by}`；`player_json` 透传；按 demo 路径 + mtime 缓存，第二个玩家起零成本（+0.2s/人）。
- **包点真值**：`site` 326 = A、327 = B，在 mirage 上用雷达变换核对过（A 落在右下 530–595/740–777，B 落在左上 208–262/253–294）。这是**唯一**的 A/B 来源，没有包点数据时一律 `unknown`，不猜。
- **画像**：`server/app/trajectory.py` 把每人的 CT 8 秒站位（A/B/offsite）、T 边下包分布（A/B）、平均下包时间、开局 25 秒内死亡数、12 秒内道具统计成 JSON；包点锚点按地图累积在 `DATA_DIR/anchors.json`（单场 demo 常常只打一边，靠多场补齐）。
- **第二段 AI**：`TACTICAL_PATHS_READY` 之后链式 `submit_tactics`，事件 `AI_TACTICS_CHUNK` / `AI_TACTICS_READY`，手机新增「开局预判」卡片；`tacticsState/tacticsText/trajectory` 一起落盘。

**关键实测修正**：原本想用「20 秒时站在哪」判断 T 边打哪，实测**不成立**——demo 只截取开局 20 秒，而 mirage 的下包时间实测 31–42 秒（四人 62 回合的 avgPlantT 39.8–50.1s）。所以 T 边选点一律用下包真值，位置快照只用于 CT 站位。这条如果没跑真实数据会一直错下去。

真实四人一局的结果（可直接当验收样例）：

| 玩家 | CT 8s 站位 | T 下包分布 | 平均下包 | 开局死亡 | 早期道具 |
| --- | --- | --- | --- | --- | --- |
| 背身步马枪 | A 1 | **A 7 / B 4** | 39.8s | 1 | 烟2 闪1 火4 |
| 半团空气 | A 2 / B 3 / 外场 5 | A 1 / B 3 | 44.2s | 3 | 烟1 闪2 火2 |
| Z大爷 | 外场 1 | A 1 / B 3 | 50.1s | 3 | 闪3 火6 雷1 烟2 |
| Farewell-海海 | A 2 / 外场 6 | A 1 / B 2 | 47.9s | 1 | 烟3 闪1 |

## 未做 / 待验证

- **桌面端只是"改造"，不是推倒重写**：`src/mainview` 仍有 2.7 万行，包含完美世界登录、平台选择、留言板、本地 AI 等本项目用不到的面。本轮换掉了「分析」页的数据来源，但 App 外壳、平台选择、设置页都还是旧的。彻底重写需要能真正跑起来的窗口做视觉验收（当前环境没有 Rust 工具链、没有显示器），建议分三步：① 删掉 perfect/comments/本地 AI 三条支线；② 收敛成单窗口「连接 → 对局 → 服务端结果」；③ 逐页做真机走查。
- **桌面端存在历史类型错误**：`npx tsc --noEmit` 报十几条（`useCounterStrafing` 引用了不存在的模块、若干隐式 any）。CI 只跑 vitest + vite build，不跑 tsc，所以一直没暴露。建议把 `tsc --noEmit` 加进 CI，但需要先清完存量。
- **`useCounterStrafing*` 是死代码**：依赖的 `@core/counter-strafing/*` 模块已不存在，未被任何视图引用，可直接删。
- **签名网关的长期有效性**：密钥硬编码在 5E 前端产物里，5E 改版即失效。已做可降级 + 提示，但没有自动发现新密钥的能力。
- **开局预判未接真实模型**：环境没有 `CS_HELPER_AI_KEY`，只验证了提示词结构与真实画像数据。
- **包点映射只验证了 mirage**：326/327 的 A/B 约定按 CS2 实体顺序推断。
- **历史习惯聚合**：跨场聚合（同一对手多场叠加）还没做。
- 328MB 集成 demo 缺失，engine 有 10 个用例 skip。

## 建议下一步

1. 接真实 key 跑一次开局预判，校准提示词（这是本轮唯一没闭环的环节）。
2. 跨场聚合：同一对手多场 demo 的包点分布叠加，`/api/v1/history/sessions` 已是入口。
3. 发布桌面端：latest-build 已可用，打 `v1.0.0` 发正式版并更新根 README 下载链接。
4. 真机走查手机端轨迹页与新的「开局预判」卡片。
