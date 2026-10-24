# 交接文档

> 接手先读这份：现状、约定、验收清单都在这。
> 历史改动与踩坑细节见 [HISTORY.md](HISTORY.md)，架构取舍见 [architecture.md](architecture.md)。

## 一句话项目

CS2 开黑辅助：**PC 客户端**侦测对局并上报阵容 → **服务端**聚合房间、拉取并解析对手历史 Demo、跑 AI 战术分析 → **手机**（PWA / 原生 Android）实时展示十人画像、习惯轨迹与赛后复盘。只做**赛前历史数据**（合规红线：不读内存、不注入、不做局内实时敌人位置）。

## 仓库

三个远端，同一份 main：

| remote | 仓库 | 角色 |
| --- | --- | --- |
| `exe` | `QAQ-AWA/cs-helper-exe` | **构建 + 发布**：Actions 在这里跑，安装包发到本仓 `latest-build`（默认 `GITHUB_TOKEN` 即可） |
| `test` | `QAQ-AWA/cs-test` | 镜像（本地默认上游）：构建只跑测试 + 产 artifact，发布步骤用 `github.repository` 挡住 |
| `helper` | `QAQ-AWA/cs-helper` | 主仓库（源码归档） |

- 第四个仓库 `QAQ-AWA/cs-helper-android` 是 Flutter 客户端，**不在这份 main 里**：
  本地 `mobile/` 只是它的工作副本，已被 `.gitignore` 忽略，别往主仓库提交
- 推代码要推三个：`git push`（test）+ `git push helper main` + `git push exe main`
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

## 真实对局测试清单（首次验收）

前置：**必须用 `7d1aded` 及之后的构建**（`a853bd9` 之前的 exe 没有服务端分析面板与同步设置）。

1. **起服务端**（带 AI key，否则战术/开局会显示「未配置 AI key」）：
   ```bash
   CS_HELPER_SERVER_SECRET=... CS_HELPER_AI_KEY=... CS_HELPER_AI_MODEL=deepseek-flash \
   CS_HELPER_DEV=1 CS_HELPER_DEMO=1 \
   CS_HELPER_DEMO_DIR=I:/workbuddy/cn-code/cs-helper/.cache/realjob/demos \
   .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --app-dir server
   ```
2. **客户端设置 → 同步**：地址填 `http://<局域网IP>:8787`（不是 127.0.0.1，手机要访问），
   点「创建房间」或输入房间码加入。标题栏「小队协同」应变绿并显示房间码。
3. **启动页**：选 5E 客户端路径 → 拉起 5E → 等 hook（`MatchEmptyState` 应显示等待动画）。
4. **开始匹配**：检测到对局后应进入 `MatchWorkspace`，阵容页 10 人带 Rating/ADR/K/D/HS%。
5. **手机**：`http://<局域网IP>:8787/?room=MAIN` → 阵容、轨迹、AI。
6. **分析页**：战术分析（服务端 AI，首字约 0.5s）、开局预判（轨迹就绪后自动跑）。
7. **赛后**：赛后页点「拉取战报」→ 手机赛后卡片同步出现（战报由桌面端拉取后上报）。
8. **重启服务端**：桌面端自动重连，历史里能看到这一局（会话已落盘）。

### 常见失败点

| 现象 | 先查 |
| --- | --- |
| 阵容页空 | 服务端日志有没有 `POST /api/v1/match/report 200`；`curl /api/v1/room/MAIN/snapshot` |
| 检测不到对局 | 5E 是否由客户端拉起、9222 端口是否被占用 |
| 轨迹一直「解析中」 | 首次 10 人 1–3 分钟是正常的（下载瓶颈），看 `/healthz` 的 `artifacts` 是否增长 |
| AI 卡片空白 | 服务端是否配了 `CS_HELPER_AI_KEY`；日志里的 2005 |
| 手机连不上 | 设置页的手机链接是否是 `192.168.x.x`（不是 198.18.x 代理地址） |

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
