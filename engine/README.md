# engine — Demo 解析引擎（从 `demo/server` 抽离）

纯计算与网络层，**不含任何 HTTP 框架**。服务端把它当作库调用，单机 legacy 模式也复用它。

## 来源与边界

| 文件 | 来源 | 说明 |
| --- | --- | --- |
| `pipeline.py` | demo/server | 检索 → 下载 → 解析 → 组装，含 fast 模式 |
| `parse.py` | demo/server | 回合分类、位置采样、投掷物 |
| `api_client.py` | demo/server | 5E arena/gate 公开接口，含 CDN 白名单与 SSRF 防护 |
| `maps.py` | demo/server | `game_to_pixel`、地图资源加载 |
| `player_json.py` | demo/server | 单玩家回放 JSON 组装 |
| `combat.py` | demo/server | K/D 与 AWP 持枪率 |
| `config.py` | demo/server | 环境变量配置（`CS_SCOUT_*`） |
| `setup_maps.py` | demo/server | 从 `awpy get maps` 生成地图资源（CDN 有时 403） |
| `import_radar.py` | 本项目新增 | 从本地解包的 `<map>.png` + `<map>.txt` 生成地图资源，离线可用 |
| `job_runner.py` | 本项目新增 | 子进程入口：stdin 收任务、stdout 发 JSONL、退出码表成败 |

**未迁入**（有意为之）：

- `web_server.py`：Flask 全局单例状态机，无法多房间，由 `server/` 的 FastAPI 网关替代。
- `fivee_monitor.py`(2260 行) / `perfectworld_experiment/`：本机侦测，统一由客户端 Rust 层负责，服务端不应连接玩家本机 CDP。
- 对应的 4 个测试（`test_web` / `test_local_startup` / `test_fivee_monitor` / `test_frontend_js`）随其被测代码一起留在 `demo`，此处保留 16 个覆盖本目录模块的用例。

## 与 demo 的差异（唯一一处代码改动）

`api_client._get_player_uuid`：当**所有**候选详情请求都失败时抛 `DemoLookupError`，而不是返回 `None`。

原因：原来的实现把"每个请求都报错"吞成 `None`，上层 `get_demos_by_domain` 因此认为"该玩家没有录像"，在完整数据源故障时返回空列表而不是抛错，服务端无法区分"该重试"与"确实没有"。对应测试 `test_uuid_bootstrap_request_failure_is_not_reported_as_empty` 在 `demo` 原仓库中同样是失败的（已复现确认），属于上游遗留缺陷。`demo/server/api_client.py` 需要同步这一处。

## 目录约定

```
engine/
├── data/maps/<map>/radar.png + meta.json   （由 setup_maps.py 生成，不入库）
├── demos_opponents/                         （.dem 缓存 + .demo_index.json）
└── output/                                  （player_<domain>.json）
```

默认路径相对本目录；可用 `CS_SCOUT_DEMO_DIR` / `CS_SCOUT_OUTPUT_DIR` / `CS_SCOUT_MAPS_DIR` 覆盖。

## 测试

```bash
pip install -r requirements.txt
cd engine && python -m pytest tests -v
```

当前结果：**101 passed, 10 skipped**。skip 的是需要约 328 MB 真实 demo 的集成用例，缺文件时自动跳过。

## 地图资源

解析和回放都需要 `data/maps/<map>/{radar.png,meta.json}`（坐标变换 + 雷达底图），仓库不附带。两种来源：

```bash
# A. 官方雷达图（需要 awpy，CDN 偶尔 403）
pip install awpy==2.0.2
awpy get maps
python setup_maps.py

# B. 离线：从 pak01.vpk 解包出 resource/overviews 后导入
python import_radar.py --from-dir D:/overviews
```

缺少资源时服务端会直接回 `ROOM_ERROR 2002`，不会跑到一半才失败。

## 与服务端的接缝

```python
import pipeline
pipeline.run(
    usernames=["Alpha", "Bravo"],      # 顺序与 player_hints 一致
    map_name="de_mirage",
    max_demos=6,
    player_hints=[                     # 来自客户端上报，跳过模糊搜索
        {"username": "Alpha", "domain": "player_a", "steamid": "76561198000000002"},
    ],
    progress_cb=lambda i, total, name, step, msg: ...,   # → JOB_PROGRESS
    cancel_event=threading.Event(),
)
```

`player_hints` 必须是完整的 `username + domain + steamid`；任一缺失或非法时传 `None`，让引擎回退到自身搜索（见 `adapters.to_engine_hints`）。

## 子进程入口

服务端不直接 import 本目录，而是执行 `job_runner.py`：

```bash
echo '{"usernames":["Alpha"],"mapName":"de_mirage","outputDir":"/tmp/o","demoDir":"/tmp/d","mapsDir":"/tmp/m"}' \
  | python job_runner.py
```

它在 import 任何引擎模块**之前**把 `CS_SCOUT_*_DIR` 写进环境变量，因此每个任务的输出目录互不干扰。stdout 只输出 JSON 行（`progress` / `done` / `error`），日志走 stderr。

## 待办（P2 之后）

- `config.py` 仍从环境变量读路径；若将来需要在同一进程内跑多任务，再抽 `EngineConfig` 对象。
- `cleanup_demos` 的全局 30GB 阈值仍是单租户假设，多房间时应改为配额。
- `.demo_index.json` 的读写尚未抽成可注入的 `DemoIndex`（目前跨任务共享缓存，行为正确）。
