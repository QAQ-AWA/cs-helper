export type SyncStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface SyncSettings {
  enabled: boolean;
  serverUrl: string;
  roomCode: string;
  token: string;
  nickname: string;
  autoReport: boolean;
  /** 上报密钥：服务端设了 CS_HELPER_REPORT_KEY 时必填，否则上报会被 403。 */
  reportKey: string;
}

export const DEFAULT_SYNC_SETTINGS: SyncSettings = {
  enabled: false,
  // 与 server/README 的默认端口一致（旧占位值 3000 会连不上）。
  serverUrl: 'http://127.0.0.1:8787',
  roomCode: '',
  token: '',
  nickname: 'PC 房主',
  autoReport: true,
  reportKey: '',
};
