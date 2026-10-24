/**
 * Fixture-only preview of the server-driven panels.
 *
 * Why it exists: the real window needs Rust + the 5E client, which makes visual
 * iteration impossible on a dev box. This page mounts the same components with
 * hand-written state, so a screenshot can be taken from plain Chromium.
 *
 *   npx vite                      # from desktop/
 *   open http://127.0.0.1:5173/ui-preview/index.html?state=ready
 *
 * States: ready | no-ai | signature | empty
 */
import { createApp, h, ref } from 'vue';
import '../index.css';
import { teamSyncClient } from '@core/sync/sync-client';
import MatchWorkspace from '../components/MatchWorkspace.vue';
import ServerRoomPanel from '../components/ServerRoomPanel.vue';
import TeamSyncSettingsSection from '../components/settings/TeamSyncSettingsSection.vue';
import AboutSettingsSection from '../components/settings/AboutSettingsSection.vue';
import MatchHistoryListRow from '../components/match-history/MatchHistoryListRow.vue';
import StoredAiReport from '../components/StoredAiReport.vue';

type Scenario = 'ready' | 'no-ai' | 'signature' | 'empty' | 'no-side';

const params = new URLSearchParams(location.search);
const scenario = (params.get('state') ?? 'ready') as Scenario;
const view = params.get('view') ?? 'panel';
const tab = params.get('tab') ?? 'roster';

const PROFILES = [
  { nickname: '半团空气', team: 'ct', stats: { rating: 1.09, seasonRating: 1.09, seasonAdr: 78, seasonRws: 10.4, kd: 0.93, headshotRate: 35, winRate: 52, matchesPlayed: 63, elo: 2140, recentResults: 'WWLWW' } },
  { nickname: '背身步马枪', team: 'ct', stats: { rating: 1.06, seasonRating: 1.06, seasonAdr: 86, seasonRws: 9.8, kd: 0.88, headshotRate: 41, winRate: 49, matchesPlayed: 88, elo: 2055, recentResults: 'LWWLW' } },
  { nickname: 'Z大爷', team: 't', stats: { rating: 1.08, seasonRating: 1.08, seasonAdr: 106, seasonRws: 12.1, kd: 1.31, headshotRate: 52, winRate: 55, matchesPlayed: 117, elo: 2188, recentResults: 'WLWWW' } },
  { nickname: 'Farewell-海海', team: 't', stats: { rating: 1.09, seasonRating: 1.09, seasonAdr: 74, seasonRws: 8.7, kd: 0.91, headshotRate: 38, winRate: 44, matchesPlayed: 41, elo: 1980, recentResults: 'LLWLL' } },
];

const AI_TEXT = `## 结论
CT 更被看好，但优势不来自枪法，而是对面 T 边的下包点过于集中。

## 双方强弱
- **Z大爷** ADR 106、K/D 1.31，是对面唯一稳定输出点
- 我方两人 ADR 78–86，属于正常水平，不构成劣势
- 对面 Farewell-海海 打了 117 场，样本充足，数据可信

## 对方威胁点
- **Z大爷**：ADR 106 远高于全场中位数，首杀后容易滚雪球
- **背身步马枪**：K/D 0.88 偏低，可作为突破口

## 开局建议
- 前两回合重点照顾 A 区，对面 11 个下包回合里 7 次打 A
- 中路给一颗烟，切断对面转点
- 让 ADR 最高的队友守 A 小道`;

const AI_RESULT = {
  schemaVersion: 3,
  predictedWinner: 'A' as const,
  modelWinProbability: { A: 58, B: 42 },
  winProbability: { A: 58, B: 42 },
  confidence: 72,
  dataCoverage: 0.8,
  headline: 'CT 首杀优势明显，对面靠枪法硬拼',
  decisiveFactors: [
    {
      id: 'f1',
      dimension: 'opening' as const,
      advantage: 'A' as const,
      impact: 3 as const,
      title: '首杀控制权',
      summary: 'CT 首杀成功率 66.7%，对面仅 33.3%，开局拿人头的概率是对方两倍',
      evidence: [],
    },
    {
      id: 'f2',
      dimension: 'aim' as const,
      advantage: 'B' as const,
      impact: 2 as const,
      title: '对面爆头更狠',
      summary: '对面爆头率 57% 高于我方 46%，正面拼枪可能吃亏',
      evidence: [],
    },
    {
      id: 'f3',
      dimension: 'strength' as const,
      advantage: 'Even' as const,
      impact: 2 as const,
      title: '整体实力持平',
      summary: '双方 Rating 1.00 对 1.01、ADR 77.5 对 76.3，几乎完全对等',
      evidence: [],
    },
  ],
  playerSignals: [
    {
      steamId: '76561198000000001',
      nickname: '半团空气',
      side: 'A' as const,
      kind: 'carry' as const,
      impact: 2 as const,
      title: '首杀尖刀',
      summary: 'Rating 1.08、ADR 82.2、RWS 12.0、首杀成功率 80%',
      evidence: [],
    },
    {
      steamId: '76561198000000002',
      nickname: '背身步马枪',
      side: 'A' as const,
      kind: 'specialist' as const,
      impact: 1 as const,
      title: '首杀支点',
      summary: '首杀成功率 80%、爆头率 55%，但 RWS 9.3 偏低',
      evidence: [],
    },
    {
      steamId: '76561198000000003',
      nickname: 'Z大爷',
      side: 'B' as const,
      kind: 'carry' as const,
      impact: 3 as const,
      title: '对面最强火力',
      summary: 'Rating 1.12、K/D 1.23、ADR 83.2，是对面唯一稳定正贡献点',
      evidence: [],
    },
    {
      steamId: '76561198000000004',
      nickname: 'Farewell-海海',
      side: 'B' as const,
      kind: 'weakLink' as const,
      impact: 2 as const,
      title: '对面短板',
      summary: 'Rating 0.94、K/D 0.90、ADR 71.4，多项低于分界',
      evidence: [],
    },
  ],
  teamPlans: {
    A: {
      winConditions: [
        { text: '利用 66.7% 首杀成功率，主动抢 A 大和中路首杀', evidence: [] },
        { text: '稳守长枪线，把比赛拖进人数优势残局', evidence: [] },
      ],
      risks: [{ text: '全队爆头率 46% 低于对面 57%，正面拼枪可能吃亏', evidence: [] }],
    },
    B: {
      winConditions: [{ text: '靠 Z大爷 的前压找首杀，把节奏拖快', evidence: [] }],
      risks: [{ text: '首杀成功率只有 33.3%，一旦开局掉人很难翻', evidence: [] }],
    },
  },
  uncertainties: [
    '双方 KAST 和残局胜率缺失，无法评估残局能力',
    '半团空气、Farewell-海海 样本仅 16-17 场，数据波动大',
  ],
  dataQuality: '赛季数据 8 项中 6 项可用',
};

const TACTICS_TEXT = `## 开局选点预判
对面 T 边明显偏 A：11 个下包回合里 7 次打 A，平均 39.8 秒完成下包。

## 各人习惯
- **Z大爷**：CT 常驻外场，T 边 3 次打 B、1 次打 A，喜欢先给火
- **Farewell-海海**：CT 有 6 回合在外场游走，T 边偏 B

## 我方应对
- A 区开局放 3 人，其中 1 人前压 A 坡拿信息
- B 区 2 人足够，对面 B 边只有 4 个回合
- 第 3 回合起注意对面可能改打 B

## 数据缺口
样本只有 16 个回合，CT 站位结论仅供参考。`;

function makeMatch(state: Scenario) {
  if (state === 'empty') return null;
  const base = {
    sessionId: 'e9f952bd',
    matchId: '2603231600001',
    mapName: 'de_mirage',
    mySide: 'ct' as const,
    mySideSource: 'explicit' as const,
    profileState: 'ready',
    homeState: 'ready',
    homeCoverage: 4,
    demoState: 'ready',
    aiState: 'ready',
    tacticsState: 'ready',
    updatedAt: Date.now(),
  };
  if (state === 'no-side') {
    // 服务端认不出我方是谁：客户端应该先弹窗问，而不是替用户猜。
    return { ...base, mySide: null, mySideSource: null, aiText: AI_TEXT, aiResult: AI_RESULT };
  }
  if (state === 'no-ai') {
    return { ...base, aiState: 'skipped', aiText: null, tacticsState: 'skipped', tacticsText: null };
  }
  if (state === 'signature') {
    return {
      ...base,
      homeState: 'signature',
      homeCoverage: 0,
      homeError: '5E 签名已失效，赛季数据（ADR/RWS/KAST）这次没拿到，仅用本场数据。',
      aiText: AI_TEXT,
      aiResult: AI_RESULT,
      tacticsText: TACTICS_TEXT,
    };
  }
  return { ...base, aiText: AI_TEXT, aiResult: AI_RESULT, tacticsText: TACTICS_TEXT };
}

const POST_REPORT = {
  matchCode: '2603231600001',
  mapName: 'de_mirage',
  roundTotal: 24,
  status: 1,
  isFinished: true,
  winnerSide: 'A',
  scoreA: 13,
  scoreB: 11,
  halfScores: { fhA: 8, shA: 5, fhB: 4, shB: 7 },
  demoUrl: 'https://example.invalid/demo.zip',
  players: [
    { uid: 'a1', nickname: '半团空气', teamSide: 1, kill: 24, death: 16, assist: 5, rating: 1.32, adr: 96, isMvp: true, isSvp: false },
    { uid: 'a2', nickname: '背身步马枪', teamSide: 1, kill: 18, death: 18, assist: 7, rating: 1.05, adr: 78, isMvp: false, isSvp: false },
    { uid: 'b1', nickname: 'Z大爷', teamSide: 2, kill: 26, death: 17, assist: 3, rating: 1.28, adr: 104, isMvp: false, isSvp: true },
    { uid: 'b2', nickname: 'Farewell-海海', teamSide: 2, kill: 14, death: 20, assist: 6, rating: 0.92, adr: 71, isMvp: false, isSvp: false },
  ],
  comparison: { isCorrect: true, headline: 'AI 预判 CT 更被看好，命中' },
  fetchedAt: Date.now(),
};

const sync = {
  serverMatch: ref(
    tab === 'post' && scenario !== 'empty'
      ? { ...(makeMatch(scenario) as object), postReport: POST_REPORT }
      : makeMatch(scenario),
  ),
  serverProfiles: ref(scenario === 'empty' ? [] : PROFILES),
  aiStreamChunk: ref(''),
  tacticsStream: ref(''),
  sideBusy: ref(false),
  sideError: ref<string | null>(null),
  aiError: ref<string | null>(null),
  setAnalysisSide: async () => {},
  rerunAnalysis: async () => {},
  settings: ref({ roomCode: 'MAIN', enabled: true }),
  status: ref('connected'),
};

function localPlayer(name: string, steamId: string, teamSide: number, rating: number, adr: number, kd: number, hs: number) {
  return {
    steamId,
    nickname: name,
    teamSide,
    isSingle: false,
    rating,
    seasonRating: rating,
    adpr: adr,
    kd,
    hsRate: hs,
    radar: {},
    recentResults: [],
    recentRatings: [],
    tags: [],
  };
}

const MATCH_RECORD = {
  id: 'local-1',
  platformId: '5e',
  data: {},
  summary: { playerCount: 4, mapName: 'de_mirage' },
  detail: {
    platformGameId: '2603231600001',
    mapName: 'de_mirage',
    readyDeadlineAt: Date.now() + 45_000,
    teams: [
      {
        side: 'A',
        id: 0,
        singleCount: 0,
        partyGroups: [],
        players: [
          localPlayer('半团空气', '76561198000000001', 0, 1.09, 78, 0.93, 0.35),
          localPlayer('背身步马枪', '76561198000000002', 0, 1.06, 86, 0.88, 0.41),
        ],
      },
      {
        side: 'B',
        id: 1,
        singleCount: 0,
        partyGroups: [],
        players: [
          localPlayer('Z大爷', '76561198000000003', 1, 1.08, 106, 1.31, 0.52),
          localPlayer('Farewell-海海', '76561198000000004', 1, 1.09, 74, 0.91, 0.38),
        ],
      },
    ],
    unassigned: [],
    hasExtraInfo: false,
    parseWarnings: [],
  },
};

async function bootstrap() {
  // ?live=1 时连本机服务端，用真实房间数据（雷达图走 vite 代理）。
  if (params.get('live') === '1') {
    try {
      const res = await fetch('http://127.0.0.1:8787/api/v1/room/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: '预览', deviceType: 'pc' }),
      });
      const json = await res.json();
      if (json?.code === 0) {
        teamSyncClient.updateSettings({
          enabled: true,
          serverUrl: 'http://127.0.0.1:8787',
          roomCode: json.data.roomCode,
          token: json.data.token,
        });
      }
    } catch {
      // 服务端没起就退回 fixture
    }
  }

  createApp({
    // Fixture only: the real composable carries more methods than the panel reads.
    render: () => {
      if (view === 'sync') return h(TeamSyncSettingsSection);
      if (view === 'about') return h('div', { class: 'max-w-2xl p-6' }, [h(AboutSettingsSection)]);
      if (view === 'stored-ai') {
        const report = {
          schemaVersion: 3,
          predictedWinner: 'A',
          winProbability: { A: 58, B: 42 },
          modelWinProbability: { A: 58, B: 42 },
          confidence: 72,
          dataCoverage: 0.8,
          headline: 'A 队略占上风，优势主要来自开局首杀与道具协同。',
          decisiveFactors: [
            { id: 'f1', dimension: 'opening', advantage: 'A', impact: 3, title: '首杀转化更高', summary: 'A 队首杀成功率 31%，高于 B 队 24%，前期更容易拿到人数优势。', evidenceIds: [] },
            { id: 'f2', dimension: 'utility', advantage: 'A', impact: 2, title: '道具覆盖更完整', summary: 'A 队 ADR 与 RWS 均高于对手，说明道具交换更占优。', evidenceIds: [] },
          ],
          playerSignals: [
            { steamId: '1', side: 'A', kind: 'carry', impact: 3, title: '半团空气 状态火热', summary: 'ADR 96、Rating 1.32，是 A 队最稳定的输出点。', evidenceIds: [] },
            { steamId: '2', side: 'B', kind: 'weakLink', impact: 2, title: 'Farewell-海海 偏弱', summary: 'K/D 0.91、ADR 71，对枪中容易被突破。', evidenceIds: [] },
          ],
          teamPlans: { A: { winConditions: [], risks: [] }, B: { winConditions: [], risks: [] } },
          uncertainties: ['B 队地图样本只有 3 场，结论仅供参考。'],
          dataQuality: '',
        };
        return h('div', { class: 'max-w-2xl p-6' }, [h(StoredAiReport, { report: report as never })]);
      }
      if (view === 'history') {
        const items = [
          { id: 'm1', platformId: '5e', savedAt: Date.now(), updatedAt: Date.now(), matchTime: '10-23 20:15', mapName: 'de_mirage', playerCount: 10, matchAvgScore: 2410, postMatchScore: '13 : 10', postMatchWinner: 'A', hasPostMatch: true, aiStatus: 'ready' },
          { id: 'm2', platformId: '5e', savedAt: Date.now(), updatedAt: Date.now() - 86_400_000, matchTime: '10-22 21:03', mapName: 'de_dust2', playerCount: 10, matchAvgScore: 2380, aiStatus: 'ready' },
          { id: 'm3', platformId: '5e', savedAt: Date.now(), updatedAt: Date.now() - 172_800_000, matchTime: '10-21 19:40', mapName: 'de_inferno', playerCount: 8, matchAvgScore: 2355, aiStatus: 'none' },
        ];
        return h('div', { class: 'max-w-3xl p-6' }, [
          h('ul', { class: 'flex flex-col gap-3' }, items.map((item, index) => h(MatchHistoryListRow, { item: item as never, staggerIndex: index }))),
        ]);
      }
      if (view === 'workspace') {
        return h(MatchWorkspace, {
          match: MATCH_RECORD as never,
          sync: sync as never,
          initialTab: tab as never,
        });
      }
      return h(ServerRoomPanel, { sync: sync as never });
    },
  }).mount('#app');
}

void bootstrap();
