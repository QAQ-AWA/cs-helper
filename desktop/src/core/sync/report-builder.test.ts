import { describe, expect, it } from 'vitest';

import type { MatchRecord } from '@core/match/models';
import { buildMatchReport, shouldReport } from './report-builder';

function record(overrides: Partial<MatchRecord> = {}, detail: Record<string, unknown> = {}): MatchRecord {
  return {
    id: 'local-1',
    platformId: '5e',
    data: {},
    summary: { playerCount: 10, mapName: 'de_mirage' } as MatchRecord['summary'],
    detail: {
      platformGameId: '2603212003001',
      mapName: 'de_mirage',
      teams: [
        {
          players: [
            {
              nickname: 'Alpha',
              steamId64: '76561198000000002',
              platformUserId: 'player_a',
              isSelf: true,
              stats: { rating: 1.18, kd: 1.25, headshotRate: 48, winRate: 54, totalMatches: 320 },
            },
          ],
        },
        {
          players: [
            {
              nickname: 'Bravo',
              steamId64: '76561198000000003',
              platformUserId: 'player_b',
              stats: { rating: 0.95, kd: 0.88, headshotRate: 41, winRate: 47, totalMatches: 210 },
            },
          ],
        },
      ],
      unassigned: [],
      hasExtraInfo: false,
      parseWarnings: [],
      ...detail,
    } as MatchRecord['detail'],
    ...overrides,
  } as MatchRecord;
}

describe('buildMatchReport', () => {
  it('maps both teams into ct/t and keeps stats', () => {
    const built = buildMatchReport(record());
    expect(built).not.toBeNull();
    expect(built!.body.platform).toBe('5e');
    expect(built!.body.mapName).toBe('de_mirage');
    expect(built!.body.teams.ct.map((p) => p.nickname)).toEqual(['Alpha']);
    expect(built!.body.teams.t.map((p) => p.nickname)).toEqual(['Bravo']);
    expect(built!.body.teams.ct[0].stats?.rating).toBe(1.18);
    expect(built!.body.teams.ct[0].isSelf).toBe(true);
    expect(built!.idempotencyKey).toBe('5e:2603212003001');
  });

  it('derives the countdown from readyLeftTimeMs', () => {
    const built = buildMatchReport(record({}, { readyLeftTimeMs: 58_400 }));
    expect(built!.body.countdownSeconds).toBe(58);
  });

  it('falls back to the deadline when the remaining time is absent', () => {
    const now = 1_000_000;
    const built = buildMatchReport(record({}, { readyDeadlineAt: now + 45_000 }), now);
    expect(built!.body.countdownSeconds).toBe(45);
  });

  it('refuses an incomplete Perfect snapshot', () => {
    const incomplete = record(
      { platformId: 'perfect' },
      { source: 'ladder-events', perfectSessionPhase: 'accepting' },
    );
    expect(shouldReport(incomplete)).toBe(false);
    expect(buildMatchReport(incomplete)).toBeNull();
  });

  it('accepts an assigned Perfect match with its phase', () => {
    const assigned = record(
      { platformId: 'perfect' },
      { source: 'ladder-events', perfectSessionPhase: 'assigned' },
    );
    const built = buildMatchReport(assigned);
    expect(built!.body.platform).toBe('perfect');
    expect(built!.body.phase).toBe('assigned');
    expect(built!.idempotencyKey).toBe('perfect:2603212003001');
  });

  it('returns null when no player carries an identity', () => {
    const empty = record({}, { teams: [{ players: [{ nickname: '' }] }, { players: [] }] });
    expect(buildMatchReport(empty)).toBeNull();
  });
});
