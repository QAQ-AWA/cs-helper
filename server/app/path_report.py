"""对手开局习惯解读：把解析出来的轨迹喂给模型，产出可直接照着打的结论。

和 `analysis_result` 的区别：那份是赛前实力对比（谁更强、为什么），
这份只看**走位**——每个对手从哪出发、多久到位、大概率出现在哪、怎么针对。
所以它必须挂在轨迹页上，而不是和实力分析混在一起。
"""

from __future__ import annotations

import json
from typing import Any

_FENCE_MARKERS = ("```json", "```")

SYSTEM_PROMPT = (
    "你是 CS2 教练，负责把对手最近一场 demo 的开局走位翻译成「怎么打」。"
    "只依据证据包里的数字，不编造回合、点位和时间；样本少要主动降调。"
)

RULES = """# 输出格式（只输出 JSON，不要任何解释文字、不要代码块）

{
  "summary": "一句话说清对面的开局习惯（30 字以内）",
  "tempo": "偏快 / 中性 / 偏慢，并带上平均下包秒数，例如「偏慢，平均 58 秒」",
  "sitePreference": "A 66% / B 34%（用 teamPlants；没有落包数据就写「走位倾向」并说明依据）",
  "players": [
    {
      "nickname": "必须与证据包里的名字完全一致",
      "side": "T 或 CT 或 两侧",
      "habit": "他实际怎么走：哪一侧、走哪条路、多快到位（带次数，例如「T 4 次压 B，20 秒内到 B 通道中段」）",
      "likely": "下一局开局 20 秒最可能出现的位置与动作（具体到点位，不要空话）",
      "counter": "一条针对他的具体动作：谁架哪、什么时候给什么道具"
    }
  ],
  "counters": ["整队层面 2-3 条可执行对策，每条不超过 25 字"]
}

硬性规则：
1. 名字只能来自证据包，不要新增、不要改写；
2. 每个玩家的 rounds 少于 4 时，habit 里要写明样本少，likely 用「倾向」而不是「一定」；
3. siteKnown 里没有的包点不许断言，只能说「无法判断」；
4. players 最多 5 人，优先给回合数多的；
5. 不确定的字段留空字符串，不要瞎编。"""


def build_prompt(profile: dict[str, Any], my_side: str | None = None) -> str:
    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    ours = {"ct": "CT", "t": "T"}.get((my_side or "").lower(), "")
    side_hint = (
        f"\n# 我方阵营\n我方是 {ours}，所以对面是 {'T' if ours == 'CT' else 'CT'}；"
        "写「针对」时要站在我方视角。\n"
        if ours
        else ""
    )
    return (
        "# 任务\n"
        "下面是这张地图上对手最近一场 demo 的开局轨迹统计。请把它翻译成可执行的走位判断：\n"
        "每个人习惯从哪出发、多久到位、大概率出现在哪个点位，以及我方该怎么针对。\n"
        f"{side_hint}\n"
        f"# 证据包（JSON）\n{payload}\n\n{RULES}"
    )


def _text(value: Any, limit: int = 240) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit]


def _load_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    for marker in _FENCE_MARKERS:
        text = text.replace(marker, "")
    text = text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def parse_report(
    raw: str,
    *,
    allowed_players: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any] | None:
    """把模型输出收成稳定结构；名字对不上的条目直接丢掉。

    ``allowed_players`` 是 ``{nickname: (steam_id, side)}``，和结构化分析共用，
    防止模型把人名写错后前端出现不存在的选手。
    """

    payload = _load_json(raw)
    if not payload:
        return None

    players: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.get("players") or []:
        if not isinstance(item, dict):
            continue
        nickname = _text(item.get("nickname"), 40)
        if not nickname or nickname in seen:
            continue
        if allowed_players and nickname not in allowed_players:
            continue
        steam_id, roster_side = (allowed_players or {}).get(nickname, ("", ""))
        seen.add(nickname)
        players.append(
            {
                "nickname": nickname,
                "steamId": steam_id,
                "side": roster_side or _text(item.get("side"), 4),
                "habit": _text(item.get("habit")),
                "likely": _text(item.get("likely")),
                "counter": _text(item.get("counter"), 120),
            }
        )
        if len(players) >= 5:
            break

    counters = [
        _text(item, 60)
        for item in (payload.get("counters") or [])
        if _text(item, 60)
    ][:3]

    summary = _text(payload.get("summary"), 80)
    if not summary and not players:
        return None

    return {
        "summary": summary,
        "tempo": _text(payload.get("tempo"), 40),
        "sitePreference": _text(payload.get("sitePreference"), 60),
        "players": players,
        "counters": counters,
    }
