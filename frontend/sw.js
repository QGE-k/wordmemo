/* ====================================================
   WordMemo PWA Service Worker
   作用：缓存前端静态资源，实现秒开；API请求始终走网络
   策略：静态资源 stale-while-revalidate（缓存优先，后台更新）
         API 请求网络优先，缓存兜底
   ==================================================== */
const CACHE_NAME = 'wordmemo-v13';
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

// 激活：清理所有旧缓存，立即接管页面
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

  // API 请求：网络优先，不缓存
  if (url.pathname.startsWith('/api')) {
    return;
  }

  // 跨站请求：不处理
  if (url.origin !== self.location.origin) {
    return;
  }

  // 同源静态资源：stale-while-revalidate 策略
  // 1. 先从缓存返回（秒开）
  // 2. 后台从网络更新缓存（下次用新版）
  event.respondWith(
    caches.match(event.request).then((cached) => {
      // 后台更新：无论是否有缓存，都从网络拉取最新版本更新缓存
      const fetchPromise = fetch(event.request)
        .then((resp) => {
          if (resp && resp.ok) {
            const respClone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, respClone));
          }
          return resp;
        })
        .catch(() => cached); // 网络失败时返回缓存

      // 有缓存就先返回缓存（秒开），没有就走网络
      return cached || fetchPromise;
    })
  );
});
