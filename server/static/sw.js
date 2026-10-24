/* 已废弃的 Service Worker —— 只负责把自己注销掉。
 *
 * 网页端跑在手机上，靠局域网访问电脑，不需要离线能力；而旧版 SW 会把页面外壳
 * 缓存住，表现就是「改了没生效，只有无痕窗口能看到新数据」。
 * 这里保留文件是为了让还装着旧 SW 的设备能通过更新检查拿到这个版本，
 * 装上后立刻注销自己并清空缓存。
 */

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((key) => caches.delete(key)));
      } catch (_) {
        /* ignore */
      }
      try {
        await self.registration.unregister();
      } catch (_) {
        /* ignore */
      }
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((client) => client.navigate(client.url).catch(() => {}));
    })(),
  );
});
