<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { Route } from 'lucide-vue-next';
import { teamSyncClient } from '@core/sync/sync-client';
import { ReplayPlayer } from '@shared/replay-core.js';
import { resolveRadarUrl } from '../utils/resolve-radar-url';

interface PathReportPlayer {
  nickname: string;
  steamId?: string;
  side?: string;
  habit?: string;
  likely?: string;
  counter?: string;
}

interface PathReport {
  summary?: string;
  tempo?: string;
  sitePreference?: string;
  players?: PathReportPlayer[];
  counters?: string[];
}

const props = defineProps<{ report?: PathReport | null }>();

interface PathPlayer {
  steamId: string;
  username?: string;
  nickname?: string;
  rounds: number;
  bytes?: number;
}

/** The engine may omit `username`; fall back to the roster nickname. */
function displayName(player: PathPlayer) {
  return player.nickname || player.username || player.steamId;
}

const players = ref<PathPlayer[]>([]);
const artifactId = ref<string | null>(null);
const activeSteam = ref<string | null>(null);
const status = ref<'idle' | 'loading' | 'ready' | 'empty' | 'error'>('idle');
const message = ref('等待电脑端完成解析…');
const canvasRef = ref<HTMLCanvasElement | null>(null);
const playing = ref(true);
const speed = ref(2);
const side = ref<'' | 'CT' | 'T'>('');
const progress = ref(0);

let renderer: ReplayPlayer | null = null;
let unsubscribe: (() => void) | null = null;
let observer: ResizeObserver | null = null;

const settings = teamSyncClient.getSettings();
const baseUrl = settings.serverUrl.replace(/\/+$/, '');

const activeName = computed(() => {
  const player = players.value.find((item) => item.steamId === activeSteam.value);
  return player ? displayName(player) : '';
});
const canRender = computed(() => status.value === 'ready' && Boolean(settings.token));

function authHeaders() {
  return { Authorization: `Bearer ${settings.token}` };
}

async function getJson(path: string) {
  const response = await fetch(`${baseUrl}${path}`, { headers: authHeaders() });
  const body = await response.json().catch(() => null);
  if (!response.ok || !body || body.code !== 0) {
    throw new Error(body?.message || `请求失败 (${response.status})`);
  }
  return body.data;
}

function applyIndex(data: { artifactId?: string; players?: PathPlayer[] }) {
  if (data?.artifactId) artifactId.value = data.artifactId;
  players.value = Array.isArray(data?.players) ? data.players : [];
  status.value = players.value.length ? 'ready' : 'empty';
  message.value = players.value.length ? '' : '这批对手没有可用的历史录像';
  if (!players.value.length) teardown();
}

async function loadSnapshot() {
  if (!settings.enabled || !settings.roomCode || !settings.token) {
    status.value = 'error';
    message.value = '未连接同步服务端';
    return;
  }
  try {
    const snapshot = await getJson(`/api/v1/room/${encodeURIComponent(settings.roomCode)}/snapshot`);
    const artifact = snapshot?.match?.artifactId;
    if (!artifact) return;
    // 索引响应体里没有 artifactId（它在 URL 上），不补回去的话列表能显示、
    // 点选手却什么都不发生——重连后正是走这条路径。
    applyIndex({ ...(await getJson(`/api/v1/artifacts/${artifact}`)), artifactId: artifact });
  } catch (error) {
    status.value = 'error';
    message.value = error instanceof Error ? error.message : '加载失败';
  }
}

function teardown() {
  renderer?.destroy();
  renderer = null;
  observer?.disconnect();
  observer = null;
}

async function openPlayer(player: PathPlayer) {
  if (!artifactId.value) return;
  activeSteam.value = player.steamId;
  status.value = 'loading';
  message.value = '加载轨迹…';
  try {
    const detail = await getJson(
      `/api/v1/artifacts/${artifactId.value}/players/${encodeURIComponent(player.steamId)}`,
    );
    await nextTick();
    const canvas = canvasRef.value;
    if (!canvas) return;
    teardown();
    const replay = detail.replay || {};
    renderer = new ReplayPlayer(canvas, {
      // 产物里是 /maps/<map>/radar.png 这种服务端相对路径，桌面端页面
      // 来自 tauri://localhost，必须补上服务端地址，否则画布只有「缺少雷达图资源」。
      radar: resolveRadarUrl(replay.radar, baseUrl),
      transform: replay.transform,
      rounds: replay.rounds || [],
      autoplay: true,
      onTick: (instance) => {
        progress.value = instance.progress;
      },
    });
    renderer.setSpeed(speed.value);
    renderer.setFilter(side.value || null, null);
    playing.value = true;
    status.value = 'ready';
    message.value = '';
    observer = new ResizeObserver(() => renderer?.resize());
    observer.observe(canvas);
  } catch (error) {
    status.value = 'error';
    message.value = error instanceof Error ? error.message : '轨迹加载失败';
  }
}

function togglePlay() {
  if (!renderer) return;
  playing.value = renderer.toggle();
}

function setSpeed(value: number) {
  speed.value = value;
  renderer?.setSpeed(value);
}

function setSide(value: '' | 'CT' | 'T') {
  side.value = value;
  renderer?.setFilter(value || null, null);
}

onMounted(() => {
  void loadSnapshot();
  unsubscribe = teamSyncClient.subscribe((event, data) => {
    if (event === 'TACTICAL_PATHS_READY') applyIndex(data as { artifactId?: string; players?: PathPlayer[] });
    if (event === 'ROOM_STATE_SYNC' && (data as { match?: { artifactId?: string } })?.match?.artifactId) {
      void loadSnapshot();
    }
  });
});

onBeforeUnmount(() => {
  unsubscribe?.();
  unsubscribe = null;
  teardown();
});
</script>

<template>
  <div class="flex h-full min-h-0 gap-3 p-3">
    <aside class="flex w-48 shrink-0 flex-col gap-1 overflow-y-auto">
      <p v-if="!players.length" class="px-1 text-xs text-fg-muted">{{ message }}</p>
      <button
        v-for="player in players"
        :key="player.steamId"
        type="button"
        class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors"
        :class="
          activeSteam === player.steamId
            ? 'bg-surface text-accent shadow-sm'
            : 'text-fg-secondary hover:bg-elevated'
        "
        @click="openPlayer(player)"
      >
        <span class="min-w-0 flex-1 truncate">{{ displayName(player) }}</span>
        <span class="shrink-0 text-[10px] text-fg-muted">{{ player.rounds }} 回合</span>
      </button>
    </aside>

    <section class="flex min-w-0 flex-1 flex-col">
      <div
        v-if="!activeSteam"
        class="min-h-0 flex-1 overflow-y-auto rounded border border-border bg-surface p-4"
      >
        <template v-if="props.report">
          <div class="flex flex-wrap items-center gap-2">
            <span class="rounded bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">
              开局走位解读
            </span>
            <span v-if="props.report.tempo" class="text-[11px] text-fg-secondary">
              {{ props.report.tempo }}
            </span>
            <span v-if="props.report.sitePreference" class="text-[11px] text-fg-secondary">
              {{ props.report.sitePreference }}
            </span>
          </div>
          <p class="mt-2 text-sm font-semibold leading-relaxed text-fg">{{ props.report.summary }}</p>

          <div class="mt-3 space-y-2">
            <article
              v-for="item in props.report.players"
              :key="item.nickname"
              class="rounded-lg border border-border bg-elevated/40 px-3 py-2"
            >
              <div class="flex items-center gap-2">
                <span class="text-[13px] font-semibold text-fg">{{ item.nickname }}</span>
                <span v-if="item.side" class="rounded bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-fg-secondary">
                  {{ item.side }}
                </span>
              </div>
              <p v-if="item.habit" class="mt-1 text-[12px] leading-relaxed text-fg-secondary">{{ item.habit }}</p>
              <p v-if="item.likely" class="mt-1 text-[12px] leading-relaxed text-fg-secondary">
                <span class="text-fg-muted">大概率：</span>{{ item.likely }}
              </p>
              <p v-if="item.counter" class="mt-1 text-[12px] leading-relaxed text-accent">
                <span class="text-fg-muted">针对：</span>{{ item.counter }}
              </p>
            </article>
          </div>

          <div v-if="props.report.counters?.length" class="mt-3 rounded-lg bg-accent-soft/60 px-3 py-2">
            <p class="text-[11px] font-semibold text-accent">整队对策</p>
            <ul class="mt-1 list-disc space-y-0.5 pl-4">
              <li v-for="line in props.report.counters" :key="line" class="text-[12px] text-fg-secondary">
                {{ line }}
              </li>
            </ul>
          </div>
        </template>
        <div v-else class="grid h-full place-items-center text-xs text-fg-muted">
          选择左侧选手查看开局习惯轨迹；AI 走位解读会在解析完成后自动生成
        </div>
      </div>
      <template v-else>
        <div class="mb-2 flex flex-wrap items-center gap-1.5">
          <span class="mr-auto truncate text-xs font-medium text-fg-secondary">{{ activeName }}</span>
          <button
            type="button"
            class="rounded bg-accent px-2.5 py-1 text-xs font-medium text-white"
            @click="togglePlay"
          >
            {{ playing ? '暂停' : '播放' }}
          </button>
          <button
            v-for="value in [1, 2, 4]"
            :key="value"
            type="button"
            class="rounded px-2 py-1 text-xs"
            :class="speed === value ? 'bg-surface text-fg shadow-sm' : 'text-fg-muted'"
            @click="setSpeed(value)"
          >
            {{ value }}x
          </button>
          <button
            v-for="value in (['', 'CT', 'T'] as const)"
            :key="value || 'all'"
            type="button"
            class="rounded px-2 py-1 text-xs"
            :class="side === value ? 'bg-surface text-fg shadow-sm' : 'text-fg-muted'"
            @click="setSide(value)"
          >
            {{ value || '全部' }}
          </button>
        </div>
        <canvas ref="canvasRef" class="min-h-0 w-full flex-1 rounded bg-slate-900" />
        <div class="mt-2 h-1 w-full overflow-hidden rounded bg-border">
          <div class="h-full bg-accent transition-[width] duration-75" :style="{ width: `${progress * 100}%` }" />
        </div>
        <p v-if="status === 'error'" class="mt-1 text-xs text-danger">{{ message }}</p>
        <p v-else-if="status === 'loading'" class="mt-1 text-xs text-fg-muted">{{ message }}</p>
        <p v-else class="mt-1 text-[11px] text-fg-muted">
          <Route class="mr-1 inline h-3 w-3 align-[-2px]" aria-hidden="true" />
          路径越集中，说明该选手的开局习惯越固定；{{ canRender ? '' : '未连接服务端' }}
        </p>
      </template>
    </section>
  </div>
</template>
