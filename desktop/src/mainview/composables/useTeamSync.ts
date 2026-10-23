import { ref, onMounted, onUnmounted } from 'vue';
import { teamSyncClient } from '@core/sync/sync-client';
import type { SyncSettings, SyncStatus } from '@core/sync/types';
import type { MatchRecord } from '@core/match/models';

export function useTeamSync() {
  const settings = ref<SyncSettings>(teamSyncClient.getSettings());
  const status = ref<SyncStatus>(teamSyncClient.getStatus());
  const roomMembers = ref<Array<{ id: string; nickname: string; deviceType: string; isOnline: boolean }>>([]);
  const aiReport = ref<unknown | null>(null);
  const aiStreamChunk = ref<string>('');
  const lastReportedAt = ref<number | null>(null);

  let unsubscribe: (() => void) | null = null;

  onMounted(() => {
    unsubscribe = teamSyncClient.subscribe((event, data) => {
      if (event === 'statusChanged') {
        status.value = data as SyncStatus;
      } else if (event === 'ROOM_MEMBERS_CHANGED') {
        const payload = data as { members: typeof roomMembers.value };
        if (payload?.members) {
          roomMembers.value = payload.members;
        }
      } else if (event === 'ROOM_STATE_SYNC') {
        const payload = data as { members?: typeof roomMembers.value };
        if (payload?.members) {
          roomMembers.value = payload.members;
        }
      } else if (event === 'AI_STREAM_CHUNK') {
        const payload = data as { accumulated?: string };
        if (payload?.accumulated) {
          aiStreamChunk.value = payload.accumulated;
        }
      } else if (event === 'AI_REPORT_READY') {
        aiReport.value = data;
      } else if (event === 'matchReported') {
        lastReportedAt.value = Date.now();
      }
    });

    if (settings.value.enabled) {
      teamSyncClient.connectWs();
    }
  });

  onUnmounted(() => {
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
  });

  async function createRoom(nickname?: string) {
    const res = await teamSyncClient.createRoom(nickname);
    settings.value = teamSyncClient.getSettings();
    return res;
  }

  async function joinRoom(roomCode: string, nickname?: string) {
    await teamSyncClient.joinRoom(roomCode, nickname);
    settings.value = teamSyncClient.getSettings();
  }

  function disconnect() {
    teamSyncClient.disconnect();
    settings.value = teamSyncClient.getSettings();
    status.value = 'disconnected';
    roomMembers.value = [];
  }

  function updateSettings(partial: Partial<SyncSettings>) {
    teamSyncClient.updateSettings(partial);
    settings.value = teamSyncClient.getSettings();
  }

  async function reportMatch(record: MatchRecord) {
    if (settings.value.enabled && settings.value.autoReport) {
      await teamSyncClient.reportMatch(record);
    }
  }

  return {
    settings,
    status,
    roomMembers,
    aiReport,
    aiStreamChunk,
    lastReportedAt,
    createRoom,
    joinRoom,
    disconnect,
    updateSettings,
    reportMatch,
  };
}
