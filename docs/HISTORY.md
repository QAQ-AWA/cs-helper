# 开发历程

> 按时间顺序记录每一轮改了什么、为什么、实测数据是什么。
> **当前状态与待办看 [HANDOFF.md](HANDOFF.md)**，这份只用来查「当时为什么这么改」。

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

### 0.2.3 对局面板重写（本轮）

旧的 `MatchFeaturedPanel`（756 行、五页签）挂着客户端 AI 的 props/watcher，还带 719 行的
队伍表格与列自定义器。现在换成四个直白的问题：

```
MatchWorkspace
├─ header：地图 / 对局号 / 我方阵营·来源 / 房间 / 准备倒计时
└─ tabs：阵容 · 分析 · 轨迹 · 赛后
    ├─ RosterBoard      两列阵容，Rating/ADR/K/D/HS%，服务端赛季值优先
    ├─ ServerAnalysisPanel
    ├─ TacticalPathsPanel
    └─ P5ePostMatchPanel
```

删除（只被彼此引用，已无入口）：`MatchFeaturedPanel`、`TeamDataBoard`、`TeamCompareBoard`、
`TeamPlayerTable`、`AiAnalysisPanel`、`ai-v3-ui.test.ts`。主包 842KB → 486KB。

实时视图与历史回放都走 `MatchWorkspace`；历史回放没有 `sync`，分析页显示「历史回放不包含服务端分析」。

**第二轮（同一轮内完成）**：

- 赛后页 `P5ePostMatchPanel`（605 行）→ `PostMatchBoard`（约 200 行）：展示服务端 `postReport`，
  本地拉取后一边渲染一边 `reportPostMatch` 上报。**注意**：上一轮删旧面板时把上报调用一起删了，
  战报再也到不了服务端，新面板已接回。
- 轨迹页：`slate/emerald` 换成主题 token；修「从快照恢复时点选手没反应」——
  索引响应体里没有 `artifactId`（它在 URL 上），不补回去 `openPlayer` 会直接 return。
- 设置页：去掉「AI 设置」「留言板」两个页签，AI 已由服务端负责。
- `vite.config.ts` 加 `/maps` 代理，预览页可直接看真实雷达（`?live=1` 连本机 8787）。

主包 842KB（重写前）→ 486KB（换面板）→ **417KB**（去设置页 AI/留言板）。

**第三轮：同步设置与连接状态**

- `TeamSyncSettingsSection` 重写：原来只有「保存设置」，`createRoom/joinRoom` 解构了却没接到按钮，
  用户根本没法从设置页连房间。现在有 创建 / 加入（房间码）/ 断开，已连接时显示设备列表与手机链接。
  原来用的 `bg-primary` / `text-emerald-400` 在主题里不存在（渲染成无色），全部换成 token。
- 标题栏「小队协同」常驻状态点 + 房间码。
- **服务端 `lan_addresses()` 过滤代理 TUN**：198.18.0.0/15（RFC 2544）会被 Clash 之类的 TUN 适配器占用，
  且排序靠前，导致手机链接指向 `198.18.0.1` 这种手机永远连不上的地址。现在过滤 198.18/19、link-local、CGNAT，
  并按 192.168 > 10 > 172.16-31 排序。

**第四轮：历史页与关于页视觉统一**

- 历史列表 4 个组件 + 视图里的 `slate-*` / `rose-*` / `emerald-*` / `bg-white` 全量替换成
  `fg` / `surface` / `border` / `danger` / `success`。
- 关于页：仓库链接原本指向 `cs-helper-exe`（旧独立桌面项目），改为 `cs-helper`；
  版本号加构建期兜底（`vite define __APP_VERSION__`），Tauri 取不到时不再空白。
- 预览页新增 `?view=about` 与 `?view=history`，两页都能截图自检。

**第五轮：清理原作者信息 / 对局 HUD / 客户端 AI**

- 关于页删掉作者、Bilibili、QQ 群，只留 版本 / 反馈(Issue) / 源代码；标题栏去掉「-By 小淳」。
- 对局 HUD 整条删除（标题栏入口、介绍弹窗、演示舞台、图标，共 4 个组件 + 1 个测试）。
- 历史列表只保留 5E，旧版本残留的完美对局不再进入列表。
- **客户端 AI 引擎整体删除（-5400 行）**：`core/ai` 23 个文件、`useAiAnalysis`(633)、
  `useAiSettingsForm`、`AiSettingsSection`、`native.ts` 的 8 个 AI 封装、调试面板的 AI 注入子标签。
  保留 `core/ai/types.ts`（历史文档存储契约）与新增的 `core/ai/normalize.ts`（只做 v3 结构校验）。
  历史回放改用 `StoredAiReport.vue` 只读渲染存档结果，不再调模型。


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

## 桌面端 UI 开发工具（本轮新增）

改 UI 最大的障碍是**看不到界面**：这台机器没有 Rust/MSVC，`tauri dev` 起不来；出 exe 只能等 CI。为此补了三层：

| 工具 | 位置 | 用途 |
| --- | --- | --- |
| `vue-tsc` | `desktop`（已装，新增 `npm run typecheck`） | 类型检查。`vite build` 用 esbuild **不做类型检查**，report-builder 那个「读不存在的字段」的 bug 就是这么潜伏三个月的 |
| `@vue/test-utils` + `happy-dom` | `desktop` devDependencies | 组件级挂载测试。vitest 配置里补了 `@vitejs/plugin-vue`，否则 `.vue` 解析不了 |
| `@playwright/test` + Chromium | `.tools/ui-check/`（gitignore） | 截图验收。浏览器内核装在该目录的 `browsers/`，不污染仓库 |

**fixture 预览页**：`desktop/src/mainview/ui-preview/`，纯前端、不依赖 Tauri：

```bash
cd desktop && npx vite            # http://127.0.0.1:5173/ui-preview/index.html?state=ready
```

`state` 支持 `ready` / `no-ai` / `signature` / `empty`，覆盖服务端房间的四种状态。

**截图**：

```bash
cd .tools/ui-check
PLAYWRIGHT_BROWSERS_PATH="$PWD/browsers" npx playwright test
# 产出 shots/{ready,no-ai,signature,empty}.png
```

注意 `vue-tsc` 现存 **41 个存量错误**（`useCounterStrafing` 缺模块、`post-match.test.ts` 的 `stabilityReason` 等），**还不能接进 CI**，否则必挂。新代码至少要保证不新增错误。

## 真实十人链路实测（2026-10-23，DeepSeek 官方）

用一场真实 5E 对局的 10 名玩家（从 match detail 取的 domain + steamid）跑通全链路，
`mySide=ct` → 只下载对面 5 人。

| 阶段 | 冷启动（首次下载） | 缓存命中 |
| --- | --- | --- |
| 画像 | <1s | 0s |
| 赛季补全（player/home，10 人） | ~5s | 6s |
| 轨迹（5 人 × 1 demo） | ~70s | 21s |
| 战术分析（deepseek-flash） | 3s | 9s（含在轨迹等待里） |
| 开局预判 | 3s | 27s |
| **合计** | **87s** | **27s** |

结论：**缓存命中时 27 秒可交付**，与"双档交付"的设计预期一致；冷启动瓶颈仍是下载。

### 这一轮暴露并修掉的三个问题

1. **模型把内部编号写进正文**（「p1 吃醋了我」「p3、p4 两人」）：证据包不再下发 `id`，
   系统提示词补「一律用昵称」。
2. **开局预判横向相加导致重复计数**：同一场比赛 19 个下包回合被算成 17、B 13 次被算成 10 次。
   原因是一个下包会出现在每个被解析选手的回合里。现在 `trajectory.build_profile` 输出
   按 `round_id` 去重的 `teamPlants`，提示词明确要求只看它。
3. 修完之后模型会说「A 8 次、B 7 次，几乎对半，不能断言对面必打 B」——比之前的武断结论更可信。

### 数据质量验证

- 10/10 赛季数据补全（Rating/ADR/RWS/KAST/场次），数值与 5E 页面一致；
- 5 个对手各 12–19 回合轨迹，产物 290KB；
- AI 785 字、开局预判 868 字，抽查的每个数字都能在证据包里找到；
- 两份报告都有「数据缺口」段落，主动点名低样本选手（如 2 场的沈师高冷男孩）。

## 只分析对手五人（2026-10-24 修复）

真机一局（dust2，我方 CT）只拉到自己那份 demo。根因不是引擎，是**标识层**：

| 层 | 问题 | 现象 |
| --- | --- | --- |
| 客户端 | `isSelf` 写死 false，服务端不知道「我」是谁 | 只能分析十个人 |
| 服务端 | `to_engine_hints` 把 steamId 当 5E domain 下发（19 位数字也过正则） | 引擎拿 steamId 查 5E → `Arena API error: None`，五人全失败 |
| 引擎 | `BOMBSITE_LABELS` 写死 mirage 的 326/327 | dust2 的 313/314 → site 全 None，开局预判永远「没有下包数据」 |

修复后（同一局重放，`isSelf` 标在「雷霆的名字」上）：

- 轨迹 5 人，全是对面：17 / 16 / 18 / 23 / 16 回合
- `teamPlants` 20 回合 · A 13 / B 7 · avgT 48.9s
- 开局预判：「20 个下包回合 13 次打 A、7 次打 B，A 是主攻方向」

### 5E 的「我是谁」只有一处可靠来源

`/api/user/info` 的响应里**只有当前登录账号**带 `domain`，其余九人 `platformBoardId`
是空的（回退成 steamId）。客户端据此标 `isSelf`；多人带 domain 时宁可让用户手选，
也不要猜错边。手动选边后服务端会 `learn_identity`，下一局不用再点。

### 新增地图时要注意

`bomb_planted.site` 是**地图内的炸弹点实体索引**，每张图都不一样。已知的查表，
未登记的按索引升序编号（实测 de_mirage 326/327、de_dust2 313/314 都是
「索引小的在雷达右侧＝A」）。加新图后建议先跑一局确认 A/B 没反。

## 雷达图与走位方向（2026-10-24）

**桌面端雷达图空白**：产物里的 `replay.radar` 是服务端相对路径
`/maps/<map>/radar.png`，桌面端页面来自 `tauri://localhost`，根相对路径会被
当成应用内资源 → 404，画布只剩「缺少雷达图资源」。手机上同源，所以看不出来。
客户端现在用同步设置里的服务端地址补全（`resolveRadarUrl`）。

**开局预判分两层**：

| 字段 | 含义 | 局限 |
| --- | --- | --- |
| `teamPlants` | 真的在哪下的包（地面真相） | mirage 落包在 30–40s，20s 窗口看不到 |
| `teamApproach` | 前 20 秒往 A/B 哪边压（每回合多数票） | 只说明方向，不等于落点 |

两者不一致（都往 A 压却常在 B 落包）说明对面爱打默认/骗点，提示词要求点出来，
样本 <5 回合不许写「必打某点」。

**顺带修的计数错误**：`round_id` 每场都从 0 开始，之前只按 `round_id` 去重，
五个对手五场会被压成一场（40 个下包回合只算 20）。引擎现在给每个回合盖
`match_code`，服务端按 `(match_code, round_id)` 去重。

## 分析页与阵容页（2026-10-24 恢复旧 UI）

旧客户端 AI 那套界面（胜率条 / 决定因素 / 玩家信号 / 双方取胜路径）在重写面板时
删掉了，用户更习惯那套呈现。现在按「UI 回来、算力留在服务端」恢复：

| 层 | 现在的做法 |
| --- | --- |
| 服务端 | 分析输出 v3 结构化 JSON，`app/analysis_result.py` 负责解析与兜底 |
| 手机 | `ai_text` 由结构化结果本地渲染成 Markdown，不额外调模型 |
| 桌面 | `AiAnalysisPanel` 渲染结构化结果；老会话退回 Markdown 面板 |
| 阵容 | `TeamPlayerTable` 按队伍列 10 人，可排序，行上带 AI 信号底色 |

### 为什么解析要兜底

模型偶尔把 JSON 包在解释文字或代码块里，字段也可能缺。`parse_analysis_result`
会剥代码块、从首个 `{` 到最后一个 `}` 截取、夹紧概率到 100、纠偏枚举、
截断超长文案，并丢弃不在名单里的 `playerSignals`（编造的玩家卡片比没有更糟）。
仍然解析不出来时给一次「只输出 JSON」的修复调用，再失败才报错。

### 重新分析

`POST /api/v1/room/{code}/analysis/rerun` 只重跑 AI，不动轨迹下载。
面板上的「重新分析」按钮走这个接口。

### 雷达图跨源

桌面端页面来自 `tauri://localhost`，雷达图是跨源图片。`replay-core.js` 先按
`crossOrigin=anonymous` 取，失败再退回普通加载：前者让 canvas 不被标记 tainted
（能读像素），后者保证反向代理吞掉 CORS 头时雷达图至少还能显示。

## 轨迹页的 AI 走位解读（2026-10-24）

轨迹解析完只给一堆路径，用户看不出结论。现在 demo 就绪后会多跑一次结构化 AI：

| 层 | 字段 | 说明 |
| --- | --- | --- |
| 队伍 | `summary` / `tempo` / `sitePreference` | 一句话总结、节奏（带平均下包秒数）、A-B 落包占比 |
| 个人 | `habit` / `likely` / `counter` | 实际怎么走（带次数）、开局 20 秒大概率在哪、一条针对动作 |
| 整队 | `counters` | 2-3 条可执行对策 |

- 实现在 `server/app/path_report.py`，跑在「开局预判」之后，失败不影响已有结果
- 事件 `PATHS_REPORT_READY`，会话字段 `pathReport`
- 桌面端：轨迹页右侧默认态就是这张卡，点左侧选手才切到画布
- 手机端：轨迹页顶部一张卡

**注意**：名字必须能在名单里对上（`allowed_players`），模型写错人的条目会被丢掉——
宁可少一个人，也不要出现不存在的选手。

## 5E 是分段落数据的（2026-10-24）

真机看到的顺序：

| 阶段 | 到达内容 | 之前的问题 |
| --- | --- | --- |
| 1 | matchId | 立刻跑全套作业 |
| 2 | 十个人 ID（可能分两次） | 名单只到一半就开始写分析 |
| 3 | 地图（晚几秒到几十秒） | demo 在 de_unknown 上白跑一次 |
| 4 | 持续回报（准备、阵营、赛季） | 真数据到了，`ai_state=ready` 挡住重算 |

现在的准入规则（`server/app/readiness.py`）：

- **地图未知就等**：`de_unknown` / `unknown` / `workshop` 时 demo 与 AI 都进 `waiting`，
  前端显示「等地图确认，到位后自动生成」
- **输入变了才重算**：每次上报算指纹 `地图 + 名单 steamIds + 敌我`，变了就作废
  `aiResult` 重算；头像、准备状态这类变化不触发
- **名单补齐算输入变了**：这条最容易漏——第一份分析建立在 4 个人上，补齐后必须重算
- **手动「重新分析」用 `force=True`** 绕过地图等待，按钮点了就得有反应

坑：`profile_state` 已经是 `ready` 时，`submit_profile` 会直接返回，链式的
`profile → home → ai` 不会走，所以 `report_match` 必须显式补一次 `submit_ai`。

## 网页端（手机）2026-10-24 改版

和桌面端同一套界面：浅色卡片、四个页签（阵容/分析/轨迹/赛后）、分析页用结构化
卡片渲染（胜率条 / 决定因素 / 玩家信号 / 双方取胜路径 / 数据边界）。

### 「只有开无痕窗口才能看到数据」的三个原因

| 层 | 问题 | 修法 |
| --- | --- | --- |
| HTTP | 外壳没有缓存头，浏览器缓存旧 HTML/JS | 中间件给 `/`、`/static/*`、`/sw.js`、manifest 加 `no-store` |
| Service Worker | 旧版缓存优先，永久返回旧外壳 | `sw.js` 改成 kill switch（注销 + 清缓存 + 重载），页面启动也主动注销 |
| 认证 | 旧 token 让 WS 握手直接 403，客户端只看到 1006 → 无限重连 | 启动先探活快照（401 就清 token 回登录）；连续两次连不上也清 token；加「退出房间」 |

排查手法：Playwright 往 localStorage 塞一个假 token，刷新后必须看到登录弹层。
这条用例现在固定在 `.tools/ui-check/tests/mobile-stale.spec.ts`。

### 手机端的取舍

阵容页不做八列表格（要横滑），改成两行卡片：第一行名字 + 信号标签 + Rating，
第二行 ADR / RWS / K/D / 爆头 / 近 5 场。所有数字都在，不用横滑。

## 原生 Android 客户端（Flutter，2026-10-24）

手机端在 PWA 之外多了一份原生实现：`mobile/`，Flutter 3.47.8 / Dart 3.13.7。
**不是 WebView 套壳**，雷达回放、WS 重连、状态合并都在 Dart 里自己实现。

### 为什么做

PWA 的三个老问题都出在浏览器层，服务端再改也绕不过去：

| PWA | 原生 |
| --- | --- |
| Service Worker / 浏览器缓存 → 「只有无痕能看到新数据」 | 没有缓存层，启动即新代码 |
| 切后台回来 WS 可能已断，页面停在「已断开」 | 自己管重连，回前台补快照 |
| Canvas + rAF 在低端机掉帧 | `Ticker` + `CustomPainter`，只重绘雷达层 |

### 结构

```
mobile/lib/
├─ controllers/room_controller.dart   唯一状态源：连接 / 快照 / 事件 / 轨迹缓存
├─ services/api_client.dart           REST 信封 + WS URL；settings_store.dart 存地址/房间/token
├─ models/                            Player / Match / Analysis / Replay / PostMatch
├─ pages/                             join / room（四页签）/ replay
└─ widgets/                           卡片、头像、信号标签、Markdown、底部弹层
```

### 和网页端保持一致的行为（别改出分歧）

- **快照是权威**：`ROOM_STATE_SYNC` 整份替换；`MATCH_DETECTED` 新对局整份替换；`AI_*` / `PROFILE_READY` 按字段合并。
- **token 按「服务端地址 + 房间」分开存**，换房不会串号。
- **4401 与连续两次握手失败**都清 token 回登录页；不能无限重连。
- **我方阵营**：`analysis-side` 的 `{mySide, all}` 语义与网页端一致；「都看」必须压过 ID 库。
- **百分比只转换一次**：`fraction()` 统一 0-1 / 0-100；`pct()` 只负责显示。
- **A/B 视角**：`persp()` 在 `mySide` 已知时把「A队/B队」替换成「我方/对方」；未知时保留 A/B。
- **轨迹窗口**：20 秒、坐标公式 `(gx-pos_x)/scale`、`(pos_y-gy)/scale`，与 `replay-core.js` 逐字一致。
- 雷达图路径 `/maps/...` 是根相对路径，客户端用服务端地址补全（和桌面端 `resolveRadarUrl` 同一个坑）。

### 实现上的几个坑

1. **旧连接的回调会抢新连接**：`WebSocket.close()` 的 `onDone` 是异步的，重连前必须先 `++generation`，
   回调里比对 generation，否则一次重连会变成两条连接、两个重连定时器。
2. **雷达图 `ui.Image` 要 clone**：`ImageInfo` 在回调结束后可能被回收，直接存 `info.image`
   会在下一次绘制时抛「Image was disposed」。现在 clone 一份并在替换/销毁时 dispose。
3. **换对局要清 profiles**：只换 `match` 不清画像，会把上一局的人补进新阵容（网页端也有同样的隐患）。
4. **Android 9+ 默认禁明文**：`AndroidManifest.xml` 显式 `usesCleartextTraffic="true"`，否则连不上 `http://192.168.x.x:8787`。
5. **国内网络**：`dl.google.com` 在本机会 TLS 失败；`settings.gradle.kts` / `build.gradle.kts` 已把阿里云镜像放在 `google()` 前面。

### 构建

```bash
cd mobile
flutter pub get
flutter analyze          # 0 issue
flutter test             # 17 passed
flutter build apk --release
# build/app/outputs/flutter-apk/app-release.apk
```

本机验证用的工具链装在 `.tools/`（gitignore）：Flutter 3.47.8、Android SDK 36（platform 35/36 +
build-tools 36.0.0/36.1.0 + NDK 28.2 + CMake 3.22.1）、JDK 17、AGP 9.1.0、Gradle 9.3.1。
`android/local.properties` 由 Flutter / Android Studio 生成，不入库。

实测产物：`app-release.apk` **50.4MB**（universal，arm64 + armeabi-v7a + x86_64），
包名 `com.qaqawa.cshelper`，minSdk 24 / targetSdk 36，目前是 debug 签名（可自装，正式分发要换 keystore）。

踩过的构建坑（都在 README 里）：

- Flutter SDK 自带的 `packages/flutter_tools/gradle/settings.gradle.kts` 也要拉 AGP，需同样加阿里云镜像；
- `shared_preferences_android` 依赖 `jni`，要 NDK 28.2 + CMake 3.22.1；`jni` 的 compileSdk 是 35，还要 platform 35；
- Windows 上 Kotlin 增量缓存会 `Could not close incremental caches`，已在 `android/gradle.properties` 设
  `kotlin.incremental=false`。

### 独立仓库与 CI

`mobile/` 现在**只在独立仓库** <https://github.com/QAQ-AWA/cs-helper-android> 维护
（主仓库 `.gitignore` 已忽略 `/mobile/`，本地目录只是工作副本）。独立仓库带自己的 `.github/workflows/build.yml`：

- push `main` → 构建 universal + arm64 + armeabi-v7a，更新 `latest-build` 预发布；
- 打 `v*` tag → 生成正式 Release（APK 直接可下）；
- 工作流会先装 platform 35/36、build-tools 36、NDK 28.2、CMake 3.22.1，再跑 analyze/test/build。

### 对手开局走位解读（v0.2.0）

服务端上线 `pathReport`（结构化的对手开局走位结论），客户端只负责展示：

- **入口**：快照 / `MATCH_DETECTED` 的 `match.pathReport`，以及新事件 `PATHS_REPORT_READY {report}`。
- **模型**：`PathReport` / `PathReportPlayer`，所有字段可选；`isEmpty` 时整张卡不渲染。
- **位置**：轨迹页 `_statusCard()` **上方**，先看结论再点选手。
- **卡片**：chip 行（tempo / sitePreference）→ summary（15sp w600）→ 每人一块（习惯 / 大概率 / 针对）
  → 整队对策；长文本换行不截断，缺省行直接不渲染。
- **不要**做成可折叠、不要重复分析页的「开局预判」Markdown。

真实服务端验收（`http://129.146.178.13:8787`，房间 `V9LSAH`）：`pathReport` 有
summary / tempo / sitePreference + 2 名选手 + 3 条对策，字段与约定一致，昵称能和轨迹列表对上。
`flutter analyze` 0 issue，22 tests passed（新增 3 个模型用例 + 2 个轨迹页渲染用例）。

### 未做

- 历史对局列表（服务端 `/api/v1/history/sessions` 已就绪，客户端没入口）。
- 轨迹本地持久化：只在单次会话内存缓存。
- iOS 构建目标；协议层可直接复用。
- 真机视觉走查：目前只有 `flutter analyze`、17 个测试（13 模型 + 4 UI）与 APK 构建/签名校验。
