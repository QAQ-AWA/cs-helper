<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { Route } from 'lucide-vue-next';
import { teamSyncClient } from '@core/sync/sync-client';
import { ReplayPlayer } from '@shared/replay-core.js';

interface PathPlayer {
  steamId: string;
  username?: string;
  rounds: number;
  bytes?: number;
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

const activeName = computed(
  () => players.value.find((item) => item.steamId === activeSteam.value)?.username || '',
);
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
    applyIndex(await getJson(`/api/v1/artifacts/${artifact}`));
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
      radar: replay.radar,
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
    <aside class="flex w-44 shrink-0 flex-col gap-1 overflow-y-auto">
      <p v-if="!players.length" class="px-1 text-xs text-slate-500">{{ message }}</p>
      <button
        v-for="player in players"
        :key="player.steamId"
        type="button"
        class="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors"
        :class="
          activeSteam === player.steamId
            ? 'bg-white text-emerald-600 shadow-sm'
            : 'text-slate-600 hover:bg-white/60'
        "
        @click="openPlayer(player)"
      >
        <span class="min-w-0 flex-1 truncate">{{ player.username || player.steamId }}</span>
        <span class="shrink-0 text-[10px] text-slate-400">{{ player.rounds }} 回合</span>
      </button>
    </aside>

    <section class="flex min-w-0 flex-1 flex-col">
      <div v-if="!activeSteam" class="grid min-h-0 flex-1 place-items-center rounded bg-slate-50 text-xs text-slate-400">
        选择左侧选手查看开局习惯轨迹
      </div>
      <template v-else>
        <div class="mb-2 flex flex-wrap items-center gap-1.5">
          <span class="mr-auto truncate text-xs font-medium text-slate-600">{{ activeName }}</span>
          <button
            type="button"
            class="rounded bg-emerald-500 px-2.5 py-1 text-xs font-medium text-white"
            @click="togglePlay"
          >
            {{ playing ? '暂停' : '播放' }}
          </button>
          <button
            v-for="value in [1, 2, 4]"
            :key="value"
            type="button"
            class="rounded px-2 py-1 text-xs"
            :class="speed === value ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-500'"
            @click="setSpeed(value)"
          >
            {{ value }}x
          </button>
          <button
            v-for="value in (['', 'CT', 'T'] as const)"
            :key="value || 'all'"
            type="button"
            class="rounded px-2 py-1 text-xs"
            :class="side === value ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-500'"
            @click="setSide(value)"
          >
            {{ value || '全部' }}
          </button>
        </div>
        <canvas ref="canvasRef" class="min-h-0 w-full flex-1 rounded bg-slate-900" />
        <div class="mt-2 h-1 w-full overflow-hidden rounded bg-slate-200">
          <div class="h-full bg-emerald-500 transition-[width] duration-75" :style="{ width: `${progress * 100}%` }" />
        </div>
        <p v-if="status === 'error'" class="mt-1 text-xs text-rose-500">{{ message }}</p>
        <p v-else-if="status === 'loading'" class="mt-1 text-xs text-slate-400">{{ message }}</p>
        <p v-else class="mt-1 text-[11px] text-slate-400">
          <Route class="mr-1 inline h-3 w-3 align-[-2px]" aria-hidden="true" />
          路径越集中，说明该选手的开局习惯越固定；{{ canRender ? '' : '未连接服务端' }}
        </p>
      </template>
    </section>
  </div>
</template>
