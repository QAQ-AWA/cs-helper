import { describe, expect, it } from 'vitest';

import type { MatchPlayer, MatchRecord } from '@core/match/models';
import { buildMatchReport, shouldReport } from './report-builder';

function player(overrides: Partial<MatchPlayer> = {}): MatchPlayer {
  return {
    steamId: '76561198000000002',
    nickname: 'Alpha',
    teamSide: 0,
    isSingle: false,
    radar: {},
    recentResults: [],
    recentRatings: [],
    tags: [],
    ...overrides,
  } as MatchPlayer;
}

function record(players: MatchPlayer[][], detail: Record<string, unknown> = {}): MatchRecord {
  return {
    id: 'local-1',
    platformId: '5e',
    data: {},
    summary: { playerCount: 10, mapName: 'de_mirage' },
    detail: {
      platformGameId: '2603212003001',
      mapName: 'de_mirage',
      teams: players.map((team, index) => ({
        side: index === 0 ? 'A' : 'B',
        id: index,
        players: team,
        singleCount: 0,
        partyGroups: [],
      })),
      unassigned: [],
      hasExtraInfo: false,
      parseWarnings: [],
      ...detail,
    },
  } as unknown as MatchRecord;
}

describe('buildMatchReport', () => {
  it('maps both teams into ct/t', () => {
    const built = buildMatchReport(
      record([
        [player({ nickname: 'Alpha' })],
        [player({ steamId: '76561198000000003', nickname: 'Bravo' })],
      ]),
    );
    expect(built).not.toBeNull();
    expect(built!.body.platform).toBe('5e');
    expect(built!.body.mapName).toBe('de_mirage');
    expect(built!.body.teams.ct.map((p) => p.nickname)).toEqual(['Alpha']);
    expect(built!.body.teams.t.map((p) => p.nickname)).toEqual(['Bravo']);
    expect(built!.idempotencyKey).toBe('5e:2603212003001');
  });

  it('uploads the whole stat sheet, not six fields', () => {
    const built = buildMatchReport(
      record([
        [
          player({
            seasonRating: 1.18,
            rating: 1.12,
            kd: 1.25,
            adpr: 86.4,
            rws: 10.2,
            kast: 0.72,
            hsRate: 0.48,
            seasonWinRate: 0.54,
            seasonTotalNum: 320,
            firstKillSuccessRate: 0.31,
            clutchWinRate: 0.42,
            entryKillRatio: 0.28,
            tradeFragRate: 0.19,
            recentResults: ['win', 'win', 'lose', 'win', 'lose'],
            recentRatings: [1.2, 1.1, 0.9, 1.3, 1.0, 0.8],
            mapWinRate: 0.6,
            mapTotalNum: 12,
            mapSampleLow: false,
            score: 2410,
            eloChange: 18,
            rankNum: 1523,
            kills: 2100,
            deaths: 1900,
            assists: 400,
            mvpCount: 52,
          }),
        ],
        [],
      ]),
    );
    const stats = built!.body.teams.ct[0].stats!;

    expect(stats.rating).toBe(1.18);
    expect(stats.seasonAdr).toBe(86.4);
    expect(stats.seasonRws).toBe(10.2);
    // Fractions are normalised once, at the upload boundary.
    expect(stats.headshotRate).toBe(48);
    expect(stats.winRate).toBe(54);
    expect(stats.seasonKast).toBe(72);
    expect(stats.firstKillRate).toBe(31);
    expect(stats.clutchWinRate).toBe(42);
    expect(stats.mapWinRate).toBe(60);
    expect(stats.matchesPlayed).toBe(320);
    expect(stats.recentResults).toBe('WWLWL');
    expect(stats.recentRatings).toEqual([1.2, 1.1, 0.9, 1.3, 1.0]);
    expect(stats.elo).toBe(2410);
    expect(stats.eloChange).toBe(18);
    expect(stats.rankNum).toBe(1523);
    expect(stats.kills).toBe(2100);
    expect(stats.mvpCount).toBe(52);
  });

  it('omits fields the parser did not provide', () => {
    const built = buildMatchReport(record([[player({ kd: 1.1 })], []]));
    const stats = built!.body.teams.ct[0].stats!;
    expect(stats.kd).toBe(1.1);
    expect('seasonAdr' in stats).toBe(false);
    expect('clutchWinRate' in stats).toBe(false);
  });

  it('carries the 5E domain and party id', () => {
    const built = buildMatchReport(
      record([[player({ platformBoardId: '1204gmjzkzoj', troopTeamId: 8123 })], []]),
    );
    const payload = built!.body.teams.ct[0];
    expect(payload.platformUserId).toBe('1204gmjzkzoj');
    expect(payload.partyTag).toBe('8123');
  });

  it('treats troopTeamId 0 as "no party"', () => {
    const built = buildMatchReport(record([[player({ troopTeamId: 0 })], []]));
    expect(built!.body.teams.ct[0].partyTag).toBeUndefined();
  });

  it('derives the countdown from readyLeftTimeMs', () => {
    const built = buildMatchReport(record([[player()], []], { readyLeftTimeMs: 58_400 }));
    expect(built!.body.countdownSeconds).toBe(58);
  });

  it('falls back to the deadline when the remaining time is absent', () => {
    const now = 1_000_000;
    const built = buildMatchReport(record([[player()], []], { readyDeadlineAt: now + 45_000 }), now);
    expect(built!.body.countdownSeconds).toBe(45);
  });

  it('refuses an incomplete Perfect snapshot', () => {
    const incomplete = record([[player()], []], {
      source: 'ladder-events',
      perfectSessionPhase: 'accepting',
    });
    incomplete.platformId = 'perfect';
    expect(shouldReport(incomplete)).toBe(false);
    expect(buildMatchReport(incomplete)).toBeNull();
  });

  it('accepts an assigned Perfect match with its phase', () => {
    const assigned = record([[player()], []], {
      source: 'ladder-events',
      perfectSessionPhase: 'assigned',
    });
    assigned.platformId = 'perfect';
    const built = buildMatchReport(assigned);
    expect(built!.body.platform).toBe('perfect');
    expect(built!.body.phase).toBe('assigned');
    expect(built!.idempotencyKey).toBe('perfect:2603212003001');
  });

  it('returns null when no player carries an identity', () => {
    const empty = record([[player({ steamId: '', nickname: '' })], []]);
    expect(buildMatchReport(empty)).toBeNull();
  });
});

describe('marking ourselves in the roster', () => {
  it('marks the only player carrying a 5E domain as self', () => {
    // 5E 只在当前登录账号那条 user/info 里给 domain，其余人是空。
    const built = buildMatchReport(
      record([
        [player({ steamId: '76561198000000001', nickname: 'A' })],
        [
          player({
            steamId: '76561198000000002',
            nickname: 'Me',
            platformBoardId: '0606bexalmmc',
          }),
          player({ steamId: '76561198000000003', nickname: 'C' }),
        ],
      ]),
    );

    const t = built!.body.teams.t;
    expect(t.map((p) => p.isSelf)).toEqual([true, false]);
    expect(built!.body.teams.ct[0].isSelf).toBe(false);
  });

  it('marks nobody when more than one player carries a domain', () => {
    // 分不清就别猜：猜错边会把整局分析翻到对手身上。
    const built = buildMatchReport(
      record([
        [
          player({ steamId: '76561198000000001', platformBoardId: 'aaaa1111' }),
          player({ steamId: '76561198000000002', platformBoardId: 'bbbb2222' }),
        ],
        [],
      ]),
    );

    expect(built!.body.teams.ct.every((p) => !p.isSelf)).toBe(true);
  });

  it('never marks anyone on the perfect platform', () => {
    // 完美世界给所有人都带 zq_id，区分不出自己。
    const built = buildMatchReport(
      record([[player({ steamId: '76561198000000001', platformBoardId: 'zq-1' })], []], {
        source: 'ladder-events',
        perfectSessionPhase: 'assigned',
      }),
    );

    expect(built!.platform).toBe('perfect');
    expect(built!.body.teams.ct[0].isSelf).toBe(false);
  });
});
