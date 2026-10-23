import type { MatchPlayer, MatchRecord } from '@core/match/models';

/** Keep in step with `package.json`; the server only logs it, never gates on it. */
export const CLIENT_VERSION = '4.0.0';
export const PROTOCOL_VERSION = 1;

export interface ReportPlayerPayload {
  steamId: string;
  platformUserId: string;
  nickname: string;
  avatarUrl?: string;
  isSelf: boolean;
  partyTag?: string;
  stats?: {
    rating: number;
    kd: number;
    headshotRate: number;
    winRate: number;
    matchesPlayed: number;
    rankLevel?: string | number;
  };
}

export interface MatchReportBody {
  protocolVersion: number;
  clientVersion: string;
  platform: '5e' | 'perfect';
  matchId: string;
  mapName: string;
  phase: string;
  countdownSeconds?: number;
  teams: { ct: ReportPlayerPayload[]; t: ReportPlayerPayload[] };
}

export interface BuiltMatchReport {
  body: MatchReportBody;
  /** Stable dedupe key shared with the server: `platform:matchId`. */
  idempotencyKey: string;
  platform: '5e' | 'perfect';
  matchId: string;
}

function playerPayload(player: MatchPlayer): ReportPlayerPayload | null {
  const steamId = player.steamId64 || player.steamId || '';
  const nickname = player.nickname || player.name || '';
  if (!steamId && !nickname) return null;

  const payload: ReportPlayerPayload = {
    steamId,
    platformUserId: player.platformUserId || player.uniqueId || steamId,
    nickname: nickname || 'Unknown',
    avatarUrl: player.avatarUrl,
    isSelf: Boolean(player.isSelf),
    partyTag: player.partyTag,
  };

  if (player.stats) {
    payload.stats = {
      rating: player.stats.rating ?? 1,
      kd: player.stats.kd ?? 1,
      headshotRate: player.stats.headshotRate ?? 0,
      winRate: player.stats.winRate ?? 50,
      matchesPlayed: player.stats.totalMatches ?? 0,
      rankLevel: player.stats.rankLevel ?? player.stats.rankName,
    };
  }
  return payload;
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
