import { ref, onMounted, onUnmounted } from 'vue';
import { teamSyncClient } from '@core/sync/sync-client';
import type { SyncSettings, SyncStatus } from '@core/sync/types';
import type { MatchRecord } from '@core/match/models';
import type { P5ePostMatchReport } from '@platforms/5e/post-match';
import type { AiAnalysisResultV3 } from '@core/ai/types';
import { clientLog, setClientLogServer } from '@core/log/client-log';

/** The slice of the relay's session that the desktop renders. */
export interface ServerMatchView {
  sessionId?: string;
  matchId?: string;
  mapName?: string;
  mySide?: 'ct' | 't' | null;
  mySideSource?: 'explicit' | 'explicit-all' | 'library' | 'self' | 'party' | null;
  profileState?: string;
  demoState?: string;
  homeState?: string;
  homeError?: string | null;
  homeCoverage?: number;
  aiState?: string;
  aiText?: string | null;
  /** 结构化分析结果（v3）；老会话只有 aiText。 */
  aiResult?: AiAnalysisResultV3 | null;
  /** 还差什么才能开算（例如「等地图确认」）。 */
  aiWait?: string[] | null;
  tacticsState?: string;
  tacticsText?: string | null;
  postReport?: P5ePostMatchReport | null;
  createdAt?: number;
  updatedAt?: number;
}

export interface ServerPlayerView {
  steamId?: string;
  nickname?: string;
  team?: string;
  avatarUrl?: string;
  partyTag?: string | null;
  isSelf?: boolean;
  stats?: Record<string, number | string | boolean | undefined> | null;
}

export function useTeamSync() {
  const settings = ref<SyncSettings>(teamSyncClient.getSettings());
  // 客户端日志跟着服务端地址走，改地址后日志也发到新地址。
  setClientLogServer(settings.value.serverUrl);
  const status = ref<SyncStatus>(teamSyncClient.getStatus());
  const roomMembers = ref<Array<{ id: string; nickname: string; deviceType: string; isOnline: boolean }>>([]);
  const aiReport = ref<unknown | null>(null);
  const aiStreamChunk = ref<string>('');
  const tacticsStream = ref<string>('');
  const lastReportedAt = ref<number | null>(null);
  /** Everything the relay knows about the current match. */
  const serverMatch = ref<ServerMatchView | null>(null);
  const serverProfiles = ref<ServerPlayerView[]>([]);
  const sideBusy = ref(false);
  const sideError = ref<string | null>(null);
  /** 上一次分析失败的原因（面板上要能说清楚，而不是空着）。 */
  const aiError = ref<string | null>(null);

  let unsubscribe: (() => void) | null = null;
  // 「已连接/未连接」闪一下最容易被当成故障。断线先压 1.5 秒，
  // 期间重连成功就什么都不显示——真断了才切到未连接。
  let disconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function applyStatus(next: SyncStatus) {
    if (next === 'disconnected') {
      if (disconnectTimer) return;
      disconnectTimer = setTimeout(() => {
        disconnectTimer = null;
        status.value = 'disconnected';
      }, 1500);
      return;
    }
    if (disconnectTimer) {
      clearTimeout(disconnectTimer);
      disconnectTimer = null;
    }
    status.value = next;
  }

  function mergeMatch(partial: Partial<ServerMatchView>) {
    serverMatch.value = { ...(serverMatch.value ?? {}), ...partial };
  }

  onMounted(() => {
    unsubscribe = teamSyncClient.subscribe((event, data) => {
      if (event === 'statusChanged') {
        applyStatus(data as SyncStatus);
      } else if (event === 'ROOM_MEMBERS_CHANGED') {
        const payload = data as { members: typeof roomMembers.value };
        if (payload?.members) {
          roomMembers.value = payload.members;
        }
      } else if (event === 'ROOM_STATE_SYNC') {
        const payload = data as {
          members?: typeof roomMembers.value;
          match?: ServerMatchView | null;
          profiles?: ServerPlayerView[] | null;
        };
        if (payload?.members) {
          roomMembers.value = payload.members;
        }
        if (payload?.match) {
          serverMatch.value = payload.match;
        }
        if (payload?.profiles?.length) {
          serverProfiles.value = payload.profiles;
        }
      } else if (event === 'MATCH_DETECTED') {
        const payload = data as ServerMatchView;
        if (payload?.matchId) {
          serverMatch.value = { ...(serverMatch.value ?? {}), ...payload };
        }
      } else if (event === 'PROFILE_READY') {
        const payload = data as { players?: ServerPlayerView[] };
        if (payload?.players?.length) {
          serverProfiles.value = payload.players;
        }
      } else if (event === 'AI_STREAM_CHUNK') {
        const payload = data as { accumulated?: string };
        if (payload?.accumulated) {
          aiStreamChunk.value = payload.accumulated;
        }
      } else if (event === 'AI_REPORT_READY') {
        const payload = data as { report?: string; result?: AiAnalysisResultV3 | null };
        aiReport.value = data;
        aiError.value = null;
        mergeMatch({
          aiText: typeof payload?.report === 'string' ? payload.report : null,
          aiState: 'ready',
          aiResult: payload?.result ?? null,
        });
      } else if (event === 'AI_TACTICS_CHUNK') {
        const payload = data as { accumulated?: string };
        if (payload?.accumulated) {
          tacticsStream.value = payload.accumulated;
        }
      } else if (event === 'AI_TACTICS_READY') {
        const payload = data as { report?: string };
        if (typeof payload?.report === 'string') {
          mergeMatch({ tacticsText: payload.report, tacticsState: 'ready' });
        }
      } else if (event === 'ROOM_ERROR') {
        const payload = data as { stage?: string; message?: string };
        if (payload?.stage === 'home') {
          mergeMatch({ homeError: payload.message ?? null, homeState: 'signature' });
        } else if (payload?.stage === 'ai') {
          aiError.value = payload.message ?? '分析失败';
        }
      } else if (event === 'matchReported') {
        lastReportedAt.value = Date.now();
      }
    });

    if (settings.value.enabled) {
      teamSyncClient.connectWs();
      void teamSyncClient.fetchSnapshot();
    }
  });

  onUnmounted(() => {
    if (disconnectTimer) {
      clearTimeout(disconnectTimer);
      disconnectTimer = null;
    }
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
  });

  async function createRoom(nickname?: string) {
    const res = await teamSyncClient.createRoom(nickname);
    settings.value = teamSyncClient.getSettings();
    await teamSyncClient.fetchSnapshot();
    return res;
  }

  async function joinRoom(roomCode: string, nickname?: string) {
    await teamSyncClient.joinRoom(roomCode, nickname);
    settings.value = teamSyncClient.getSettings();
    await teamSyncClient.fetchSnapshot();
  }

  function disconnect() {
    teamSyncClient.disconnect();
    settings.value = teamSyncClient.getSettings();
    status.value = 'disconnected';
    roomMembers.value = [];
    serverMatch.value = null;
    serverProfiles.value = [];
  }

  function updateSettings(partial: Partial<SyncSettings>) {
    teamSyncClient.updateSettings(partial);
    settings.value = teamSyncClient.getSettings();
  }

  async function reportMatch(record: MatchRecord) {
    if (!settings.value.enabled || !settings.value.autoReport) {
      clientLog('INFO', '上报', `跳过上报：enabled=${settings.value.enabled} autoReport=${settings.value.autoReport}`);
      return;
    }
    clientLog('INFO', '上报', `上报对局 ${record.id}（${record.detail.mapName || '未知地图'}）`);
    try {
      await teamSyncClient.reportMatch(record);
      clientLog('INFO', '上报', `上报成功 ${record.id}`);
    } catch (err) {
      clientLog('ERROR', '上报', `上报失败 ${record.id}: ${err instanceof Error ? err.message : String(err)}`);
      throw err;
    }
  }

  /**
   * Tell the relay which roster is ours. `null` means "analyze both" and must
   * carry `all: true`, otherwise an ID-library hit immediately takes the side
   * back and the button looks broken.
   */
  /** 让服务端重跑一次分析（不动轨迹下载）。 */
  async function rerunAnalysis() {
    const { enabled, serverUrl, roomCode, token } = settings.value;
    if (!enabled || !roomCode || !token) return;
    aiError.value = null;
    try {
      const res = await fetch(
        `${serverUrl.replace(/\/+$/, '')}/api/v1/room/${encodeURIComponent(roomCode)}/analysis/rerun`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
      );
      const json = await res.json().catch(() => null);
      if (!res.ok || json?.code !== 0) {
        throw new Error(json?.message || '重跑失败');
      }
      mergeMatch({ aiState: json.data?.aiState ?? 'running' });
    } catch (err) {
      aiError.value = err instanceof Error ? err.message : String(err);
    }
  }

  async function setAnalysisSide(side: 'ct' | 't' | null) {
    const { enabled, serverUrl, roomCode, token } = settings.value;
    if (!enabled || !roomCode || !token) return;
    sideBusy.value = true;
    sideError.value = null;
    try {
      const res = await fetch(
        `${serverUrl.replace(/\/+$/, '')}/api/v1/room/${encodeURIComponent(roomCode)}/analysis-side`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ mySide: side, all: side === null }),
        },
      );
      const json = await res.json().catch(() => null);
      if (!res.ok || json?.code !== 0) {
        throw new Error(json?.message || '切换失败');
      }
      mergeMatch({
        mySide: json.data?.mySide ?? null,
        mySideSource: json.data?.mySideSource ?? null,
      });
    } catch (err) {
      sideError.value = err instanceof Error ? err.message : String(err);
    } finally {
      sideBusy.value = false;
    }
  }

  return {
    settings,
    status,
    roomMembers,
    aiReport,
    aiStreamChunk,
    tacticsStream,
    lastReportedAt,
    serverMatch,
    serverProfiles,
    sideBusy,
    sideError,
    aiError,
    rerunAnalysis,
    createRoom,
    joinRoom,
    disconnect,
    updateSettings,
    reportMatch,
    setAnalysisSide,
  };
}
