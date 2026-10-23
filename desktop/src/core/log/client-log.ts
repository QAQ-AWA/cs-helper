/**
 * 把客户端日志推给本机服务端落盘。
 *
 * 为什么需要：5E 侦测出问题时，debug 面板只存在于内存里，出问题的机器上没人能看。
 * 推一份到服务端（`POST /api/v1/dev/client-log`，仅 DEV_MODE），排查时直接读 JSONL。
 *
 * 失败一律静默——日志不能影响主流程。
 */

type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

interface LogLine {
  at: string;
  level: LogLevel;
  category: string;
  text: string;
}

const MAX_QUEUE = 500;
const FLUSH_MS = 2000;

const queue: LogLine[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let baseUrl = 'http://127.0.0.1:8787';
let suspended = false;

export function setClientLogServer(url: string | undefined | null): void {
  const next = (url ?? '').trim().replace(/\/+$/, '');
  if (next) baseUrl = next;
}

/** 断网/退出前暂停上报，避免无意义的失败请求。 */
export function suspendClientLog(): void {
  suspended = true;
}

export function clientLog(level: LogLevel, category: string, text: unknown): void {
  if (suspended) return;
  const message = typeof text === 'string' ? text : String(text ?? '');
  if (!message) return;

  queue.push({
    at: new Date().toISOString(),
    level,
    category: category.slice(0, 40),
    text: message.slice(0, 1200),
  });
  if (queue.length > MAX_QUEUE) queue.splice(0, queue.length - MAX_QUEUE);
  if (timer === null) timer = setTimeout(() => void flush(), FLUSH_MS);
}

async function flush(): Promise<void> {
  timer = null;
  if (!queue.length) return;
  const batch = queue.splice(0, 200);
  try {
    await fetch(`${baseUrl}/api/v1/dev/client-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines: batch }),
      keepalive: true,
    });
  } catch {
    // 服务端没起就丢掉，不重试、不打扰用户
  }
}
