import { describe, expect, it } from 'vitest';
import type { MatchRecord } from '@core/match/models';
import { shouldReplayMatchReveal } from './match-reveal-policy';

function record(source: MatchRecord['detail']['source'], platformId: 'perfect' | '5e'): MatchRecord {
  return {
    id: 'next',
    platformId,
    time: '',
    level: 'INFO',
    category: 'test',
    data: {},
    summary: { playerCount: 0 },
    detail: {
      platformId,
      source,
      teams: [],
      unassigned: [],
      hasExtraInfo: false,
      parseWarnings: [],
    },
  };
}

describe('match reveal policy', () => {
  it('keeps whole-panel reveals for real id changes on other flows', () => {
    expect(shouldReplayMatchReveal(record(undefined, '5e'), 'next', 'previous')).toBe(true);
    expect(shouldReplayMatchReveal(record(undefined, '5e'), 'same', 'same')).toBe(false);
  });
});
