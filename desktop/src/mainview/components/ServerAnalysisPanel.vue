<script setup lang="ts">
import { computed } from 'vue';
import type { useTeamSync } from '../composables/useTeamSync';

const props = defineProps<{
  sync: ReturnType<typeof useTeamSync>;
}>();

const match = computed(() => props.sync.serverMatch.value);
const aiText = computed(
  () => match.value?.aiText || props.sync.aiStreamChunk.value || '',
);
const tacticsText = computed(
  () => match.value?.tacticsText || props.sync.tacticsStream.value || '',
);
const mySide = computed(() => match.value?.mySide ?? null);

/** Why the tactics card is empty — "skipped" must not read as "still working". */
const tacticsPlaceholder = computed(() => {
  const value = match.value;
  if (!value) return '';
  if (value.tacticsState === 'skipped') {
    return value.aiState === 'skipped' ? '服务端未配置 AI key，只提供数据' : '这次没有可分析的轨迹';
  }
  if (value.tacticsState === 'running') return '正在读对面的开局轨迹…';
  if (value.tacticsState === 'failed') return '开局预判生成失败，可稍后重试';
  if (value.demoState === 'ready') return '等待服务端生成…';
  if (value.demoState === 'running') return '轨迹解析中，完成后自动生成（首次 1–3 分钟）';
  return '轨迹就绪后自动生成';
});

const analysisPlaceholder = computed(() => {
  const value = match.value;
  if (!value) return '';
  if (value.aiState === 'skipped') return '服务端未配置 AI key，只提供数据';
  if (value.aiState === 'running') return 'AI 正在生成战术分析…';
  if (value.aiState === 'failed') return '战术分析生成失败';
  return '等待服务端生成…';
});

const SIDE_LABEL: Record<string, string> = { ct: 'CT', t: 'T' };

const sourceHint = computed(() => {
  switch (match.value?.mySideSource) {
    case 'library':
      return 'ID 库自动判断';
    case 'explicit':
      return '手动选择';
    case 'explicit-all':
      return '手动选择：分析双方';
    case 'self':
      return '按本机玩家判断';
    case 'party':
      return '按组队标记判断';
    default:
      return '未选择时十人全下';
  }
});

interface Chip {
  label: string;
  state: string;
}

const chips = computed<Chip[]>(() => {
  const value = match.value;
  if (!value) return [];
  return [
    { label: '画像', state: value.profileState ?? 'pending' },
    { label: '赛季', state: value.homeState ?? 'pending' },
    { label: '轨迹', state: value.demoState ?? 'pending' },
    { label: '战术', state: value.aiState ?? 'pending' },
    { label: '开局', state: value.tacticsState ?? 'pending' },
  ];
});

function chipClass(state: string): string {
  if (state === 'ready') return 'bg-success/10 text-success';
  if (state === 'running') return 'bg-accent/10 text-accent';
  if (state === 'partial') return 'bg-warning/10 text-warning';
  if (state === 'signature') return 'bg-warning/10 text-warning';
  if (state === 'failed') return 'bg-danger/10 text-danger';
  if (state === 'skipped') return 'bg-muted text-fg-muted';
  return 'bg-muted text-fg-secondary';
}

function chipText(state: string): string {
  switch (state) {
    case 'ready':
      return '就绪';
    case 'running':
      return '进行中';
    case 'partial':
      return '部分';
    case 'signature':
      return '签名失效';
    case 'failed':
      return '失败';
    case 'skipped':
      return '跳过';
    default:
      return '等待';
  }
}

/** Escape first, then a minimal Markdown subset — the model only emits these. */
function renderMarkdown(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escaped
    .replace(/^#{1,4}\s*(.+)$/gm, '<div class="md-h">$1</div>')
    .replace(/^[-*]\s+(.+)$/gm, '<div class="md-li">$1</div>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n{2,}/g, '<div class="md-gap"></div>')
    .replace(/\n/g, '<br>');
}

function choose(side: 'ct' | 't' | null) {
  void props.sync.setAnalysisSide(side);
}
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-y-auto px-4 py-3">
    <div v-if="!match" class="flex h-full items-center justify-center text-sm text-fg-muted">
      等待电脑端上报对局…
    </div>

    <template v-else>
      <header class="mb-3 flex flex-wrap items-center gap-2">
        <h3 class="text-sm font-semibold text-fg">服务端分析</h3>
        <span
          v-for="chip in chips"
          :key="chip.label"
          class="rounded-full px-2 py-0.5 text-[11px] leading-4"
          :class="chipClass(chip.state)"
        >
          {{ chip.label }} · {{ chipText(chip.state) }}
        </span>
      </header>

      <section class="mb-3 rounded-lg border border-border bg-surface px-3 py-2">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs text-fg-secondary">我方</span>
          <button
            v-for="side in (['ct', 't'] as const)"
            :key="side"
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition-colors"
            :class="
              mySide === side
                ? 'bg-accent text-white'
                : 'bg-muted text-fg-secondary hover:bg-border'
            "
            :disabled="sync.sideBusy.value"
            @click="choose(side)"
          >
            {{ SIDE_LABEL[side] }}
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1 text-xs transition-colors"
            :class="
              mySide === null && match.mySideSource === 'explicit-all'
                ? 'bg-accent text-white'
                : 'bg-muted text-fg-secondary hover:bg-border'
            "
            :disabled="sync.sideBusy.value"
            @click="choose(null)"
          >
            都看
          </button>
          <span class="text-[11px] text-fg-muted">{{ sourceHint }}</span>
        </div>
        <p v-if="sync.sideError.value" class="mt-1 text-[11px] text-danger">
          {{ sync.sideError.value }}
        </p>
      </section>

      <section class="mb-3 rounded-lg border border-border bg-surface px-3 py-2">
        <h4 class="mb-1 text-xs font-medium text-fg-secondary">战术分析</h4>
        <div
          v-if="aiText"
          class="md-body text-[13px] leading-relaxed text-fg"
          v-html="renderMarkdown(aiText)"
        />
        <p v-else class="text-xs text-fg-muted">{{ analysisPlaceholder }}</p>
      </section>

      <section class="mb-3 rounded-lg border border-border bg-surface px-3 py-2">
        <h4 class="mb-1 text-xs font-medium text-fg-secondary">开局预判</h4>
        <div
          v-if="tacticsText"
          class="md-body text-[13px] leading-relaxed text-fg"
          v-html="renderMarkdown(tacticsText)"
        />
        <p v-else class="text-xs text-fg-muted">{{ tacticsPlaceholder }}</p>
      </section>

      <p v-if="match.homeError" class="text-[11px] text-warning">{{ match.homeError }}</p>
      <p v-else-if="match.homeState === 'partial'" class="text-[11px] text-fg-muted">
        赛季数据补全 {{ match.homeCoverage ?? 0 }} 人，其余用客户端上报值
      </p>
    </template>
  </div>
</template>

<style scoped>
.md-body :deep(.md-h) {
  margin: 10px 0 4px;
  font-weight: 600;
  color: var(--color-fg);
}
.md-body :deep(.md-h:first-child) {
  margin-top: 0;
}
.md-body :deep(.md-li) {
  padding-left: 12px;
  position: relative;
}
.md-body :deep(.md-li::before) {
  content: '·';
  position: absolute;
  left: 3px;
  color: var(--color-fg-muted);
}
.md-body :deep(.md-gap) {
  height: 6px;
}
</style>
