import type { MatchRecord, MatchTeam } from '@core/match/models';
import type { AiAnalysisResult } from '@core/ai/types';

export interface P5ePostMatchPlayerStat {
  uid: string;
  uuid?: string;
  steamId?: string;
  nickname: string;
  avatar?: string;
  teamSide: 1 | 2; // 1 = Team A, 2 = Team B
  kill: number;
  death: number;
  assist: number;
  kd: number;
  adr: number;
  rating: number;
  rating2?: number;
  rws?: number;
  kast?: number;
  headshotRate?: number;
  firstKill?: number;
  firstDeath?: number;
  isMvp: boolean;
  isSvp: boolean;
  eloChange?: number;
  currElo?: number;
}

export interface P5ePostMatchHalfScores {
  fhA: number;
  shA: number;
  fhB: number;
  shB: number;
}

export interface P5ePostMatchComparison {
  aiPredictedWinner?: string;
  actualWinner: 'A' | 'B' | 'Draw' | null;
  isCorrect: boolean | null;
  winProbA?: number;
  winProbB?: number;
  headline?: string;
}

export interface P5ePostMatchReport {
  matchCode: string;
  mapName: string;
  mapDesc?: string;
  roundTotal: number;
  status: number; // 1 = 正常完赛
  isFinished: boolean;
  winnerSide: 'A' | 'B' | 'Draw' | null;
  scoreA: number;
  scoreB: number;
  halfScores?: P5ePostMatchHalfScores;
  startTime?: number; // Unix 秒
  endTime?: number;
  durationMinutes?: number;
  demoUrl?: string;
  mvpUid?: string;
  players: P5ePostMatchPlayerStat[];
  comparison?: P5ePostMatchComparison;
  fetchedAt: number; // 本地获取时间戳
}

function safeNum(val: unknown, fallback = 0): number {
  if (typeof val === 'number' && !Number.isNaN(val)) return val;
  if (typeof val === 'string' && val.trim()) {
    const parsed = Number(val);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return fallback;
}

function safeNumOrUndef(val: unknown): number | undefined {
  if (typeof val === 'number' && !Number.isNaN(val)) return val;
  if (typeof val === 'string' && val.trim()) {
    const parsed = Number(val);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return undefined;
}

function asRecord(val: unknown): Record<string, unknown> | undefined {
  return val && typeof val === 'object' && !Array.isArray(val)
    ? (val as Record<string, unknown>)
    : undefined;
}

function parsePlayerEntry(
  raw: unknown,
  teamSide: 1 | 2,
  mvpUidStr?: string,
): P5ePostMatchPlayerStat | null {
  const item = asRecord(raw);
  if (!item) return null;

  const fight = asRecord(item.fight) ?? {};
  const userInfo = asRecord(item.user_info);
  const userData = asRecord(userInfo?.user_data);
  const profile = asRecord(userData?.profile);
  const steam = asRecord(userData?.steam);
  const sts = asRecord(item.sts);

  const uid = String(fight.uid ?? userData?.uid ?? item.uid ?? '');
  if (!uid) return null;

  const nickname = String(userData?.username ?? profile?.username ?? fight.username ?? `玩家 ${uid}`);
  const avatar = typeof profile?.avatarUrl === 'string' && profile.avatarUrl
    ? profile.avatarUrl
    : typeof userData?.avatar_url === 'string'
      ? userData.avatar_url
      : undefined;

  const steamId = typeof steam?.steamId === 'string'
    ? steam.steamId
    : typeof userData?.steam_id === 'string'
      ? userData.steam_id
      : undefined;

  const kill = safeNum(fight.kill);
  const death = safeNum(fight.death);
  const assist = safeNum(fight.assist);
  const kd = death > 0 ? Math.round((kill / death) * 100) / 100 : kill;
  const adr = Math.round(safeNum(fight.adr) * 10) / 10;
  const rating = Math.round(safeNum(fight.rating) * 100) / 100;
  const rating2 = safeNumOrUndef(fight.rating2);
  const rws = safeNumOrUndef(fight.rws);
  const kast = safeNumOrUndef(fight.kast);

  let headshotRate = safeNumOrUndef(fight.per_headshot);
  if (headshotRate != null && headshotRate > 1) {
    headshotRate = Math.round(headshotRate) / 100;
  } else if (headshotRate == null && kill > 0 && fight.headshot != null) {
    headshotRate = Math.round((safeNum(fight.headshot) / kill) * 100) / 100;
  }

  const firstKill = safeNumOrUndef(fight.first_kill);
  const firstDeath = safeNumOrUndef(fight.first_death);

  const isMvp = fight.is_mvp === '1' || fight.is_mvp === 1 || uid === mvpUidStr;
  const isSvp = fight.is_svp === '1' || fight.is_svp === 1;

  const eloChange = safeNumOrUndef(sts?.change_elo);
  const currElo = safeNumOrUndef(sts?.curr_elo);

  return {
    uid,
    uuid: typeof userData?.uuid === 'string' ? userData.uuid : undefined,
    steamId,
    nickname,
    avatar,
    teamSide,
    kill,
    death,
    assist,
    kd,
    adr,
    rating,
    rating2: rating2 != null ? Math.round(rating2 * 100) / 100 : undefined,
    rws: rws != null ? Math.round(rws * 10) / 10 : undefined,
    kast: kast != null ? Math.round(kast * 10) / 10 : undefined,
    headshotRate,
    firstKill,
    firstDeath,
    isMvp,
    isSvp,
    eloChange,
    currElo,
  };
}

/**
 * 解析 5E match 接口（/crane/http/api/data/match/{code}）返回的完整赛后战报数据
 */
export function parseP5ePostMatchReport(
  rawResponse: unknown,
  aiResult?: AiAnalysisResult | null,
): P5ePostMatchReport | null {
  const root = asRecord(rawResponse);
  if (!root) return null;

  const data = asRecord(root.data);
  if (!data) return null;

  const main = asRecord(data.main);
  if (!main) return null;

  const matchCode = String(main.match_code ?? '');
  if (!matchCode) return null;

  const mapName = String(main.map ?? '未知地图');
  const mapDesc = typeof main.map_desc === 'string' ? main.map_desc : undefined;
  const roundTotal = safeNum(main.round_total);
  const status = safeNum(main.status);

  const scoreA = safeNum(main.group1_all_score);
  const scoreB = safeNum(main.group2_all_score);

  // 1 = 正常打完, 或者回合数 > 0 且有一方比分达到常规胜场 (如 13 或加时)
  const isFinished = status === 1 || (roundTotal > 0 && (scoreA >= 13 || scoreB >= 13 || scoreA + scoreB >= 24));

  let winnerSide: 'A' | 'B' | 'Draw' | null = null;
  const winnerRaw = safeNum(main.match_winner);
  if (winnerRaw === 1) {
    winnerSide = 'A';
  } else if (winnerRaw === 2) {
    winnerSide = 'B';
  } else if (isFinished) {
    if (scoreA > scoreB) winnerSide = 'A';
    else if (scoreB > scoreA) winnerSide = 'B';
    else if (scoreA === scoreB && scoreA > 0) winnerSide = 'Draw';
  }

  const halfScores: P5ePostMatchHalfScores = {
    fhA: safeNum(main.group1_fh_score),
    shA: safeNum(main.group1_sh_score),
    fhB: safeNum(main.group2_fh_score),
    shB: safeNum(main.group2_sh_score),
  };

  const startTime = safeNumOrUndef(main.start_time);
  const endTime = safeNumOrUndef(main.end_time);
  let durationMinutes: number | undefined;
  if (startTime && endTime && endTime > startTime) {
    durationMinutes = Math.round((endTime - startTime) / 60);
  }

  const demoUrl = typeof main.demo_url === 'string' && main.demo_url.startsWith('http')
    ? main.demo_url
    : undefined;

  const mvpUid = main.mvp_uid != null ? String(main.mvp_uid) : undefined;

  // 解析两队玩家
  const players: P5ePostMatchPlayerStat[] = [];

  if (Array.isArray(data.group_1)) {
    for (const item of data.group_1) {
      const p = parsePlayerEntry(item, 1, mvpUid);
      if (p) players.push(p);
    }
  }
  if (Array.isArray(data.group_2)) {
    for (const item of data.group_2) {
      const p = parsePlayerEntry(item, 2, mvpUid);
      if (p) players.push(p);
    }
  }

  // 计算 AI 预测对比
  let comparison: P5ePostMatchComparison | undefined;
  if (aiResult && isFinished && winnerSide) {
    const predicted = aiResult.predictedWinner;
    const isCorrect =
      predicted === 'Even'
        ? winnerSide === 'Draw'
        : predicted === winnerSide;

    comparison = {
      aiPredictedWinner: predicted,
      actualWinner: winnerSide,
      isCorrect,
      winProbA: aiResult.winProbability?.A,
      winProbB: aiResult.winProbability?.B,
      headline: aiResult.headline,
    };
  }

  return {
    matchCode,
    mapName,
    mapDesc,
    roundTotal,
    status,
    isFinished,
    winnerSide,
    scoreA,
    scoreB,
    halfScores,
    startTime,
    endTime,
    durationMinutes,
    demoUrl,
    mvpUid,
    players,
    comparison,
    fetchedAt: Date.now(),
  };
}

/**
 * 从 MatchRecord 中提取用于查询 match 接口的 matchCode
 */
export function resolveMatchCode(match: MatchRecord): string | undefined {
  const p5eBundle = match.data?.p5eBundle as { matchCode?: string; gameId?: string } | undefined;
  if (p5eBundle?.matchCode && /^g\d+-/.test(p5eBundle.matchCode)) {
    return p5eBundle.matchCode;
  }
  if (p5eBundle?.gameId && /^g\d+-/.test(p5eBundle.gameId)) {
    return p5eBundle.gameId;
  }
  if (match.detail?.platformGameId && /^g\d+-/.test(match.detail.platformGameId)) {
    return match.detail.platformGameId;
  }
  if (match.summary?.platformGameId && /^g\d+-/.test(match.summary.platformGameId)) {
    return match.summary.platformGameId;
  }
  if (match.id && /^g\d+-/.test(match.id)) {
    return match.id;
  }
  return undefined;
}
