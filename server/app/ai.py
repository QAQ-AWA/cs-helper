"""Server-side AI orchestration.

One call per match, broadcast to every device in the room. The provider must be
OpenAI-compatible (DeepSeek / OpenAI / Gemini's compatible endpoint / Ollama),
configured through `CS_HELPER_AI_*`. Without a key the job is skipped, so the
relay stays useful with tournament data only.

The prompt is built from :mod:`app.evidence` rather than a raw stat table: the
model gets pre-computed directions and reliability labels, and is forbidden
from quoting numbers that are not in the pack.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

import requests

from . import settings
from .evidence import build_evidence

SYSTEM_PROMPT = (
    "你是 CS2 赛前战术分析师，服务对象是中国玩家，表达像赛前队友交流。\n"
    "输入是一份本地算好的证据包：direction 已按全场中位数计算，reliability 由样本量决定。\n"
    "硬性规则：\n"
    "1. 只能使用证据包里出现过的数值，严禁编造 ADR、RWS、首杀率、残局成功率等未提供的指标；\n"
    "2. 不得推翻 direction，也不得自行重算强弱；\n"
    "3. reliability 为 low/unknown 的玩家只能写进「数据缺口」，不能当作强弱结论；\n"
    "4. 结论要落到可执行动作，不要空话；\n"
    "5. 提到选手一律用昵称，不要输出任何内部编号；\n"
    "5. 只输出 Markdown，不要代码块，不要客套话。"
)

_OUTPUT_RULES = """# 输出格式（严格按此四段，总长 450 字以内）

## 结论
一句话说清哪边更被看好，以及最关键的 1 个理由。

## 双方强弱
2-3 条，每条必须引用证据包里的具体数值或 direction。

## 对方威胁点
对方最需要提防的 2 个人，各一句话，写清是哪个指标支撑的判断。

## 开局建议
3 条可执行动作（谁走哪、先给什么道具），结合地图特性。

## 数据缺口
仅当 dataQuality.missing 或 dataQuality.lowSamplePlayers 非空时输出，说明哪些结论不可靠；否则省略本节。"""


STRUCTURED_SYSTEM_PROMPT = (
    "你是 CS2 赛前分析师，服务对象是中国玩家，表达像赛前队友交流。\n"
    "输入是一份本地算好的证据包：direction 已按全场中位数计算，reliability 由样本量决定。\n"
    "硬性规则：\n"
    "1. 只输出 JSON，不要 Markdown，不要代码块；\n"
    "2. 只能使用证据包里出现过的数值，严禁编造 ADR、RWS、首杀率、残局成功率等未提供的指标；\n"
    "3. 不得推翻 direction，也不得自行重算强弱；\n"
    "4. reliability 为 low/unknown 的玩家只能写进 uncertainties，不能当作强弱结论；\n"
    "5. 提到选手一律用昵称，不要输出任何内部编号；\n"
    "6. 结论要落到可执行动作，不要空话。"
)

# 与客户端历史文档的存储契约一致（core/ai/types.ts 的 AiAnalysisResultV3）。
# evidenceIds 不再使用：服务端没有证据目录，客户端按空数组渲染。
_STRUCTURED_SCHEMA = """{
  "schemaVersion": 3,
  "predictedWinner": "A|B|Even|Unknown",
  "modelWinProbability": { "A": 58, "B": 42 },
  "confidence": 72,
  "headline": "一句话结论（不超过 32 个汉字）",
  "decisiveFactors": [{
    "dimension": "strength|aim|opening|utility|clutch|map|form|party",
    "advantage": "A|B|Even",
    "impact": 1,
    "title": "不超过 12 个汉字",
    "summary": "不超过 50 个汉字，必须引用证据包里的数值"
  }],
  "playerSignals": [{
    "steamId": "证据包 allowedPlayers 里的 steamId",
    "side": "A|B",
    "kind": "carry|anchor|specialist|weakLink|volatile",
    "impact": 2,
    "title": "不超过 12 个汉字",
    "summary": "不超过 50 个汉字"
  }],
  "teamPlans": {
    "A": { "winConditions": [{ "text": "不超过 50 个汉字" }], "risks": [{ "text": "..." }] },
    "B": { "winConditions": [{ "text": "..." }], "risks": [{ "text": "..." }] }
  },
  "uncertainties": ["低样本、缺失指标等，单条不超过 40 个汉字"]
}"""

_STRUCTURED_RULES = """# 严格规则

- 只输出一个 JSON 对象，不要任何解释、Markdown 或代码块
- A 队 / B 队 的定义见下方「A/B 定义」，全文只准用 A/B 指代队伍，不要写「我方/对方」
- decisiveFactors 最多 4 条，按影响从大到小；每条必须引用证据包里的具体数值
- playerSignals 最多 4 条、每队最多 2 条，steamId 必须来自 allowedPlayers；没有值得说的玩家时返回空数组，不要硬凑
- kind 的语义：carry 强点、anchor 支点、specialist 专长、weakLink 短板、volatile 波动
- impact 只能是 1（一般）、2（重要）、3（决定性）
- modelWinProbability 的 A + B 必须等于 100
- confidence 是数据把握度（0-100），不是胜率；样本不足时必须降低
- 低样本、缺指标只能写进 uncertainties，不能当成强弱证据
- 文案用简体中文；允许 Rating、ADR、RWS、ELO、K/D、AWP 等术语
- 长度上限：headline 32 汉字、title 12 汉字、summary/取胜条件/隐患 50 汉字、uncertainties 单条 40 汉字"""


def _structured_evidence(evidence: dict[str, Any], my_side: str | None) -> dict[str, Any]:
    """Rewrite sides to A/B and publish the allowed player list."""

    def label(side: str) -> str:
        if my_side in {"ct", "t"}:
            return "A" if side == my_side else "B"
        return "A" if side == "ct" else "B"

    pack = json.loads(json.dumps(evidence, ensure_ascii=False))
    allowed = []
    for player in pack.get("players") or []:
        raw_side = str(player.get("side") or "")
        player["side"] = label(raw_side)
        player["role"] = "我方" if player["side"] == "A" else "对方"
        allowed.append(
            {
                "steamId": player.get("steamId"),
                "name": player.get("name"),
                "side": player["side"],
                "role": player["role"],
            }
        )
    for team in pack.get("teams") or []:
        raw_side = str(team.get("side") or "")
        team["side"] = label(raw_side)
        team["role"] = "我方" if team["side"] == "A" else "对方"
    pack["allowedPlayers"] = allowed
    match = pack.get("match") or {}
    match["mySide"] = "A"
    match["opponentSide"] = "B"
    pack["match"] = match
    return pack


def build_structured_prompt(evidence: dict[str, Any], my_side: str | None) -> str:
    """Prompt for the v3 JSON contract the desktop panel renders."""

    pack = _structured_evidence(evidence, my_side)
    if my_side in {"ct", "t"}:
        side_line = f"A 队 = 我方（{my_side.upper()} 开局），B 队 = 对方"
    else:
        side_line = "尚未确定哪边是我方：A 队 = CT 方，B 队 = T 方"
    payload = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    return (
        "# 任务\n给出一份赛前分析：谁更强、为什么、哪些玩家值得注意、双方各自怎么赢。\n\n"
        f"# A/B 定义\n{side_line}\n\n"
        f"{_STRUCTURED_RULES}\n\n"
        f"# 输出结构（严格 JSON）\n{_STRUCTURED_SCHEMA}\n\n"
        f"# 证据包（JSON）\n{payload}"
    )


def structured_allowed_players(
    evidence: dict[str, Any], my_side: str | None
) -> dict[str, tuple[str, str]]:
    """SteamID -> (nickname, A/B) for validating ``playerSignals``."""

    pack = _structured_evidence(evidence, my_side)
    return {
        str(item["steamId"]): (str(item.get("name") or ""), str(item.get("side") or "A"))
        for item in pack.get("allowedPlayers") or []
        if item.get("steamId")
    }


def build_repair_prompt(raw: str) -> str:
    """Second attempt when the model wrapped the JSON in prose."""

    return (
        "上一次输出不是合法 JSON（可能夹了说明文字或代码块）。\n"
        "请只输出一个 JSON 对象，字段与下面完全一致，不要任何解释：\n"
        f"{_STRUCTURED_SCHEMA}\n\n"
        f"上一次的输出（供你修正，不要照抄格式）：\n{raw[:4000]}"
    )


TACTICS_SYSTEM_PROMPT = (
    "你是 CS2 开局预判分析师，服务对象是中国玩家。\n"
    "输入是对手最近一场 demo 的统计：CT 开局站位分布（8 秒时在哪个包点）、"
    "T 边下包点分布与平均下包时间、开局死亡与道具习惯。\n"
    "硬性规则：\n"
    "1. 只能使用证据包里的数字，不得编造回合数或时间；\n"
    "2. 每个玩家的 rounds 少于 4 时必须说明样本不足，结论要降调；\n"
    "3. siteKnown 里没有 A 或 B 时，禁止声称对面打或不打那个点，只能说无法判断；\n"
    "4. 预判要具体到回合数与人数，例如「11 个下包回合里 7 次打 A」；\n"
    "5. 只输出 Markdown，不要代码块。"
)

_TACTICS_RULES = """# 输出格式（严格按此四段，总长 400 字以内）

## 开局选点预判
分两层说，不要混为一谈：
1. teamPlants 是地面真相（真的在哪下的包），队伍级次数只看它，不要把人名下的 planted 相加——
   同一个下包会出现在每个人的回合里；
2. teamApproach 是前 20 秒的走位方向（每回合多数票，A/B/even），落包数据不足时靠它，
   并说明是「往哪边压」而不是「在哪落包」。
两者结论不一致时（例如都往 A 压却常在 B 落包）要点出来，这是对手在打默认或骗点。
回合数少于 5 时只给倾向，不要写「必打某点」。

## 各人习惯
逐人一句话：CT 常驻哪个点、T 边下包倾向与走位方向（approach）、开局道具偏好。

## 我方应对
3 条可执行动作（谁守哪、怎么防默认、什么时候前压或反清）。

## 数据缺口
样本不足、包点未知、某人没有轨迹时说明；没有缺口就省略本节。"""


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int
    max_tokens: int
    thinking: bool = False

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


def config_from_settings() -> AiConfig | None:
    key = (settings.AI_KEY or "").strip()
    if not key:
        return None
    return AiConfig(
        base_url=settings.AI_BASE_URL,
        model=settings.AI_MODEL,
        api_key=key,
        timeout=settings.AI_TIMEOUT,
        max_tokens=settings.AI_MAX_TOKENS,
        thinking=settings.AI_THINKING,
    )


def build_analysis_prompt(
    map_name: str,
    players: Iterable[dict[str, Any]],
    my_side: str | None = None,
) -> str:
    """Evidence pack + fixed output skeleton. Kept as text so the phone can render it."""

    pack = build_evidence(map_name, list(players), my_side)
    payload = json.dumps(pack, ensure_ascii=False, separators=(",", ":"))
    return (
        f"# 任务\n赛前判断 {map_name} 这张图该怎么打。\n\n"
        f"# 证据包（JSON）\n{payload}\n\n{_OUTPUT_RULES}"
    )


def build_prompt(
    map_name: str,
    players: Iterable[dict[str, Any]],
    my_side: str | None = None,
) -> str:
    """Backwards-compatible alias."""

    return build_analysis_prompt(map_name, players, my_side)


def build_tactics_prompt(profile: dict[str, Any]) -> str:
    """Second pass: opening habits read off the parsed trajectories."""

    payload = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
    return (
        f"# 任务\n根据对手最近一场 demo 的前 20 秒轨迹，预判这张图的对方开局选点与可能动作。\n\n"
        f"# 证据包（JSON）\n{payload}\n\n{_TACTICS_RULES}"
    )


def iter_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    """Yield ``(kind, text)`` from an OpenAI-compatible SSE stream.

    ``kind`` is ``"reason"`` for a reasoning model's scratchpad and
    ``"content"`` for the answer that users actually see. Callers must surface
    the scratchpad as progress: on a reasoning model it arrives first and can
    run for ten seconds before the first visible token.
    """

    for raw in lines:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = parsed.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        reasoning = delta.get("reasoning_content")
        if reasoning:
            yield "reason", reasoning
        content = delta.get("content")
        if content:
            yield "content", content


def iter_sse_deltas(lines: Iterable[str]) -> Iterator[str]:
    """Yield only the visible answer deltas."""

    for kind, text in iter_sse_events(lines):
        if kind == "content":
            yield text


class OpenAiClient:
    def __init__(self, config: AiConfig) -> None:
        self.config = config

    def stream(
        self,
        prompt: str,
        on_reason: Callable[[str], None] | None = None,
        system: str | None = None,
    ) -> Iterator[str]:
        body: dict[str, Any] = {
            "model": self.config.model,
            "stream": True,
            "max_tokens": self.config.max_tokens,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": system or SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        if not self.config.thinking:
            # Supported by DeepSeek's reasoning endpoints; harmless elsewhere
            # only because unknown fields would 400, so keep it opt-in.
            body["thinking"] = {"type": "disabled"}

        response = requests.post(
            self.config.endpoint,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.config.timeout,
            stream=True,
        )
        if response.status_code >= 400:
            detail = response.text[:200]
            raise RuntimeError(f"AI 服务返回 {response.status_code}: {detail}")

        for kind, text in iter_sse_events(response.iter_lines(decode_unicode=True)):
            if kind == "reason":
                if on_reason is not None:
                    on_reason(text)
            else:
                yield text
