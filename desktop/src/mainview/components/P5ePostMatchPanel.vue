<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue';
import {
  CheckCircle2,
  Clock,
  Copy,
  Download,
  ExternalLink,
  Flame,
  Medal,
  RefreshCw,
  Trophy,
  XCircle,
} from 'lucide-vue-next';
import type { MatchRecord } from '@core/match/models';
import { fetch5eMatchDetail } from '@core/platform/5e';
import {
  parseP5ePostMatchReport,
  resolveMatchCode,
  type P5ePostMatchPlayerStat,
  type P5ePostMatchReport,
} from '@platforms/5e/post-match';
import type { useAiAnalysis } from '../composables/useAiAnalysis';
import { openExternalUrl } from '../native';
import PlayerAvatar from './PlayerAvatar.vue';

const props = defineProps<{
  match: MatchRecord;
  ai?: ReturnType<typeof useAiAnalysis>;
  initialReport?: P5ePostMatchReport | null;
  historyMode?: boolean;
}>();

const emit = defineEmits<{
  reportUpdated: [report: P5ePostMatchReport];
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const report = ref<P5ePostMatchReport | null>(props.initialReport ?? null);
const copySuccess = ref(false);

const matchCode = computed(() => resolveMatchCode(props.match));

const teamAPlayers = computed(() =>
  (report.value?.players ?? [])
    .filter((p) => p.teamSide === 1)
    .sort((a, b) => b.rating - a.rating),
);

const teamBPlayers = computed(() =>
  (report.value?.players ?? [])
    .filter((p) => p.teamSide === 2)
    .sort((a, b) => b.rating - a.rating),
);

const aiResult = computed(() => props.ai?.result.value);

async function loadPostMatch(force = false) {
  const code = matchCode.value;
  if (!code) {
    error.value = '未找到有效的对局代码 (match_code)，无法拉取战报';
    return;
  }

  if (!force && report.value && report.value.isFinished) {
    return;
  }

  loading.value = true;
  error.value = null;

  try {
    const raw = await fetch5eMatchDetail(code);
    const parsed = parseP5ePostMatchReport(raw, aiResult.value);
    if (!parsed) {
      error.value = '未能解析到赛后数据，对局可能未开始或数据尚未入库';
      return;
    }
    report.value = parsed;
    emit('reportUpdated', parsed);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.initialReport,
  (newVal) => {
    if (newVal) {
      report.value = newVal;
    }
  },
  { immediate: true },
);

watch(
  () => props.match.id,
  () => {
    if (!props.initialReport) {
      void loadPostMatch();
    }
  },
);

onMounted(() => {
  if (!report.value) {
    void loadPostMatch();
  }
});

function copyDemoLink(url: string) {
  void navigator.clipboard.writeText(url);
  copySuccess.value = true;
  setTimeout(() => {
    copySuccess.value = false;
  }, 2000);
}

function ratingColorClass(rating: number) {
  if (rating >= 1.25) return 'text-emerald-600 font-bold';
  if (rating >= 1.05) return 'text-blue-600 font-semibold';
  if (rating < 0.85) return 'text-rose-500 font-medium';
  return 'text-slate-700';
}

function kdDiff(k: number, d: number) {
  const diff = k - d;
  return diff > 0 ? `+${diff}` : `${diff}`;
}

function formatFetchedTime(ts?: number) {
  if (!ts) return '';
  const date = new Date(ts);
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
}
</script>

<template>
  <div class="h-full overflow-y-auto px-4 py-4 space-y-4">
    <!-- Header / Scoreboard Card -->
    <div
      class="relative overflow-hidden rounded-2xl border border-slate-200 bg-linear-to-b from-white to-slate-50 p-5 shadow-xs"
    >
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/80 pb-3">
        <div class="flex items-center gap-2">
          <span
            class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold tracking-wide"
            :class="
              report?.isFinished
                ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                : 'bg-amber-50 text-amber-700 ring-1 ring-amber-200'
            "
          >
            <Trophy class="h-3.5 w-3.5" />
            {{ report?.isFinished ? '比赛已完结' : '对局结算中 / 进行中' }}
          </span>
          <span class="text-xs text-slate-500">
            地图：<strong class="text-slate-800">{{ report?.mapDesc || report?.mapName || '未知' }}</strong>
          </span>
          <span v-if="report?.roundTotal" class="text-xs text-slate-400">
            · 共 {{ report.roundTotal }} 回合
          </span>
          <span v-if="report?.durationMinutes" class="text-xs text-slate-400">
            · 耗时 {{ report.durationMinutes }} 分钟
          </span>
        </div>

        <div class="flex items-center gap-2">
          <span v-if="report?.fetchedAt" class="text-[11px] text-slate-400">
            {{ formatFetchedTime(report.fetchedAt) }} 更新
          </span>
          <button
            type="button"
            :disabled="loading"
            class="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-2xs hover:bg-slate-50 active:scale-95 disabled:opacity-50"
            @click="loadPostMatch(true)"
          >
            <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
            {{ loading ? '拉取中...' : '刷新战报' }}
          </button>
        </div>
      </div>

      <!-- Scoreboard Display -->
      <div class="py-6 flex items-center justify-around">
        <!-- Team A -->
        <div class="flex flex-col items-center space-y-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-bold text-blue-600">A 队</span>
            <span
              v-if="report?.winnerSide === 'A'"
              class="rounded bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white shadow-2xs"
            >
              胜利
            </span>
            <span
              v-else-if="report?.winnerSide === 'B'"
              class="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600"
            >
              败北
            </span>
          </div>
          <div class="text-5xl font-black tracking-tight text-blue-600 tabular-nums">
            {{ report?.scoreA ?? '-' }}
          </div>
          <div v-if="report?.halfScores" class="text-[11px] text-slate-500 font-medium">
            上半场 {{ report.halfScores.fhA }} | 下半场 {{ report.halfScores.shA }}
          </div>
        </div>

        <!-- VS Divider -->
        <div class="flex flex-col items-center justify-center space-y-1">
          <span class="text-xs font-black uppercase tracking-widest text-slate-400">VS</span>
          <div class="h-8 w-px bg-slate-200"></div>
          <span class="text-[11px] font-semibold text-slate-400">
            {{ report?.roundTotal ? `${report.roundTotal} 回合` : 'BO1' }}
          </span>
        </div>

        <!-- Team B -->
        <div class="flex flex-col items-center space-y-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-bold text-orange-600">B 队</span>
            <span
              v-if="report?.winnerSide === 'B'"
              class="rounded bg-emerald-500 px-1.5 py-0.5 text-[10px] font-bold text-white shadow-2xs"
            >
              胜利
            </span>
            <span
              v-else-if="report?.winnerSide === 'A'"
              class="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium text-slate-600"
            >
              败北
            </span>
          </div>
          <div class="text-5xl font-black tracking-tight text-orange-600 tabular-nums">
            {{ report?.scoreB ?? '-' }}
          </div>
          <div v-if="report?.halfScores" class="text-[11px] text-slate-500 font-medium">
            上半场 {{ report.halfScores.fhB }} | 下半场 {{ report.halfScores.shB }}
          </div>
        </div>
      </div>

      <!-- Demo Download Banner if available -->
      <div
        v-if="report?.demoUrl"
        class="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-100/80 px-3.5 py-2 text-xs text-slate-600"
      >
        <div class="flex items-center gap-2">
          <Download class="h-4 w-4 text-blue-600" />
          <span>官方 Demo 录像已生成：可下载后在游戏内复盘观战</span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex cursor-pointer items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
            @click="copyDemoLink(report.demoUrl!)"
          >
            <Copy class="h-3 w-3" />
            {{ copySuccess ? '已复制！' : '复制 Demo 链接' }}
          </button>
          <button
            type="button"
            class="inline-flex cursor-pointer items-center gap-1 rounded-md bg-blue-600 px-2.5 py-1 text-xs font-semibold text-white shadow-2xs hover:bg-blue-700"
            @click="openExternalUrl(report.demoUrl!)"
          >
            <ExternalLink class="h-3 w-3" />
            浏览器下载
          </button>
        </div>
      </div>
    </div>

    <!-- AI 预测复盘卡片 -->
    <div
      v-if="report?.comparison || (report?.isFinished && aiResult)"
      class="rounded-xl border p-4 shadow-2xs transition-all"
      :class="
        report?.comparison?.isCorrect === true
          ? 'border-emerald-200 bg-emerald-50/50'
          : report?.comparison?.isCorrect === false
            ? 'border-rose-200 bg-rose-50/50'
            : 'border-indigo-100 bg-indigo-50/40'
      "
    >
      <div class="flex items-start justify-between gap-3">
        <div class="space-y-1">
          <div class="flex items-center gap-2">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">
              AI 赛前预测复盘
            </span>
            <span
              v-if="report?.comparison?.isCorrect === true"
              class="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2 py-0.5 text-xs font-bold text-white shadow-2xs"
            >
              <CheckCircle2 class="h-3.5 w-3.5" />
              预测命中！
            </span>
            <span
              v-else-if="report?.comparison?.isCorrect === false"
              class="inline-flex items-center gap-1 rounded-md bg-rose-600 px-2 py-0.5 text-xs font-bold text-white shadow-2xs"
            >
              <XCircle class="h-3.5 w-3.5" />
              爆冷逆转
            </span>
          </div>

          <p class="text-xs text-slate-700 leading-relaxed">
            赛前 AI 给出的胜率预估为：
            <strong class="text-blue-600 font-semibold">A 队 {{ report?.comparison?.winProbA ?? aiResult?.winProbability?.A }}%</strong>
            vs
            <strong class="text-orange-600 font-semibold">B 队 {{ report?.comparison?.winProbB ?? aiResult?.winProbability?.B }}%</strong>，
            实际最终比分为
            <strong class="text-slate-900 font-bold">{{ report?.scoreA }} : {{ report?.scoreB }}</strong>
            （{{ report?.winnerSide === 'A' ? 'A 队获胜' : report?.winnerSide === 'B' ? 'B 队获胜' : '平局' }}）。
          </p>

          <p
            v-if="report?.comparison?.headline || aiResult?.headline"
            class="text-[11px] italic text-slate-500"
          >
            "{{ report?.comparison?.headline || aiResult?.headline }}"
          </p>
        </div>
      </div>
    </div>

    <!-- Error notice -->
    <div
      v-if="error"
      class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700"
    >
      {{ error }}
    </div>

    <!-- Loading skeleton -->
    <div
      v-if="loading && !report"
      class="flex h-32 items-center justify-center rounded-2xl border border-slate-200 bg-white"
    >
      <div class="flex items-center gap-2 text-xs font-medium text-slate-500">
        <RefreshCw class="h-4 w-4 animate-spin text-blue-600" />
        正在从 5E 网关拉取最新对局战报...
      </div>
    </div>

    <!-- Player Stats Tables -->
    <template v-if="report && report.players.length > 0">
      <!-- Team A Players -->
      <div class="rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-200 bg-blue-50/50 px-4 py-2.5">
          <div class="flex items-center gap-2">
            <span class="inline-block h-3 w-1 rounded-full bg-blue-600"></span>
            <span class="text-xs font-bold text-blue-700">A 队赛后数据</span>
            <span class="text-xs text-slate-500">({{ teamAPlayers.length }} 人)</span>
          </div>
          <span class="text-xs font-semibold text-blue-600 tabular-nums">
            比分: {{ report.scoreA }}
          </span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500 border-b border-slate-200/80">
              <tr>
                <th class="py-2.5 pl-4 pr-2">选手</th>
                <th class="px-2 py-2.5 text-center">Rating</th>
                <th class="px-2 py-2.5 text-center">K / D / A</th>
                <th class="px-2 py-2.5 text-center">差值</th>
                <th class="px-2 py-2.5 text-center">ADR</th>
                <th class="px-2 py-2.5 text-center">RWS</th>
                <th class="px-2 py-2.5 text-center">爆头率</th>
                <th class="px-2 py-2.5 text-center">首杀/首死</th>
                <th class="py-2.5 pl-2 pr-4 text-right">天梯分变动</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                v-for="p in teamAPlayers"
                :key="p.uid"
                class="hover:bg-slate-50/80 transition-colors"
                :class="{ 'bg-amber-50/30': p.isMvp, 'bg-purple-50/20': p.isSvp }"
              >
                <!-- Player Avatar & Name -->
                <td class="py-2.5 pl-4 pr-2">
                  <div class="flex items-center gap-2">
                    <PlayerAvatar :src="p.avatar" :alt="p.nickname" size="sm" />
                    <div class="flex flex-col">
                      <div class="flex items-center gap-1.5">
                        <span class="font-bold text-slate-800">{{ p.nickname }}</span>
                        <span
                          v-if="p.isMvp"
                          class="inline-flex items-center gap-0.5 rounded bg-amber-100 px-1 py-px text-[10px] font-bold text-amber-800"
                          title="本场 MVP"
                        >
                          <Medal class="h-3 w-3 text-amber-600" /> MVP
                        </span>
                        <span
                          v-else-if="p.isSvp"
                          class="inline-flex items-center gap-0.5 rounded bg-purple-100 px-1 py-px text-[10px] font-bold text-purple-800"
                          title="败方 SVP"
                        >
                          SVP
                        </span>
                      </div>
                      <span v-if="p.currElo" class="text-[10px] text-slate-400">
                        ELO: {{ p.currElo }}
                      </span>
                    </div>
                  </div>
                </td>

                <!-- Rating -->
                <td class="px-2 py-2.5 text-center tabular-nums">
                  <span :class="ratingColorClass(p.rating2 ?? p.rating)">
                    {{ (p.rating2 ?? p.rating).toFixed(2) }}
                  </span>
                </td>

                <!-- K / D / A -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-700 font-medium">
                  {{ p.kill }} / {{ p.death }} / {{ p.assist }}
                </td>

                <!-- K-D Diff -->
                <td class="px-2 py-2.5 text-center tabular-nums">
                  <span
                    class="font-semibold"
                    :class="p.kill >= p.death ? 'text-emerald-600' : 'text-rose-500'"
                  >
                    {{ kdDiff(p.kill, p.death) }}
                  </span>
                </td>

                <!-- ADR -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-700">
                  {{ p.adr }}
                </td>

                <!-- RWS -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  {{ p.rws ?? '-' }}
                </td>

                <!-- Headshot Rate -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  {{ p.headshotRate != null ? `${Math.round(p.headshotRate * 100)}%` : '-' }}
                </td>

                <!-- First Kill / Death -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  <span class="text-emerald-600 font-medium">{{ p.firstKill ?? 0 }}</span>
                  /
                  <span class="text-rose-500 font-medium">{{ p.firstDeath ?? 0 }}</span>
                </td>

                <!-- ELO change -->
                <td class="py-2.5 pl-2 pr-4 text-right tabular-nums">
                  <span
                    v-if="p.eloChange != null"
                    class="font-bold text-xs"
                    :class="p.eloChange > 0 ? 'text-emerald-600' : p.eloChange < 0 ? 'text-rose-500' : 'text-slate-400'"
                  >
                    {{ p.eloChange > 0 ? `+${p.eloChange}` : `${p.eloChange}` }}
                  </span>
                  <span v-else class="text-slate-300">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Team B Players -->
      <div class="rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden">
        <div class="flex items-center justify-between border-b border-slate-200 bg-orange-50/50 px-4 py-2.5">
          <div class="flex items-center gap-2">
            <span class="inline-block h-3 w-1 rounded-full bg-orange-600"></span>
            <span class="text-xs font-bold text-orange-700">B 队赛后数据</span>
            <span class="text-xs text-slate-500">({{ teamBPlayers.length }} 人)</span>
          </div>
          <span class="text-xs font-semibold text-orange-600 tabular-nums">
            比分: {{ report.scoreB }}
          </span>
        </div>

        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 text-[11px] font-semibold text-slate-500 border-b border-slate-200/80">
              <tr>
                <th class="py-2.5 pl-4 pr-2">选手</th>
                <th class="px-2 py-2.5 text-center">Rating</th>
                <th class="px-2 py-2.5 text-center">K / D / A</th>
                <th class="px-2 py-2.5 text-center">差值</th>
                <th class="px-2 py-2.5 text-center">ADR</th>
                <th class="px-2 py-2.5 text-center">RWS</th>
                <th class="px-2 py-2.5 text-center">爆头率</th>
                <th class="px-2 py-2.5 text-center">首杀/首死</th>
                <th class="py-2.5 pl-2 pr-4 text-right">天梯分变动</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <tr
                v-for="p in teamBPlayers"
                :key="p.uid"
                class="hover:bg-slate-50/80 transition-colors"
                :class="{ 'bg-amber-50/30': p.isMvp, 'bg-purple-50/20': p.isSvp }"
              >
                <!-- Player Avatar & Name -->
                <td class="py-2.5 pl-4 pr-2">
                  <div class="flex items-center gap-2">
                    <PlayerAvatar :src="p.avatar" :alt="p.nickname" size="sm" />
                    <div class="flex flex-col">
                      <div class="flex items-center gap-1.5">
                        <span class="font-bold text-slate-800">{{ p.nickname }}</span>
                        <span
                          v-if="p.isMvp"
                          class="inline-flex items-center gap-0.5 rounded bg-amber-100 px-1 py-px text-[10px] font-bold text-amber-800"
                          title="本场 MVP"
                        >
                          <Medal class="h-3 w-3 text-amber-600" /> MVP
                        </span>
                        <span
                          v-else-if="p.isSvp"
                          class="inline-flex items-center gap-0.5 rounded bg-purple-100 px-1 py-px text-[10px] font-bold text-purple-800"
                          title="败方 SVP"
                        >
                          SVP
                        </span>
                      </div>
                      <span v-if="p.currElo" class="text-[10px] text-slate-400">
                        ELO: {{ p.currElo }}
                      </span>
                    </div>
                  </div>
                </td>

                <!-- Rating -->
                <td class="px-2 py-2.5 text-center tabular-nums">
                  <span :class="ratingColorClass(p.rating2 ?? p.rating)">
                    {{ (p.rating2 ?? p.rating).toFixed(2) }}
                  </span>
                </td>

                <!-- K / D / A -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-700 font-medium">
                  {{ p.kill }} / {{ p.death }} / {{ p.assist }}
                </td>

                <!-- K-D Diff -->
                <td class="px-2 py-2.5 text-center tabular-nums">
                  <span
                    class="font-semibold"
                    :class="p.kill >= p.death ? 'text-emerald-600' : 'text-rose-500'"
                  >
                    {{ kdDiff(p.kill, p.death) }}
                  </span>
                </td>

                <!-- ADR -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-700">
                  {{ p.adr }}
                </td>

                <!-- RWS -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  {{ p.rws ?? '-' }}
                </td>

                <!-- Headshot Rate -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  {{ p.headshotRate != null ? `${Math.round(p.headshotRate * 100)}%` : '-' }}
                </td>

                <!-- First Kill / Death -->
                <td class="px-2 py-2.5 text-center tabular-nums text-slate-500">
                  <span class="text-emerald-600 font-medium">{{ p.firstKill ?? 0 }}</span>
                  /
                  <span class="text-rose-500 font-medium">{{ p.firstDeath ?? 0 }}</span>
                </td>

                <!-- ELO change -->
                <td class="py-2.5 pl-2 pr-4 text-right tabular-nums">
                  <span
                    v-if="p.eloChange != null"
                    class="font-bold text-xs"
                    :class="p.eloChange > 0 ? 'text-emerald-600' : p.eloChange < 0 ? 'text-rose-500' : 'text-slate-400'"
                  >
                    {{ p.eloChange > 0 ? `+${p.eloChange}` : `${p.eloChange}` }}
                  </span>
                  <span v-else class="text-slate-300">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
