"""Server-side AI orchestration.

One call per match, broadcast to every device in the room. The provider must be
OpenAI-compatible (DeepSeek / OpenAI / Gemini's compatible endpoint / Ollama),
configured through `CS_HELPER_AI_*`. Without a key the job is skipped, so the
relay stays useful with tournament data only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

import requests

from . import settings

SYSTEM_PROMPT = (
    "你是 CS2 战术分析师。根据双方选手的公开数据给出简洁、可执行的赛前判断。"
    "只输出 Markdown，不要客套话，不要编造数据里没有的信息。"
)


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    model: str
    api_key: str
    timeout: int
    max_tokens: int

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
    )


def _fmt(value: Any, digits: int = 2, suffix: str = "") -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "—"
    return f"{value:.{digits}f}{suffix}"


def build_prompt(map_name: str, players: Iterable[dict[str, Any]]) -> str:
    rows: list[str] = []
    for player in players:
        stats = player.get("stats") or {}
        rows.append(
            "| {name} | {team} | {rating} | {kd} | {hs} | {win} |".format(
                name=player.get("nickname") or "Unknown",
                team=(player.get("team") or "").upper() or "—",
                rating=_fmt(stats.get("rating")),
                kd=_fmt(stats.get("kd")),
                hs=_fmt(stats.get("headshotRate"), 1, "%"),
                win=_fmt(stats.get("winRate"), 1, "%"),
            )
        )

    table = "\n".join(rows) if rows else "（无选手数据）"
    return f"""地图：{map_name}

| 选手 | 阵营 | Rating | K/D | 爆头率 | 胜率 |
| --- | --- | --- | --- | --- | --- |
{table}

请输出：
1. 一句话结论（哪边更被看好，为什么）；
2. 双方胜率预估（百分比，两数相加约 100）；
3. 对方最需要提防的 2 个人，各一句话理由；
4. 针对这张图开局的 3 条具体建议（谁走哪里、先给什么道具）。
总长度控制在 400 字以内。"""


def iter_sse_deltas(lines: Iterable[str]) -> Iterator[str]:
    """Yield content deltas from an OpenAI-compatible SSE stream."""

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
        content = delta.get("content")
        if content:
            yield content


class OpenAiClient:
    def __init__(self, config: AiConfig) -> None:
        self.config = config

    def stream(self, prompt: str) -> Iterator[str]:
        response = requests.post(
            self.config.endpoint,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "stream": True,
                "max_tokens": self.config.max_tokens,
                "temperature": 0.4,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.config.timeout,
            stream=True,
        )
        if response.status_code >= 400:
            detail = response.text[:200]
            raise RuntimeError(f"AI 服务返回 {response.status_code}: {detail}")
        return iter_sse_deltas(response.iter_lines(decode_unicode=True))
