# CS 匹配助手系统架构、实现原理与多端协同合并方案

> **文档版本**: v1.0.0  
> **适用代码基线**: `v3.3.0` (commit `fc70799` 及以上)  
> **目标读者**: 项目维护者、合并重构开发者、后端与移动端开发人员

---

## 目录
1. [项目定位与核心理念](#1-项目定位与核心理念)
2. [当前项目整体架构与技术栈](#2-当前项目整体架构与技术栈)
3. [核心功能实现原理](#3-核心功能实现原理)
   - [3.1 平台对局捕获与会话引擎 (5E & 完美)](#31-平台对局捕获与会话引擎-5e--完美)
   - [3.2 5E 赛后战报与预测复盘机制](#32-5e-赛后战报与预测复盘机制)
   - [3.3 AI 对局预测与智能分析流](#33-ai-对局预测与智能分析流)
   - [3.4 历史战绩本地持久化与适配器模式](#34-历史战绩本地持久化与适配器模式)
   - [3.5 急停评估与选手评价互动](#35-急停评估与选手评价互动)
4. [核心数据模型与关键字段字典](#4-核心数据模型与关键字段字典)
   - [4.1 实时对局与选手对象 (5E / Perfect)](#41-实时对局与选手对象-5e--perfect)
   - [4.2 赛后战报模型 (P5ePostMatchReport)](#42-赛后战报模型-p5epostmatchreport)
   - [4.3 AI 输入上下文与输出契约 (AI Contract)](#43-ai-输入上下文与输出契约-ai-contract)
   - [4.4 历史记录模型 (MatchHistoryItem)](#44-历史记录模型-matchhistoryitem)
5. [项目工程目录结构与核心模块划分](#5-项目工程目录结构与核心模块划分)
6. [两项目合并方案：从单机工具到「端-云-多端协同」战术中台](#6-两项目合并方案从单机工具到端-云-多端协同战术中台)
   - [6.1 合并背景与另一项目特性](#61-合并背景与另一项目特性)
   - [6.2 目标架构拓扑图 (Edge-Cloud-Teammate 模式)](#62-目标架构拓扑图-edge-cloud-teammate-模式)
   - [6.3 三大核心角色分工与职责](#63-三大核心角色分工与职责)
   - [6.4 降本提效机制 (API 聚合、AI 缓存、Demo 离线分析)](#64-降本提效机制-api-聚合ai-缓存demo-离线分析)
   - [6.5 协议与接口设计 (云端通信规范)](#65-协议与接口设计-云端通信规范)
   - [6.6 实施落地路线图 (Phase 1 ~ Phase 3)](#66-实施落地路线图-phase-1--phase-3)

---

## 1. 项目定位与核心理念

`cs-match-helper` 是一款专为 CS (Counter-Strike 2) 玩家打造的**实时竞技匹配分析与战术复盘助手**。
其核心价值在于：
1. **秒级侦测**：在 5E 对战平台或完美世界对战平台匹配成功、进入选人或准备就绪的第一时间，自动捕获本局 10 位选手的身份信息与对战背景。
2. **多维画像**：聚合历史天梯分、Rating 2.0、ADR、爆头率、近期胜率以及擅长地图表现，形成全维度选手画像。
3. **AI 战术辅助**：利用大模型对双方对阵阵容进行深度战术推演，输出胜率预估、关键突破口、危险人物警示与防守/进攻建议。
4. **赛后自动复盘**：对局结束后自动拉取战报大比分、半场得分、10 位选手详细数据、Demo 录像地址，并与赛前 AI 预测进行闭环比对（命中或爆冷）。

---

## 2. 当前项目整体架构与技术栈

项目基于现代前后端分离与轻量级桌面端架构构建：

```
┌────────────────────────────────────────────────────────┐
│                   前端呈现层 (Vue 3)                    │
│   Tailwind CSS v4 + Motion-V + Lucide Icons + Vite     │
│  - 实时对战看板 (MatchAssistantView)                     │
│  - 历史战绩库 (MatchHistoryView)                         │
│  - AI 战术卡片 / 赛后战报卡片 / 急停评测卡片            │
└───────────────────────────▲────────────────────────────┘
                            │ (Tauri IPC / Events)
┌───────────────────────────▼────────────────────────────┐
│                  核心业务逻辑层 (TypeScript)              │
│  - 平台适配层 (src/platforms/{5e, perfect})            │
│  - AI 推理编排层 (src/core/ai)                          │
│  - 历史归一化层 (src/core/match/history)                │
│  - 辅助算法 (急停评测、评论系统、倒计时调度)            │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                 系统级宿主层 (Rust / Tauri v2)           │
│  - 窗口管理、系统托盘、无边框沉浸式窗口拖拽             │
│  - 本地日志文件监控 / 进程捕获 (Perfect log sniffer)     │
│  - 网络请求代理 (免去跨域与浏览器安全沙箱限制)          │
└────────────────────────────────────────────────────────┘
```

---

## 3. 核心功能实现原理

### 3.1 平台对局捕获与会话引擎 (5E & 完美)

#### 5E 平台 (`src/platforms/5e/`)
- **会话状态机 (`match-session.ts`)**：
  采用轮询/事件双驱动模型维护 `P5eMatchSession` 生命周期（`idle` -> `matching` -> `ready` -> `active` -> `finished`）。
- **数据源获取 (`match-api.ts`)**：
  利用 5E Crane API (`https://gate.5eplay.com/crane/http/api/data/match/{match_code}`) 与选手主页 API，通过 Rust/Tauri 代理请求，无需玩家登录 Cookie 即可拉取公开对局元数据。
- **数据解析与补齐 (`match-parser.ts`, `field-mapper.ts`)**：
  将 5E 原生 JSON 映射归一化为标准的 10 选手阵列，分配为 Team 1 与 Team 2，并结合近期表现计算综合战力分。

#### 完美平台 (`src/platforms/perfect/`)
- **日志解密流 (`log-parser.ts`, `log-decrypt.ts`)**：
  完美对战平台客户端在本地生成加密对局日志。Rust 后台或前端嗅探器读取日志流后，通过自定义解密算法还原出 JSON 载荷（`extractEmbeddedJson`）。
- **就绪倒计时 (`ready-deadline.ts`)**：
  解析日志中的就绪截止时间（`ready_left_time_ms`），结合本地时区换算成时间戳，在界面上驱动秒级就绪倒计时。

---

### 3.2 5E 赛后战报与预测复盘机制

位于 [`src/platforms/5e/post-match.ts`](file:///I:/code项目/CS/src/platforms/5e/post-match.ts) 及组件 [`P5ePostMatchPanel.vue`](file:///I:/code项目/CS/src/mainview/components/P5ePostMatchPanel.vue)。

1. **接口解析**：
   请求 `https://gate.5eplay.com/crane/http/api/data/match/{matchCode}`，提取：
   - 最终比分：`main.group_1_score` : `main.group_2_score`；
   - 半场比分：`main.round_details` 或 `main.half_score`；
   - 胜负方：根据比分与 `winner` 字段判定（`A` | `B` | `Draw`）；
   - Demo 下载地址：`main.demo_url`；
   - 比赛时长：`main.match_time`。
2. **10 选手战绩与荣誉计算**：
   - 统计每个人的 K/D/A、Rating 2.0、ADR、RWS、KAST、爆头率、首杀首死差值、天梯 Elo 变动分。
   - 胜方最高评分者标记为 **MVP**，败方最高评分者标记为 **SVP**。
3. **AI 闭环复盘对比**：
   若该场比赛在赛前已生成 AI 预测（例如预测队伍 A 胜率 68%）：
   - 若队伍 A 获胜：判定为 `hit`（AI 预测命中 ✅）；
   - 若队伍 B 获胜：判定为 `upset`（下克上爆冷 ❌）；
   - 在战报面板中高亮展示复盘总结。

---

### 3.3 AI 对局预测与智能分析流

位于 [`src/core/ai/`](file:///I:/code项目/CS/src/core/ai/)。

1. **Prompt 组装工程 (`p5e-prompt.ts`)**：
   - 提取地图名称（如 `de_mirage`、`de_inferno`）；
   - 提取双方队伍的平均 Rating、平均 ADR、最高/最低分段落差；
   - 加入历史地图胜率补偿数据（`p5e-map-supplement.ts`）；
   - 注入结构化格式约束（要求输出指定 JSON 或带有预定义标记的 Markdown，避免 AI 幻觉）。
2. **推理与解析 (`sanitize-result.ts`, `display.ts`)**：
   - 调用配置的模型 API（支持 DeepSeek、OpenAI、Gemini 等兼容格式）；
   - 净化输出内容，提取：
     - 队伍 A / 队伍 B 胜率百分比；
     - 战力评级（碾压、势均力敌、劣势局）；
     - 核心突破口与防范重点选手；
     - 战术建议（慢打架枪、封道具快提等）。

---

### 3.4 历史战绩本地持久化与适配器模式

位于 [`src/core/match/history/`](file:///I:/code项目/CS/src/core/match/history/)。

- **多平台归一化 (`adapters.ts`)**：无论是 5E 的 `P5eMatch` 还是完美的 `PerfectMatch`，在存入本地历史记录时，均通过适配器统一转化为 `MatchHistoryItem`。
- **增量 Patch 机制**：支持对已有历史记录局部更新（例如赛前先存入对局基础信息与 AI 预测，赛后调用 `patchMatchPostMatch` 将战报比分与 10 人数据无损打入该条记录中）。
- **列表与详情解耦**：列表视图使用轻量对象 `MatchHistoryListItem`，详情弹窗使用全量对象 `MatchHistoryViewModel`，保障海量战绩流畅渲染。

---

## 4. 核心数据模型与关键字段字典

在未来与另一项目合并时，以下核心数据结构是跨模块、跨服务交互的基准协议。

### 4.1 实时对局与选手对象 (5E / Perfect)

```typescript
// 选手核心字段 (P5ePlayer)
export interface P5ePlayer {
  domain: string;              // 5E 唯一用户标识 / 自定义域名 (用于调取个人主页和历史战绩)
  nickname: string;            // 游戏昵称
  avatar: string;              // 头像 URL
  rating: number;              // Rating 2.0 (如 1.25)
  elo: number;                 // 当前天梯 Elo 分数 (如 2150)
  kill_avg: number;            // 场均击杀 (Kills Per Round / Match)
  death_avg: number;           // 场均死亡
  assist_avg: number;          // 场均助攻
  adr: number;                 // 场均伤害 (Average Damage per Round, 如 88.5)
  headshot_rate: number;       // 爆头率 (0~100)
  win_rate: number;            // 综合胜率 (0~100)
  kdr: number;                 // K/D 比率
  steam_id?: string;           // SteamID64 (关键：关联 Demo 的核心索引)
}

// 对局会话元数据 (P5eMatch)
export interface P5eMatch {
  match_code: string;          // 5E 比赛唯一标识码 (例: "2603212003001")
  map_name: string;            // 地图代码 (例: "de_dust2", "de_mirage")
  server_name?: string;        // 服务器节点 (例: "华东一区 128Tick")
  created_at: number;          // 匹配建立时间戳
  team1: P5ePlayer[];          // 阵营 A 5名选手
  team2: P5ePlayer[];          // 阵营 B 5名选手
}
```

---

### 4.2 赛后战报模型 (P5ePostMatchReport)

定义于 [`src/platforms/5e/types.ts`](file:///I:/code项目/CS/src/platforms/5e/types.ts)：

```typescript
export interface P5ePostMatchReport {
  matchCode: string;           // 比赛识别码
  mapName: string;             // 对战地图
  score: string;               // 最终大比分，例: "13 : 10"
  halfScores: string;          // 半场比分，例: "7 : 5, 6 : 5"
  totalRounds: number;         // 总回合数，例: 23
  winner: 'A' | 'B' | 'Draw';  // 胜负归属
  gameDuration: string;        // 对局耗时，例: "36分12秒"
  demoUrl?: string;            // 5E 官方 Demo (.dem.zip) 下载地址 (合并后提供给解析服务)
  teamA: P5ePostMatchPlayer[]; // 队伍 A 选手赛后数据
  teamB: P5ePostMatchPlayer[]; // 队伍 B 选手赛后数据
  aiComparison?: {             // AI 预测与现实复盘对照
    predictedWinner: string;   // 赛前 AI 预测获胜方
    actualWinner: string;      // 实际胜方
    isHit: boolean;            // 是否命中 (true = 命中, false = 爆冷)
    confidence?: number;       // 赛前预测置信度/胜率
  };
}

export interface P5ePostMatchPlayer {
  domain: string;              // 选手 ID
  nickname: string;            // 选手昵称
  avatar: string;              // 头像
  kills: number;               // 击杀数
  deaths: number;              // 死亡数
  assists: number;             // 助攻数
  kdDiff: number;              // 净胜差 (kills - deaths)
  rating: number;              // 本场 Rating 2.0
  adr: number;                 // 本场 ADR
  rws: number;                 // 本场 RWS (Round Win Share)
  kast?: number;               // KAST 百分比 (例: 78.3)
  hsRate: number;              // 爆头率
  firstKills: number;          // 首杀数 (FK)
  firstDeaths: number;         // 首死数 (FD)
  eloDelta?: number;           // 天梯分增减 (例: +18 或 -16)
  isMvp: boolean;              // 是否为本场最佳 (胜方最高评分)
  isSvp: boolean;              // 是否为败方最强 (败方最高评分)
}
```

---

### 4.3 AI 输入上下文与输出契约 (AI Contract)

```typescript
// AI 输入载荷 (AiPromptContext)
export interface AiPromptContext {
  mapName: string;
  myTeam: {
    avgRating: number;
    avgAdr: number;
    players: { name: string; rating: number; adr: number; winRate: number; topMap: string }[];
  };
  enemyTeam: {
    avgRating: number;
    avgAdr: number;
    players: { name: string; rating: number; adr: number; winRate: number; topMap: string }[];
  };
}

// AI 规范化输出 (AiAnalysisResult)
export interface AiAnalysisResult {
  winRateTeamA: number;        // 队伍 A 预测胜率 (0~100)
  winRateTeamB: number;        // 队伍 B 预测胜率 (0~100)
  matchPace: string;           // 对局节奏预测 (如: "激进快打", "道具默认控图")
  threatPlayers: string[];     // 对面高危枪男 (警惕其首杀)
  weakPoints: string[];        // 对面战术短板 (可针对其防守弱点)
  tacticalAdvice: string[];    // 具体给玩家的 3~5 条实战建议
}
```

---

## 5. 项目工程目录结构与核心模块划分

```
cs-match-helper/
├── src-tauri/                 # Rust 核心宿主 (Tauri v2)
│   ├── src/
│   │   ├── main.rs            # 桌面应用入口
│   │   └── lib.rs             # Tauri 命令注入 (网络代理、文件监听、窗口控制)
│   ├── Cargo.toml             # Rust 依赖声明
│   └── tauri.conf.json        # Tauri 应用视窗与安全策略配置
│
├── src/                       # 前端核心源码 (Vue 3 + TS)
│   ├── core/                  # 平台无关的通用领域层
│   │   ├── ai/                # 大模型 Prompt 构建、流式传输、响应净化
│   │   ├── match/history/     # 历史战绩存储适配器、格式转换
│   │   ├── counter-strafing/  # 急停分析算法 (Sub-tick 射击速度与移动时间戳判定)
│   │   └── comments/          # 玩家口碑库与匿名评价模块
│   │
│   ├── platforms/             # 对战平台适配层 (插件式设计)
│   │   ├── 5e/                # 5E 平台完整生命周期驱动
│   │   │   ├── match-session.ts  # 会话状态机
│   │   │   ├── match-api.ts      # 5E API 客户端
│   │   │   ├── match-parser.ts   # 实时数据清洗
│   │   │   └── post-match.ts     # 赛后战报拉取与复盘引擎
│   │   └── perfect/           # 完美世界平台适配
│   │       ├── log-parser.ts     # 日志行解析
│   │       ├── log-decrypt.ts    # 本地加密日志解密还原
│   │       └── ready-deadline.ts # 就绪倒计时校准
│   │
│   └── mainview/              # 前端 UI 表现层
│       ├── views/
│       │   ├── MatchAssistantView.vue  # 实时匹配主面板
│       │   └── MatchHistoryView.vue    # 历史战绩总览
│       └── components/
│           ├── MatchFeaturedPanel.vue  # 多 Tab 容器 (AI、战报、急停、评价)
│           ├── P5ePostMatchPanel.vue   # 5E 赛后战报大屏与十人详细榜单
│           ├── AiPredictionCard.vue    # 赛前 AI 胜率卡片
│           └── TeamTable.vue           # 双方阵容详细对比表
│
├── .github/workflows/         # CI/CD 自动化构建
│   └── build.yml              # Windows 自动化测试、Vite 打包、Cargo 编译与 Release
└── package.json               # Node 依赖与脚本编排
```

---

## 6. 两项目合并方案：从单机工具到「端-云-多端协同」战术中台

### 6.1 合并背景与另一项目特性

- **当前项目擅长**：本地轻量级侵入、毫秒级捕获实时对局、5E/完美平台画像呈现、赛前大模型推演、赛后战报复盘。
- **另一项目擅长**：依据对手的 SteamID / 平台 ID，自动化检索下载其最近数场对局的 **Demo 原始录像文件**，并解析出选手的**行动路径轨迹**（开局默认跑位、投掷物习惯点位、首杀交火点、常驻守包点等）。
- **两项目结合的痛点与目标**：
  - **算力与带宽痛点**：解析 Demo 涉及大量的空间坐标解包与矩阵计算，若直接在本地客户端边玩游戏边跑 Demo 解析，会造成玩家游戏掉帧、卡顿。
  - **API 成本与配额浪费**：一个车队 5 个人开黑，如果每个人电脑都在跑独立客户端拉数据、调 AI，会导致同一场对局被重复请求 5 次，造成 5 倍的 API 额度浪费与限流风险。
  - **战术协同价值**：开黑时，一人电脑开启捕获，队友无需在电脑上装任何插件，只需手机扫码或打开小程序/App，即可在手机屏幕上直观查看对面的走位热力图与 AI 破局点。

---

### 6.2 目标架构拓扑图 (Edge-Cloud-Teammate 模式)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        【边缘采集端：本地 PC】                           │
│  - 本地轻量运行 CS-Helper Desktop (Tauri)                              │
│  - 监听游戏进程 / 平台日志，瞬间捕获 match_code 与 10 人 SteamID         │
│  - 极轻开销，只负责采集，立即将对局基础元数据推送到中央服务器            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (1) 上传当前对局上下文 (HTTP/WS)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        【中央服务端：战术中台】                          │
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐    │
│   │ 1. 会话聚合中心 (Session Room Hub)                            │    │
│   │    - 生成 6 位房间码 (例: 8848) 或对局 Token                   │    │
│   │    - 针对同一局比赛，做 5 玩家去重，仅执行一次拉取与计算        │    │
│   │ 2. 外部 API 与大模型调度器 (API Aggregator & Cache)          │    │
│   │    - 统一缓存选手 30 天表现数据 (TTL: 2小时)                 │    │
│   │    - 聚合生成 Prompt，仅向大模型请求一次分析，结果多路广播     │    │
│   │ 3. 历史 Demo 路径解析 Worker (来自第二项目合并)              │    │
│   │    - 依据对手 5 人的 SteamID，异步并发拉取各自近 3 场 Demo     │    │
│   │    - 云端高性能解析 .dem：提取跑位轨迹坐标 (x,y,z) 与热力图     │    │
│   │    - 提取战术标签 (例: "长廊控图专家", "开局 15 秒必前压香蕉道")│    │
│   └──────────────────────────────────────────────────────────────┘    │
└──────────────┬──────────────────────────────────────────┬──────────────┘
               │ (2) 推送 Demo 路径与全局战报               │ (3) 手机端房间同步
               ▼                                          ▼
┌──────────────────────────────┐          ┌──────────────────────────────┐
│     【PC 客户端展示层】       │          │     【队友手机/网页移动端】    │
│ - 悬浮窗 / HUD / 双屏大板     │          │ - 手机 App (Flutter/React N) │
│ - 实时战术提示与对手弱点      │          │ - 队友扫码即看，不占游戏屏幕 │
│ - 进阶路径热力图弹窗          │          │ - 手机查看对手走位习惯与 AI  │
└──────────────────────────────┘          └──────────────────────────────┘
```

---

### 6.3 三大核心角色分工与职责

#### 1. PC 边缘客户端 (Desktop Edge Agent)
- **减负降噪**：关闭本地大算力消耗模块，仅保留本仓库中的**平台会话嗅探器 (`match-session.ts` / `log-parser.ts`)**。
- **上传握手**：匹配成功后，打包发送 `{ matchCode, platform: '5e', myPlayerId, opponentIds }` 到云端。
- **本地展示**：作为轻量级接收端，监听云端下发的结构化战术包并呈现在现有 Vue 界面或小巧的 In-Game Overlay 悬浮窗上。

#### 2. 云端中央服务器 (Tactical Backend Server)
- **Session 归并去重**：当车队中有多个队友开启了助手，服务端按 `match_code` 进行去重锁定（Distributed Lock），同一场比赛只触发一次后端计算流程。
- **Demo 异步下载与解析管道**（**吸收第二项目的核心代码**）：
  - 接收到对手 5 人的 ID 后，在后台 Worker 集群中调用官方或第三方 Demo 接口拉取录像压缩包；
  - 运行 Demo 语法分析器，统计：
    1. **开局第 0~20 秒跑位轨迹（Pathfinding Routes）**；
    2. **常规首发投掷物（烟雾/闪光/燃烧瓶）落点分布**；
    3. **狙击手第一架枪位分布**；
  - 将坐标点归一化到 2D 小地图（Overhead Radar Map）的像素坐标系上。
- **AI 综合推理引擎**（**继承本仓库 `src/core/ai`**）：
  - 将双方选手近期数据与 Demo 提取出的战术特征（如“对手 B 点防守容易被闪光致盲”、“对面 A 选手经常强起鸟狙前压”）共同喂给大模型；
  - 生成更加精准、更有实战指向性的战术攻略。

#### 3. 队友移动端 (Mobile Companion App / Web / 小程序)
- **免安装轻量化**：队友手机只需访问一个轻量 Web / PWA，或者手机 App；
- **扫码或房间码加入**：房主客户端界面显示一个“车队二维码”或 6 位房间码，队友手机输入即可同步当前对局。
- **移动端专属交互**：
  - 手机放在键盘旁或支架上，作为**第二屏战术面板**；
  - 点击对方某位选手，手机屏幕立即切换为该选手的**习惯跑位轨迹动图与热力图**；
  - 实时播报 AI 提炼的简明破局要点。

---

### 6.4 降本提效机制 (API 聚合、AI 缓存、Demo 离线分析)

| 优化维度 | 单机独立运行模式 (现状) | 云端中台协同模式 (合并后) | 节省幅度 / 效益 |
| :--- | :--- | :--- | :--- |
| **API 调用次数** | 5 名队友各拉 1 次，共 5 次 | 云端拉取 1 次，缓存并分发 5 份 | **节省 80% 外部 API 配额** |
| **大模型推理费用** | 5 人各调用一次大模型 API | 仅调用 1 次，通过 WebSocket 广播给 5 人 | **节省 80% 算力与 Token 开销** |
| **本地 CPU/内存** | 电脑解析 Demo，CPU 占用拉升 40%+ | 电脑零解析压力，云端 Worker 离线处理 | **零掉帧，保障竞技游戏高帧率** |
| **队友使用门槛** | 5 个人电脑都必须安装编译环境 | 1 人开 PC 客户端，其余 4 人手机扫码即用 | **使用门槛骤降，车队粘性极大增强** |

---

### 6.5 协议与接口设计 (云端通信规范)

#### 1. PC 客户端向云端同步对局 (`POST /api/v1/match/sync`)
```json
{
  "clientVersion": "3.3.0",
  "platform": "5e",
  "matchCode": "2603212003001",
  "mapName": "de_mirage",
  "reporterSteamId": "76561198000000001",
  "players": [
    { "domain": "player_a", "steamId": "76561198000000002", "team": "A" },
    { "domain": "player_b", "steamId": "76561198000000003", "team": "B" }
  ]
}
```
**响应 (`Response`)**：
```json
{
  "code": 0,
  "roomId": "884823",
  "roomToken": "jwt_token_for_websocket",
  "isLeader": true
}
```

#### 2. WebSocket 实时战术事件流 (`/ws/match/{roomId}`)
云端计算完毕后，主动向 PC 客户端和所有连接的手机端广播以下事件：

- **`match:profile_ready`**：10 选手全景数据与对比就绪（即本项目的 `P5eMatch` 数据）。
- **`match:ai_prediction`**：AI 胜率预测与战术建议就绪（即本项目的 `AiAnalysisResult`）。
- **`match:tactical_paths`**（**来自第二项目的产物**）：
  ```json
  {
    "event": "match:tactical_paths",
    "data": {
      "targetSteamId": "76561198000000003",
      "sampleDemosCount": 3,
      "routes": [
        {
          "side": "CT",
          "area": "B_Site",
          "probability": 0.75,
          "timingSecond": 14,
          "points": [ [120, 450], [135, 480], [150, 520] ],
          "tag": "常规开局下水道/二楼前压"
        }
      ]
    }
  }
  ```
- **`match:post_report`**：比赛结束后，自动推送战报大比分、半场分及 10 人赛后数据（即本项目的 `P5ePostMatchReport`）。

---

### 6.6 实施落地路线图 (Phase 1 ~ Phase 3)

#### 第一阶段：数据模型对齐与中台 SDK 封装 (Phase 1)
1. **统一数据抽象**：
   - 提取本仓库的 `P5ePlayer` 与另一项目的 `DemoPlayerSummary`，在公用接口中以 `steam_id` 为主外键打通关联；
2. **提取网络上报中间件**：
   - 在本项目的 `src/platforms/5e/match-session.ts` 与 `src/platforms/perfect/` 增加 Hook：当捕获到对局建立事件时，除向本地前端发 Event 外，同时发送轻量 HTTP 请求上报到服务端。

#### 第二阶段：服务端架构与 Demo 解析 Worker 搭建 (Phase 2)
1. **搭设云端 Node.js / Go 后端服务**：
   - 搭建房间中心（基于 Redis 管理房间与对局元数据，设置 2 小时过期时间）；
   - 接入大模型 API，并迁移本仓库 `src/core/ai/p5e-prompt.ts` 至服务端，实现服务端的 Prompt 渲染与缓存；
2. **集成另一项目的 Demo 分析引擎**：
   - 将 Demo 下载器与解包分析逻辑封装成独立的 Worker；
   - 对手 ID 传入后，Worker 自动拉取最近 3 场 Demo 进行并行轨迹分析，将生成的小地图路径 JSON 写入房间缓存。

#### 第三阶段：移动端伴侣与多端同步打通 (Phase 3)
1. **开发轻量伴侣端（Mobile / PWA）**：
   - 实现扫码加房逻辑；
   - 复用本仓库成熟的 UI 逻辑（选手对比表、AI 卡片、赛后战报），并在移动端适配触控与竖屏操作；
   - 增加**小地图轨迹重放画布（Canvas / SVG）**，直观演示对手开局常规路线。
2. **闭环测试**：
   - PC 单机只需 10MB 内存静默运行；
   - 5 名队友实时共享对手路径与 AI 分析，全流程自动化触发，赛后自动归档到云端历史战绩库。
