<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { RefreshCw } from 'lucide-vue-next';
import type { MatchRecord } from '@core/match/models';
import { fetch5eMatchDetail } from '@core/platform/5e';
import {
  parseP5ePostMatchReport,
  resolveMatchCode,
  type P5ePostMatchReport,
} from '@platforms/5e/post-match';
import { teamSyncClient } from '@core/sync/sync-client';
import { openExternalUrl } from '../native';

/**
 * 赛后页。
 *
 * 桌面端仍然是「拉取方」——服务端不重复抓 5E（见 HANDOFF 决策 5）。拿到战报后
 * 一边本地渲染，一边 `reportPostMatch` 推到服务端，手机端和重连的客户端都能看到。
 */
const props = defineProps<{
  match: MatchRecord;
  /** 服务端已有的战报（重连/别人拉过），优先展示。 */
  report?: P5ePostMatchReport | null;
  historyMode?: boolean;
}>();

const emit = defineEmits<{
  reportUpdated: [report: P5ePostMatchReport];
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const local = ref<P5ePostMatchReport | null>(props.report ?? null);

watch(
  () => props.report,
  (next) => {
    if (next) local.value = next;
  },
);

const matchCode = computed(() => resolveMatchCode(props.match));

const sides = computed(() => {
  const players = local.value?.players ?? [];
  return [
    { key: 'A' as const, label: 'A 队', rows: players.filter((p) => p.teamSide === 1) },
    { key: 'B' as const, label: 'B 队', rows: players.filter((p) => p.teamSide === 2) },
  ].map((side) => ({
    ...side,
    rows: [...side.rows].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0)),
  }));
});

const scoreLine = computed(() => {
  const value = local.value;
  if (!value) return '';
  return `${value.scoreA ?? 0} : ${value.scoreB ?? 0}`;
});

const winnerText = computed(() => {
  const side = local.value?.winnerSide;
  if (!side) return '';
  return side === 'Draw' ? '平局' : `${side} 队胜`;
});

const halfText = computed(() => {
  const half = local.value?.halfScores;
  if (!half) return '';
  return `半场 ${half.fhA}:${half.fhB} · ${half.shA}:${half.shB}`;
});

const comparisonText = computed(() => {
  const cmp = local.value?.comparison;
  if (!cmp) return '';
  if (cmp.headline) return cmp.headline;
  if (cmp.isCorrect === true) return 'AI 预测命中';
  if (cmp.isCorrect === false) return 'AI 预测落空';
  return '';
});

async function load(force = false) {
  const code = matchCode.value;
  if (!code) {
    error.value = '缺少对局代码，无法拉取战报';
    return;
  }
  if (!force && local.value?.isFinished) return;

  loading.value = true;
  error.value = null;
  try {
    const raw = await fetch5eMatchDetail(code);
    const parsed = parseP5ePostMatchReport(raw, null);
    if (!parsed) {
      error.value = '还没解析到赛后数据，对局可能尚未结束或数据未入库';
      return;
    }
    local.value = parsed;
    emit('reportUpdated', parsed);
    // 归档到服务端：手机端、重连的客户端都靠这份。
    void teamSyncClient.reportPostMatch(parsed).catch(() => undefined);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function openDemo() {
  const url = local.value?.demoUrl;
  if (url) void openExternalUrl(url);
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-y-auto px-4 py-3">
    <div v-if="!local" class="flex h-full flex-col items-center justify-center gap-3 text-center">
      <p class="text-sm text-fg-secondary">还没有这一局的战报</p>
      <p v-if="error" class="max-w-md text-xs text-danger">{{ error }}</p>
      <button
        type="button"
        class="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        :disabled="loading"
        @click="load(true)"
      >
        <RefreshCw class="h-3.5 w-3.5" :class="loading ? 'animate-spin' : ''" />
        {{ loading ? '拉取中…' : '拉取战报' }}
      </button>
    </div>

    <template v-else>
      <header class="mb-3 flex flex-wrap items-baseline gap-3">
        <span class="text-2xl font-semibold tabular-nums text-fg">{{ scoreLine }}</span>
        <span v-if="winnerText" class="text-xs font-medium text-fg-secondary">{{ winnerText }}</span>
        <span v-if="halfText" class="text-[11px] text-fg-muted">{{ halfText }}</span>
        <span class="text-[11px] text-fg-muted">{{ local.roundTotal || 0 }} 回合</span>
        <div class="ml-auto flex items-center gap-2">
          <button
            v-if="local.demoUrl"
            type="button"
            class="cursor-pointer rounded-md border border-border px-2 py-1 text-[11px] text-fg-secondary hover:text-fg"
            @click="openDemo"
          >
            下载 Demo
          </button>
          <button
            type="button"
            class="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-fg-secondary hover:text-fg disabled:opacity-50"
            :disabled="loading"
            @click="load(true)"
          >
            <RefreshCw class="h-3 w-3" :class="loading ? 'animate-spin' : ''" />
            刷新
          </button>
        </div>
      </header>

      <div class="grid grid-cols-2 gap-3">
        <section
          v-for="side in sides"
          :key="side.key"
          class="self-start rounded-lg border border-border bg-surface"
        >
          <header class="border-b border-border px-3 py-2">
            <div class="flex items-baseline justify-between">
              <span class="text-xs font-semibold" :class="side.key === 'A' ? 'text-team-a' : 'text-team-b'">
                {{ side.label }}
              </span>
              <span class="text-[10px] text-fg-muted">K/D/A · Rating · ADR</span>
            </div>
          </header>

          <div v-if="!side.rows.length" class="px-3 py-3 text-xs text-fg-muted">暂无数据</div>

          <div
            v-for="player in side.rows"
            :key="player.uid"
            class="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-2 px-3 py-1.5 text-[12px] odd:bg-elevated/40"
          >
            <span class="flex min-w-0 items-baseline gap-1">
              <span class="truncate text-fg">{{ player.nickname }}</span>
              <span v-if="player.isMvp" class="rounded bg-warning/15 px-1 text-[10px] text-warning">MVP</span>
              <span v-else-if="player.isSvp" class="rounded bg-accent/10 px-1 text-[10px] text-accent">SVP</span>
            </span>
            <span class="flex shrink-0 items-baseline gap-2 tabular-nums text-fg-secondary">
              <span class="w-14 text-right">{{ player.kill }}/{{ player.death }}/{{ player.assist }}</span>
              <span class="w-9 text-right font-medium text-fg">{{ (player.rating ?? 0).toFixed(2) }}</span>
              <span class="w-9 text-right">{{ Math.round(player.adr ?? 0) }}</span>
            </span>
          </div>
        </section>
      </div>

      <p v-if="comparisonText" class="mt-3 text-[11px] text-fg-muted">{{ comparisonText }}</p>
      <p v-if="error" class="mt-2 text-[11px] text-danger">{{ error }}</p>
    </template>
  </div>
</template>
