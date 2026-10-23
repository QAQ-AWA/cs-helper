import type { MatchPlayer, MatchRecord } from '@core/match/models';

/** Keep in step with `package.json`; the server only logs it, never gates on it. */
export const CLIENT_VERSION = '4.0.0';
export const PROTOCOL_VERSION = 1;

/**
 * Everything useful the client knows about one player, in one flat object.
 *
 * The relay builds its AI evidence from this, so the rule is "upload whatever
 * exists, omit what doesn't" rather than picking six fields and dropping the
 * rest. Percentages are normalised here — the 5E parsers hand back 0-1
 * fractions for hsRate/winRate/kast while the UI shows 48%, and a single
 * boundary conversion keeps both sides honest.
 */
export interface ReportPlayerStats {
  // Core (always present, with sane fallbacks)
  rating: number;
  kd: number;
  headshotRate: number;
  winRate: number;
  matchesPlayed: number;
  rankLevel?: string | number;
  // Season combat
  seasonRating?: number;
  seasonAdr?: number;
  seasonRws?: number;
  seasonKast?: number;
  // Opening / clutch / trading
  firstKillRate?: number;
  clutchWinRate?: number;
  entryKillRatio?: number;
  tradeFragRate?: number;
  // Form
  recentWinRate?: number;
  /** Newest first, e.g. "WWLWL" */
  recentResults?: string;
  recentRatings?: number[];
  continuedWins?: number;
  // Current map
  mapWinRate?: number;
  mapMatches?: number;
  mapSampleLow?: boolean;
  // Identity / rank
  elo?: number;
  eloChange?: number;
  rankNum?: number;
  rankDesc?: string;
  // Raw counts
  kills?: number;
  deaths?: number;
  assists?: number;
  mvpCount?: number;
}

export interface ReportPlayerPayload {
  steamId: string;
  platformUserId: string;
  nickname: string;
  avatarUrl?: string;
  isSelf: boolean;
  partyTag?: string;
  stats?: ReportPlayerStats;
}

export interface MatchReportBody {
  protocolVersion: number;
  clientVersion: string;
  platform: '5e' | 'perfect';
  matchId: string;
  mapName: string;
  phase: string;
  countdownSeconds?: number;
  /** Which block is ours; the client cannot always tell, the phone can. */
  mySide?: 'ct' | 't';
  teams: { ct: ReportPlayerPayload[]; t: ReportPlayerPayload[] };
}

export interface BuiltMatchReport {
  body: MatchReportBody;
  /** Stable dedupe key shared with the server: `platform:matchId`. */
  idempotencyKey: string;
  platform: '5e' | 'perfect';
  matchId: string;
}

function num(value: number | undefined | null): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** 0-1 → 0-100, already-percent stays put, everything is rounded to one decimal. */
function pct(value: number | undefined | null): number | undefined {
  const raw = num(value);
  if (raw === undefined) return undefined;
  const percent = raw <= 1 ? raw * 100 : raw;
  return Math.round(percent * 10) / 10;
}

function compact<T extends Record<string, unknown>>(input: T): T {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === null) continue;
    if (typeof value === 'number' && !Number.isFinite(value)) continue;
    out[key] = value;
  }
  return out as T;
}

function buildStats(player: MatchPlayer): ReportPlayerStats {
  return compact({
    rating: num(player.seasonRating) ?? num(player.rating) ?? 1,
    kd: num(player.kd) ?? 1,
    headshotRate: pct(player.hsRate) ?? 0,
    winRate: pct(player.seasonWinRate ?? player.recentWinRate) ?? 50,
    matchesPlayed: num(player.seasonTotalNum) ?? 0,
    rankLevel: player.rankLevel ?? player.rankDesc,
    seasonRating: num(player.seasonRating),
    seasonAdr: num(player.adpr),
    seasonRws: num(player.rws ?? player.weRaw),
    seasonKast: pct(player.kast),
    firstKillRate: pct(player.firstKillSuccessRate),
    clutchWinRate: pct(player.clutchWinRate),
    entryKillRatio: num(player.entryKillRatio),
    tradeFragRate: pct(player.tradeFragRate),
    recentWinRate: pct(player.recentWinRate),
    recentResults: player.recentResults?.length ? player.recentResults.map((r) => (r === 'win' ? 'W' : r === 'lose' ? 'L' : 'D')).join('') : undefined,
    recentRatings: player.recentRatings?.length ? player.recentRatings.slice(0, 5) : undefined,
    continuedWins: num(player.continuedWins),
    mapWinRate: pct(player.mapWinRate),
    mapMatches: num(player.mapTotalNum),
    mapSampleLow: player.mapSampleLow || undefined,
    elo: num(player.score),
    eloChange: num(player.eloChange),
    rankNum: num(player.rankNum),
    rankDesc: player.rankDesc,
    kills: num(player.kills),
    deaths: num(player.deaths),
    assists: num(player.assists),
    mvpCount: num(player.mvpCount),
  });
}

function playerPayload(player: MatchPlayer): ReportPlayerPayload | null {
  const steamId = player.steamId || '';
  const nickname = player.nickname || '';
  if (!steamId && !nickname) return null;

  // `platformBoardId` carries the 5E domain (and zq_id on Perfect). The relay
  // needs it to skip nickname search when looking up demos.
  const platformUserId = player.platformBoardId || steamId;
  // A party id of 0 means "no party", not "party zero".
  const partyTag = num(player.troopTeamId) && player.troopTeamId! > 0
    ? String(player.troopTeamId)
    : undefined;

  return {
    steamId,
    platformUserId,
    nickname: nickname || 'Unknown',
    avatarUrl: player.avatar,
    isSelf: false,
    partyTag,
    stats: buildStats(player),
  };
}

/**
 * The desktop client only reports matches that carry a usable roster. Perfect
 * World emits intermediate `ladder-events` snapshots before the server assigns
 * teams; uploading those would create empty sessions on the relay.
 */
export function shouldReport(record: MatchRecord): boolean {
  const detail = record.detail;
  if (!detail || !Array.isArray(detail.teams) || detail.teams.every((team) => !team?.players?.length)) {
    return false;
  }
  if (detail.source === 'ladder-events' && detail.perfectSessionPhase !== 'assigned') {
    return false;
  }
  return true;
}

export function buildMatchReport(record: MatchRecord, now = Date.now()): BuiltMatchReport | null {
  if (!shouldReport(record)) return null;

  const platform: '5e' | 'perfect' =
    record.platformId === 'perfect' || record.detail.source === 'ladder-events' ? 'perfect' : '5e';
  const matchId = record.detail.platformGameId || record.id;
  if (!matchId) return null;

  const [ctTeam, tTeam] = record.detail.teams ?? [];
  const ct = (ctTeam?.players ?? [])
    .map((player) => playerPayload(player))
    .filter((player): player is ReportPlayerPayload => player !== null);
  const t = (tTeam?.players ?? [])
    .map((player) => playerPayload(player))
    .filter((player): player is ReportPlayerPayload => player !== null);

  if (ct.length === 0 && t.length === 0) return null;

  const countdownSeconds = resolveCountdownSeconds(record, now);
  const body: MatchReportBody = {
    protocolVersion: PROTOCOL_VERSION,
    clientVersion: CLIENT_VERSION,
    platform,
    matchId,
    mapName: record.detail.mapName || record.summary?.mapName || 'de_unknown',
    phase: platform === 'perfect' ? (record.detail.perfectSessionPhase ?? 'assigned') : 'ready',
    teams: { ct, t },
  };
  if (countdownSeconds !== undefined) body.countdownSeconds = countdownSeconds;

  return { body, platform, matchId, idempotencyKey: `${platform}:${matchId}` };
}

function resolveCountdownSeconds(record: MatchRecord, now: number): number | undefined {
  const { readyLeftTimeMs, readyDeadlineAt } = record.detail;
  if (typeof readyLeftTimeMs === 'number' && readyLeftTimeMs > 0) {
    return Math.round(readyLeftTimeMs / 1000);
  }
  if (typeof readyDeadlineAt === 'number') {
    return Math.max(0, Math.round((readyDeadlineAt - now) / 1000));
  }
  return undefined;
}
