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
  serverUrl: 'http://localhost:3000',
  roomCode: '',
  token: '',
  nickname: 'PC 房主',
  autoReport: true,
};
