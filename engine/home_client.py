"""5E Gate 签名客户端：player/home 赛季数据。

从桌面端 `src-tauri/src/platform/platform_5e_gate_sign.rs` 移植。签名是阿里云
API 网关的 HMAC-SHA256 方案，密钥硬编码在 5E 前端产物里（旧项目同样如此），
**5E 一改前端就可能失效**——所以这里所有失败都必须可降级，不能影响主链路。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Iterable

import requests

log = logging.getLogger("home_client")

GATE_HMAC_SECRET = "28137ed61f21705e2cddf498e22fae8f"
PLAYER_HOME_HOST = "https://gate.5eplay.com"
PLAYER_HOME_PATH = "/cranenew/http/api/data/v3/player/home"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0"
)
TIMEOUT = 12

# 签名只覆盖这两个头（值为空也要参与），与 Rust 侧 GATE_SIGN_HEADERS 一致。
SIGNED_HEADERS = (("Accept-Language", "zh-cn"), ("Authorization", ""))


class GateSignatureError(RuntimeError):
    """401/403：密钥或签名规则失效，通常意味着 5E 改了前端。"""


class HomeLookupError(RuntimeError):
    pass


def build_signed_headers(method: str, path: str, query: dict[str, str]) -> dict[str, str]:
    """阿里云网关 HMAC 签名头。顺序与大小写都必须和 Rust 实现完全一致。"""

    method = method.upper()
    path_and_params = path
    if query:
        # BTreeMap 语义：按 key 升序拼接。
        path_and_params = path + "?" + "&".join(f"{key}={query[key]}" for key in sorted(query))

    keys = sorted(
        (name for name, _ in SIGNED_HEADERS if name.lower() not in {"accept", "content-type"}),
        key=str.lower,
    )
    lines = []
    for name in keys:
        value = next(v for k, v in SIGNED_HEADERS if k.lower() == name.lower()).strip()
        lines.append(f"{name.lower()}:{value}")
    headers_block = "\n".join(lines)

    parts = [method, "*/*", "", "", ""]
    if headers_block:
        parts.append(headers_block)
    parts.append(path_and_params)
    canonical = "\n".join(parts)

    digest = hmac.new(GATE_HMAC_SECRET.encode(), canonical.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()

    return {
        "Accept": "*/*",
        "Accept-Language": "zh-cn",
        "Authorization": "",
        "Content-MD5": "",
        "Referer": "https://view-arena.5eplay.com/",
        "Origin": "https://view-arena.5eplay.com",
        "x-ca-key": "5eplay",
        "x-ca-signature-method": "HmacSHA256",
        "x-ca-signature-headers": ",".join(keys),
        "x-ca-signature": signature,
        "User-Agent": USER_AGENT,
    }


def fetch_home(uuid: str) -> dict[str, Any]:
    uuid = (uuid or "").strip()
    if not uuid:
        raise HomeLookupError("uuid 不能为空")

    headers = build_signed_headers("GET", PLAYER_HOME_PATH, {"uuid": uuid})
    try:
        response = requests.get(
            PLAYER_HOME_HOST + PLAYER_HOME_PATH,
            params={"uuid": uuid},
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise HomeLookupError(f"请求 player/home 失败: {exc}") from exc

    if response.status_code in (401, 403):
        raise GateSignatureError(
            f"player/home 签名验证失败（HTTP {response.status_code}），5E 可能已更新密钥"
        )
    if response.status_code >= 400:
        raise HomeLookupError(f"player/home HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError as exc:
        raise HomeLookupError("player/home 返回的不是 JSON") from exc
    if not isinstance(body, dict) or body.get("code") not in (0, "0"):
        message = body.get("message") if isinstance(body, dict) else None
        raise HomeLookupError(f"player/home 业务错误: {message or '未知'}")
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("season_data"), dict):
        raise HomeLookupError("player/home 缺少 season_data")
    return body


def parse_season(body: dict[str, Any]) -> dict[str, Any]:
    """把 5E 的 snake_case 赛季块压成我们自己的字段，缺的就不要。

    5E 的 kast / per_headshot / per_win_match 都是 0-1 的小数，而客户端上报的
    ``headshotRate`` / ``winRate`` 是百分数。这里统一乘 100，否则同一份证据包里
    会出现两种量纲。
    """

    data = body.get("data") or {}
    season = data.get("season_data") or {}

    def num(key: str) -> float | None:
        value = season.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return round(float(value), 3)

    def pct(key: str) -> float | None:
        value = num(key)
        if value is None:
            return None
        return round(value * 100, 1) if value <= 1.0 else round(value, 1)

    kill, death = num("kill"), num("death")
    out = {
        "rating": num("rating"),
        "avgRating": num("avg_rating"),
        "adr": num("adr"),
        "rws": num("rws"),
        "kast": pct("kast"),
        "headshot": pct("per_headshot"),
        "matches": num("match_total"),
        "winRate": pct("per_win_match"),
        "impact": num("impact"),
        "kd": round(kill / death, 2) if kill and death else None,
    }
    return {key: value for key, value in out.items() if value is not None}


def resolve_uuids(domains: Iterable[str], max_matches: int = 2) -> dict[str, str]:
    """domain → Gate UUID。

    一份 match detail 里有十个玩家的 uuid，所以一次详情请求往往能把整队都解析
    出来，而不是一人一次。
    """

    import api_client  # 与 job_runner 一样按顶层模块导入

    wanted = [d for d in dict.fromkeys(domains) if d]
    found: dict[str, str] = {}
    missing = set(wanted)

    for domain in wanted:
        if not missing:
            break
        try:
            matches = api_client._get_public_matches(domain)
        except Exception as exc:  # noqa: BLE001
            log.warning("uuid bootstrap for %s failed: %s", domain, exc)
            continue
        for match in matches[:max_matches]:
            code = api_client._match_code(match)
            if not code:
                continue
            try:
                detail = api_client.get_match_detail(code)
            except Exception:  # noqa: BLE001
                continue
            for player in api_client._extract_players(detail):
                player_domain = player.get("domain")
                player_uuid = player.get("uuid")
                if (
                    player_domain in missing
                    and isinstance(player_uuid, str)
                    and len(player_uuid) == 36
                ):
                    found[player_domain] = player_uuid
                    missing.discard(player_domain)
            if not missing:
                break

    return found


def fetch_seasons(
    domains: Iterable[str], uuid_by_domain: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], bool]:
    """Returns ``(season_by_domain, failures, signature_failed)``."""

    seasons: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []
    signature_failed = False

    for domain in domains:
        uuid = uuid_by_domain.get(domain)
        if not uuid:
            failures.append({"domain": domain, "reason": "找不到 5E UUID"})
            continue
        try:
            seasons[domain] = parse_season(fetch_home(uuid))
        except GateSignatureError as exc:
            signature_failed = True
            failures.append({"domain": domain, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001 - 单个玩家失败不影响其他人
            failures.append({"domain": domain, "reason": str(exc)[:160]})

    return seasons, failures, signature_failed
