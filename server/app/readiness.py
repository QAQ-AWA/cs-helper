"""何时可以开跑：5E 的数据是分几段到的，不能一拿到 matchId 就全套开跑。

真机观察到的顺序：

1. 匹配信息（matchId、房间）
2. 双方十个人的 ID（名单，可能分两次补齐）
3. 再过一会儿才是地图
4. 之后还有持续回报（准备状态、阵营、赛季数据）

之前每个上报都无条件触发 profile/demo/ai：地图没到时 demo 直接 skipped，
名单只到一半时 AI 已经写完了一份「敌我未定、地图未知」的分析，后面真数据到了
又因为 ai_state 已经是 ready 不再重算。结果就是用户看到的结论建立在空数据上。

这里把「跑不跑」和「跑完的输入变没变」分开判断。
"""

from __future__ import annotations

from typing import Any, Iterable

# 5E 在未选图/加载阶段会把这些当占位符报上来。
UNKNOWN_MAPS = {"", "de_unknown", "unknown", "de_workshop", "workshop"}
# 5E 是 5v5；少于这个数说明名单还在补齐。
FULL_ROSTER = 10


def players_of(report: dict[str, Any]) -> list[dict[str, Any]]:
    teams = report.get("teams") or {}
    return [player for side in ("ct", "t") for player in teams.get(side) or [] if isinstance(player, dict)]


def map_ready(map_name: str | None) -> bool:
    return (map_name or "").strip().lower() not in UNKNOWN_MAPS


def roster_ready(report: dict[str, Any]) -> bool:
    return len(players_of(report)) >= FULL_ROSTER


def side_ready(report: dict[str, Any], my_side: str | None) -> bool:
    """敌我明确，或者用户明确说了「十个人都看」。"""

    return my_side in {"ct", "t"} or report.get("analyzeAll") is True


def analysis_key(map_name: str, report: dict[str, Any], my_side: str | None) -> str:
    """什么变了才值得重算：地图、名单、敌我。头像/准备状态不算。"""

    steam_ids = sorted(
        str(player.get("steamId") or player.get("nickname") or "") for player in players_of(report)
    )
    return "|".join([map_name or "", ",".join(steam_ids), my_side or ""])


def missing_for_analysis(map_name: str, report: dict[str, Any], my_side: str | None) -> list[str]:
    """硬性阻塞项：地图和敌我。

    名单没满不阻塞——5E 的名单一般在报 matchId 后一两秒就齐，而地图要等选图；
    真到了 4 打 5 的情况，少一个人的分析也比没有强。名单进度放在 note 里展示。
    """

    # 只拦地图：敌我未定时照样能算，只是按 CT/T 说，不再冒充「我方/对方」。
    # 地图未知则一定不算——那份结论连地图适配都没有，纯属误导。
    return [] if map_ready(map_name) else ["等地图确认"]


def roster_note(report: dict[str, Any]) -> str | None:
    """名单进度，只用于展示，不阻塞。"""

    count = len(players_of(report))
    return None if count >= FULL_ROSTER else f"名单 {count}/{FULL_ROSTER}"


def missing_for_demo(map_name: str) -> list[str]:
    return [] if map_ready(map_name) else ["等地图确认"]
