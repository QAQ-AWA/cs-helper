<script setup lang="ts">
import { computed } from 'vue';
import type { AiAnalysisResult } from '@core/ai/types';

/**
 * 历史对局里存下来的那份 AI 报告，只读展示。
 *
 * 客户端已经不再跑模型（AI 在服务端），但历史文档里保留了当年那份结果；
 * 这里只负责把它渲染出来，不做任何推理或校准。
 */
const props = defineProps<{ report: AiAnalysisResult }>();

const probability = computed(() => {
  const value = props.report.winProbability;
  const a = Number(value?.A ?? 0);
  const b = Number(value?.B ?? 0);
  const total = a + b || 1;
  return { a: Math.round((a / total) * 100), b: Math.round((b / total) * 100) };
});

const winnerText = computed(() => {
  switch (props.report.predictedWinner) {
    case 'A':
      return 'A 队更被看好';
    case 'B':
      return 'B 队更被看好';
    case 'Even':
      return '势均力敌';
    default:
      return '数据不足';
  }
});

const factors = computed(() => (props.report.decisiveFactors ?? []).slice(0, 4));
const signals = computed(() => (props.report.playerSignals ?? []).slice(0, 4));
const uncertainties = computed(() => (props.report.uncertainties ?? []).slice(0, 4));
</script>

<template>
  <div class="flex h-full min-h-0 flex-col overflow-y-auto px-4 py-3">
    <header class="mb-3">
      <div class="flex items-baseline gap-2">
        <span class="text-sm font-semibold text-fg">{{ winnerText }}</span>
        <span class="text-[11px] text-fg-muted">置信度 {{ Math.round(report.confidence ?? 0) }}</span>
        <span class="ml-auto text-[11px] text-fg-muted">历史报告</span>
      </div>
      <div class="mt-2 flex h-1.5 overflow-hidden rounded-full bg-border">
        <span class="h-full bg-team-a" :style="{ width: `${probability.a}%` }" />
        <span class="h-full bg-team-b" :style="{ width: `${probability.b}%` }" />
      </div>
      <div class="mt-1 flex justify-between text-[10px] text-fg-muted">
        <span>A {{ probability.a }}%</span>
        <span>B {{ probability.b }}%</span>
      </div>
      <p v-if="report.headline" class="mt-2 text-[13px] leading-relaxed text-fg">{{ report.headline }}</p>
    </header>

    <section v-if="factors.length" class="mb-3">
      <h4 class="mb-1 text-xs font-medium text-fg-secondary">关键因素</h4>
      <div
        v-for="factor in factors"
        :key="factor.id"
        class="rounded-lg border border-border bg-surface px-3 py-2"
      >
        <div class="flex items-baseline gap-2">
          <span class="text-[12px] font-medium text-fg">{{ factor.title }}</span>
          <span class="text-[10px] text-fg-muted">
            {{ factor.advantage === 'Even' ? '均势' : `${factor.advantage} 队占优` }}
          </span>
        </div>
        <p class="mt-0.5 text-[11px] leading-relaxed text-fg-secondary">{{ factor.summary }}</p>
      </div>
    </section>

    <section v-if="signals.length" class="mb-3">
      <h4 class="mb-1 text-xs font-medium text-fg-secondary">选手信号</h4>
      <div
        v-for="signal in signals"
        :key="`${signal.steamId}-${signal.kind}`"
        class="rounded-lg border border-border bg-surface px-3 py-2"
      >
        <div class="flex items-baseline gap-2">
          <span class="text-[12px] font-medium text-fg">{{ signal.title }}</span>
          <span class="text-[10px] text-fg-muted">{{ signal.side }} 队</span>
        </div>
        <p class="mt-0.5 text-[11px] leading-relaxed text-fg-secondary">{{ signal.summary }}</p>
      </div>
    </section>

    <section v-if="uncertainties.length" class="mb-2">
      <h4 class="mb-1 text-xs font-medium text-fg-secondary">不确定项</h4>
      <ul class="space-y-0.5">
        <li v-for="(item, index) in uncertainties" :key="index" class="text-[11px] text-fg-muted">
          · {{ item }}
        </li>
      </ul>
    </section>
  </div>
</template>
