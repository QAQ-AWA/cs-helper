#!/usr/bin/env bash
# 一键部署到 Ubuntu 22.04/24.04（ARM64 或 x86_64 都行）。
#
#   sudo bash deploy/install.sh                 # 部署到 /opt/cs-helper
#   REPO_DIR=/srv/cs-helper sudo -E bash deploy/install.sh
#
# 脚本可重复执行：已存在的 .env、数据目录不会被覆盖。
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/cs-helper}"
SERVICE_USER="${SERVICE_USER:-cshelper}"
PORT="${PORT:-8787}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

say() { printf '\033[36m==>\033[0m %s\n' "$1"; }
die() { printf '\033[31m错误：\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 运行：sudo bash deploy/install.sh"
command -v apt-get >/dev/null || die "这个脚本只处理 Debian/Ubuntu；别的发行版照着 docs/DEPLOY.md 手工来"

say "安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip rsync curl ca-certificates

"$PY" - <<'PY' || die "Python 版本太低，需要 3.10+（demoparser2 的 ARM 轮子从 3.10 起）"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

say "创建服务账号 $SERVICE_USER"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

say "同步代码到 $REPO_DIR"
mkdir -p "$REPO_DIR"
if [ "$(readlink -f "$SRC_DIR")" = "$(readlink -f "$REPO_DIR")" ]; then
  echo "    源目录就是目标目录，跳过同步（就地部署）"
else
  rsync -a --delete \
    --exclude '.git' --exclude '.cache' --exclude 'node_modules' \
    --exclude 'desktop' --exclude 'mobile' --exclude '.tools' --exclude 'dist' \
    "$SRC_DIR"/ "$REPO_DIR"/
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"

say "创建虚拟环境并安装依赖（ARM64 上全部走预编译轮子，不需要编译器）"
if [ ! -x "$REPO_DIR/.venv/bin/python" ]; then
  "$PY" -m venv "$REPO_DIR/.venv"
fi
"$REPO_DIR/.venv/bin/pip" install -q --upgrade pip wheel
"$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/server/requirements.txt"
"$REPO_DIR/.venv/bin/pip" install -q -r "$REPO_DIR/engine/requirements.txt"

say "写入 /etc/cs-helper.env"
if [ -f /etc/cs-helper.env ]; then
  echo "    已存在，保留不动（要改就编辑 /etc/cs-helper.env）"
else
  install -m 0640 -o root -g "$SERVICE_USER" "$REPO_DIR/deploy/cs-helper.env.example" /etc/cs-helper.env
  secret="$("$REPO_DIR/.venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(32))')"
  sed -i "s|^CS_HELPER_SERVER_SECRET=.*|CS_HELPER_SERVER_SECRET=$secret|" /etc/cs-helper.env
  echo "    已生成签名密钥；AI key 需要你自己填 CS_HELPER_AI_KEY"
fi

say "安装 systemd 服务"
install -m 0644 "$REPO_DIR/deploy/cs-helper.service" /etc/systemd/system/cs-helper.service
systemctl daemon-reload
systemctl enable --now cs-helper >/dev/null

say "等待服务起来"
for i in $(seq 1 30); do
  if curl -fsS -m 2 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
  [ "$i" = "30" ] && { journalctl -u cs-helper -n 30 --no-pager; die "服务没起来，日志在上面"; }
done

say "本机健康检查"
curl -s "http://127.0.0.1:$PORT/healthz" | head -c 200; echo

ip="$(curl -fsS -m 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
cat <<EOF

部署完成。

  服务状态：systemctl status cs-helper
  实时日志：journalctl -u cs-helper -f
  配置文件：/etc/cs-helper.env（改完 systemctl restart cs-helper）
  数据目录：/var/lib/cs-helper（会话、产物、demo 缓存）

接下来两件事：

1. 放行端口（二选一或都做）
   - 云厂商安全列表 / 安全组放行 TCP $PORT
   - 本机防火墙：ufw allow $PORT/tcp

2. 在桌面端「设置 → 小队协同」里把服务端地址填成：
     http://$ip:$PORT
   然后打开协同面板，二维码里的手机链接会自动变成这个公网地址。

想上 HTTPS（手机上更好用、也能装成 PWA）：见 docs/DEPLOY.md 的 Caddy 一节。
EOF
