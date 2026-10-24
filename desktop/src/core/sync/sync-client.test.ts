import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * 连接抖动的回归测试。
 *
 * 真机现象：设置页显示「已连接 → 未连接」反复闪，服务端日志里每 7 秒就有一条
 * 新的 WebSocket 连接。原因是 connectWs() 每次都先 disconnect() 再新建：
 * 只要有两个 useTeamSync 实例（App + 设置页/弹窗），它们就会互相把对方的连接掐掉，
 * 被掐的一方 5 秒后重连再掐回去 —— 稳定的 7 秒乒乓。
 */

class FakeSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSED = 3;
  static instances: FakeSocket[] = [];

  readyState = FakeSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onclose: ((event: { code: number; reason?: string }) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }

  close(): void {
    this.readyState = FakeSocket.CLOSED;
    this.onclose?.({ code: 1000 });
  }

  // 测试辅助：模拟握手成功
  open(): void {
    this.readyState = FakeSocket.OPEN;
    this.onopen?.();
  }
}

const SETTINGS = {
  enabled: true,
  serverUrl: 'http://127.0.0.1:8787',
  roomCode: 'MAIN',
  token: 'test-token',
  nickname: '测试',
  autoReport: true,
};

describe('TeamSyncClient 连接管理', () => {
  beforeEach(async () => {
    vi.resetModules();
    FakeSocket.instances = [];
    vi.stubGlobal('WebSocket', FakeSocket);
    // 这些用例跑在 node 环境里，没有 localStorage / window，手动补上。
    const store = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, String(value)),
      removeItem: (key: string) => void store.delete(key),
    });
    vi.stubGlobal('window', globalThis);
    localStorage.setItem('cs_helper_team_sync_settings_v1', JSON.stringify(SETTINGS));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('重复调用 connectWs 不会把已有连接掐掉重开', async () => {
    const { TeamSyncClient } = await import('./sync-client');
    const client = new TeamSyncClient();

    client.connectWs();
    expect(FakeSocket.instances).toHaveLength(1);

    FakeSocket.instances[0].open();
    client.connectWs(); // 第二个 useTeamSync 实例挂载时也会调
    client.connectWs();

    expect(FakeSocket.instances).toHaveLength(1);
    expect(client.getStatus()).toBe('connected');
  });

  it('旧 socket 的 onclose 不影响新连接的状态', async () => {
    const { TeamSyncClient } = await import('./sync-client');
    const client = new TeamSyncClient();

    client.connectWs();
    const first = FakeSocket.instances[0];
    first.open();

    client.disconnect(); // 主动断开（等价于用户点「断开」）
    client.connectWs(); // 再连一次
    const second = FakeSocket.instances[1];
    expect(second).toBeDefined();
    second.open();
    expect(client.getStatus()).toBe('connected');

    // 第一个 socket 的 onclose 晚到，不该把状态改成「未连接」
    first.onclose?.({ code: 1006 });
    expect(client.getStatus()).toBe('connected');
  });
});
