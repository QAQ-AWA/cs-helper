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
| `setup_maps.py` | demo/server | 一次性生成 `data/maps/<map>/{radar.png,meta.json}` |

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

当前结果：**97 passed, 10 skipped**。skip 的是需要约 328 MB 真实 demo 的集成用例，缺文件时自动跳过。

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

## 待办（P2）

- `config.py` 的模块级 env → `EngineConfig` 对象，`OUTPUT_DIR` 按 job 隔离（当前全局目录会在并发任务间相互覆盖）。
- `cleanup_demos` 的全局 30GB 阈值 → 按租户配额。
- `.demo_index.json` 的读写 → 注入 `DemoIndex` 接口（Redis 实现）。
