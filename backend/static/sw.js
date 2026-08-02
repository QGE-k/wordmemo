/* ====================================================
   WordMemo PWA Service Worker v3
   策略：
   - 静态资源：stale-while-revalidate（缓存优先，后台更新）
   - 只读 GET API（stats/words/wordbooks）：网络优先，缓存兜底（离线可用）
   - 写操作 API（POST/PUT/DELETE）：纯网络，不缓存
   - 用户切换时清空 API 缓存（防止新用户看到旧用户数据）
   ==================================================== */
const CACHE_NAME = 'wordmemo-v46';
const API_CACHE_NAME = 'wordmemo-api-v46';
const CORE_ASSETS = [
  '/',
  '/index.html',
  '/assets/style.css',
  '/assets/app.js',
  '/manifest.json',
];

// 只缓存这些只读 GET API（安全，不会缓存写操作）
const CACHEABLE_API = [
  '/api/stats',
  '/api/words',
  '/api/wordbooks',
  '/api/review/today',
  '/api/learn/today-words',
  '/api/me',
];

// API 缓存有效期：5 分钟（与 Render 保活节奏一致）
const API_CACHE_TTL = 5 * 60 * 1000;

// 安装：预缓存核心资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

// 激活：清理所有旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => {
        if (k !== CACHE_NAME && k !== API_CACHE_NAME) {
          return caches.delete(k);
        }
        return null;
      }))
    )
  );
  self.clients.claim();
});

// === 消息监听：用户登录/注册/退出时清空 API 缓存 ===
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CLEAR_API_CACHE') {
    caches.delete(API_CACHE_NAME).then(() => {
      console.log('[SW] API 缓存已清空（用户切换）');
    });
  }
});

// 判断是否为可缓存的只读 API
function isCacheableApi(pathname) {
  return CACHEABLE_API.some(api => pathname.startsWith(api));
}

// 获取带时间戳的 API 缓存
async function getApiCache(request) {
  const cache = await caches.open(API_CACHE_NAME);
  const cached = await cache.match(request);
  if (!cached) return null;

  // 检查是否过期
  const cachedTime = cached.headers.get('sw-cache-time');
  if (cachedTime) {
    const age = Date.now() - parseInt(cachedTime);
    if (age > API_CACHE_TTL) {
      // 过期了，返回 null 触发网络请求
      return null;
    }
  }
  return cached;
}

// 存储带时间戳的 API 响应到缓存
async function putApiCache(request, response) {
  try {
    const cache = await caches.open(API_CACHE_NAME);
    // 克隆响应并添加缓存时间戳
    const respClone = response.clone();
    const headers = new Headers(respClone.headers);
    headers.set('sw-cache-time', Date.now().toString());
    const body = await respClone.text();
    const cachedResponse = new Response(body, {
      status: respClone.status,
      statusText: respClone.statusText,
      headers: headers,
    });
    await cache.put(request, cachedResponse);
  } catch (e) {
    // 缓存失败不影响使用
  }
}

// 请求拦截
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 跨站请求：不处理
  if (url.origin !== self.location.origin) {
    return;
  }

  // 只处理 GET 请求
  if (event.request.method !== 'GET') {
    return;
  }

  // === 只读 GET API：网络优先，缓存兜底 ===
  if (isCacheableApi(url.pathname)) {
    event.respondWith(
      (async () => {
        // 先尝试网络
        try {
          const networkResp = await fetch(event.request);
          if (networkResp && networkResp.ok) {
            // 缓存成功的 API 响应
            await putApiCache(event.request, networkResp);
          }
          return networkResp;
        } catch (e) {
          // 网络失败：尝试缓存
          const cached = await getApiCache(event.request);
          if (cached) {
            return cached;
          }
          // 缓存也没有：返回错误
          return new Response(JSON.stringify({ success: false, error: '网络不可用' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        }
      })()
    );
    return;
  }

  // === 静态资源：stale-while-revalidate ===
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((resp) => {
          if (resp && resp.ok) {
            const respClone = resp.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, respClone));
          }
          return resp;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
