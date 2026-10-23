import { describe, expect, it } from 'vitest';
import { parseP5ePostMatchReport, resolveMatchCode } from './post-match';
import type { AiAnalysisResult } from '@core/ai/types';
import type { MatchRecord } from '@core/match/models';

describe('5E Post-Match Parser', () => {
  const sampleResponse = {
    code: 0,
    data: {
      main: {
        match_code: 'g161-20260614142743982331607',
        map: 'de_dust2',
        map_desc: '炙热沙城2',
        round_total: 23,
        start_time: 1781418601,
        end_time: 1781420942,
        status: 1,
        match_winner: 1,
        group1_all_score: 13,
        group2_all_score: 10,
        group1_fh_score: 5,
        group1_sh_score: 8,
        group2_fh_score: 7,
        group2_sh_score: 3,
        mvp_uid: 19554457,
        demo_url: 'https://demo.5eplaycdn.com/pug/123.zip',
      },
      group_1: [
        {
          fight: {
            uid: '19554457',
            kill: '22',
            death: '14',
            assist: '5',
            adr: '98.5',
            rating: '1.42',
            rating2: '1.45',
            rws: '14.2',
            kast: '78.2',
            per_headshot: '54.5',
            first_kill: '3',
            first_death: '1',
            is_mvp: '1',
          },
          user_info: {
            user_data: {
              username: 'TopFragger',
              profile: { avatarUrl: 'https://avatar.com/1.jpg' },
              steam: { steamId: '76561198000000001' },
            },
          },
          sts: {
            change_elo: '18',
            curr_elo: '2150',
          },
        },
      ],
      group_2: [
        {
          fight: {
            uid: '20060703',
            kill: '18',
            death: '16',
            assist: '3',
            adr: '82.0',
            rating: '1.08',
            rating2: '1.10',
            rws: '9.5',
            kast: '68.0',
            per_headshot: '40.0',
            first_kill: '2',
            first_death: '2',
            is_svp: '1',
          },
          user_info: {
            user_data: {
              username: 'EnemyCaptain',
              profile: { avatarUrl: 'https://avatar.com/2.jpg' },
              steam: { steamId: '76561198000000002' },
            },
          },
          sts: {
            change_elo: '-16',
            curr_elo: '1980',
          },
        },
      ],
    },
  };

  it('parses finished 5E match scoreboard and basic info correctly', () => {
    const report = parseP5ePostMatchReport(sampleResponse);
    expect(report).not.toBeNull();
    if (!report) return;

    expect(report.matchCode).toBe('g161-20260614142743982331607');
    expect(report.mapName).toBe('de_dust2');
    expect(report.mapDesc).toBe('炙热沙城2');
    expect(report.roundTotal).toBe(23);
    expect(report.scoreA).toBe(13);
    expect(report.scoreB).toBe(10);
    expect(report.winnerSide).toBe('A');
    expect(report.isFinished).toBe(true);
    expect(report.durationMinutes).toBe(39);
    expect(report.demoUrl).toBe('https://demo.5eplaycdn.com/pug/123.zip');
    expect(report.halfScores).toEqual({
      fhA: 5,
      shA: 8,
      fhB: 7,
      shB: 3,
    });
  });

  it('parses player fight statistics and MVP/SVP badges accurately', () => {
    const report = parseP5ePostMatchReport(sampleResponse);
    expect(report).not.toBeNull();
    if (!report) return;

    expect(report.players).toHaveLength(2);

    const p1 = report.players.find((p) => p.uid === '19554457');
    expect(p1).toBeDefined();
    expect(p1?.nickname).toBe('TopFragger');
    expect(p1?.kill).toBe(22);
    expect(p1?.death).toBe(14);
    expect(p1?.assist).toBe(5);
    expect(p1?.kd).toBe(1.57);
    expect(p1?.adr).toBe(98.5);
    expect(p1?.rating).toBe(1.42);
    expect(p1?.rating2).toBe(1.45);
    expect(p1?.isMvp).toBe(true);
    expect(p1?.isSvp).toBe(false);
    expect(p1?.eloChange).toBe(18);

    const p2 = report.players.find((p) => p.uid === '20060703');
    expect(p2).toBeDefined();
    expect(p2?.nickname).toBe('EnemyCaptain');
    expect(p2?.kill).toBe(18);
    expect(p2?.death).toBe(16);
    expect(p2?.isMvp).toBe(false);
    expect(p2?.isSvp).toBe(true);
    expect(p2?.eloChange).toBe(-16);
  });

  it('correctly compares actual result with AI prediction', () => {
    const aiResultCorrect: AiAnalysisResult = {
      predictedWinner: 'A',
      winProbability: { A: 65, B: 35 },
      headline: 'A 队突破能力占优',
      confidence: 80,
      stabilityReason: '',
      teamSummary: { A: '', B: '' },
      keyFactors: [],
      playerNotes: [],
      risks: [],
      dataQuality: 'good',
    };

    const reportWithAi = parseP5ePostMatchReport(sampleResponse, aiResultCorrect);
    expect(reportWithAi?.comparison).toBeDefined();
    expect(reportWithAi?.comparison?.isCorrect).toBe(true);
    expect(reportWithAi?.comparison?.actualWinner).toBe('A');
    expect(reportWithAi?.comparison?.aiPredictedWinner).toBe('A');

    const aiResultIncorrect: AiAnalysisResult = {
      ...aiResultCorrect,
      predictedWinner: 'B',
      winProbability: { A: 40, B: 60 },
    };
    const reportIncorrect = parseP5ePostMatchReport(sampleResponse, aiResultIncorrect);
    expect(reportIncorrect?.comparison?.isCorrect).toBe(false);
  });

  it('handles ongoing / unfinished match status gracefully', () => {
    const ongoingResponse = {
      data: {
        main: {
          match_code: 'g161-20260614142743982331607',
          map: 'de_mirage',
          status: 0,
          round_total: 0,
          group1_all_score: 0,
          group2_all_score: 0,
        },
        group_1: [],
        group_2: [],
      },
    };

    const report = parseP5ePostMatchReport(ongoingResponse);
    expect(report).not.toBeNull();
    expect(report?.isFinished).toBe(false);
    expect(report?.winnerSide).toBeNull();
    expect(report?.scoreA).toBe(0);
    expect(report?.scoreB).toBe(0);
  });

  it('extracts matchCode from various MatchRecord patterns', () => {
    const match1 = {
      id: 'g161-123456',
      data: {},
      summary: { playerCount: 10 },
      detail: { teams: [], unassigned: [], hasExtraInfo: true, parseWarnings: [] },
    } as unknown as MatchRecord;
    expect(resolveMatchCode(match1)).toBe('g161-123456');

    const match2 = {
      id: 'local_id',
      data: {
        p5eBundle: {
          matchCode: 'g161-987654',
        },
      },
      summary: { playerCount: 10 },
      detail: { teams: [], unassigned: [], hasExtraInfo: true, parseWarnings: [] },
    } as unknown as MatchRecord;
    expect(resolveMatchCode(match2)).toBe('g161-987654');
  });
});
