/**
 * 轨迹回放的雷达图地址。
 *
 * 引擎在产物里给的是**服务端相对路径**（`/maps/de_dust2/radar.png`）。
 * 桌面端页面来自 `tauri://localhost`，根相对路径会被当成应用内资源，
 * 结果 404 → 画布上只剩「缺少雷达图资源」。手机上不会有这个问题，
 * 因为页面本身就是从服务端同源加载的。
 */
export function resolveRadarUrl(
  radar: string | null | undefined,
  baseUrl: string,
): string | undefined {
  const value = (radar ?? '').trim();
  if (!value) return undefined;
  const base = (baseUrl ?? '').trim().replace(/\/+$/, '');
  if (!base) return value;
  try {
    // 已经是绝对地址时 new URL 会原样返回，不需要额外分支。
    return new URL(value, `${base}/`).href;
  } catch {
    return value;
  }
}
