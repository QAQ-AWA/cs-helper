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
import MatchWorkspace from '../components/MatchWorkspace.vue';
import ServerRoomPanel from '../components/ServerRoomPanel.vue';

type Scenario = 'ready' | 'no-ai' | 'signature' | 'empty';

const params = new URLSearchParams(location.search);
const scenario = (params.get('state') ?? 'ready') as Scenario;
const view = params.get('view') ?? 'panel';
const tab = params.get('tab') ?? 'roster';

const PROFILES = [
  { nickname: '半团空气', team: 'ct', stats: { rating: 1.09, seasonAdr: 78, kd: 0.93 } },
  { nickname: '背身步马枪', team: 'ct', stats: { rating: 1.06, seasonAdr: 86, kd: 0.88 } },
  { nickname: 'Z大爷', team: 't', stats: { rating: 1.08, seasonAdr: 106, kd: 1.31 } },
  { nickname: 'Farewell-海海', team: 't', stats: { rating: 1.09, seasonAdr: 74, kd: 0.91 } },
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
      tacticsText: TACTICS_TEXT,
    };
  }
  return { ...base, aiText: AI_TEXT, tacticsText: TACTICS_TEXT };
}

const sync = {
  serverMatch: ref(makeMatch(scenario)),
  serverProfiles: ref(scenario === 'empty' ? [] : PROFILES),
  aiStreamChunk: ref(''),
  tacticsStream: ref(''),
  sideBusy: ref(false),
  sideError: ref<string | null>(null),
  setAnalysisSide: async () => {},
  settings: ref({ roomCode: 'MAIN', enabled: true }),
  status: ref('connected'),
};

function localPlayer(name: string, teamSide: number, rating: number, adr: number, kd: number, hs: number) {
  return {
    steamId: `7656119800000000${teamSide}${Math.round(rating * 100)}`,
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
          localPlayer('半团空气', 0, 1.09, 78, 0.93, 0.35),
          localPlayer('背身步马枪', 0, 1.06, 86, 0.88, 0.41),
        ],
      },
      {
        side: 'B',
        id: 1,
        singleCount: 0,
        partyGroups: [],
        players: [
          localPlayer('Z大爷', 1, 1.08, 106, 1.31, 0.52),
          localPlayer('Farewell-海海', 1, 1.09, 74, 0.91, 0.38),
        ],
      },
    ],
    unassigned: [],
    hasExtraInfo: false,
    parseWarnings: [],
  },
};

createApp({
  // Fixture only: the real composable carries more methods than the panel reads.
  render: () =>
    view === 'workspace'
      ? h(MatchWorkspace, { match: MATCH_RECORD as never, sync: sync as never, initialTab: tab as never })
      : h(ServerRoomPanel, { sync: sync as never }),
}).mount('#app');
