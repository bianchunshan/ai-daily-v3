/* ===== 前沿科技日报 · Service Worker =====
 * 策略:同源 GET 一律网络优先、失败回退缓存(保证新闻新鲜,离线也能看上次内容)。
 * 安装时预缓存应用壳,方便离线冷启动。
 */
var CACHE = 'aid-v1';
var SHELL = [
  'index.html',
  'detail.html',
  'stock.html',
  'assets/theme.css?v=20260703a',
  'assets/app.js?v=20260703a',
  'assets/favicon.svg',
  'assets/icons/icon-192.png',
  'manifest.webmanifest'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) { return c.addAll(SHELL); }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // 三方资源(行情接口/外链图片)不接管
  if (url.pathname.indexOf('/api/') === 0) return;   // API 永远走网络

  e.respondWith(
    fetch(req).then(function (res) {
      if (res && res.ok) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(req).then(function (hit) {
        if (hit) return hit;
        if (req.mode === 'navigate') return caches.match('index.html');
        return Response.error();
      });
    })
  );
});
