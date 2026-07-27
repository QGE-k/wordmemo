/* ====================================================
   WordMemo PWA Service Worker
   作用：缓存前端静态资源，支持离线打开；API请求始终走网络
   ==================================================== */
const CACHE_NAME = 'wordmemo-v1';
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/assets/style.css',
  '/assets/app.js',
  '/manifest.json',
];

// 安装：预缓存核心资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  );
  self.clients.claim();
});

// 请求拦截
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API 请求、跨站请求：不缓存，直接走网络
  if (url.pathname.startsWith('/api') || url.origin !== self.location.origin) {
    return;
  }

  // 同源静态资源：缓存优先，网络回退
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request)
        .then((resp) => {
          if (resp && resp.ok) {
            const respClone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, respClone));
          }
          return resp;
        })
        .catch(() => caches.match('/index.html'));
    })
  );
});
