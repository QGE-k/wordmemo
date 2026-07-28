/* ====================================================
   WordMemo PWA Service Worker
   作用：缓存前端静态资源，支持离线打开；API请求始终走网络
   策略：网络优先（确保更新立即生效），缓存作为离线兜底
   ==================================================== */
const CACHE_NAME = 'wordmemo-v8';
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/assets/style.css',
  '/assets/app.js',
  '/manifest.json',
];

// 安装：预缓存核心资源，跳过等待立即激活
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

// 激活：清理所有旧缓存（包括 v1），立即接管页面
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  );
  self.clients.claim();
});

// 请求拦截：网络优先，缓存兜底
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API 请求、跨站请求：不缓存，直接走网络
  if (url.pathname.startsWith('/api') || url.origin !== self.location.origin) {
    return;
  }

  // 同源静态资源：网络优先，失败时用缓存（离线可用）
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        // 网络成功：更新缓存并返回
        if (resp && resp.ok) {
          const respClone = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, respClone));
        }
        return resp;
      })
      .catch(() => {
        // 网络失败：用缓存兜底
        return caches.match(event.request).then((cached) => {
          return cached || caches.match('/index.html');
        });
      })
  );
});
