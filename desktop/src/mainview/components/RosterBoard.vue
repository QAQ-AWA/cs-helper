<script setup lang="ts">
import { computed } from 'vue';
import type { MatchPlayer, MatchTeam } from '@core/match/models';
import type { ServerPlayerView } from '../composables/useTeamSync';

/**
 * The roster the user actually needs before a match: who is on each side and
 * how good they are. Server-reported season numbers win over whatever the
 * client scraped, because the relay fills the gaps the client could not.
 */
const props = defineProps<{
  teams: MatchTeam[];
  profiles?: ServerPlayerView[];
}>();

const SIDE_ORDER = [
  { key: 'ct' as const, teamIndex: 0, label: 'CT' },
  { key: 't' as const, teamIndex: 1, label: 'T' },
];

interface Row {
  key: string;
  name: string;
  rating: number | null;
  adr: number | null;
  kd: number | null;
  hs: number | null;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** 0-1 fractions (client) and percentages (server) both land here. */
function pct(value: unknown): number | null {
  const raw = num(value);
  if (raw === null) return null;
  return raw <= 1 ? raw * 100 : raw;
}

function serverStats(player: MatchPlayer) {
  const match = (props.profiles ?? []).find(
    (item) => item.nickname && item.nickname === player.nickname,
  );
  return (match?.stats ?? {}) as Record<string, unknown>;
}

function rowsFor(teamIndex: number): Row[] {
  const team = props.teams?.[teamIndex];
  const players = team?.players ?? [];
  return players
    .map((player) => {
      const stats = serverStats(player);
      return {
        key: player.steamId || player.nickname,
        name: player.nickname || 'Unknown',
        rating: num(stats.seasonRating) ?? num(stats.rating) ?? num(player.seasonRating) ?? num(player.rating),
        adr: num(stats.seasonAdr) ?? num(player.adpr),
        kd: num(stats.kd) ?? num(player.kd),
        hs: pct(stats.headshotRate) ?? pct(player.hsRate),
      };
    })
    .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
}

const sides = computed(() =>
  SIDE_ORDER.map((side) => {
    const rows = rowsFor(side.teamIndex);
    const ratings = rows.map((row) => row.rating).filter((value): value is number => value !== null);
    const avg = ratings.length ? ratings.reduce((sum, value) => sum + value, 0) / ratings.length : null;
    return { ...side, rows, avg };
  }),
);

function ratingClass(value: number | null): string {
  if (value === null) return 'text-fg-muted';
  if (value >= 1.1) return 'text-success';
  if (value < 0.95) return 'text-danger';
  return 'text-fg';
}

function show(value: number | null, digits = 2): string {
  return value === null ? '—' : value.toFixed(digits);
}
</script>

<template>
  <div class="grid h-full min-h-0 grid-cols-2 gap-3 overflow-y-auto p-3">
    <section
      v-for="side in sides"
      :key="side.key"
      class="min-h-0 self-start rounded-lg border border-border bg-surface"
    >
      <header class="border-b border-border px-3 py-2">
        <div class="flex items-baseline justify-between">
          <span class="text-xs font-semibold" :class="side.key === 'ct' ? 'text-team-a' : 'text-team-b'">
            {{ side.label }}
          </span>
          <span class="text-[11px] text-fg-muted">
            {{ side.rows.length }} 人<template v-if="side.avg !== null"> · 均 {{ side.avg.toFixed(2) }}</template>
          </span>
        </div>
        <div
          class="mt-1 grid grid-cols-[minmax(0,1fr)_44px_40px_44px_40px] gap-1 text-[10px] text-fg-muted"
        >
          <span />
          <span class="text-right">Rating</span>
          <span class="text-right">ADR</span>
          <span class="text-right">K/D</span>
          <span class="text-right">HS%</span>
        </div>
      </header>

      <div v-if="!side.rows.length" class="px-3 py-3 text-xs text-fg-muted">暂无数据</div>

      <div
        v-for="row in side.rows"
        :key="row.key"
        class="grid grid-cols-[minmax(0,1fr)_44px_40px_44px_40px] items-baseline gap-1 px-3 py-1.5 text-[12px] odd:bg-elevated/40"
      >
        <span class="truncate text-fg">{{ row.name }}</span>
        <span class="text-right font-medium tabular-nums" :class="ratingClass(row.rating)">
          {{ show(row.rating) }}
        </span>
        <span class="text-right tabular-nums text-fg-secondary">
          {{ row.adr === null ? '—' : Math.round(row.adr) }}
        </span>
        <span class="text-right tabular-nums text-fg-secondary">{{ show(row.kd) }}</span>
        <span class="text-right tabular-nums text-fg-secondary">
          {{ row.hs === null ? '—' : `${Math.round(row.hs)}%` }}
        </span>
      </div>
    </section>
  </div>
</template>
