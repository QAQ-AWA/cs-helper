#!/usr/bin/env bash
# 部署前的环境自检：Python 依赖能否在 ARM64 上装、5E 的接口和 demo CDN 通不通。
# 用法：bash deploy/preflight.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

echo "== 机器 =="
echo "  架构：$(uname -m)   内核：$(uname -r)"
echo "  发行版：$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME")"
echo "  内存：$(free -h 2>/dev/null | awk '/Mem:/{print $2}')   磁盘：$(df -h "$REPO_DIR" | awk 'NR==2{print $4" 可用"}')"

echo "== Python =="
if command -v "$PY" >/dev/null; then
  ver="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  ok "python $ver（$("$PY" -c 'import platform;print(platform.machine())')）"
  case "$ver" in
    3.1[0-4]) ;;
    *) warn "3.10-3.14 才有 demoparser2 的 ARM 预编译轮子，当前 $ver 可能要自己编译" ;;
  esac
else
  bad "找不到 $PY"
  exit 1
fi

echo "== 依赖轮子（ARM64 是否有预编译包）=="
for spec in "demoparser2==0.41.4" "pandas==3.0.3" "numpy==2.4.6"; do
  if "$PY" -m pip download --only-binary=:all: --no-deps -d /tmp/cs-preflight "$spec" >/tmp/cs-preflight.log 2>&1; then
    ok "$spec 有 $(ls /tmp/cs-preflight | grep -c "$(echo "$spec" | cut -d= -f1)") 个可用包"
  else
    bad "$spec 拿不到预编译包（看 /tmp/cs-preflight.log）"
  fi
done
rm -rf /tmp/cs-preflight /tmp/cs-preflight.log

echo "== 5E 接口 =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 https://api.5eplay.com/ 2>/dev/null)
[ "$code" = "200" ] || [ "$code" = "404" ] || [ "$code" = "403" ] && ok "api.5eplay.com 可达（HTTP $code）" || bad "api.5eplay.com 不可达（$code）"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 https://gate.5eplay.com/ 2>/dev/null)
[ "$code" != "000" ] && ok "gate.5eplay.com 可达（HTTP $code）" || bad "gate.5eplay.com 不可达"

echo "== demo CDN 速度（真正决定轨迹出得快不快）=="
# 只取前 8MB，测速后丢弃；5E 的 demo 是 200-400MB 一个。
url="https://cd-t-demo.5eplaycdn.com/pug/20261017/g161-20261017061226220457717_de_dust2.zip"
speed=$(curl -s -o /dev/null -m 20 -r 0-8388607 -w '%{speed_download}' "$url" 2>/dev/null || echo 0)
mbps=$(awk -v s="${speed:-0}" 'BEGIN{printf "%.1f", s*8/1000000}')
if [ "${speed%.*}" -gt 2000000 ] 2>/dev/null; then
  ok "约 ${mbps} Mbps（8MB 测速）—— 一个 300MB demo 约 $(awk -v s="$speed" 'BEGIN{printf "%.0f", 300*1024*1024/s}') 秒"
elif [ "${speed%.*}" -gt 500000 ] 2>/dev/null; then
  warn "约 ${mbps} Mbps —— 偏慢，5 个对手可能要等几分钟"
else
  bad "拉不动 demo（${mbps} Mbps）——这台机器到 5E CDN 的线路很差，建议换区域"
fi

echo "== AI 端点 =="
[ -n "${CS_HELPER_AI_KEY:-}" ] && ok "已设置 CS_HELPER_AI_KEY" || warn "没有 CS_HELPER_AI_KEY，分析任务会被跳过（其它功能照常）"

echo
echo "结论：架构与依赖没问题就看 5E 那两行。CDN 太慢的话，把服务端放在离 5E 近的机房（首尔/香港/上海）比堆配置有用。"
