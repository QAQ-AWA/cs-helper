<script setup lang="ts">
import { computed } from 'vue';
import type { MatchRecord } from '@core/match/models';
import type { WatcherStatus } from '@core/types';
import type { PlatformId } from '@platforms/types';
import type { useAiAnalysis } from '../composables/useAiAnalysis';
import type { useComments } from '../composables/useComments';
import type { useMatchHistory } from '../composables/useMatchHistory';
import type { useP5eCdp } from '../composables/useP5eCdp';
import type { useTeamSync } from '../composables/useTeamSync';
import type { P5ePostMatchReport } from '@platforms/5e/post-match';
import MatchEmptyState from '../components/MatchEmptyState.vue';
import MatchWorkspace from '../components/MatchWorkspace.vue';
import ServerRoomPanel from '../components/ServerRoomPanel.vue';

const props = defineProps<{
  ai: ReturnType<typeof useAiAnalysis>;
  sync: ReturnType<typeof useTeamSync>;
  comments: ReturnType<typeof useComments>;
  matches: MatchRecord[];
  watcher: WatcherStatus;
  platform: PlatformId;
  active?: boolean;
  viewerSteamId?: string;
  p5e?: ReturnType<typeof useP5eCdp>;
  history?: ReturnType<typeof useMatchHistory>;
}>();

const emit = defineEmits<{
  openSettings: [];
  back: [];
}>();

const latestMatch = computed(() => props.matches[0] ?? null);

/** Never leave "waiting" ambiguous about whether the relay is up. */
const relayLabel = computed(() => {
  const settings = props.sync.settings.value;
  if (!settings.enabled) return '';
  const state = props.sync.status.value;
  if (state === 'connected') {
    return settings.roomCode ? `已连接服务端房间 ${settings.roomCode}` : '已连接服务端（未进房）';
  }
  if (state === 'connecting') return '正在连接服务端…';
  if (state === 'error') return '服务端连接异常';
  return '服务端未连接';
});

function onPostMatchUpdated(report: P5ePostMatchReport) {
  if (!latestMatch.value || !props.history) return;
  void props.history.patchMatchPostMatch(
    latestMatch.value.id,
    props.platform,
    report,
    latestMatch.value,
  );
}
</script>

<template>
  <div class="relative flex h-full flex-col overflow-hidden">
    <div v-if="latestMatch" class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <MatchWorkspace
        :match="latestMatch"
        :sync="sync"
        @post-match-updated="onPostMatchUpdated"
      />
    </div>

    <!--
      No local match yet, but the relay already holds one (a restored session,
      or a match reported by another PC). Without this branch the window sits on
      the waiting screen while the analysis exists server-side.
    -->
    <div v-else-if="sync.serverMatch.value" class="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ServerRoomPanel :sync="sync" />
    </div>

    <MatchEmptyState
      v-else
      :watcher="watcher"
      :platform="platform"
      :p5e-phase="p5e?.status.value.phase"
      :p5e-recovering="p5e?.autoRecovering.value"
      :relay-label="relayLabel"
      @back="emit('back')"
    />
  </div>
</template>
