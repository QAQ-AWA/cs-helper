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
  ├─ trajectory.py ─── 开局画像：CT 站位、T 下包分布、道具与开局死亡
  ├─ ws.py ────── 每连接有界队列；重连先补事件、快照最后发
  ├─ jobs.py ──── 画像(秒级) → AI(流式) → Demo 任务；按 platform:matchId 全局去重
  ├─ engine_runner.py ── 子进程管理（见"为什么跑子进程"）
  ├─ artifacts.py ────── 内容寻址存储：索引(~1KB) + 按玩家 parts(~150KB)，写穿到磁盘
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

# 运维（P5）
CS_HELPER_DATA_DIR=...             # 历史根目录，默认 .cache/data
CS_HELPER_ROOM_TTL=14400           # 房间无访问多久回收（秒）
CS_HELPER_GC_INTERVAL=60           # 后台回收周期（秒），0 关闭
CS_HELPER_HISTORY_DAYS=7           # 历史保留天数，到期连轨迹一起删
CS_HELPER_SESSION_MEMORY_MAX=50    # 内存里最多常驻多少局

# 测试
cd server && pytest tests -q    # 102
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

### 1. 我方阵营：只下对面 5 人

下载是唯一瓶颈（单人 130–230MB / ~21s），十人全下就是十份等待，而赛前真正要研究的只有对面。

- `MatchReport.mySide: "ct"|"t"|null`；解析顺序 **显式选择 > `isSelf` 标记 > `partyTag` > 不确定**（不确定就退回十人，绝不猜）。
- `adapters.demo_targets()` 一处过滤，`to_engine_hints` / `demo_job_targets` / 进度总数全部走它。
- `POST /api/v1/room/{code}/analysis-side` 改边重跑：demo 按 domain 缓存在磁盘，切换只补没下过的人。
- 手机端「我们在哪边」三档（CT / T / 都看），改完立刻显示目标人数。
- 重复上报同一局且没带 `mySide` 时，保留已有选择（否则第二台 PC 一上报就白下十人）。

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

- **开局预判未接真实模型**：本轮环境没有 `CS_HELPER_AI_KEY`，只验证了提示词结构与真实画像数据，`tacticsState` 落在 `skipped`。接上 key 后应能看到 400 字左右的四段输出。
- **`mySide` 桌面端未上报**：桌面端目前既没有 `isSelf` 也没有 `partyTag`，所以只能靠手机端手动选；后续可在桌面端读本机 SteamID 自动填。
- **包点映射只验证了 mirage**：326/327 的 A/B 约定按 CS2 实体顺序推断，其他图若出现反向需在 `parse.BOMBSITE_LABELS` 按图覆盖。
- **历史习惯聚合**：现在是单场轨迹回放 + 单场开局画像；跨场聚合（同一对手多场叠加）还没做。
- 真机视觉：手机渲染逻辑有无头断言保证不崩，但配色/缩放/手感未做真机走查。
- 桌面端 AI 面板未订阅 `phase:"thinking"`，也没订阅新的 `AI_TACTICS_*`。
- 328MB 集成 demo 缺失，engine 有 10 个用例 skip。

## 建议下一步

1. 接真实 key 跑一次开局预判，校准提示词（这是本轮唯一没闭环的环节）。
2. 跨场聚合：同一对手多场 demo 的包点分布叠加，`/api/v1/history/sessions` 已是入口。
3. 发布桌面端：latest-build 已可用，打 `v1.0.0` 发正式版并更新根 README 下载链接。
4. 真机走查手机端轨迹页与新的「开局预判」卡片。
