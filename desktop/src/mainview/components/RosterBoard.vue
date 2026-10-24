<script setup lang="ts">
import { computed } from 'vue';
import type { MatchPlayer, MatchTeam } from '@core/match/models';
import type { AiPlayerSignal } from '@core/ai/types';
import type { ServerPlayerView } from '../composables/useTeamSync';
import { getTeamTableColumnDefs } from './team-table-columns';
import TeamPlayerTable from './TeamPlayerTable.vue';

/**
 * 赛前阵容：按队伍列 10 人，可排序、可点开细节。
 *
 * 数据来源是服务端补齐后的赛季数据（覆盖客户端抓到的值），因为 5E 页面上
 * 有些人的赛季字段是空的，服务端 player/home 才拿得到全量。
 */
const props = defineProps<{
  teams: MatchTeam[];
  profiles?: ServerPlayerView[];
  mySide?: 'ct' | 't' | null;
  playerSignals?: AiPlayerSignal[];
  mapName?: string;
}>();

const SIDE_ORDER = [
  { key: 'ct' as const, teamIndex: 0, label: 'CT' },
  { key: 't' as const, teamIndex: 1, label: 'T' },
];

function num(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** 服务端给的是百分数（46.0），表格要 0-1 的小数。 */
function fraction(value: unknown): number | undefined {
  const raw = num(value);
  if (raw === undefined) return undefined;
  return raw > 1 ? raw / 100 : raw;
}

function serverStats(player: MatchPlayer): Record<string, unknown> {
  const match = (props.profiles ?? []).find(
    (item) => item.nickname && item.nickname === player.nickname,
  );
  return (match?.stats ?? {}) as Record<string, unknown>;
}

function recentResults(value: unknown): MatchPlayer['recentResults'] | undefined {
  if (typeof value !== 'string') return undefined;
  const parsed = value
    .toUpperCase()
    .split('')
    .filter((flag) => flag === 'W' || flag === 'L' || flag === 'D')
    .map((flag) => (flag === 'W' ? 'win' : flag === 'L' ? 'lose' : 'draw'));
  return parsed.length ? (parsed as MatchPlayer['recentResults']) : undefined;
}

/** 服务端的赛季数据优先，客户端抓到的值兜底。 */
function withServerStats(player: MatchPlayer): MatchPlayer {
  const stats = serverStats(player);
  const seasonRating = num(stats.seasonRating) ?? player.seasonRating;
  const recent = num(stats.rating) ?? player.rating;
  return {
    ...player,
    score: num(stats.elo) ?? player.score,
    // 两列同名同值只会让人以为出 bug：拿不到真正的赛季场均时留空。
    rating: recent !== undefined && recent === seasonRating ? undefined : recent,
    seasonRating,
    adpr: num(stats.seasonAdr) ?? player.adpr,
    weRaw: num(stats.seasonRws) ?? player.weRaw,
    kd: num(stats.kd) ?? player.kd,
    hsRate: fraction(stats.headshotRate) ?? player.hsRate,
    firstKillSuccessRate: fraction(stats.firstKillRate) ?? player.firstKillSuccessRate,
    seasonWinRate: fraction(stats.winRate) ?? player.seasonWinRate,
    seasonTotalNum: num(stats.matchesPlayed) ?? player.seasonTotalNum,
    rankDesc: (stats.rankDesc as string) ?? player.rankDesc,
    rankLevel: (stats.rankLevel as string) ?? player.rankLevel,
    rankNum: num(stats.rankNum) ?? player.rankNum,
    eloChange: num(stats.eloChange) ?? player.eloChange,
    recentResults: recentResults(stats.recentResults) ?? player.recentResults,
  };
}

const columns = computed(() =>
  getTeamTableColumnDefs('5e').filter((column) => column.fixed || column.defaultVisible),
);

const sides = computed(() =>
  SIDE_ORDER.map((side) => {
    const raw = props.teams?.[side.teamIndex];
    // 我方永远是 A（蓝色），跟服务端的 A/B 定义保持一致。
    const token: 'A' | 'B' = !props.mySide
      ? side.key === 'ct' ? 'A' : 'B'
      : side.key === props.mySide ? 'A' : 'B';
    const team: MatchTeam = {
      ...(raw ?? { side: token, id: side.teamIndex, players: [], singleCount: 0, partyGroups: [] }),
      side: token,
      players: (raw?.players ?? []).map(withServerStats),
    };
    // 还没确定我方是谁时，别把 CT 写成「我方」——那是猜的。
    const title = props.mySide ? `${side.label} · ${token === 'A' ? '我方' : '对方'}` : side.label;
    return { ...side, token, title, team };
  }),
);

function signalsFor(token: 'A' | 'B'): AiPlayerSignal[] {
  return (props.playerSignals ?? []).filter((signal) => signal.side === token);
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col gap-5 overflow-y-auto bg-slate-50/70 px-4 py-3">
    <TeamPlayerTable
      v-for="side in sides"
      :key="side.key"
      :team="side.team"
      :columns="columns"
      :title="side.title"
      :side-token="side.token"
      :player-signals="signalsFor(side.token)"
      :current-map="mapName"
      :platform-id="'5e'"
      self-side="A"
    />
  </div>
</template>
