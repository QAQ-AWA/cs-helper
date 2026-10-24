# 部署到远程服务器（甲骨文 A1 / ARM64）

结论：**能跑**。整个链路是 Python + 一个 Rust 扩展（demoparser2），所有依赖在
aarch64 上都有预编译轮子，不需要在服务器上编译任何东西。

## 为什么能跑

| 组件 | ARM64 情况 |
| --- | --- |
| 服务端（FastAPI + uvicorn） | 纯 Python，无架构依赖 |
| 引擎（pandas / numpy） | manylinux_aarch64 轮子齐全 |
| 引擎（demoparser2） | **关键**：0.41.4 提供 `manylinux_2_17_aarch64` 轮子，覆盖 cp310–cp314 |
| 子进程调度 | `CREATE_NO_WINDOW` 只在 `os.name == "nt"` 时生效，Linux 走 0 |
| 路径 | 全部走 `REPO_ROOT` + 环境变量，没有硬编码 Windows 路径 |

要求：Python **3.10–3.14**（3.13 的轮子也有）。Ubuntu 22.04 自带 3.10、24.04 自带 3.12，都行。

## 地图资源

雷达图（`engine/data/maps/`，8 张共 1.2MB）**随仓库走**，部署时不需要额外下载。
换季加了新地图时，在任意一台装了 `awpy` 的机器上跑 `python engine/setup_maps.py`
生成后再提交；服务器上没有 awpy 也不用管，缺图会报
`Map assets missing for de_xxx`——说明那张图还没进仓库。

## 资源需求

| 项 | 单局实际占用 | 说明 |
| --- | --- | --- |
| CPU | 解析时 1 核跑满 ~2.5s/人 | 4 个对手 ≈ 10s，串行解析，不吃多核 |
| 内存 | 峰值 1–2GB | 一个 300MB demo 全量读进内存；unit 里 `MemoryMax=8G` 兜底 |
| 磁盘 | 1–2GB/局 | 5 个 demo × 200–400MB；`cleanup_demos` 会清，留 20GB 足够 |
| 带宽 | 下行 1–2GB/局 | 这是**唯一可能卡住的地方**，见下面风险 |

甲骨文 A1 免费额度（4 OCPU / 24GB / 200GB 盘 / 10TB 出站）远超需求。

## 一键部署

```bash
# 1) 把代码放到服务器上（任选一种）
git clone https://github.com/QAQ-AWA/cs-helper-exe.git /tmp/cs-helper-src
#   或者本地 rsync：rsync -a --exclude .git --exclude .cache ./ user@host:/tmp/cs-helper-src/

# 2) 先自检（会测 5E 接口和 demo CDN 速度）
cd /tmp/cs-helper-src && bash deploy/preflight.sh

# 3) 安装
sudo bash deploy/install.sh
```

装完会得到：

```
/etc/systemd/system/cs-helper.service   服务单元（已 enable + start）
/etc/cs-helper.env                      环境变量（已生成签名密钥）
/opt/cs-helper/                         代码 + .venv
/var/lib/cs-helper/                     数据（会话、产物、demo 缓存）
```

然后放行端口：

```bash
sudo ufw allow 8787/tcp          # 本机防火墙
# 云控制台还要在「安全列表 / Security List」里放行 TCP 8787
```

## 客户端怎么连

桌面端 **设置 → 小队协同**：

```
服务端地址：http://<公网IP>:8787
房间码：    MAIN
```

连上之后打开协同面板，二维码里的手机链接会自动变成 `http://<公网IP>:8787/?room=MAIN`，
队友扫码即可。**不需要改任何代码**——手机链接就是从 `serverUrl` 派生的。

> 如果想让手机走域名 + HTTPS，见下一节；桌面端和手机都填 `https://` 地址即可。

## 可选：套 HTTPS（Caddy）

```bash
sudo apt install -y caddy
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo vim /etc/caddy/Caddyfile     # 把 cs.example.com 换成你的域名
sudo systemctl reload caddy
```

域名 A 记录指向服务器公网 IP，Caddy 自动签证书。WebSocket 走 `/ws`，Caddy 自动升级，不用额外配置。

## 风险：5E 的 demo CDN 线路

这是唯一需要**先测再决定**的点。服务端要自己去 `cd-t-demo.5eplaycdn.com` 拉
200–400MB 的 demo，如果机房到 5E 的线路差：

- 轨迹会从「2 分钟」变成「十几分钟」，甚至超时失败
- 5E 的接口（`gate.5eplay.com` / `player/home`）可能对境外 IP 限流

`deploy/preflight.sh` 会实测 8MB 的下载速度并给出估算。经验值：

| 测速结果 | 判断 |
| --- | --- |
| > 20 Mbps | 很好，一个 300MB demo 约 2 分钟 |
| 2–20 Mbps | 能用，5 个对手 5–10 分钟 |
| < 2 Mbps | 别在这台机器上跑，换首尔/香港/新加坡的机房，或者继续用本机 |

## 运维

```bash
systemctl status cs-helper          # 状态
journalctl -u cs-helper -f          # 日志（含每个玩家的下载/解析进度）
systemctl restart cs-helper         # 改完 /etc/cs-helper.env 后重启

# 升级
cd /tmp/cs-helper-src && git pull
sudo bash deploy/install.sh         # 幂等：只同步代码 + 重装依赖，不动 .env 和数据

# 备份（会话 + 产物，不含 demo 缓存）
tar czf cs-helper-data-$(date +%F).tgz -C /var/lib/cs-helper data
```

## 常见问题

**重启后手机提示「登录状态已失效」**
签名密钥变了。检查 `/etc/cs-helper.env` 里的 `CS_HELPER_SERVER_SECRET` 是否为空
（为空会每次启动随机生成）。装脚本已经写过一次固定值，手工部署要注意。

**轨迹一直 waiting**
看 `journalctl -u cs-helper`：地图没确认时本来就会等；如果地图有了还不动，多半是
demo 下载失败（CDN 拉不动），日志里会有 `Download failed for g161-...`。

**手机连不上但桌面端正常**
桌面端连的是 `127.0.0.1` 还是公网 IP？手机必须用公网 IP/域名。另外确认云安全列表放行了端口。

**内存吃满被杀**
`MemoryMax=8G` 会触发 OOM kill。把 `CS_HELPER_DEMO_MAX_DEMOS` 保持 1，
或者调低 `CS_SCOUT_NORMAL_DOWNLOAD_WORKERS`（同时下载的 demo 数）。
