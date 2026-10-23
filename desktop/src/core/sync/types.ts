export type SyncStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface SyncSettings {
  enabled: boolean;
  serverUrl: string;
  roomCode: string;
  token: string;
  nickname: string;
  autoReport: boolean;
}

export const DEFAULT_SYNC_SETTINGS: SyncSettings = {
  enabled: false,
  // 与 server/README 的默认端口一致（旧占位值 3000 会连不上）。
  serverUrl: 'http://127.0.0.1:8787',
  roomCode: '',
  token: '',
  nickname: 'PC 房主',
  autoReport: true,
};
