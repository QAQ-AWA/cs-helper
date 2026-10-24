<script setup lang="ts">
import { computed, ref } from 'vue';
import type { MatchRecord } from '@core/match/models';
import type { P5ePostMatchReport } from '@platforms/5e/post-match';
import type { AiAnalysisResult } from '@core/ai/types';
import type { useTeamSync } from '../composables/useTeamSync';
import { useMatchCountdown } from '../composables/useMatchCountdown';
import AiAnalysisPanel from './AiAnalysisPanel.vue';
import RosterBoard from './RosterBoard.vue';
import ServerAnalysisPanel from './ServerAnalysisPanel.vue';
import TacticalPathsPanel from './TacticalPathsPanel.vue';
import PostMatchBoard from './PostMatchBoard.vue';

/**
 * One match, four questions: who is playing, what does the relay think, where
 * do they go, how did it end. Everything the client used to compute locally
 * (AI signals, column customisers, comparison boards) is gone on purpose — the
 * relay owns the analysis now.
 */
const props = defineProps<{
  match: MatchRecord;
  sync?: ReturnType<typeof useTeamSync>;
  historyMode?: boolean;
  initialPostMatch?: P5ePostMatchReport | null;
  /** 历史回放里存下来的 AI 报告（只读展示，不再调模型）。 */
  storedAi?: AiAnalysisResult | null;
  /** Deep-link / screenshot support; the app always starts on the roster. */
  initialTab?: Tab;
}>();

const emit = defineEmits<{
  postMatchUpdated: [report: P5ePostMatchReport];
}>();

type Tab = 'roster' | 'analysis' | 'paths' | 'post';
const activeTab = ref<Tab>(props.initialTab ?? 'roster');

const deadline = computed(() => props.match.detail.readyDeadlineAt);
const { timeLeftSec, isActive: countdownActive, isUrgent } = useMatchCountdown(deadline);

const mySide = computed(() => props.sync?.serverMatch.value?.mySide ?? null);
const sideSource = computed(() => props.sync?.serverMatch.value?.mySideSource ?? null);

const sideLabel = computed(() => {
  if (!mySide.value) return null;
  const source =
    sideSource.value === 'library'
      ? 'ID 库'
      : sideSource.value === 'explicit'
        ? '手动'
        : sideSource.value === 'party'
          ? '组队'
          : '';
  return `我方 ${mySide.value.toUpperCase()}${source ? ` · ${source}` : ''}`;
});

const roomCode = computed(() => props.sync?.settings.value.roomCode ?? '');

const hasAnalysis = computed(() => Boolean(props.sync?.serverMatch.value));

/** 服务端给的结构化结果；历史回放退回本地存档的那一份。 */
const aiResult = computed(() => props.sync?.serverMatch.value?.aiResult ?? props.storedAi ?? null);

const aiStatus = computed<'pending' | 'running' | 'ready' | 'failed' | 'skipped'>(() => {
  if (aiResult.value) return 'ready';
  const state = props.sync?.serverMatch.value?.aiState;
  if (state === 'running') return 'running';
  if (state === 'failed') return 'failed';
  if (state === 'skipped') return 'skipped';
  return 'pending';
});

const aiError = computed(() => props.sync?.aiError.value ?? null);
/** 老会话只有 Markdown，没有结构化结果。 */
const aiText = computed(() => props.sync?.serverMatch.value?.aiText ?? '');
const postReport = computed(
  () => props.sync?.serverMatch.value?.postReport ?? props.initialPostMatch ?? null,
);
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-hidden">
    <header class="border-b border-border px-4 pb-2 pt-3">
      <div class="flex items-baseline gap-2">
        <h2 class="text-[15px] font-semibold text-fg">
          {{ match.detail.mapName || match.summary?.mapName || '未知地图' }}
        </h2>
        <span class="truncate text-[11px] text-fg-muted">{{ match.detail.platformGameId || match.id }}</span>
      </div>

      <div class="mt-1 flex items-center gap-2 text-[11px] text-fg-muted">
        <span v-if="sideLabel">{{ sideLabel }}</span>
        <span v-if="roomCode">房间 {{ roomCode }}</span>
        <span v-if="!sync" class="text-fg-muted">历史回放</span>
        <span
          v-if="countdownActive"
          class="ml-auto rounded-full px-2 py-0.5 tabular-nums"
          :class="isUrgent ? 'bg-danger/10 text-danger' : 'bg-accent/10 text-accent'"
        >
          准备 {{ timeLeftSec }}s
        </span>
      </div>

      <nav class="mt-2 flex gap-1" role="tablist">
        <button
          v-for="tab in ([
            { id: 'roster', label: '阵容' },
            { id: 'analysis', label: '分析' },
            { id: 'paths', label: '轨迹' },
            { id: 'post', label: '赛后' },
          ] as const)"
          :key="tab.id"
          type="button"
          role="tab"
          class="cursor-pointer rounded-md px-2.5 py-1 text-[12px] font-medium transition-colors"
          :class="
            activeTab === tab.id
              ? 'bg-surface text-fg shadow-sm ring-1 ring-border'
              : 'text-fg-muted hover:text-fg-secondary'
          "
          :aria-selected="activeTab === tab.id"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>
    </header>

    <div class="min-h-0 flex-1 overflow-hidden">
      <RosterBoard
        v-if="activeTab === 'roster'"
        :teams="match.detail.teams ?? []"
        :profiles="sync?.serverProfiles.value"
        :my-side="mySide"
        :player-signals="aiResult?.playerSignals ?? []"
        :map-name="match.detail.mapName"
      />
      <AiAnalysisPanel
        v-else-if="activeTab === 'analysis' && (aiResult || hasAnalysis)"
        :result="aiResult"
        :status="aiStatus"
        :error="aiError"
        self-side="A"
        @analyze="sync?.rerunAnalysis()"
      />
      <ServerAnalysisPanel v-else-if="activeTab === 'analysis' && aiText" :sync="sync!" />
      <div
        v-else-if="activeTab === 'analysis'"
        class="flex h-full items-center justify-center px-6 text-center text-sm text-fg-muted"
      >
        这一局没有留下 AI 分析
      </div>
      <TacticalPathsPanel v-else-if="activeTab === 'paths'" />
      <PostMatchBoard
        v-else
        :match="match"
        :report="postReport"
        :history-mode="historyMode"
        @report-updated="(report) => emit('postMatchUpdated', report)"
      />
    </div>
  </div>
</template>
