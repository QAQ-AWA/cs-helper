import type { MatchRecord } from '@core/match/models';
import { buildMatchReport, CLIENT_VERSION, PROTOCOL_VERSION } from './report-builder';
import { DEFAULT_SYNC_SETTINGS, type SyncSettings, type SyncStatus } from './types';

const STORAGE_KEY = 'cs_helper_team_sync_settings_v1';

export type SyncEventListener = (event: string, data: unknown) => void;

export class TeamSyncClient {
  private settings: SyncSettings;
  private ws: WebSocket | null = null;
  private status: SyncStatus = 'disconnected';
  private listeners = new Set<SyncEventListener>();
  private reconnectTimer: number | null = null;
  private lastReportedMatchId: string | null = null;
  private readonly reportedPostMatches = new Set<string>();
  /** Last event sequence applied, used to resume after a dropped socket. */
  private lastSeq = 0;

  constructor() {
    this.settings = this.loadSettings();
  }

  public getSettings(): SyncSettings {
    return { ...this.settings };
  }

  public updateSettings(partial: Partial<SyncSettings>): void {
    this.settings = { ...this.settings, ...partial };
    this.saveSettings();
    if (!this.settings.enabled) {
      this.disconnect();
    }
  }

  public getStatus(): SyncStatus {
    return this.status;
  }

  public subscribe(listener: SyncEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(event: string, data: unknown): void {
    for (const listener of this.listeners) {
      try {
        listener(event, data);
      } catch (err) {
        console.error('Error in sync listener:', err);
      }
    }
  }

  public async createRoom(nickname?: string): Promise<{ roomCode: string; token: string }> {
    const serverUrl = this.settings.serverUrl.replace(/\/+$/, '');
    const res = await fetch(`${serverUrl}/api/v1/room/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        creatorNickname: nickname || this.settings.nickname,
        deviceType: 'pc',
      }),
    });

    const json = await res.json();
    if (json.code !== 0) {
      throw new Error(json.message || '创建房间失败');
    }

    const { roomCode, token } = json.data;
    this.updateSettings({
      enabled: true,
      roomCode,
      token,
      nickname: nickname || this.settings.nickname,
    });
    this.resetMatchTracking();

    this.connectWs();
    return { roomCode, token };
  }

  public async joinRoom(roomCode: string, nickname?: string): Promise<void> {
    const serverUrl = this.settings.serverUrl.replace(/\/+$/, '');
    const res = await fetch(`${serverUrl}/api/v1/room/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        roomCode: roomCode.trim().toUpperCase(),
        nickname: nickname || this.settings.nickname,
        deviceType: 'pc',
      }),
    });

    const json = await res.json();
    if (json.code !== 0) {
      throw new Error(json.message || '加入房间失败');
    }

    const { token } = json.data;
    this.updateSettings({
      enabled: true,
      roomCode: roomCode.trim().toUpperCase(),
      token,
      nickname: nickname || this.settings.nickname,
    });
    this.resetMatchTracking();

    this.connectWs();
  }

  private resetMatchTracking(): void {
    this.lastReportedMatchId = null;
    this.lastSeq = 0;
  }

  public disconnect(): void {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.status = 'disconnected';
    this.emit('statusChanged', this.status);
  }

  public connectWs(): void {
    if (!this.settings.enabled || !this.settings.roomCode || !this.settings.token) {
      return;
    }

    this.disconnect();
    this.status = 'connecting';
    this.emit('statusChanged', this.status);

    const serverUrl = this.settings.serverUrl.replace(/^http/i, 'ws').replace(/\/+$/, '');
    const wsUrl = `${serverUrl}/ws?token=${encodeURIComponent(this.settings.token)}&lastSeq=${this.lastSeq}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.status = 'connected';
        this.emit('statusChanged', this.status);
      };

      this.ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          this.trackSequence(parsed);
          this.emit(parsed.action, parsed.payload);
        } catch (err) {
          console.error('Failed to parse incoming WebSocket message:', err);
        }
      };

      this.ws.onclose = () => {
        this.status = 'disconnected';
        this.emit('statusChanged', this.status);
        if (this.settings.enabled) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        this.status = 'error';
        this.emit('statusChanged', this.status);
      };
    } catch {
      this.status = 'error';
      this.emit('statusChanged', this.status);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (this.settings.enabled) {
        this.connectWs();
      }
    }, 5000);
  }

  public async reportMatch(record: MatchRecord): Promise<void> {
    if (!this.settings.enabled || !this.settings.roomCode) return;

    const built = buildMatchReport(record);
    if (!built) return; // no usable roster yet, or an incomplete Perfect snapshot
    if (built.idempotencyKey === this.lastReportedMatchId) return;

    const serverUrl = this.settings.serverUrl.replace(/\/+$/, '');

    try {
      const res = await fetch(
        `${serverUrl}/api/v1/match/report?roomCode=${encodeURIComponent(this.settings.roomCode)}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${this.settings.token}`,
            'Idempotency-Key': built.idempotencyKey,
            'X-Client-Version': CLIENT_VERSION,
            'X-Protocol-Version': String(PROTOCOL_VERSION),
          },
          body: JSON.stringify(built.body),
        },
      );

      const json = await res.json().catch(() => null);
      if (res.ok && json?.code === 0) {
        this.lastReportedMatchId = built.idempotencyKey;
        this.emit('matchReported', json.data);
        return;
      }

      this.emit('ROOM_ERROR', {
        code: json?.code ?? res.status,
        message: json?.message || '对局上报失败',
        retryable: res.status >= 500,
        stage: 'report',
      });
    } catch (err) {
      console.warn('Failed to upload match report to server:', err);
      this.emit('ROOM_ERROR', {
        code: 0,
        message: '无法连接同步服务端',
        retryable: true,
        stage: 'report',
      });
    }
  }

  /** 赛后战报由客户端取回后上报，服务端只做归档与广播。 */
  public async reportPostMatch(report: unknown): Promise<void> {
    if (!this.settings.enabled || !this.settings.roomCode || !this.settings.token) return;
    const key = (report as { matchCode?: string })?.matchCode || 'unknown';
    if (this.reportedPostMatches.has(key)) return;

    const serverUrl = this.settings.serverUrl.replace(/\/+$/, '');
    try {
      const res = await fetch(
        `${serverUrl}/api/v1/match/post-report?roomCode=${encodeURIComponent(this.settings.roomCode)}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${this.settings.token}`,
          },
          body: JSON.stringify(report),
        },
      );
      const json = await res.json().catch(() => null);
      if (res.ok && json?.code === 0) {
        this.reportedPostMatches.add(key);
        this.emit('postMatchReported', json.data);
        return;
      }
      this.emit('ROOM_ERROR', {
        code: json?.code ?? res.status,
        message: json?.message || '赛战报上报失败',
        retryable: res.status >= 500,
        stage: 'post-match',
      });
    } catch (err) {
      console.warn('Failed to upload post-match report:', err);
    }
  }

  /** Full state fetch, used when a reconnect cannot be replayed from `lastSeq`. */
  public async fetchSnapshot(): Promise<void> {
    if (!this.settings.enabled || !this.settings.roomCode || !this.settings.token) return;
    const serverUrl = this.settings.serverUrl.replace(/\/+$/, '');
    try {
      const res = await fetch(
        `${serverUrl}/api/v1/room/${encodeURIComponent(this.settings.roomCode)}/snapshot`,
        { headers: { Authorization: `Bearer ${this.settings.token}` } },
      );
      const json = await res.json().catch(() => null);
      if (!res.ok || json?.code !== 0) return;
      if (typeof json.data?.latestSeq === 'number') {
        this.lastSeq = Math.max(this.lastSeq, json.data.latestSeq);
      }
      this.emit('ROOM_STATE_SYNC', json.data);
    } catch (err) {
      console.warn('Failed to fetch room snapshot:', err);
    }
  }

  private trackSequence(message: { action?: string; seq?: number; payload?: { latestSeq?: number } }): void {
    if (message.action === 'ROOM_STATE_SYNC' && typeof message.payload?.latestSeq === 'number') {
      this.lastSeq = Math.max(this.lastSeq, message.payload.latestSeq);
      return;
    }
    if (typeof message.seq === 'number') {
      this.lastSeq = Math.max(this.lastSeq, message.seq);
    }
  }

  private loadSettings(): SyncSettings {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        return { ...DEFAULT_SYNC_SETTINGS, ...JSON.parse(raw) };
      }
    } catch {
      // Fallback
    }
    return { ...DEFAULT_SYNC_SETTINGS };
  }

  private saveSettings(): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.settings));
    } catch {
      // Ignore
    }
  }
}

export const teamSyncClient = new TeamSyncClient();
