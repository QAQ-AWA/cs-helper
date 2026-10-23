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
    roomCode: str = Field(min_length=4, max_length=12)
    nickname: str = Field(default="队友", max_length=32)
    deviceType: _DEVICE = "mobile"


class RoomView(BaseModel):
    roomCode: str
    roomId: str
    expiresAt: int
    members: list[dict]
    sessionId: str | None = None
