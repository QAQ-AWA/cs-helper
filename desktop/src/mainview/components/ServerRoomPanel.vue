<script setup lang="ts">
import { computed } from 'vue';
import type { useTeamSync } from '../composables/useTeamSync';
import ServerAnalysisPanel from './ServerAnalysisPanel.vue';

/**
 * Shown while the local detector has no match yet but the relay already knows
 * one. Without this the desktop sits on the waiting screen even though the
 * server is holding a full session — the analysis exists, it just had nowhere
 * to render.
 */
const props = defineProps<{
  sync: ReturnType<typeof useTeamSync>;
}>();

const match = computed(() => props.sync.serverMatch.value);
const players = computed(() => props.sync.serverProfiles.value);

/** A restored session is not a live one — say when it happened. */
const matchTime = computed(() => {
  const stamp = match.value?.updatedAt;
  if (!stamp) return '';
  const at = new Date(stamp);
  const sameDay = new Date().toDateString() === at.toDateString();
  return sameDay
    ? at.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : at.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
});

const SIDE_LABEL: Record<string, string> = { ct: 'CT', t: 'T' };

function sidePlayers(side: string) {
  return players.value.filter((player) => (player.team || '').toLowerCase() === side);
}

function statLine(player: (typeof players.value)[number]): string {
  const stats = player.stats || {};
  const parts: string[] = [];
  if (stats.rating != null) parts.push(`R ${Number(stats.rating).toFixed(2)}`);
  if (stats.seasonAdr != null) parts.push(`ADR ${Math.round(Number(stats.seasonAdr))}`);
  if (stats.kd != null) parts.push(`K/D ${Number(stats.kd).toFixed(2)}`);
  return parts.join(' · ') || '无数据';
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden">
    <header class="flex items-center gap-2 border-b border-border px-4 py-2">
      <span class="text-sm font-semibold text-fg">{{ match?.mapName || '服务端房间' }}</span>
      <span v-if="match?.matchId" class="text-[11px] text-fg-muted">{{ match.matchId }}</span>
      <span v-if="matchTime" class="text-[11px] text-fg-muted">· {{ matchTime }}</span>
      <span class="ml-auto rounded-full bg-accent/10 px-2 py-0.5 text-[11px] text-accent">
        {{ sync.settings.value.roomCode || '未进房' }}
      </span>
    </header>

    <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] overflow-hidden">
      <section class="min-h-0 overflow-y-auto border-r border-border px-3 py-2">
        <h4 class="mb-2 text-xs font-medium text-fg-secondary">阵容（服务端）</h4>
        <div v-if="!players.length" class="text-xs text-fg-muted">
          房间里还没有对局数据。
        </div>
        <div v-for="side in ['ct', 't']" :key="side" class="mb-3">
          <div class="mb-1 text-[11px] font-medium text-fg-muted">{{ SIDE_LABEL[side] }}</div>
          <div
            v-for="(player, index) in sidePlayers(side)"
            :key="`${side}-${index}`"
            class="flex items-baseline justify-between gap-2 py-0.5"
          >
            <span class="truncate text-[13px] text-fg">{{ player.nickname || 'Unknown' }}</span>
            <span class="shrink-0 text-[11px] text-fg-muted">{{ statLine(player) }}</span>
          </div>
          <div v-if="!sidePlayers(side).length" class="text-[11px] text-fg-muted">—</div>
        </div>
      </section>

      <section class="min-h-0 overflow-hidden">
        <ServerAnalysisPanel :sync="sync" />
      </section>
    </div>
  </div>
</template>
