<script setup lang="ts">
import { computed } from 'vue';
import type { MatchPlayer, MatchRecord, MatchTeam } from '@core/match/models';
import type { ServerPlayerView, useTeamSync } from '../composables/useTeamSync';
import MatchWorkspace from './MatchWorkspace.vue';

/**
 * 本地还没检测到对局、但服务端房间里已经有一局时显示。
 *
 * 以前这里是另一套简化界面（窄列表 + Markdown 分析），跟本地对局的四个页签
 * 长得完全不一样，同一个房间在两台设备上会看到两种样子。现在把服务端会话
 * 还原成一份 MatchRecord，直接复用 MatchWorkspace——界面只有一套。
 */
const props = defineProps<{
  sync: ReturnType<typeof useTeamSync>;
}>();

const match = computed(() => props.sync.serverMatch.value);
const players = computed(() => props.sync.serverProfiles.value);

function toPlayer(player: ServerPlayerView): MatchPlayer {
  return {
    steamId: player.steamId || `server-${player.nickname}`,
    nickname: player.nickname || 'Unknown',
    avatar: player.avatarUrl,
    teamSide: 0,
    // 有组队标记就不是单排，阵容页靠这个画组队条。
    isSingle: !player.partyTag,
    radar: {},
    recentResults: [],
    recentRatings: [],
    tags: [],
  } as MatchPlayer;
}

function teamFor(side: 'ct' | 't', token: 'A' | 'B', id: number): MatchTeam {
  return {
    side: token,
    id,
    singleCount: 0,
    partyGroups: [],
    players: players.value
      .filter((player) => (player.team || '').toLowerCase() === side)
      .map(toPlayer),
  };
}

const record = computed<MatchRecord | null>(() => {
  const current = match.value;
  if (!current || !players.value.length) return null;
  return {
    id: current.sessionId || current.matchId || 'server-session',
    platformId: '5e',
    data: {},
    summary: { playerCount: players.value.length, mapName: current.mapName || '' },
    detail: {
      platformGameId: current.matchId || '',
      mapName: current.mapName || '',
      teams: [teamFor('ct', 'A', 0), teamFor('t', 'B', 1)],
      unassigned: [],
      hasExtraInfo: false,
      parseWarnings: [],
    },
  } as unknown as MatchRecord;
});
</script>

<template>
  <MatchWorkspace v-if="record" :match="record" :sync="sync" />
  <div v-else class="flex h-full items-center justify-center px-6 text-center text-sm text-fg-muted">
    房间里还没有对局数据。
  </div>
</template>
