"""Wire contracts for the CS Helper relay server.

These models are the single source of truth for the HTTP payloads. The
WebSocket event catalogue lives in ``app/events.py`` and is mirrored by
``contract/events.json`` (enforced by a test).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PROTOCOL_VERSION = 1

_MATCH_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAP_RE = re.compile(r"^de_[a-z0-9_]{1,40}$")
_DEVICE = Literal["pc", "mobile", "web"]


class PlayerStats(BaseModel):
    """Client-reported summary stats. Treated as an untrusted first paint."""

    model_config = {"extra": "allow"}

    rating: float | None = None
    kd: float | None = None
    headshotRate: float | None = None
    winRate: float | None = None
    matchesPlayed: int | None = None
    rankLevel: str | int | None = None


class ReportPlayer(BaseModel):
    model_config = {"extra": "allow"}

    steamId: str = ""
    platformUserId: str = ""
    nickname: str = Field(default="", max_length=64)
    avatarUrl: str | None = None
    isSelf: bool = False
    partyTag: str | None = None
    stats: PlayerStats | None = None

    @field_validator("steamId")
    @classmethod
    def _check_steam_id(cls, value: str) -> str:
        if value and not re.fullmatch(r"765\d{14}", value):
            raise ValueError("steamId must be a SteamID64")
        return value


class TeamPayload(BaseModel):
    ct: list[ReportPlayer] = Field(default_factory=list)
    t: list[ReportPlayer] = Field(default_factory=list)

    @field_validator("ct", "t")
    @classmethod
    def _max_five(cls, value: list[ReportPlayer]) -> list[ReportPlayer]:
        if len(value) > 5:
            raise ValueError("a team cannot hold more than 5 players")
        return value

    def players(self) -> list[ReportPlayer]:
        return [*self.ct, *self.t]


class MatchReport(BaseModel):
    """PC -> server match context. Idempotent on ``platform:matchId``."""

    protocolVersion: int = PROTOCOL_VERSION
    clientVersion: str = Field(default="", max_length=32)
    platform: Literal["5e", "perfect"]
    matchId: str
    mapName: str
    phase: str = Field(default="ready", max_length=24)
    countdownSeconds: int | None = Field(default=None, ge=0, le=3600)
    # Which roster block is ours. When known, only the *other* five players'
    # demos are downloaded — the download, not the parse, is the bottleneck.
    # ``None`` means "analyze everyone", which is the old behaviour.
    mySide: Literal["ct", "t"] | None = None
    reporter: dict | None = None
    teams: TeamPayload = Field(default_factory=TeamPayload)
    demoHints: list[dict] = Field(default_factory=list)

    @field_validator("matchId")
    @classmethod
    def _check_match_id(cls, value: str) -> str:
        if not _MATCH_ID_RE.match(value):
            raise ValueError("matchId contains unsupported characters")
        return value

    @field_validator("mapName")
    @classmethod
    def _check_map(cls, value: str) -> str:
        if not _MAP_RE.match(value):
            raise ValueError("mapName must look like de_mirage")
        return value

    def all_players(self) -> list[ReportPlayer]:
        return self.teams.players()


class RoomCreate(BaseModel):
    creatorNickname: str = Field(default="PC 房主", max_length=32)
    deviceType: _DEVICE = "pc"


class RoomJoin(BaseModel):
    # Empty is valid in single-room mode, where the code is implied.
    roomCode: str = Field(default="", max_length=12)
    nickname: str = Field(default="队友", max_length=32)
    deviceType: _DEVICE = "mobile"


class RoomView(BaseModel):
    roomCode: str
    roomId: str
    expiresAt: int
    members: list[dict]
    sessionId: str | None = None


class PostMatchReport(BaseModel):
    """赛后战报，由桌面端从平台接口取回后上报（服务端不重复抓取）。

    结构对齐桌面端的 P5ePostMatchReport；未知字段原样保留并转发，
    这样客户端加字段不需要服务端同步发版。
    """

    model_config = {"extra": "allow"}

    matchCode: str = Field(default="", max_length=128)
    mapName: str = Field(default="", max_length=64)
    roundTotal: int = Field(default=0, ge=0, le=200)
    scoreA: int = Field(default=0, ge=0, le=100)
    scoreB: int = Field(default=0, ge=0, le=100)
    winnerSide: str | None = Field(default=None, max_length=8)
    halfScores: dict | None = None
    demoUrl: str | None = Field(default=None, max_length=2048)
    mvpUid: str | None = Field(default=None, max_length=64)
    players: list[dict] = Field(default_factory=list)
    comparison: dict | None = None
    isFinished: bool = True

    @field_validator("players")
    @classmethod
    def _max_players(cls, value: list[dict]) -> list[dict]:
        if len(value) > 20:
            raise ValueError("players cannot exceed 20 entries")
        return value

    @field_validator("demoUrl")
    @classmethod
    def _check_demo_url(cls, value: str | None) -> str | None:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("demoUrl must be an absolute URL")
        return value


class DevParseRequest(BaseModel):
    """Dev-only: parse a local .dem by file name (no path traversal)."""

    name: str = Field(min_length=5, max_length=200)


class AnalysisSideRequest(BaseModel):
    """Which roster is ours; ``null`` means "let the ID library decide".

    ``all=True`` is the explicit "analyze both sides" override: without it a
    library hit would immediately re-take the side and the "both" choice would
    look broken to the user.
    """

    mySide: Literal["ct", "t"] | None = None
    all: bool = False


class IdentityLearnRequest(BaseModel):
    """Remember one roster block as ours, so the next match auto-detects."""

    side: Literal["ct", "t"]
