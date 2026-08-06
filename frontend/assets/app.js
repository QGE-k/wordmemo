/* ====================================================
   背单词应用 - 主逻辑
   连接 Flask 后端 API（相对路径 /api，本地与部署后通用）
   本地开发：通过 http://localhost:5000/ 访问前端
   ==================================================== */

/* ====================================================
   答题音效（Web Audio API，无需外部音频文件）
   ==================================================== */
let _audioCtx = null;
function getAudioCtx() {
  if (!_audioCtx) {
    try { _audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
    catch(e) { return null; }
  }
  return _audioCtx;
}
// 播放正确音效（上升音调 C-E-G）
function playCorrectSound() {
  const ctx = getAudioCtx();
  if (!ctx) return;
  const notes = [523.25, 659.25, 783.99]; // C5, E5, G5
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = freq;
    osc.type = 'sine';
    const t0 = ctx.currentTime + i * 0.1;
    gain.gain.setValueAtTime(0.3, t0);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.15);
    osc.start(t0); osc.stop(t0 + 0.15);
  });
}
// 播放错误音效（下降音调）
function playWrongSound() {
  const ctx = getAudioCtx();
  if (!ctx) return;
  const notes = [392.00, 311.13]; // G4, Eb4
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = freq;
    osc.type = 'square';
    const t0 = ctx.currentTime + i * 0.12;
    gain.gain.setValueAtTime(0.2, t0);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.2);
    osc.start(t0); osc.stop(t0 + 0.2);
  });
}

/* ====================================================
   一、API 封装类
   统一处理 fetch 请求、错误、JSON 解析
   ==================================================== */
class WordAPI {
  constructor(baseURL = '/api') {
    this.baseURL = baseURL;
  }

  /**
   * 统一请求方法
   * @param {string} path - 接口路径
   * @param {object} options - fetch 配置
   * @returns {Promise<any>} 返回 JSON 数据
   */
  async request(path, options = {}) {
    const url = this.baseURL + path;
    // 默认请求头
    const headers = { ...options.headers };

    // 若不是 FormData，则设置 JSON Content-Type
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    // 根据请求类型设置不同的超时策略
    // AI 识别类请求需要很长时间（后端 120s 超时 + Render 冷启动 30s），用 120 秒
    // 普通请求：首次 10 秒 → 超时重试 30 秒
    const isAIRequest = path.includes('/ai/') || path.includes('/ocr/');
    const isLongAIRequest = path.includes('/ocr/add-words') || path.includes('/words/batch') || path.includes('/import/confirm');
    const firstTimeout = isLongAIRequest ? 120000 : (isAIRequest ? 120000 : 10000);
    const retryTimeout = isLongAIRequest ? 180000 : (isAIRequest ? 180000 : 30000);

    // 带超时的单次请求
    const fetchWithTimeout = async (timeoutMs) => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const res = await fetch(url, { ...options, headers, credentials: 'include', signal: controller.signal });
        clearTimeout(timeoutId);

        if (!res.ok) {
          let errMsg = `请求失败 (${res.status})`;
          let errData = null;
          try {
            errData = await res.json();
            errMsg = errData.error || errData.message || errMsg;
          } catch (e) { }
          const err = new Error(errMsg);
          // 保留后端返回的额外字段（如 quota_exceeded）
          if (errData && errData.quota_exceeded) err.quota_exceeded = true;
          throw err;
        }

        const text = await res.text();
        return text ? JSON.parse(text) : null;
      } catch (err) {
        clearTimeout(timeoutId);
        throw err;
      }
    };

    // 两级超时策略：
    // 1. 首次请求（普通 10 秒 / AI 60 秒）
    // 2. 超时后提示用户并重试（普通 30 秒 / AI 90 秒，覆盖 Render 冷启动）
    try {
      return await fetchWithTimeout(firstTimeout);
    } catch (err) {
      const isRetryable = err.name === 'AbortError' ||
        (err instanceof TypeError && err.message.includes('Failed to fetch')) ||
        err.name === 'SyntaxError'; // Render免费层休眠时返回HTML页，JSON解析失败，可重试
      if (!isRetryable) throw err;

      // 提示用户服务正在唤醒（非阻塞 toast，AI 请求不提示因为有 loading）
      if (!isAIRequest && typeof showToast === 'function') {
        showToast('服务唤醒中，请稍候...', 'info');
      }

      try {
        return await fetchWithTimeout(retryTimeout);
      } catch (err2) {
        if (err2.name === 'AbortError') {
          throw new Error(isAIRequest ? 'AI识别超时，服务繁忙请稍后重试，或减小图片尺寸' : '请求超时，请稍后重试');
        }
        if (err2 instanceof TypeError && err2.message.includes('Failed to fetch')) {
          throw new Error('无法连接服务器，请检查网络');
        }
        throw err2;
      }
    }
  }

  /* ---- 单词相关 ---- */

  // 获取所有单词，支持 status / search 过滤
  // 返回值：单词数组 [{id, word, phonetic, ...}, ...]
  async getWords(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.search) qs.set('search', params.search);
    if (params.wordbook_id !== undefined && params.wordbook_id !== null && params.wordbook_id !== '') {
      qs.set('wordbook_id', params.wordbook_id);
    }
    if (params.starred) qs.set('starred', '1');
    const query = qs.toString();
    const res = await this.request('/words' + (query ? '?' + query : ''));
    // 后端返回 {success, data, total}，提取 data 数组
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 添加单个单词
  // 返回值：{success, data, source}
  async addWord(word, phonetic = '', meaning = '', wordbookId = null) {
    const payload = { word, phonetic, meaning };
    if (wordbookId && wordbookId !== '0' && wordbookId !== 0) payload.wordbook_id = wordbookId;
    const res = await this.request('/words', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    return res;  // 返回完整响应（含 source 字段）
  }

  // 批量添加单词（可选 wordbook_id 指定单词本）
  // 返回值：{success, added, skipped, failed, added_count, ...}
  async addWordsBatch(words, wordbookId) {
    const payload = { words };
    if (wordbookId && wordbookId !== '0' && wordbookId !== 0) payload.wordbook_id = wordbookId;
    const res = await this.request('/words/batch', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    return res;  // 返回完整响应
  }

  // 获取单词详情
  // 返回值：单词对象 {id, word, phonetic, meaning, split_data, morph_data, ...}
  async getWord(id) {
    const res = await this.request('/words/' + id);
    return res && res.data ? res.data : res;
  }

  // 更新单词
  updateWord(id, data) {
    return this.request('/words/' + id, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  // 批量更新单词状态
  batchUpdateStatus(wordIds, status) {
    return this.request('/words/batch-update-status', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds, status: status })
    });
  }

  // 切换单词重点标记
  toggleStar(wordId) {
    return this.request('/words/' + wordId + '/star', {
      method: 'POST'
    });
  }

  // 批量移动单词到词本
  batchMoveWords(wordIds, wordbookId) {
    return this.request('/words/batch-move', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds, wordbook_id: wordbookId })
    });
  }

  // 按文档顺序重排词本内单词，保证导入后顺序与用户原始文档一致
  reorderByNames(names, wordbookId) {
    const payload = { names };
    if (wordbookId) payload.wordbook_id = wordbookId;
    return this.request('/words/reorder-by-names', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // 自定义排序：按 wordIds 的顺序重新排列单词
  reorderWords(wordIds) {
    return this.request('/words/reorder', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds })
    });
  }

  // 批量删除单词
  batchDeleteWords(wordIds) {
    return this.request('/words/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds })
    });
  }

  // 删除单词
  deleteWord(id) {
    return this.request('/words/' + id, { method: 'DELETE' });
  }

  /* ---- OCR 相关 ---- */

  // OCR 识别（仅识别不添加）
  ocrRecognize(file) {
    const fd = new FormData();
    fd.append('image', file);
    return this.request('/ocr/recognize', { method: 'POST', body: fd });
  }

  // OCR 识别并添加
  ocrAddWords(file) {
    const fd = new FormData();
    fd.append('image', file);
    return this.request('/ocr/add-words', { method: 'POST', body: fd });
  }

  // 极速OCR扫描预览（OCR提取文字 + ECDICT查释义，不写入词库）
  ocrScanPreview(file) {
    const fd = new FormData();
    fd.append('image', file);
    return this.request('/ocr/scan-preview', { method: 'POST', body: fd });
  }

  // 查询当月OCR用量
  ocrUsage() {
    return this.request('/ocr/usage', { method: 'GET' });
  }

  /* ---- AI 视觉识别 ---- */

  // AI视觉识别图片中的单词（仅识别，返回单词+释义列表）
  async aiRecognizeImage(file) {
    // 将文件转为base64
    const base64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    return this.request('/ai/recognize-image', {
      method: 'POST',
      body: JSON.stringify({ image: base64 }),
    });
  }

  /* ---- 统计相关 ---- */

  // 获取统计数据
  // 返回值：{total, new, review, mastered, today_review, today_learned, history}
  // wordbookId: 按词书过滤（空=全部，0=未归类，具体id=该词书）
  async getStats(wordbookId) {
    const qs = (wordbookId !== undefined && wordbookId !== '') ? `?wordbook_id=${wordbookId}` : '';
    const res = await this.request('/stats' + qs);
    return res && res.data ? res.data : res;
  }

  /* ---- 复习相关 ---- */

  // 获取今日待复习单词
  // 返回值：单词数组
  // options.random: 随机排序
  async getReviewToday(wordbookId, options = {}) {
    let params = [];
    if (wordbookId !== '' && wordbookId !== undefined) params.push(`wordbook_id=${wordbookId}`);
    if (options.random) params.push('random=1');
    if (options.starred) params.push('starred=1');
    const qs = params.length > 0 ? '?' + params.join('&') : '';
    const res = await this.request('/review/today' + qs);
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 自主复习：获取所有已学过的单词（不受到期限制）
  // options.random: 随机排序
  async getReviewAll(wordbookId, options = {}) {
    let params = [];
    if (wordbookId !== '' && wordbookId !== undefined) params.push(`wordbook_id=${wordbookId}`);
    if (options.random) params.push('random=1');
    if (options.starred) params.push('starred=1');
    const qs = params.length > 0 ? '?' + params.join('&') : '';
    const res = await this.request('/review/all' + qs);
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 提交复习结果
  submitReview(id, rating) {
    return this.request('/review/' + id, {
      method: 'POST',
      body: JSON.stringify({ rating })
    });
  }

  /* ---- 学习相关 ---- */

  // 获取今日新词队列
  // 返回值：单词数组
  async getLearnToday(wordbookId, options = {}) {
    let params = [];
    if (wordbookId !== '' && wordbookId !== undefined) params.push(`wordbook_id=${wordbookId}`);
    if (options.random) params.push('random=1');
    if (options.exclude && options.exclude.length > 0) params.push(`exclude=${options.exclude.join(',')}`);
    if (options.limit) params.push(`limit=${options.limit}`);
    if (options.new_only) params.push('new_only=1');
    if (options.starred) params.push('starred=1');
    const qs = params.length > 0 ? '?' + params.join('&') : '';
    const res = await this.request('/learn/today' + qs);
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 获取随机干扰项（用于看词选义/看义选词模式）
  // word: 目标单词（用于 ECDICT 补充形近词干扰项）
  async getDistractors(word, wordbookId, excludeIds = [], limit = 3) {
    let params = [];
    if (word && word !== '') params.push(`word=${encodeURIComponent(word)}`);
    if (wordbookId !== '' && wordbookId !== undefined) params.push(`wordbook_id=${wordbookId}`);
    if (excludeIds.length > 0) params.push(`exclude=${excludeIds.join(',')}`);
    params.push(`limit=${limit}`);
    const qs = '?' + params.join('&');
    const res = await this.request('/words/distractors' + qs);
    return res && res.data ? res.data : [];
  }

  // 获取形近词干扰项（基于拼写相似度）
  async getSimilarDistractors(word, wordbookId, excludeIds = [], limit = 3) {
    let params = [`word=${encodeURIComponent(word)}`];
    if (wordbookId !== '' && wordbookId !== undefined) params.push(`wordbook_id=${wordbookId}`);
    if (excludeIds.length > 0) params.push(`exclude=${excludeIds.join(',')}`);
    params.push(`limit=${limit}`);
    const qs = '?' + params.join('&');
    const res = await this.request('/words/similar-distractors' + qs);
    return res && res.data ? res.data : [];
  }

  // 获取今天学过的所有单词
  async getTodayLearnedWords(wordbookId) {
    const qs = wordbookId !== '' && wordbookId !== undefined ? `?wordbook_id=${wordbookId}` : '';
    const res = await this.request('/learn/today-words' + qs);
    return res && res.data ? res.data : [];
  }

  // 获取日历统计数据
  async getCalendarStats() {
    const res = await this.request('/stats/calendar');
    return res && res.data ? res.data : [];
  }

  /* ---- 签到相关 ---- */

  // 每日签到
  async checkin() {
    const res = await this.request('/checkin', { method: 'POST' });
    return res;
  }

  // 获取签到状态
  async getCheckinStatus() {
    const res = await this.request('/checkin/status');
    return res && res.data ? res.data : { checked_in: false, streak_days: 0 };
  }

  // 获取设置
  async getSettings() {
    const res = await this.request('/settings');
    return res && res.data ? res.data : { daily_goal: 20 };
  }

  // 更新设置
  async updateSettings(data) {
    return this.request('/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // 清空所有单词
  async clearAllWords() {
    return this.request('/words/clear', { method: 'DELETE' });
  }

  // 文档导入预览（上传文件，返回提取的单词列表）
  async importPreview(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${this.baseURL}/import/preview`, {
      method: 'POST',
      body: formData,
    });
    return res.json();
  }

  // 确认导入单词（可选 wordbook_id 指定单词本）
  async importConfirm(words, wordbookId) {
    const payload = { words };
    if (wordbookId) payload.wordbook_id = wordbookId;
    return this.request('/import/confirm', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ===== 单词本 API =====
  async listWordbooks() {
    const res = await this.request('/wordbooks');
    return res && res.data ? res.data : [];
  }

  async createWordbook(data) {
    return this.request('/wordbooks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateWordbook(id, data) {
    return this.request(`/wordbooks/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteWordbook(id) {
    return this.request(`/wordbooks/${id}`, { method: 'DELETE' });
  }

  // ===== 全局词本 API =====
  async listGlobalWordbooks() {
    const res = await this.request('/global-wordbooks');
    return res && res.data ? res.data : [];
  }

  async shareWordbook(id) {
    return this.request(`/wordbooks/${id}/share`, { method: 'POST' });
  }

  async unshareWordbook(id) {
    return this.request(`/wordbooks/${id}/share`, { method: 'DELETE' });
  }

  async getGlobalWordbookWords(id) {
    const res = await this.request(`/global-wordbooks/${id}/words`);
    return res && res.data ? res.data : null;
  }

  async importGlobalWords(bookId, wordIds, targetWordbookId) {
    const payload = { word_ids: wordIds };
    if (targetWordbookId) payload.target_wordbook_id = targetWordbookId;
    return this.request(`/global-wordbooks/${bookId}/import`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // ===== 认证 API =====
  async register(username, password, nickname) {
    const payload = { username, password };
    if (nickname) payload.nickname = nickname;
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async login(username, password) {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  async logout() {
    return this.request('/auth/logout', { method: 'POST' });
  }

  async getMe() {
    return this.request('/auth/me');
  }

  // ===== 管理员 API =====
  async adminListUsers() {
    return this.request('/admin/users');
  }

  async adminGetUserWords(userId) {
    return this.request(`/admin/users/${userId}/words`);
  }

  async adminDeleteUser(userId) {
    return this.request(`/admin/users/${userId}`, { method: 'DELETE' });
  }

  async adminResetPassword(userId, newPassword) {
    return this.request('/admin/reset_user_password', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, new_password: newPassword }),
    });
  }

  async adminToggleUser(userId, isActive) {
    return this.request('/admin/toggle_user', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, is_active: isActive }),
    });
  }

  // ===== 个人信息 API =====
  async updateProfile(data) {
    return this.request('/auth/profile', { method: 'PUT', body: JSON.stringify(data) });
  }

  async changePassword(oldPassword, newPassword) {
    return this.request('/auth/change-password', {
      method: 'PUT',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
  }
}

// 创建全局 API 实例
const api = new WordAPI();

/* ====================================================
   认证状态管理
   ==================================================== */
let currentUser = null;  // 当前登录用户 {id, username, role, nickname}

/**
 * 检查登录状态：页面加载时调用
 * 已登录则隐藏登录弹窗，显示用户信息
 * 未登录则显示登录弹窗
 */
async function checkAuthStatus() {
  try {
    const res = await api.getMe();
    if (res && res.success && res.data) {
      currentUser = res.data;
      // 更新用户缓存
      saveUserCache(currentUser);
      onLoginSuccess();
      return true;
    }
    // 响应不正常，当作未登录
    throw new Error('未登录');
  } catch (e) {
    const errMsg = e.message || '';
    // 判断是「未登录」(401) 还是「网络错误」(服务器冷启动/不可达)
    if (errMsg.includes('401') || errMsg.includes('未登录')) {
      // 确实未登录：清除所有用户缓存，显示登录弹窗
      currentUser = null;
      clearAllUserDataCache();
      showLoginModal();
    } else {
      // 网络错误（服务器冷启动等）：保留缓存，不弹登录窗
      // 用户可继续查看缓存数据，后台重试
      console.log('Auth check failed (network):', errMsg);
    }
    return false;
  }
}

/** 显示登录弹窗 */
function showLoginModal() {
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.display = 'flex';
}

/** 隐藏登录弹窗 */
function hideLoginModal() {
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.display = 'none';
}

/** 登录成功后的统一处理 */
function onLoginSuccess() {
  hideLoginModal();
  // 更新设置页的用户名显示
  const settingsUserEl = document.getElementById('settingsUsername');
  if (settingsUserEl && currentUser) {
    settingsUserEl.textContent = currentUser.nickname || currentUser.username || '已登录';
  }
  // 填充个人信息表单
  const nicknameInput = document.getElementById('nicknameInput');
  const secQuestionInput = document.getElementById('secQuestionInput');
  const secAnswerInput = document.getElementById('secAnswerInput');
  if (nicknameInput && currentUser) nicknameInput.value = currentUser.nickname || '';
  if (secQuestionInput && currentUser) secQuestionInput.value = currentUser.security_question || '';
  if (secAnswerInput && currentUser) secAnswerInput.value = '';
  // 加载OCR用量
  loadOcrUsage();
  // 启动服务保活（每10分钟ping一次，防止Render冷启动超时）
  startKeepAlive();
  // 管理员显示管理 Tab
  const adminTab = document.querySelector('.tab-admin-only');
  if (adminTab) {
    adminTab.style.display = currentUser.role === 'admin' ? 'flex' : 'none';
  }
}

/** 加载并显示OCR用量 */
async function loadOcrUsage() {
  const el = document.getElementById('ocrUsageText');
  if (!el) return;
  try {
    const usage = await api.ocrUsage();
    if (usage && usage.success) {
      const isAdmin = usage.is_admin;
      const globalText = `全局 ${usage.global_count}/${usage.global_limit}`;
      const userText = isAdmin
        ? '管理员不限'
        : `个人 ${usage.user_count}/${usage.user_limit}`;
      el.textContent = `${globalText}（${userText}）｜每月重置`;
    } else {
      el.textContent = '无法获取';
    }
  } catch {
    el.textContent = '无法获取';
  }
}

/** 保持Render服务唤醒（每10分钟ping一次，防止冷启动超时） */
function startKeepAlive() {
  setInterval(async () => {
    try {
      await fetch('/api/ping', { method: 'GET', cache: 'no-store' });
    } catch (e) {
      // 静默失败，不打扰用户
    }
  }, 10 * 60 * 1000);
}

/** 处理登录 */
async function handleLogin() {
  const username = document.getElementById('loginUsername').value.trim();
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  errEl.style.display = 'none';

  if (!username || !password) {
    errEl.textContent = '请输入用户名和密码';
    errEl.style.display = 'block';
    return;
  }

  const btn = document.getElementById('btnLogin');
  btn.textContent = '登录中...';
  btn.disabled = true;

  try {
    const res = await api.login(username, password);
    if (res && res.success && res.data) {
      // 清除上一个用户的缓存（LocalStorage + Service Worker API 缓存）
      clearAllUserDataCache();
      currentUser = res.data;
      saveUserCache(currentUser); // 保存用户缓存，下次打开可秒显示
      onLoginSuccess();
      showToast('登录成功', 'success');
      renderHome();
    } else {
      errEl.textContent = (res && res.error) || '登录失败';
      errEl.style.display = 'block';
    }
  } catch (err) {
    errEl.textContent = err.message || '登录失败，请检查网络';
    errEl.style.display = 'block';
  } finally {
    btn.textContent = '登录';
    btn.disabled = false;
  }
}

/** 处理注册 */
async function handleRegister() {
  const username = document.getElementById('registerUsername').value.trim();
  const password = document.getElementById('registerPassword').value;
  const confirmPassword = document.getElementById('registerConfirmPassword').value;
  const nickname = document.getElementById('registerNickname').value.trim();
  const errEl = document.getElementById('registerError');
  errEl.style.display = 'none';

  if (!username || !password) {
    errEl.textContent = '请输入用户名和密码';
    errEl.style.display = 'block';
    return;
  }
  if (password.length < 6) {
    errEl.textContent = '密码至少需要6个字符';
    errEl.style.display = 'block';
    return;
  }
  if (password !== confirmPassword) {
    errEl.textContent = '两次密码不一致';
    errEl.style.display = 'block';
    return;
  }

  const btn = document.getElementById('btnRegister');
  btn.textContent = '注册中...';
  btn.disabled = true;

  try {
    const res = await api.register(username, password, nickname);
    if (res && res.success && res.data) {
      // 清除上一个用户的缓存（LocalStorage + Service Worker API 缓存）
      clearAllUserDataCache();
      currentUser = res.data;
      saveUserCache(currentUser); // 保存用户缓存
      onLoginSuccess();
      showToast('注册成功，欢迎加入', 'success');
      renderHome();
    } else {
      errEl.textContent = (res && res.error) || '注册失败';
      errEl.style.display = 'block';
    }
  } catch (err) {
    errEl.textContent = err.message || '注册失败，请检查网络';
    errEl.style.display = 'block';
  } finally {
    btn.textContent = '注册';
    btn.disabled = false;
  }
}

/** 退出登录 */
async function handleLogout() {
  try {
    await api.logout();
  } catch (e) { /* 忽略 */ }
  // 清除所有用户缓存（LocalStorage + Service Worker API 缓存）
  clearAllUserDataCache();
  currentUser = null;
  const settingsUserEl = document.getElementById('settingsUsername');
  if (settingsUserEl) settingsUserEl.textContent = '未登录';
  const adminTab = document.querySelector('.tab-admin-only');
  if (adminTab) adminTab.style.display = 'none';
  showLoginModal();
  showToast('已退出登录', 'info');
}

/* ====================================================
   签到功能
   ==================================================== */

/** 加载签到状态并更新UI */
async function loadCheckinStatus() {
  try {
    const res = await api.getCheckinStatus();
    updateCheckinUI(res.checked_in, res.streak_days);
  } catch (e) {
    console.warn('获取签到状态失败', e);
  }
}

/** 更新签到按钮UI */
function updateCheckinUI(checkedIn, streakDays) {
  const btn = $('#btnCheckin');
  const streakEl = $('#checkinStreak');
  if (!btn) return;

  if (checkedIn) {
    btn.textContent = '已签到';
    btn.classList.add('checked-in');
    btn.disabled = true;
    if (streakEl) {
      streakEl.textContent = `连续${streakDays}天`;
      streakEl.style.display = 'inline-block';
    }
  } else {
    btn.textContent = '签到';
    btn.classList.remove('checked-in');
    btn.disabled = false;
    if (streakEl) {
      streakEl.style.display = 'none';
    }
  }

  // 同时更新首页连续天数
  const streakNum = $('#streakNum');
  if (streakNum) streakNum.textContent = streakDays || 0;
}

/** 处理签到 */
async function handleCheckin() {
  const btn = $('#btnCheckin');
  if (!btn || btn.disabled) return;

  btn.textContent = '签到中...';
  btn.disabled = true;

  try {
    const res = await api.checkin();
    if (res && res.success) {
      updateCheckinUI(true, res.data.streak_days);
      if (res.already_checked_in) {
        showToast('今天已经签到过了', 'info');
      } else {
        showToast(res.message || '签到成功！', 'success');
      }
      // 刷新首页数据
      renderHome();
    } else {
      showToast((res && res.error) || '签到失败', 'error');
      btn.textContent = '签到';
      btn.disabled = false;
    }
  } catch (err) {
    showToast(err.message || '签到失败', 'error');
    btn.textContent = '签到';
    btn.disabled = false;
  }
}

/** 切换登录/注册 Tab */
function switchLoginTab(tab) {
  document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.login-tab[data-login-tab="${tab}"]`).classList.add('active');
  document.getElementById('loginForm').classList.toggle('active', tab === 'login');
  document.getElementById('registerForm').classList.toggle('active', tab === 'register');
}

/* ====================================================
   管理员页面渲染
   ==================================================== */
async function renderAdminPage() {
  const listEl = document.getElementById('adminUserList');
  if (!listEl) return;
  listEl.innerHTML = '<div class="empty-state"><p>加载中...</p></div>';

  try {
    const res = await api.adminListUsers();
    if (!res || !res.success || !res.data || res.data.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>暂无用户数据</p></div>';
      return;
    }

    listEl.innerHTML = res.data.map(user => `
      <div class="admin-user-card" data-user-id="${user.id}">
        <div class="admin-user-header">
          <span class="admin-user-name">${escapeHtml(user.nickname || user.username)}</span>
          <span class="admin-role-badge ${user.role}">${user.role === 'admin' ? '管理员' : '普通用户'}</span>
          ${!user.is_active ? '<span class="admin-role-badge" style="background:var(--danger);color:#fff;">已禁用</span>' : ''}
        </div>
        <div class="admin-user-stats">
          <div class="admin-stat-item">
            <span class="admin-stat-num">${user.word_count || 0}</span>
            <span class="admin-stat-label">总词数</span>
          </div>
          <div class="admin-stat-item">
            <span class="admin-stat-num">${user.mastered_count || 0}</span>
            <span class="admin-stat-label">已掌握</span>
          </div>
          <div class="admin-stat-item">
            <span class="admin-stat-num">${user.wordbook_count || 0}</span>
            <span class="admin-stat-label">词书数</span>
          </div>
        </div>
        <div class="admin-user-date">注册时间：${user.created_at ? user.created_at.substring(0, 10) : '未知'}</div>
        <div class="admin-user-info" style="font-size:12px;color:var(--text-tertiary);margin:4px 0;line-height:1.6;">
          <div>用户名：${escapeHtml(user.username)}</div>
          <div>安全问题：${escapeHtml(user.security_question || '未设置')}</div>
          <div>安全答案：${escapeHtml(user.security_answer || '未设置')}</div>
          <div>密码哈希：<code style="font-size:11px;word-break:break-all;">${escapeHtml(user.password_hash ? user.password_hash.substring(0, 32) + '...' : '无')}</code></div>
        </div>
        <div class="admin-user-actions">
          <button class="btn-secondary btn-sm admin-detail-btn" data-user-id="${user.id}">查看详情</button>
          <button class="btn-secondary btn-sm admin-reset-pwd-btn" data-user-id="${user.id}" data-username="${escapeHtml(user.username)}">重置密码</button>
          ${user.role !== 'admin' ? `<button class="btn-secondary btn-sm admin-toggle-btn" data-user-id="${user.id}" data-active="${user.is_active}">${user.is_active ? '禁用' : '启用'}</button>` : ''}
          ${user.role !== 'admin' ? `<button class="btn-danger btn-sm admin-delete-btn" data-user-id="${user.id}" data-username="${escapeHtml(user.username)}">删除账号</button>` : ''}
        </div>
        <div class="admin-user-detail" id="adminDetail_${user.id}"></div>
      </div>
    `).join('');

    // 绑定查看详情按钮
    listEl.querySelectorAll('.admin-detail-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        loadUserDetail(parseInt(btn.dataset.userId));
      });
    });
    // 绑定重置密码按钮
    listEl.querySelectorAll('.admin-reset-pwd-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const userId = parseInt(btn.dataset.userId);
        const username = btn.dataset.username;
        const newPwd = prompt(`重置用户「${username}」的密码：\n请输入新密码（至少6位）：`);
        if (!newPwd) return;
        if (newPwd.length < 6) { showToast('新密码至少6位', 'warning'); return; }
        try {
          btn.disabled = true;
          btn.textContent = '重置中...';
          await api.adminResetPassword(userId, newPwd);
          showToast(`已重置用户 ${username} 的密码`, 'success');
          btn.disabled = false;
          btn.textContent = '重置密码';
        } catch (err) {
          btn.disabled = false;
          btn.textContent = '重置密码';
          handleError(err);
        }
      });
    });
    // 绑定启用/禁用按钮
    listEl.querySelectorAll('.admin-toggle-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const userId = parseInt(btn.dataset.userId);
        const currentActive = btn.dataset.active === 'true';
        try {
          btn.disabled = true;
          await api.adminToggleUser(userId, !currentActive);
          showToast(!currentActive ? '已启用' : '已禁用', 'success');
          renderAdminPage();
        } catch (err) {
          btn.disabled = false;
          handleError(err);
        }
      });
    });
    // 绑定删除账号按钮
    listEl.querySelectorAll('.admin-delete-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const userId = parseInt(btn.dataset.userId);
        const username = btn.dataset.username;
        if (!confirm(`确定要删除用户「${username}」吗？\n该用户的所有单词、词书数据将被永久删除，不可恢复。`)) return;
        try {
          btn.disabled = true;
          btn.textContent = '删除中...';
          await api.adminDeleteUser(userId);
          showToast(`已删除用户 ${username}`, 'success');
          renderAdminPage();
        } catch (err) {
          btn.disabled = false;
          btn.textContent = '删除账号';
          handleError(err);
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = `<div class="empty-state"><p>加载失败：${escapeHtml(err.message)}</p></div>`;
  }
}

/** 加载用户详情（词书和近期单词） */
async function loadUserDetail(userId) {
  const detailEl = document.getElementById(`adminDetail_${userId}`);
  if (!detailEl) return;

  if (detailEl.classList.contains('active')) {
    detailEl.classList.remove('active');
    return;
  }

  detailEl.innerHTML = '<p style="color:var(--text-tertiary);font-size:13px;">加载中...</p>';
  detailEl.classList.add('active');

  try {
    const res = await api.adminGetUserWords(userId);
    if (!res || !res.success) {
      detailEl.innerHTML = '<p style="color:var(--danger);font-size:13px;">加载失败</p>';
      return;
    }
    const data = res.data;
    let html = '';

    // 词书列表
    if (data.wordbooks && data.wordbooks.length > 0) {
      html += '<div class="admin-wordbook-list">';
      data.wordbooks.forEach(wb => {
        html += `<span class="admin-wordbook-tag">${escapeHtml(wb.name)} (${wb.word_count || 0})</span>`;
      });
      html += '</div>';
    } else {
      html += '<p style="font-size:12px;color:var(--text-tertiary);margin-bottom:8px;">暂无词书</p>';
    }

    // 近期单词
    if (data.recent_words && data.recent_words.length > 0) {
      html += '<div class="admin-recent-words">';
      html += data.recent_words.slice(0, 20).map(w =>
        `<span style="display:inline-block;margin:2px 4px;padding:2px 8px;background:var(--bg-input);border-radius:6px;font-size:12px;">${escapeHtml(w.word)} <span style="color:var(--text-tertiary);">${escapeHtml((w.meaning || '').substring(0, 15))}</span></span>`
      ).join('');
      html += '</div>';
    } else {
      html += '<p style="font-size:12px;color:var(--text-tertiary);">暂无单词</p>';
    }

    detailEl.innerHTML = html;
  } catch (err) {
    detailEl.innerHTML = `<p style="color:var(--danger);font-size:13px;">${escapeHtml(err.message)}</p>`;
  }
}

/* ====================================================
   二、工具函数
   ==================================================== */

// DOM 选择器简写
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/**
 * Toast 提示
 * @param {string} msg - 提示文字
 * @param {string} type - 类型：success/error/warning/默认
 * @param {number} duration - 显示时长(ms)
 */
function showToast(msg, type = '', duration = 2200) {
  const container = $('#toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast' + (type ? ' ' + type : '');
  toast.textContent = msg;
  container.appendChild(toast);

  // 自动消失
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/**
 * 显示/隐藏加载状态
 */
function showLoading(text = '加载中...') {
  let mask = $('#loadingMask');
  if (!mask) {
    mask = document.createElement('div');
    mask.id = 'loadingMask';
    mask.className = 'loading-mask';
    mask.innerHTML = `<div class="loading-spinner"></div><div class="loading-text">${text}</div>`;
    document.body.appendChild(mask);
  } else {
    mask.querySelector('.loading-text').textContent = text;
  }
  mask.style.display = 'block';
}

function hideLoading() {
  const mask = $('#loadingMask');
  if (mask) mask.style.display = 'none';
  const prog = $('#importProgressMask');
  if (prog) { prog.style.display = 'none'; }
}

// 导入进度条：显示已处理/总数、百分比、当前批信息
function showImportProgress({ done, total, current }) {
  let prog = $('#importProgressMask');
  if (!prog) {
    prog = document.createElement('div');
    prog.id = 'importProgressMask';
    prog.className = 'import-progress-mask';
    prog.innerHTML = `
      <div class="import-progress-box">
        <div class="import-progress-title">正在导入单词</div>
        <div class="import-progress-bar"><div class="import-progress-fill"></div></div>
        <div class="import-progress-info">
          <span class="import-progress-pct">0%</span>
          <span class="import-progress-count">0/0</span>
        </div>
        <div class="import-progress-detail"></div>
      </div>`;
    document.body.appendChild(prog);
  }
  const pct = total > 0 ? Math.min(100, Math.round(done / total * 100)) : 0;
  prog.querySelector('.import-progress-fill').style.width = pct + '%';
  prog.querySelector('.import-progress-pct').textContent = pct + '%';
  prog.querySelector('.import-progress-count').textContent = `${Math.min(done, total)}/${total}`;
  prog.querySelector('.import-progress-detail').textContent = current || '';
  prog.style.display = 'flex';
}

/**
 * 统一错误处理
 */
function handleError(err) {
  hideLoading();
  console.error(err);
  const msg = err.message || '操作失败';
  showToast(msg, 'error', 4000);
}

function handleErrorWithRetry(err, retryFn) {
  hideLoading();
  console.error(err);
  const msg = err.message || '网络错误';
  // 显示带重试按钮的Toast
  const container = $('#toastContainer');
  if (!container) { showToast(msg, 'error'); return; }
  const toast = document.createElement('div');
  toast.className = 'toast toast-error';
  toast.style.cssText = 'display:flex;align-items:center;gap:12px;';
  toast.innerHTML = `<span style="flex:1">${escapeHtml(msg)}</span><button class="error-retry-btn" style="padding:4px 12px;font-size:12px;">重试</button>`;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  toast.querySelector('.error-retry-btn').addEventListener('click', () => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
    if (retryFn) retryFn();
  });
  setTimeout(() => {
    if (toast.parentNode) {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }
  }, 6000);
}

/**
 * 格式化时间戳为日期字符串
 */
function formatDate(ts) {
  if (!ts) return '未学习';
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/**
 * 获取状态中文
 */
function statusText(status) {
  return { new: '未学习', review: '复习中', mastered: '已掌握' }[status] || status;
}

/**
 * HTML 转义，防止 XSS
 */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Fisher-Yates 洗牌 */
function shuffleArray(arr) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/** 更新环形进度条 */
function updateProgressRing(current, total) {
  const ring = $('#learnProgressRing');
  const fill = $('#progressRingFill');
  const text = $('#progressRingText');
  if (!ring || !fill || !text) return;
  if (total === 0) {
    ring.style.display = 'none';
    return;
  }
  ring.style.display = 'inline-flex';
  const circumference = 2 * Math.PI * 15; // r=15
  const percent = Math.round((current / total) * 100);
  const offset = circumference - (percent / 100) * circumference;
  fill.style.strokeDasharray = circumference;
  fill.style.strokeDashoffset = offset;
  text.textContent = percent + '%';
}

/** 密码强度检测 */
function checkPasswordStrength(password) {
  let score = 0;
  if (password.length >= 6) score++;
  if (password.length >= 10) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  if (score <= 1) return { level: 'weak', text: '弱', bars: 1 };
  if (score <= 3) return { level: 'medium', text: '中', bars: 2 };
  return { level: 'strong', text: '强', bars: 3 };
}

/** 显示骨架屏 */
function showSkeleton(container, count = 5) {
  if (!container) return;
  let html = '';
  for (let i = 0; i < count; i++) {
    html += `<div class="skeleton-item">
      <div class="skeleton-bar short"></div>
      <div class="skeleton-bar long"></div>
      <div class="skeleton-bar medium"></div>
    </div>`;
  }
  container.innerHTML = html;
}

/** 下拉刷新 */
let pullRefreshState = { startY: 0, pulling: false };
function initPullRefresh() {
  const appContent = $('#appContent');
  const indicator = $('#pullRefreshIndicator');
  if (!appContent || !indicator) return;

  appContent.addEventListener('touchstart', (e) => {
    if (appContent.scrollTop === 0) {
      pullRefreshState.startY = e.touches[0].clientY;
      pullRefreshState.pulling = true;
    } else {
      pullRefreshState.pulling = false;
    }
  }, { passive: true });

  appContent.addEventListener('touchmove', (e) => {
    if (!pullRefreshState.pulling) return;
    const diff = e.touches[0].clientY - pullRefreshState.startY;
    if (diff > 100 && diff < 300) {
      indicator.style.display = 'flex';
      indicator.style.top = ((diff - 100) / 3) + 'px';
    }
  }, { passive: true });

  appContent.addEventListener('touchend', (e) => {
    if (!pullRefreshState.pulling) return;
    // 多选模式下禁用下拉刷新，避免选中状态丢失
    const multiBar = document.getElementById('multiSelectBar');
    if (multiBar && multiBar.style.display === 'flex') {
      indicator.style.display = 'none';
      pullRefreshState.pulling = false;
      return;
    }
    const diff = (e.changedTouches[0].clientY - pullRefreshState.startY);
    indicator.style.top = '';
    if (diff > 150) {
      indicator.classList.add('active', 'spinning');
      indicator.textContent = '';
      // 触发当前页面刷新
      const activePage = document.querySelector('.page.active');
      if (activePage) {
        const pageName = activePage.id.replace('page-', '');
        onPageEnter(pageName);
      }
      setTimeout(() => {
        indicator.classList.remove('active', 'spinning');
        indicator.style.display = 'none';
        indicator.textContent = '↓';
        showToast('已刷新', 'success');
      }, 1000);
    } else {
      indicator.style.display = 'none';
    }
    pullRefreshState.pulling = false;
  }, { passive: true });
}

/** 页面左右滑动切换 */
function initPageSwipe() {
  const pages = ['home', 'library', 'learn', 'review', 'stats', 'settings'];
  const appContent = $('#appContent');
  if (!appContent) return;
  let startX = 0, startY = 0, swipping = false;

  appContent.addEventListener('touchstart', (e) => {
    // 不在弹窗、卡片、输入框上才启用
    if (e.target.closest('.modal-overlay, .quiz-option, .flip-card, input, textarea, select, .word-item')) return;
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    swipping = true;
  }, { passive: true });

  appContent.addEventListener('touchend', (e) => {
    if (!swipping) return;
    swipping = false;
    const dx = e.changedTouches[0].clientX - startX;
    const dy = e.changedTouches[0].clientY - startY;
    // 水平滑动距离 > 80 且 垂直移动 < 40
    if (Math.abs(dx) < 80 || Math.abs(dy) > 40) return;
    const activePage = document.querySelector('.page.active');
    if (!activePage) return;
    const currentName = activePage.id.replace('page-', '');
    const idx = pages.indexOf(currentName);
    if (idx === -1) return;
    if (dx > 0 && idx > 0) {
      switchPage(pages[idx - 1]);
    } else if (dx < 0 && idx < pages.length - 1) {
      switchPage(pages[idx + 1]);
    }
  }, { passive: true });
}

/** 复习预估时间 */
function updateReviewEstimate(count) {
  const el = $('#reviewEstimate');
  if (!el) return;
  if (count === 0) {
    el.style.display = 'none';
    return;
  }
  // 预估每词约8秒
  const seconds = count * 8;
  const minutes = Math.ceil(seconds / 60);
  el.textContent = `${reviewAllMode ? '自主复习' : '今日到期'} ${count} 词 · 预计 ${minutes} 分钟`;
  el.style.display = 'block';
}

/**
 * 统一同步学习范围 UI（重点单词等）
 */
function updateLearnModeUI() {
  const tip = $('#learnModeTip');
  if (!tip) return;
  if (learnStarredOnly) {
    const bookName = learnWordbookId && learnWordbookId !== '0'
      ? (wordbooks.find(b => b.id === Number(learnWordbookId)) || {}).name
      : null;
    tip.innerHTML = '当前学习范围：<b>重点单词</b>' +
      (bookName ? `（${escapeHtml(bookName)} 内的收藏单词，与主词本分开）` : '（全部词本内的收藏单词）');
    tip.className = 'review-mode-tip active';
    tip.style.display = 'block';
  } else {
    tip.style.display = 'none';
  }
}

/**
 * 统一同步复习范围 UI：按钮文案/激活态 + 顶部说明条
 * 让用户清楚当前复习的是"今日到期"还是"所有学过的词"
 */
function updateReviewModeUI() {
  const btn = $('#btnReviewAll');
  if (btn) {
    btn.classList.toggle('active', reviewAllMode);
    btn.textContent = reviewAllMode ? '今日到期' : '自主复习';
  }
  const tip = $('#reviewModeTip');
  if (tip) {
    if (reviewStarredOnly) {
      const bookName = reviewWordbookId && reviewWordbookId !== '0'
        ? (wordbooks.find(b => b.id === Number(reviewWordbookId)) || {}).name
        : null;
      tip.innerHTML = '当前复习范围：<b>重点单词</b>' +
        (bookName ? `（${escapeHtml(bookName)} 内的收藏单词，与主词本分开）` : '（全部词本内的收藏单词）') +
        '，不受到期限制';
      tip.className = 'review-mode-tip';
      tip.style.display = 'block';
    } else if (reviewAllMode) {
      tip.innerHTML = '当前复习范围：<b>自主复习</b>（所有学过的单词，不受到期限制，随时可回顾）';
      tip.className = 'review-mode-tip active';
      tip.style.display = 'block';
    } else {
      tip.innerHTML = '当前复习范围：<b>今日到期</b>（按记忆曲线今天该复习的单词）';
      tip.className = 'review-mode-tip';
      tip.style.display = 'block';
    }
  }
}

/* ====================================================
   学习时长统计 & 正确率持久化
   ==================================================== */
let studyStartTime = null;  // 学习开始时间
let studyTimerInterval = null; // 计时器

function startStudyTimer() {
  studyStartTime = Date.now();
  if (studyTimerInterval) clearInterval(studyTimerInterval);
  studyTimerInterval = setInterval(updateStudyTimerDisplay, 1000);
}

function stopStudyTimer() {
  if (!studyStartTime) return;
  const elapsed = Math.floor((Date.now() - studyStartTime) / 1000); // 秒
  studyStartTime = null;
  if (studyTimerInterval) { clearInterval(studyTimerInterval); studyTimerInterval = null; }
  // 保存到当天的学习时长
  const today = new Date().toISOString().slice(0, 10);
  const key = `wordmemo_study_time_${today}`;
  const prev = parseInt(localStorage.getItem(key) || '0', 10);
  localStorage.setItem(key, prev + elapsed);
  // 更新总时长
  const totalTime = parseInt(localStorage.getItem('wordmemo_total_study_time') || '0', 10);
  localStorage.setItem('wordmemo_total_study_time', totalTime + elapsed);
}

function updateStudyTimerDisplay() {
  if (!studyStartTime) return;
  const elapsed = Math.floor((Date.now() - studyStartTime) / 1000);
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const timerEl = $('#studyTimer');
  if (timerEl) {
    timerEl.textContent = `${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}`;
  }
}

function getTodayStudyTime() {
  const today = new Date().toISOString().slice(0, 10);
  return parseInt(localStorage.getItem(`wordmemo_study_time_${today}`) || '0', 10);
}

function getTodayStudyTimeText() {
  const seconds = getTodayStudyTime();
  const minutes = Math.floor(seconds / 60);
  if (minutes > 0) return `${minutes}分钟`;
  return `${seconds}秒`;
}

// 正确率持久化
function incrementReviewWrongCount() {
  const today = new Date().toISOString().slice(0, 10);
  const key = `wordmemo_review_wrong_${today}`;
  const prev = parseInt(localStorage.getItem(key) || '0', 10);
  localStorage.setItem(key, prev + 1);
}

function getReviewAccuracyToday() {
  const today = new Date().toISOString().slice(0, 10);
  const wrongCount = parseInt(localStorage.getItem(`wordmemo_review_wrong_${today}`) || '0', 10);
  const totalReviewed = parseInt(localStorage.getItem(`wordmemo_review_total_${today}`) || '0', 10);
  if (totalReviewed === 0) return 100;
  return Math.max(0, Math.round((totalReviewed - wrongCount) / totalReviewed * 100));
}

// 安卓返回键处理
function initBackButtonHandler() {
  window.addEventListener('popstate', (e) => {
    // 如果有弹窗打开，先关弹窗
    const openModal = document.querySelector('.modal-overlay[style*="flex"]');
    if (openModal) {
      openModal.style.display = 'none';
      history.pushState(null, '', location.href);
      return;
    }
    // 如果不在首页，回到首页
    const activePage = document.querySelector('.page.active');
    if (activePage && activePage.id !== 'page-home') {
      switchPage('home');
      history.pushState(null, '', location.href);
      return;
    }
    // 在首页则退出
  });
  // 初始压入一个状态
  history.pushState(null, '', location.href);
}

// 单词去重检查
async function checkWordDuplicate(word, wordbookId) {
  try {
    const res = await api.request(`/api/words/check_duplicate?word=${encodeURIComponent(word)}&wordbook_id=${wordbookId || ''}`);
    return res && res.exists;
  } catch (e) {
    return false;
  }
}

/**
 * 单词发音
 * 优先使用 Android 原生 TTS（WebView 不支持 Web Speech API）
 * 回退到浏览器 Web Speech API
 * @param {string} word - 要发音的单词
 * @param {HTMLElement} [btn] - 触发按钮，用于播放动画
 */
function speakWord(word, btn) {
  if (!word) return;

  // 优先使用 Android 原生 TTS 引擎
  if (window.AndroidTTS && typeof window.AndroidTTS.isAvailable === 'function' && window.AndroidTTS.isAvailable()) {
    window.AndroidTTS.speak(word);
    if (btn) {
      btn.classList.add('speaking');
      setTimeout(() => btn.classList.remove('speaking'), 1500);
    }
    return;
  }

  // 回退到浏览器 Web Speech API
  if (!('speechSynthesis' in window)) {
    showToast('当前环境不支持语音播放', 'error');
    return;
  }
  // 停止正在播放的语音
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(word);
  utter.lang = 'en-US';
  utter.rate = 0.9;     // 稍微放慢，便于学习
  utter.pitch = 1;
  // 尝试选择英语语音
  const voices = window.speechSynthesis.getVoices();
  const enVoice = voices.find(v => v.lang.startsWith('en'));
  if (enVoice) utter.voice = enVoice;
  // 播放动画
  if (btn) {
    btn.classList.add('speaking');
    utter.onend = () => btn.classList.remove('speaking');
    utter.onerror = () => btn.classList.remove('speaking');
  }
  window.speechSynthesis.speak(utter);
}

/**
 * 生成单词卡片 HTML
 */
function wordItemHtml(word, index) {
  // 查找所属单词本
  const book = word.wordbook_id ? wordbooks.find(b => b.id === word.wordbook_id) : null;
  const bookTag = book ? `<span class="word-book-tag" style="border-color:${book.color}40;color:${book.color}">${escapeHtml(book.name)}</span>` : '';
  const num = index !== undefined ? `<span class="word-num">${index}</span>` : '';
  const starTag = word.is_starred ? `<span class="word-star-icon" title="重点单词">★</span>` : '';
  // 自定义顺序模式下，且在具体某个词本内，显示拖动排序手柄（长按拖动）
  const showReorder = librarySort === 'custom' && libraryWordbook !== '' && libraryWordbook !== '0';
  const reorderHandle = showReorder ? `
    <div class="reorder-handle" title="长按拖动排序" data-id="${word.id}">☰</div>` : '';
  return `
    <div class="word-item" data-id="${word.id}">
      ${num}
      <div class="word-info">
        <div class="word-text">
          ${word.phonetic ? `<span class="word-phonetic-sm">${escapeHtml(word.phonetic)}</span>` : ''}
          ${escapeHtml(word.word)}
          ${bookTag}
          ${starTag}
        </div>
        <div class="word-meaning">${escapeHtml(word.meaning || '暂无释义')}</div>
      </div>
      <span class="word-status ${word.status}">${statusText(word.status)}</span>
      ${reorderHandle}
    </div>
  `;
}

/* ====================================================
   三、页面切换逻辑
   ==================================================== */

// 页面标题映射
const PAGE_TITLES = {
  home: '背单词',
  input: '录入单词',
  library: '我的词库',
  learn: '学习',
  review: '复习',
  stats: '学习统计'
};

/**
 * 切换页面
 * @param {string} pageName - 页面名称
 */
function switchPage(pageName) {
  // 隐藏所有页面
  $$('.page').forEach(p => {
    p.classList.remove('active');
    // 移除动画类
    p.classList.remove('page-animating');
  });
  // 显示目标页面
  const target = $('#page-' + pageName);
  if (target) {
    target.classList.add('active');
    // 仅在页面切换时添加动画类（不在首次加载时）
    if (document.body.classList.contains('app-initialized')) {
      target.classList.add('page-animating');
    }
  }

  // 更新底部 TabBar 高亮
  $$('.tab-item').forEach(t => t.classList.remove('active'));
  const tab = $(`.tab-item[data-page="${pageName}"]`);
  if (tab) tab.classList.add('active');

  // 滚动到顶部
  $('#appContent').scrollTop = 0;
  window.scrollTo(0, 0);

  // 触发对应页面的数据加载
  onPageEnter(pageName);
}

/**
 * 页面进入时的回调，按需加载数据
 */
function onPageEnter(pageName) {
  switch (pageName) {
    case 'home':
      renderHome();
      // 进入首页时加载签到状态
      loadCheckinStatus();
      break;
    case 'library':
      loadWordbooks();
      renderLibrary();
      break;
    case 'learn':
      initLearnWordbookSelector();
      // 进入学习页时自动加载（必须已选词书）
      if (learnQueue.length === 0 && learnWordbookId !== '') loadLearnQueue();
      startStudyTimer(); // 开始计时
      // 显示计时器
      const timerDisplay = $('#studyTimerDisplay');
      if (timerDisplay) timerDisplay.style.display = 'flex';
      break;
    case 'review':
      // 复习词书仅在未设置时同步为学习词书
      if (!reviewWordbookId) {
        reviewWordbookId = learnWordbookId;
      }
      initReviewWordbookSelector();
      // 同步复习范围 UI
      updateReviewModeUI();
      if (reviewQueue.length === 0) loadReviewQueue();
      startStudyTimer(); // 开始计时
      // 显示计时器
      const reviewTimerDisplay = $('#studyTimerDisplay');
      if (reviewTimerDisplay) reviewTimerDisplay.style.display = 'flex';
      break;
    case 'input':
      // 进入录入页时刷新单词本下拉
      loadWordbooks();
      break;
    case 'stats':
      renderStats();
      break;
    case 'settings':
      loadSettings();
      break;
    case 'admin':
      renderAdminPage();
      break;
  }
  // 离开学习/复习页时停止计时
  if (pageName !== 'learn' && pageName !== 'review') {
    stopStudyTimer();
    const timerDisplay = $('#studyTimerDisplay');
    if (timerDisplay) timerDisplay.style.display = 'none';
  }
}

/* ====================================================
   四、首页渲染
   ==================================================== */

let homeStatsCache = null; // 缓存统计数据

async function renderHome() {
  try {
    // 通知 Service Worker 清空 API 缓存，确保拿到最新数据
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_API_CACHE' });
    }
    // 并行请求统计与今日单词（按当前选中词书过滤）
    const wbParam = learnWordbookId !== '' ? { wordbook_id: learnWordbookId } : {};
    const [stats, words] = await Promise.all([
      api.getStats(learnWordbookId),
      api.getWords(wbParam)
    ]);
    homeStatsCache = stats;

    // 更新欢迎语
    updateGreeting();

    // 连续天数（基于签到记录）
    $('#streakNum').textContent = stats.streak_days || 0;
    // 同步签到按钮状态
    updateCheckinUI(stats.checked_in, stats.streak_days);

    // 今日概览
    $('#todayLearned').textContent = stats.today_learned || 0;
    $('#todayReviewCount').textContent = stats.today_review || 0;
    // 待学 = 每日目标 - 今日已学（最低0）
    $('#todayNewCount').textContent = stats.pending_today !== undefined ? stats.pending_today : (stats.new || 0);

    // 操作按钮描述：显示每天计划学多少 + 还有多少待学/待复习
    const dailyGoal = stats.daily_goal || 20;
    const pendingToday = stats.pending_today !== undefined ? stats.pending_today : Math.max(0, dailyGoal - (stats.today_learned || 0));
    const newWordsLeft = stats.new || 0;
    if (newWordsLeft > 0) {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，还有${pendingToday}个待学`;
    } else if (pendingToday > 0) {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，词本已学完`;
    } else {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，今日已完成`;
    }
    $('#reviewDesc').textContent = `${stats.today_review || 0}个单词待复习`;

    // 统计卡片
    $('#statTotal').textContent = stats.total || 0;
    $('#statNew').textContent = stats.new || 0;
    $('#statReview').textContent = stats.review || 0;
    $('#statMastered').textContent = stats.mastered || 0;

    // 概览数字点击跳转
    bindOverviewClicks();
    // 统计卡片点击跳转
    bindStatCardClicks();

    // 学习曲线折线图
    // 后端 history 格式：[{date, count}, ...]，需转为数字数组
    const historyArr = (stats.history || []).map(h => h.count || 0);
    drawLineChart($('#homeLineChart'), historyArr);

    // 今日单词列表（显示全部，超出区域可滚动）
    const list = $('#todayWordList');
    if (words && words.length > 0) {
      list.innerHTML = words.map((word, i) => wordItemHtml(word, i + 1)).join('');
      // 绑定点击事件查看详情
      list.querySelectorAll('.word-item').forEach(item => {
        item.addEventListener('click', () => openWordDetail(item.dataset.id));
      });
    } else {
      list.innerHTML = '<div class="empty-state"><p>暂无单词，快去添加吧</p></div>';
    }

    // 保存到本地缓存，下次打开可秒显示
    saveHomeCache(stats, words);
  } catch (err) {
    handleError(err);
  }
}

/**
 * 轻量刷新首页统计数据（不重新拉取单词列表）
 * 在添加/删除单词后调用，确保首页数字实时更新
 * 会先清除 Service Worker 的 API 缓存，确保拿到最新数据
 */
async function refreshHomeStats() {
  // 通知 Service Worker 清空 API 缓存，确保下次请求拿到最新数据
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_API_CACHE' });
  }
  try {
    const stats = await api.getStats(learnWordbookId);
    homeStatsCache = stats;
    $('#todayLearned').textContent = stats.today_learned || 0;
    $('#todayReviewCount').textContent = stats.today_review || 0;
    $('#todayNewCount').textContent = stats.pending_today !== undefined ? stats.pending_today : (stats.new || 0);
    $('#statTotal').textContent = stats.total || 0;
    $('#statNew').textContent = stats.new || 0;
    $('#statReview').textContent = stats.review || 0;
    $('#statMastered').textContent = stats.mastered || 0;
    const dailyGoal = stats.daily_goal || 20;
    const pendingToday = stats.pending_today !== undefined ? stats.pending_today : Math.max(0, dailyGoal - (stats.today_learned || 0));
    const newWordsLeft = stats.new || 0;
    if (newWordsLeft > 0) {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，还有${pendingToday}个待学`;
    } else if (pendingToday > 0) {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，词本已学完`;
    } else {
      $('#learnDesc').textContent = `每天学${dailyGoal}个，今日已完成`;
    }
    $('#reviewDesc').textContent = `${stats.today_review || 0}个单词待复习`;
    // 更新学习曲线
    const historyArr = (stats.history || []).map(h => h.count || 0);
    drawLineChart($('#homeLineChart'), historyArr);
  } catch (e) {
    // 静默失败，不影响用户操作
    console.warn('刷新首页统计失败:', e);
  }
}

/**
 * 绑定首页概览数字点击跳转
 * 今日已学 → 学习页，待复习 → 复习页，待学 → 学习页
 */
function bindOverviewClicks() {
  const overviewItems = document.querySelectorAll('.overview-item');
  if (overviewItems.length >= 3) {
    // 今日已学 → 跳转学习页
    overviewItems[0].style.cursor = 'pointer';
    overviewItems[0].onclick = () => {
      learnQueue = [];
      switchPage('learn');
    };
    // 待复习 → 跳转复习页
    overviewItems[1].style.cursor = 'pointer';
    overviewItems[1].onclick = () => {
      reviewQueue = [];
      switchPage('review');
    };
    // 待学 → 跳转学习页
    overviewItems[2].style.cursor = 'pointer';
    overviewItems[2].onclick = () => {
      learnQueue = [];
      switchPage('learn');
    };
  }
}

/**
 * 跳转到词库并按指定状态筛选
 * status: all / new / review / mastered / starred
 */
function goLibraryWithFilter(status) {
  libraryFilter = status || 'all';
  // 同步筛选标签激活态
  $$('.filter-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.status === libraryFilter);
  });
  switchPage('library');
  renderLibrary();
}

/**
 * 绑定统计卡片点击跳转
 * 点击"未学习/复习中/已掌握"卡片 → 词库并只显示对应状态的单词
 * 总词数 → 词库(全部)
 */
function bindStatCardClicks() {
  const statCards = document.querySelectorAll('.stat-card');
  if (statCards.length >= 4) {
    statCards[0].style.cursor = 'pointer';
    statCards[0].onclick = () => goLibraryWithFilter('all');
    statCards[1].style.cursor = 'pointer';
    statCards[1].onclick = () => goLibraryWithFilter('new');
    statCards[2].style.cursor = 'pointer';
    statCards[2].onclick = () => goLibraryWithFilter('review');
    statCards[3].style.cursor = 'pointer';
    statCards[3].onclick = () => goLibraryWithFilter('mastered');
  }
}

/**
 * 根据时间更新问候语
 */
function updateGreeting() {
  const h = new Date().getHours();
  let greeting = '';
  if (h < 6) greeting = '夜深了，注意休息';
  else if (h < 12) greeting = '早上好，今天也要加油哦';
  else if (h < 14) greeting = '中午好，小憩一下吧';
  else if (h < 18) greeting = '下午好，继续背单词';
  else greeting = '晚上好，今天辛苦了';
  $('#greetingText').textContent = greeting;
}

/* ====================================================
   五、录入页逻辑
   ==================================================== */

/**
 * 切换录入方式面板
 */
function switchInputTab(tab) {
  $$('.tab-switch-item').forEach(t => t.classList.remove('active'));
  $(`.tab-switch-item[data-input-tab="${tab}"]`).classList.add('active');
  $$('.input-panel').forEach(p => p.classList.remove('active'));
  $('#panel-' + tab).classList.add('active');
}

// 手动添加
async function handleManualAdd() {
  const word = $('#manualWord').value.trim();
  const phonetic = $('#manualPhonetic').value.trim();
  const meaning = $('#manualMeaning').value.trim();
  const wordbookId = ($('#manualWordbookSelect') && $('#manualWordbookSelect').value) || '';

  if (!word) {
    showToast('请输入单词', 'warning');
    return;
  }

  // 去重检查（按所选词书范围）
  const isDup = await checkWordDuplicate(word, wordbookId);
  if (isDup) {
    showToast(`单词 "${word}" 已存在`, 'warning');
    return;
  }

  try {
    showLoading('添加中...');
    await api.addWord(word, phonetic, meaning, wordbookId || null);
    hideLoading();
    showToast('添加成功', 'success');

    // 清空输入框
    $('#manualWord').value = '';
    $('#manualPhonetic').value = '';
    $('#manualMeaning').value = '';
    // 实时刷新首页统计数据
    refreshHomeStats();
  } catch (err) {
    handleError(err);
  }
}

// 批量粘贴解析：按第一个中文字符分隔单词与释义，保留多词短语/句型
// 例如 "give up v. 放弃" -> {word:"give up", meaning:"放弃"}
function parseBatchLine(line) {
  const cnIdx = line.search(/[\u4e00-\u9fff]/);
  let word, meaning;
  if (cnIdx > 0) {
    word = line.slice(0, cnIdx).trim();
    meaning = line.slice(cnIdx).trim();
  } else {
    word = line.trim();
    meaning = '';
  }
  // 剥离尾部词性标记（如 "abandon v." -> "abandon"）
  word = word.replace(/\s+(?:n|v|vt|vi|adj|adv|ad|prep|conj|pron|num|art|int|interj|aux|modal|det|ger|part|colloc|phr|phrase)\.?\s*$/i, '');
  // 剥离尾部标点
  word = word.replace(/[\.\,\;\)\]\}\:\s]+$/, '').trim();
  return { word, meaning };
}

// 批量预览
let batchPreviewWords = [];
async function handleBatchPreview() {
  const text = $('#batchText').value.trim();
  if (!text) {
    showToast('请输入单词', 'warning');
    return;
  }
  const lines = text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  batchPreviewWords = lines.map(line => parseBatchLine(line)).filter(w => w.word);

  if (batchPreviewWords.length === 0) {
    showToast('未解析到有效单词', 'warning');
    return;
  }

  // 渲染预览列表
  const listEl = $('#batchPreviewList');
  listEl.innerHTML = batchPreviewWords.map((w, i) => `
    <div class="batch-preview-item" data-idx="${i}">
      <span class="batch-preview-word">${escapeHtml(w.word)}</span>
      <span class="batch-preview-meaning">${escapeHtml(w.meaning || '(无释义)')}</span>
      <button class="batch-preview-remove" data-idx="${i}">×</button>
    </div>
  `).join('');
  $('#batchPreviewCount').textContent = `${batchPreviewWords.length} 个单词`;
  $('#batchPreview').style.display = 'block';

  // 绑定删除按钮
  listEl.querySelectorAll('.batch-preview-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx);
      batchPreviewWords.splice(idx, 1);
      // 重新渲染
      listEl.innerHTML = batchPreviewWords.map((w, i) => `
        <div class="batch-preview-item" data-idx="${i}">
          <span class="batch-preview-word">${escapeHtml(w.word)}</span>
          <span class="batch-preview-meaning">${escapeHtml(w.meaning || '(无释义)')}</span>
          <button class="batch-preview-remove" data-idx="${i}">×</button>
        </div>
      `).join('');
      $('#batchPreviewCount').textContent = `${batchPreviewWords.length} 个单词`;
      listEl.querySelectorAll('.batch-preview-remove').forEach(b => {
        b.addEventListener('click', () => {
          const i2 = parseInt(b.dataset.idx);
          batchPreviewWords.splice(i2, 1);
          b.parentElement.remove();
          $('#batchPreviewCount').textContent = `${batchPreviewWords.length} 个单词`;
        });
      });
    });
  });
}

// 批量确认导入
async function handleBatchConfirm() {
  if (batchPreviewWords.length === 0) {
    showToast('没有可导入的单词', 'warning');
    return;
  }
  try {
    showLoading('批量添加中...');
    const batchWordbookId = ($('#batchWordbookSelect') || {}).value || null;
    const pureWords = batchPreviewWords.filter(w => !w.meaning).map(w => w.word);
    const withMeaning = batchPreviewWords.filter(w => w.meaning);
    let added = 0;
    if (pureWords.length > 0) {
      const res = await api.addWordsBatch(pureWords, batchWordbookId);
      added += (res && res.added) || (res && res.count) || pureWords.length;
    }
    for (const w of withMeaning) {
      try {
        await api.addWord(w.word, '', w.meaning, batchWordbookId);
        added++;
      } catch (e) { /* 单个失败继续 */ }
    }
    hideLoading();
    showToast(`成功添加 ${added} 个单词`, 'success');
    $('#batchText').value = '';
    $('#batchPreview').style.display = 'none';
    batchPreviewWords = [];
    // 实时刷新首页统计数据
    refreshHomeStats();
  } catch (err) {
    handleError(err);
  }
}

// 批量添加
async function handleBatchAdd() {
  const text = $('#batchText').value.trim();
  if (!text) {
    showToast('请输入单词', 'warning');
    return;
  }

  // 解析每行：支持 "word" 或 "word 释义" 格式（保留多词短语/句型）
  const lines = text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  const words = lines.map(line => parseBatchLine(line)).filter(w => w.word);

  if (words.length === 0) {
    showToast('未解析到有效单词', 'warning');
    return;
  }

  try {
    showLoading('批量添加中...');
    // 后端 batch 接口接收纯单词数组；带释义的逐个添加
    const pureWords = words.filter(w => !w.meaning).map(w => w.word);
    const withMeaning = words.filter(w => w.meaning);

    // 获取选择的单词本
    const batchWordbookId = ($('#batchWordbookSelect') || {}).value || null;

    let added = 0;
    if (pureWords.length > 0) {
      const res = await api.addWordsBatch(pureWords, batchWordbookId);
      added += (res && res.added) || (res && res.count) || pureWords.length;
    }
    for (const w of withMeaning) {
      try {
        await api.addWord(w.word, '', w.meaning, batchWordbookId);
        added++;
      } catch (e) { /* 单个失败继续 */ }
    }

    hideLoading();
    showToast(`成功添加 ${added} 个单词`, 'success');
    $('#batchText').value = '';
    // 实时刷新首页统计数据
    refreshHomeStats();
  } catch (err) {
    handleError(err);
  }
}

// ===== 文档导入 =====
let docPendingWords = []; // 待导入的单词列表（预览后暂存）

/**
 * 文档文件选择
 */
function handleDocFilePick() {
  $('#docFileInput').click();
}

/**
 * 文档选择变化
 */
async function handleDocFileChange(e) {
  const file = e.target.files[0];
  if (!file) return;
  await handleDocUpload(file);
  // 清空 input，允许再次选择同一文件
  e.target.value = '';
}

/**
 * 处理文档上传（解析+预览）
 */
async function handleDocUpload(file) {
  // 校验文件大小
  if (file.size > 20 * 1024 * 1024) {
    showToast('文件过大，最大支持 20MB', 'error');
    return;
  }
  // 校验扩展名
  const ext = file.name.toLowerCase().split('.').pop();
  if (!['txt', 'docx', 'xlsx', 'xls', 'pdf'].includes(ext)) {
    showToast('不支持的格式，请上传 txt/docx/xlsx/pdf', 'error');
    return;
  }

  try {
    showLoading('正在解析文档...');
    const res = await api.importPreview(file);
    hideLoading();

    if (!res.success) {
      showToast(res.error || '解析失败', 'error');
      return;
    }

    const data = res.data;
    docPendingWords = data.words || [];

    if (docPendingWords.length === 0) {
      showToast('未从文档中提取到有效单词', 'error');
      return;
    }

    // 渲染预览
    $('#docPreviewName').textContent = data.filename;
    $('#docPreviewCount').textContent = `共 ${docPendingWords.length} 个单词`;
    $('#docWordsList').innerHTML = docPendingWords
      .map(w => `<span class="doc-word-tag">${escapeHtml(w)}</span>`)
      .join('');
    $('#docPreview').style.display = 'block';
    $('#docResult').style.display = 'none';
    showToast(`提取到 ${docPendingWords.length} 个单词`, 'success');
  } catch (err) {
    hideLoading();
    console.error('[扫描识别] 失败:', err);
    const msg = err.message || 'AI识别失败';
    // 显示更详细的错误信息，持续6秒
    showToast(msg, 'error', 6000);
  }
}

/**
 * 取消文档导入
 */
function handleDocCancel() {
  $('#docPreview').style.display = 'none';
  $('#docResult').style.display = 'none';
  docPendingWords = [];
}

/**
 * 确认导入文档中的单词
 */
async function handleDocImport() {
  if (docPendingWords.length === 0) {
    showToast('没有可导入的单词', 'error');
    return;
  }
  // 获取选择的单词本 ID
  const wordbookId = $('#docWordbookSelect').value || null;
  // 分批导入，避免一次性提交 2000+ 词导致后端 AI 分析超时
  // 每批约 40 个：其中若有一半需 AI 分析，5 并发 × 3-8 秒 ≈ 数秒~十几秒，远低于 120s 长超时
  const BATCH_SIZE = 40;
  const total = docPendingWords.length;
  const batches = [];
  for (let i = 0; i < total; i += BATCH_SIZE) {
    batches.push(docPendingWords.slice(i, i + BATCH_SIZE));
  }

  let added = 0, skipped = 0, failed = 0;
  try {
    showImportProgress({ done: 0, total, current: '正在启动导入...' });

    // 并发池：同时提交 CONCURRENT 批，缩短总耗时；每批失败自动重试3次，仍失败计入失败并继续
    const CONCURRENT = 2;
    let nextIdx = 0;
    let processedWords = 0; // 已处理批次的累计词数（用于进度条）
    const stats = { added: 0, skipped: 0, failed: 0 };

    async function worker() {
      while (true) {
        const idx = nextIdx++;
        if (idx >= batches.length) break;
        const batch = batches[idx];
        let res = null;
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            res = await api.importConfirm(batch, wordbookId);
            if (res && res.success) break;
          } catch (e) {
            res = null;
          }
          if (attempt < 2) await new Promise(r => setTimeout(r, 1000));
        }
        if (!res || !res.success) {
          stats.failed += batch.length;
        } else {
          stats.added += res.data.added_count || 0;
          stats.skipped += res.data.skipped_count || 0;
          stats.failed += res.data.failed_count || 0;
        }
        processedWords += batch.length;
        showImportProgress({
          done: processedWords,
          total,
          current: `第 ${idx + 1}/${batches.length} 批：成功 ${stats.added}，跳过 ${stats.skipped}，失败 ${stats.failed}`
        });
        // 批次间短暂停顿，避免连续高频请求触发后端限流/超时
        await new Promise(r => setTimeout(r, 200));
      }
    }

    await Promise.all(Array.from({ length: CONCURRENT }, () => worker()));
    added = stats.added; skipped = stats.skipped; failed = stats.failed;

    // 全部批次完成后，按文档原始顺序整体重排，确保词本顺序与用户文档完全一致
    // （即使中途有批失败/漏词，重排后也会归位到文档对应位置，不会排到末尾）
    showImportProgress({ done: total, total, current: '正在按文档顺序整理词本...' });
    try {
      await api.reorderByNames(docPendingWords, wordbookId);
    } catch (reorderErr) {
      console.error('[导入] 按文档顺序重排失败:', reorderErr);
    }
    hideLoading();

    // 渲染汇总结果
    const resultHtml = `
      <div class="result-row">
        <span>成功导入</span>
        <span class="result-added">${added} 个</span>
      </div>
      ${skipped > 0 ? `
      <div class="result-row">
        <span>已存在跳过</span>
        <span class="result-skipped">${skipped} 个</span>
      </div>` : ''}
      ${failed > 0 ? `
      <div class="result-row">
        <span>导入失败</span>
        <span class="result-failed">${failed} 个</span>
      </div>` : ''}
    `;
    $('#docResult').innerHTML = resultHtml;
    $('#docResult').style.display = 'block';
    $('#docPreview').style.display = 'none';

    showToast(`成功导入 ${added} 个单词`, 'success');
    // 清空待导入列表
    docPendingWords = [];
    // 刷新单词本列表（更新计数）
    loadWordbooks();
    // 实时刷新首页统计数据
    refreshHomeStats();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 扫描录入：选择图片（点击空状态选图区域）
function handleScanPick() {
  // 只在空状态下触发选图，已有图片时通过"添加更多"按钮追加
  if (scanFiles.length === 0) {
    $('#scanInput').click();
  }
}

// 压缩图片：限制最长边和大小，避免上传超大原图导致超时/失败
// 手机拍照原图常达 5-12MB，直接上传到云端极易超时；压缩后既快又不失识别精度
// 质量用0.95以保证文字清晰可辨，避免过度压缩影响OCR/AI识别率
function compressScanImage(file, maxSize = 1920, quality = 0.95) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        try {
          let w = img.naturalWidth;
          let h = img.naturalHeight;
          if (w === 0 || h === 0) { resolve(file); return; }
          // 只有小尺寸且小体积的图片才直接透传，避免无谓解码开销
          // 高分辨率但体积小的图片（如 PNG）也要压缩，防止超过百度OCR的像素/体积上限
          const needsResize = Math.max(w, h) > maxSize;
          const needsRecompress = file.size > 1024 * 1024;
          if (!needsResize && !needsRecompress) { resolve(file); return; }
          if (needsResize) {
            if (w >= h) { h = Math.round(h * maxSize / w); w = maxSize; }
            else { w = Math.round(w * maxSize / h); h = maxSize; }
          }
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.fillStyle = '#ffffff';
          ctx.fillRect(0, 0, w, h);
          ctx.drawImage(img, 0, 0, w, h);
          canvas.toBlob((blob) => {
            if (blob && blob.size > 0) {
              const name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
              resolve(new File([blob], name, { type: 'image/jpeg' }));
            } else {
              resolve(file);
            }
          }, 'image/jpeg', quality);
        } catch (err) {
          console.error('[扫描] 图片压缩失败:', err);
          resolve(file);
        }
      };
      img.onerror = () => resolve(file);
      img.src = ev.target.result;
    };
    reader.onerror = () => resolve(file);
    reader.readAsDataURL(file);
  });
}

// 选择图片后的处理：累加到 scanFiles，不覆盖之前的
async function handleScanChange(e) {
  const files = Array.from(e.target.files || []);
  if (files.length === 0) return;
  // 逐张压缩（APK 拍照原图很大，压缩后上传更稳更快）
  const compressed = [];
  for (const f of files) {
    compressed.push(await compressScanImage(f));
  }
  // 累加到图片数组，支持不断追加
  scanFiles = scanFiles.concat(compressed);
  // 更新缩略图网格
  updateScanThumbs();
  // 清除上一次的识别结果
  scanRecognizedWords = [];
  $('#scanConfirm').style.display = 'none';
  $('#scanResult').style.display = 'none';
  // 重置 input value 允许重复选同一文件
  e.target.value = '';
}

// 渲染多图缩略图网格
function updateScanThumbs() {
  const scanArea = $('#scanArea');
  const thumbsBox = $('#scanThumbs');
  const thumbsList = $('#scanThumbsList');
  const actionsBar = $('#scanActions');

  if (scanFiles.length === 0) {
    scanArea.style.display = '';
    thumbsBox.style.display = 'none';
    actionsBar.style.display = 'none';
    return;
  }

  // 有图片时隐藏空状态选图区，显示缩略图网格和操作栏
  scanArea.style.display = 'none';
  thumbsBox.style.display = '';
  actionsBar.style.display = '';

  // 生成缩略图
  thumbsList.innerHTML = '';
  scanFiles.forEach((file, idx) => {
    const item = document.createElement('div');
    item.className = 'scan-thumb-item';

    const img = document.createElement('img');
    const reader = new FileReader();
    reader.onload = (ev) => { img.src = ev.target.result; };
    reader.readAsDataURL(file);
    item.appendChild(img);

    // 删除单张图片按钮
    const removeBtn = document.createElement('button');
    removeBtn.className = 'scan-thumb-remove';
    removeBtn.type = 'button';
    removeBtn.textContent = '×';
    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      scanFiles.splice(idx, 1);
      scanRecognizedWords = [];
      $('#scanConfirm').style.display = 'none';
      $('#scanResult').style.display = 'none';
      updateScanThumbs();
    });
    item.appendChild(removeBtn);

    thumbsList.appendChild(item);
  });
}

function resetScan() {
  scanFiles = [];
  scanRecognizedWords = [];
  $('#scanArea').style.display = '';
  $('#scanThumbs').style.display = 'none';
  $('#scanActions').style.display = 'none';
  $('#scanConfirm').style.display = 'none';
  $('#scanResult').style.display = 'none';
}

let scanFiles = []; // 多张图片文件数组
let scanRecognizedWords = []; // AI识别到的单词列表 [{word, meaning, checked}]
let scanMode = 'ocr'; // 扫描模式：'ocr'（极速OCR）或 'ai'（AI精准）

// AI/OCR识别图片中的单词
async function handleScanRecognize() {
  if (scanFiles.length === 0) {
    showToast('请先选择图片', 'warning');
    return;
  }
  try {
    const modeLabel = scanMode === 'ocr' ? 'OCR极速识别' : 'AI识别';
    // OCR模式并发5（快速），AI模式并发3（避免超时）
    const concurrency = scanMode === 'ocr' ? 5 : 3;
    // 计算预估时间：AI每张约20-30秒，OCR每张约2-3秒
    const estTime = scanMode === 'ocr'
      ? Math.ceil(scanFiles.length * 3)
      : Math.ceil(scanFiles.length * 25);
    showLoading(`${modeLabel}中... (1/${scanFiles.length}，约${estTime}秒)`);

    let allWords = [];
    let completed = 0;

    for (let i = 0; i < scanFiles.length; i += concurrency) {
      const batch = scanFiles.slice(i, i + concurrency);
      const batchResults = await Promise.all(batch.map(async (file, batchIdx) => {
        const globalIdx = i + batchIdx;
        try {
          const remTime = scanMode === 'ocr'
            ? Math.ceil((scanFiles.length - globalIdx) * 3)
            : Math.ceil((scanFiles.length - globalIdx) * 25);
          showLoading(`${modeLabel}中... (${globalIdx + 1}/${scanFiles.length}，约${remTime}秒)`);
          // 根据模式调用不同接口
          const res = scanMode === 'ocr'
            ? await api.ocrScanPreview(file)
            : await api.aiRecognizeImage(file);
          completed++;
          const remTime2 = scanMode === 'ocr'
            ? Math.ceil((scanFiles.length - completed) * 3)
            : Math.ceil((scanFiles.length - completed) * 25);
          showLoading(`${modeLabel}中... (${completed}/${scanFiles.length}，约${remTime2}秒)`);
          if (res && res.success && res.words) {
            return res.words;
          }
          return [];
        } catch (err) {
          console.error(`${modeLabel}第${globalIdx + 1}张图片失败:`, err);
          completed++;
          const errMsg = (err && err.message) || String(err);
          // OCR超限时提示切换AI模式
          if (err && err.quota_exceeded) {
            showToast('当月OCR识别次数已达上限，已自动切换到AI精准模式', 'warning');
            scanMode = 'ai';
            $$('.scan-mode-item').forEach(b => {
              b.classList.toggle('active', b.dataset.scanMode === 'ai');
            });
            const tip = $('#scanModeTip');
            if (tip) tip.textContent = '拍照或选择图片，AI视觉识别单词和手写内容（每张约20秒）';
            const recognizeBtn = $('#btnScanRecognize');
            if (recognizeBtn) recognizeBtn.textContent = 'AI识别';
          } else if (errMsg.includes('API Key未配置') || errMsg.includes('API Key not configured')) {
            showToast('OCR服务未配置API Key，请切换到AI精准模式', 'error');
            scanMode = 'ai';
            $$('.scan-mode-item').forEach(b => {
              b.classList.toggle('active', b.dataset.scanMode === 'ai');
            });
          } else if (errMsg.includes('超时')) {
            showToast(`${modeLabel}超时，请重试或切换到另一种模式`, 'error');
          } else if (errMsg.includes('失败')) {
            showToast(errMsg, 'error');
          }
          return [];
        }
      }));
      batchResults.forEach(words => { allWords = allWords.concat(words); });
    }

    if (allWords.length === 0) {
      hideLoading();
      showToast('未识别到单词，请尝试更清晰的图片', 'warning');
      return;
    }

    // 去重（按word字段）
    const uniqueWords = Array.from(new Map(allWords.map(w => [w.word, w])).values());

    hideLoading();

    // 转换为识别结果格式
    scanRecognizedWords = uniqueWords.map(w => ({
      word: w.word,
      meaning: w.meaning || '',
      checked: true,
      starred: false,
    }));

    if (scanRecognizedWords.length === 0) {
      showToast('未识别到有效单词', 'warning');
      return;
    }

    renderScanWords();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 渲染识别到的单词列表（可勾选、可编辑、可标记重点）
function renderScanWords() {
  const box = $('#scanConfirm');
  const list = $('#scanWordList');
  const countEl = $('#scanWordCount');

  if (scanRecognizedWords.length === 0) {
    box.style.display = 'none';
    showToast('未识别到单词', 'warning');
    return;
  }

  box.style.display = 'block';
  countEl.textContent = scanRecognizedWords.length;

  list.innerHTML = scanRecognizedWords.map((w, i) => `
    <div class="scan-word-item" data-index="${i}">
      <span class="scan-word-num">${i + 1}</span>
      <input type="checkbox" class="scan-word-check" ${w.checked ? 'checked' : ''} data-index="${i}">
      <span class="scan-word-star ${w.starred ? 'starred' : ''}" data-index="${i}" title="标记为重点">${w.starred ? '★' : '☆'}</span>
      <div class="scan-word-info">
        <input type="text" class="scan-word-edit" value="${escapeHtml(w.word)}" data-index="${i}" placeholder="单词">
        ${w.meaning
          ? `<input type="text" class="scan-meaning-edit" value="${escapeHtml(w.meaning)}" data-index="${i}" placeholder="释义">`
          : '<input type="text" class="scan-meaning-edit scan-word-meaning-empty" value="" data-index="' + i + '" placeholder="无释义（可手动输入）">'}
      </div>
    </div>
  `).join('');

  // 绑定勾选事件
  $$('.scan-word-check').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index);
      scanRecognizedWords[idx].checked = e.target.checked;
      updateScanCheckAllState();
    });
    // 阻止 checkbox 点击冒泡到行，避免双重切换
    cb.addEventListener('click', (e) => { e.stopPropagation(); });
  });

  // 点击整行切换勾选（提升移动端体验）
  $$('.scan-word-item').forEach(item => {
    item.addEventListener('click', (e) => {
      // 如果点的是输入框、星标或复选框，不处理
      if (e.target.tagName === 'INPUT' || e.target.classList.contains('scan-word-star')) return;
      const idx = parseInt(item.dataset.index);
      scanRecognizedWords[idx].checked = !scanRecognizedWords[idx].checked;
      const cb = item.querySelector('.scan-word-check');
      if (cb) cb.checked = scanRecognizedWords[idx].checked;
      updateScanCheckAllState();
    });
  });

  // 绑定重点标记事件
  $$('.scan-word-star').forEach(star => {
    star.addEventListener('click', (e) => {
      const idx = parseInt(e.target.dataset.index);
      scanRecognizedWords[idx].starred = !scanRecognizedWords[idx].starred;
      e.target.textContent = scanRecognizedWords[idx].starred ? '★' : '☆';
      e.target.classList.toggle('starred', scanRecognizedWords[idx].starred);
    });
  });

  // 绑定编辑事件
  $$('.scan-word-edit').forEach(input => {
    input.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index);
      scanRecognizedWords[idx].word = e.target.value.trim();
    });
  });
  $$('.scan-meaning-edit').forEach(input => {
    input.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index);
      scanRecognizedWords[idx].meaning = e.target.value.trim();
      e.target.classList.toggle('scan-word-meaning-empty', !e.target.value.trim());
    });
  });

  updateScanCheckAllState();
  // 添加"重新识别"按钮（如果不存在）
  const actionsDiv = document.querySelector('.scan-confirm-actions');
  if (actionsDiv && !$('#btnScanReset')) {
    const resetBtn = document.createElement('button');
    resetBtn.className = 'btn-secondary btn-sm';
    resetBtn.id = 'btnScanReset';
    resetBtn.textContent = '重新识别';
    resetBtn.style.marginRight = '8px';
    resetBtn.addEventListener('click', () => {
      resetScan();
    });
    actionsDiv.insertBefore(resetBtn, actionsDiv.firstChild);
  }
  $('#scanResult').style.display = 'none';
}

// 更新"全选"按钮状态
function updateScanCheckAllState() {
  const btn = $('#btnScanCheckAll');
  if (!btn) return;
  const allChecked = scanRecognizedWords.length > 0 && scanRecognizedWords.every(w => w.checked);
  btn.textContent = allChecked ? '取消全选' : '全选';
}

// 全选/取消全选
function handleScanCheckAll() {
  if (scanRecognizedWords.length === 0) return;
  const allChecked = scanRecognizedWords.every(w => w.checked);
  const newState = !allChecked;
  // 更新数据模型
  scanRecognizedWords.forEach(w => { w.checked = newState; });
  // 更新 DOM 中的复选框
  document.querySelectorAll('.scan-word-check').forEach(cb => {
    cb.checked = newState;
  });
  // 立即更新按钮文字
  const btn = $('#btnScanCheckAll');
  if (btn) {
    btn.textContent = newState ? '取消全选' : '全选';
  }
}

// 添加选中的单词到词库
async function handleScanAddSelected() {
  const selected = scanRecognizedWords.filter(w => w.checked);
  if (selected.length === 0) {
    showToast('请至少选择一个单词', 'warning');
    return;
  }

  const scanWordbookId = ($('#scanWordbookSelect') || {}).value || null;
  // 发送 {word, starred} 对象数组，支持重点标记
  const wordsToAdd = selected.map(w => ({ word: w.word, starred: w.starred || false, meaning: w.meaning || '' }));

  try {
    showLoading(`正在添加 ${selected.length} 个单词...`);
    const res = await api.addWordsBatch(wordsToAdd, scanWordbookId);
    hideLoading();
    const addedCount = res.added_count || (res.added || []).length;
    const skippedCount = res.skipped_count || (res.skipped || []).length;
    renderScanAddResult({
      added: addedCount,
      skipped: skippedCount,
      failed: res.failed_count || (res.failed || []).length,
      addedWords: res.added || [],
      skippedWords: res.skipped || [],
      words: selected,
    });
    // 显示成功提示
    if (addedCount > 0) {
      showToast(`成功添加 ${addedCount} 个单词${skippedCount > 0 ? `，${skippedCount}个已跳过` : ''}`, 'success');
    } else if (skippedCount > 0) {
      showToast(`${skippedCount} 个单词已存在，已跳过`, 'warning');
    }
    // 添加成功后清空图片和识别结果
    resetScan();
    // 实时刷新首页统计数据
    refreshHomeStats();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 渲染添加结果
function renderScanAddResult(res) {
  const box = $('#scanResult');
  box.style.display = 'block';

  const { added = 0, skipped = 0, failed = 0, addedWords = [] } = res;

  let html = '';
  if (added > 0) {
    html += `<p class="scan-result-summary scan-result-success">成功添加 ${added} 个单词</p>`;
  }
  if (skipped > 0) {
    html += `<p class="scan-result-summary scan-result-skip">${skipped} 个单词已存在，已跳过</p>`;
  }
  if (failed > 0) {
    html += `<p class="scan-result-summary scan-result-fail">${failed} 个单词添加失败</p>`;
  }

  if (addedWords.length > 0) {
    html += '<div class="scan-result-tags">' +
      addedWords.map(w => `<span class="scan-result-tag">${escapeHtml(w)}</span>`).join('') +
      '</div>';
  }

  box.innerHTML = html || '<p>没有添加任何单词</p>';

  if (added > 0) {
    showToast(`成功添加 ${added} 个单词`, 'success');
    // 刷新首页和词库
    renderHome();
    if ($('#page-library').classList.contains('active')) renderLibrary();
  }
}

/* ====================================================
   六、词库页渲染
   ==================================================== */

let libraryFilter = 'all';     // 当前筛选状态
let librarySearch = '';        // 当前搜索词
let libraryData = [];          // 词库数据缓存
let librarySort = 'added_desc'; // 当前排序方式
let libraryWordbook = '';      // 当前选中的单词本（''=全部, '0'=未归类, 数字=具体单词本）
let wordbooks = [];            // 单词本列表缓存
let editingWordbookId = null;  // 正在编辑的单词本 ID（null=新建）
let currentWordbookColor = '#4a7fff'; // 新建单词本时选中的颜色

/**
 * 对词库数据进行排序（前端排序，避免后端改动）
 */
function sortLibraryData(data) {
  const sorted = [...data];
  switch (librarySort) {
    case 'added_asc':
      sorted.sort((a, b) => new Date(a.added_at) - new Date(b.added_at));
      break;
    case 'word_asc':
      sorted.sort((a, b) => a.word.localeCompare(b.word));
      break;
    case 'word_desc':
      sorted.sort((a, b) => b.word.localeCompare(a.word));
      break;
    case 'review_desc':
      sorted.sort((a, b) => (b.review_count || 0) - (a.review_count || 0));
      break;
    case 'review_asc':
      sorted.sort((a, b) => (a.review_count || 0) - (b.review_count || 0));
      break;
    case 'next_review_asc':
      sorted.sort((a, b) => {
        if (!a.next_review) return 1;
        if (!b.next_review) return -1;
        return new Date(a.next_review) - new Date(b.next_review);
      });
      break;
    case 'custom':
      // 自定义顺序：按 sort_order 排列（用户手动调整），其次按添加时间
      sorted.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || (new Date(a.added_at) - new Date(b.added_at)));
      break;
    case 'added_desc':
    default:
      sorted.sort((a, b) => new Date(b.added_at) - new Date(a.added_at));
      break;
  }
  return sorted;
}

// ====== 词库多选模式 ======
let multiSelectIds = new Set();

/**
 * 自定义顺序：上移/下移某个单词
 * 在指定词本内，把该单词在自定义顺序中移动一位，并调用后端保存新顺序。
 * 注意：必须基于该词本【全部】单词排序（而非当前筛选后的部分视图），
 * 否则会把 sort_order 覆盖为只含可见单词的序号，破坏其他单词的顺序。
 */
async function moveWordInCustomOrder(wordId, delta) {
  if (!libraryWordbook || libraryWordbook === '0') {
    showToast('请先选择具体单词本', 'warning');
    return;
  }
  // 拉取该词本全部单词（不限状态），保证全局 sort_order 正确
  let fullList;
  try {
    fullList = await api.getWords({ wordbook_id: libraryWordbook });
  } catch (err) {
    handleError(err);
    return;
  }
  const ordered = [...fullList].sort(
    (a, b) => (a.sort_order || 0) - (b.sort_order || 0) || (new Date(a.added_at) - new Date(b.added_at))
  );
  const idx = ordered.findIndex(w => w.id === wordId);
  if (idx === -1) return;
  const newIdx = idx + delta;
  if (newIdx < 0 || newIdx >= ordered.length) {
    showToast(delta < 0 ? '已在最前面' : '已在最后面', 'warning');
    return;
  }
  // 交换位置
  const t = ordered[idx];
  ordered[idx] = ordered[newIdx];
  ordered[newIdx] = t;
  const wordIds = ordered.map(w => w.id);
  try {
    await api.reorderWords(wordIds);
    showToast('已调整顺序', 'success');
    // 重新加载词库，让最新顺序生效
    renderLibrary();
  } catch (err) {
    handleError(err);
  }
}

/* ====================================================
   自定义顺序：长按拖动排序
   ==================================================== */
let dragSortState = null;   // {handle, item, pointerId, startX, startY, activated, placeholder, shiftY}

function initDragReorder() {
  const list = $('#libraryList');
  if (!list) return;

  // 长按手柄开始拖动（兼容鼠标/触摸/触控笔）
  list.addEventListener('pointerdown', (e) => {
    const handle = e.target.closest('.reorder-handle');
    if (!handle) return;
    // 仅在自定义顺序 + 具体词本下生效
    if (librarySort !== 'custom' || libraryWordbook === '' || libraryWordbook === '0') return;
    const item = handle.closest('.word-item');
    if (!item) return;
    e.preventDefault();
    dragSortState = {
      handle,
      item,
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      activated: false,
      placeholder: null,
      shiftY: 0,
      timer: setTimeout(() => activateDragSort(), 450),
    };
  });

  list.addEventListener('pointermove', (e) => {
    if (!dragSortState || e.pointerId !== dragSortState.pointerId) return;
    const dx = e.clientX - dragSortState.startX;
    const dy = e.clientY - dragSortState.startY;
    // 长按期间移动超过阈值则取消（视为滚动）
    if (!dragSortState.activated && Math.hypot(dx, dy) > 10) {
      cancelDragSort();
      return;
    }
    if (dragSortState.activated) {
      e.preventDefault();
      onDragMove(e.clientY);
    }
  });

  list.addEventListener('pointerup', (e) => {
    if (!dragSortState || e.pointerId !== dragSortState.pointerId) return;
    finishDragSort();
  });
  list.addEventListener('pointercancel', () => cancelDragSort());
}

function activateDragSort() {
  if (!dragSortState) return;
  const { item, handle } = dragSortState;
  dragSortState.activated = true;
  // 计算手柄相对 item 的纵向偏移，使拖动时 item 顶部跟随手指
  const itemRect = item.getBoundingClientRect();
  const handleRect = handle.getBoundingClientRect();
  dragSortState.shiftY = handleRect.top - itemRect.top;
  // 插入占位元素
  const ph = document.createElement('div');
  ph.className = 'word-item-placeholder';
  ph.style.height = item.offsetHeight + 'px';
  item.parentNode.insertBefore(ph, item);
  dragSortState.placeholder = ph;
  item.classList.add('dragging');
  document.body.classList.add('dragging-active');
}

function onDragMove(clientY) {
  if (!dragSortState || !dragSortState.activated) return;
  const { item, placeholder, shiftY } = dragSortState;
  // 让被拖动的 item 跟随手指
  item.style.transform = `translateY(${clientY - dragSortState.startY - shiftY}px)`;
  item.style.pointerEvents = 'none';
  // 根据手指位置把占位元素移动到合适位置
  const list = $('#libraryList');
  const siblings = Array.from(list.querySelectorAll('.word-item:not(.dragging)'));
  let targetIndex = 0;
  for (let i = 0; i < siblings.length; i++) {
    const r = siblings[i].getBoundingClientRect();
    if (clientY > r.top + r.height / 2) targetIndex = i + 1;
  }
  if (targetIndex >= siblings.length) {
    list.appendChild(placeholder);
  } else {
    list.insertBefore(placeholder, siblings[targetIndex]);
  }
}

async function finishDragSort() {
  if (!dragSortState) return;
  clearTimeout(dragSortState.timer);
  const { item, placeholder, activated } = dragSortState;
  // 清理拖动态
  item.classList.remove('dragging');
  item.style.transform = '';
  item.style.pointerEvents = '';
  document.body.classList.remove('dragging-active');
  if (placeholder) placeholder.remove();
  const state = dragSortState;
  dragSortState = null;
  if (!activated) return;
  // 用占位元素的新位置计算新顺序（当前可见列表）
  const list = $('#libraryList');
  const newIds = Array.from(list.querySelectorAll('.word-item')).map(el => parseInt(el.getAttribute('data-id'), 10));
  const oldIds = libraryData.map(w => w.id);
  // 若顺序没变则不保存
  if (JSON.stringify(newIds) === JSON.stringify(oldIds)) {
    renderLibrary();
    return;
  }
  // 计算被拖动单词在可见列表中的位移量
  const draggedId = state.item.getAttribute('data-id');
  const draggedIdNum = parseInt(draggedId, 10);
  const oldIdx = oldIds.indexOf(draggedIdNum);
  const newIdx = newIds.indexOf(draggedIdNum);
  const delta = newIdx - oldIdx;
  if (!delta || !libraryWordbook || libraryWordbook === '0') {
    renderLibrary();
    return;
  }
  // 基于该词本【全部】单词移动，保证 sort_order 全局正确
  try {
    await moveWordInCustomOrder(draggedIdNum, delta);
  } catch (err) {
    handleError(err);
  }
}

function cancelDragSort() {
  if (!dragSortState) return;
  clearTimeout(dragSortState.timer);
  const { item, placeholder } = dragSortState;
  if (item) {
    item.classList.remove('dragging');
    item.style.transform = '';
    item.style.pointerEvents = '';
  }
  if (placeholder) placeholder.remove();
  document.body.classList.remove('dragging-active');
  dragSortState = null;
}

function enterMultiSelectMode(firstId) {
  // 如果已经在多选模式，切换该词的选中状态（而非重置）
  const existingBar = document.getElementById('multiSelectBar');
  if (existingBar && existingBar.style.display === 'flex') {
    const firstItem = document.querySelector(`.word-item[data-id="${firstId}"]`);
    toggleMultiSelect(firstId, firstItem);
    return;
  }
  multiSelectIds.clear();
  multiSelectIds.add(firstId);
  // 标记第一个为选中
  const firstItem = document.querySelector(`.word-item[data-id="${firstId}"]`);
  if (firstItem) firstItem.classList.add('multi-selected');
  // 显示多选操作栏
  showMultiSelectBar();
}

function showMultiSelectBar() {
  let bar = $('#multiSelectBar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'multiSelectBar';
    bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#fff;box-shadow:0 -2px 10px rgba(0,0,0,0.1);padding:12px 16px;display:flex;align-items:center;gap:8px;z-index:500;max-width:480px;margin:0 auto;flex-wrap:wrap;';
    bar.innerHTML = `
      <span id="multiSelectCount" style="font-size:14px;color:#333;flex:1;">已选 1 个</span>
      <button class="btn-secondary btn-sm" id="multiSelectAll">全选</button>
      <button class="btn-secondary btn-sm" id="multiSelectStatus">改状态</button>
      <button class="btn-primary btn-sm" id="multiSelectMove">移动词本</button>
      <button class="btn-secondary btn-sm" id="multiSelectDelete" style="color:#ef4444;border-color:#ef4444">删除</button>
      <button class="btn-secondary btn-sm" id="multiSelectCancel">取消</button>
    `;
    document.body.appendChild(bar);
    // 绑定事件
    $('#multiSelectCancel').addEventListener('click', exitMultiSelectMode);
    $('#multiSelectMove').addEventListener('click', openMultiMoveModal);
    $('#multiSelectDelete').addEventListener('click', handleMultiDelete);
    $('#multiSelectStatus').addEventListener('click', openMultiStatusModal);
    $('#multiSelectAll').addEventListener('click', selectAllWords);
  }
  bar.style.display = 'flex';
  updateMultiSelectCount();
}

function exitMultiSelectMode() {
  multiSelectIds.clear();
  document.querySelectorAll('.word-item.multi-selected').forEach(el => el.classList.remove('multi-selected'));
  const bar = $('#multiSelectBar');
  if (bar) bar.style.display = 'none';
}

function toggleMultiSelect(id, item) {
  if (multiSelectIds.has(id)) {
    multiSelectIds.delete(id);
    item.classList.remove('multi-selected');
  } else {
    multiSelectIds.add(id);
    item.classList.add('multi-selected');
  }
  updateMultiSelectCount();
  // 如果取消选了所有，退出多选
  if (multiSelectIds.size === 0) exitMultiSelectMode();
}

function updateMultiSelectCount() {
  const el = $('#multiSelectCount');
  if (el) el.textContent = `已选 ${multiSelectIds.size} 个`;
}

function selectAllWords() {
  // 选中当前列表中所有单词
  const allItems = document.querySelectorAll('.word-item[data-id]');
  const allBtn = $('#multiSelectAll');
  // 检查当前可见的所有单词是否都已选中
  const visibleIds = [];
  allItems.forEach(item => {
    const id = parseInt(item.getAttribute('data-id'), 10);
    if (!isNaN(id)) visibleIds.push(id);
  });
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => multiSelectIds.has(id));
  if (allVisibleSelected) {
    // 如果当前可见的全选了，点击则取消全选（清空所有选中）
    multiSelectIds.clear();
    document.querySelectorAll('.word-item.multi-selected').forEach(el => el.classList.remove('multi-selected'));
    if (allBtn) allBtn.textContent = '全选';
  } else {
    // 全选当前可见的
    visibleIds.forEach(id => multiSelectIds.add(id));
    allItems.forEach(item => item.classList.add('multi-selected'));
    if (allBtn) allBtn.textContent = '取消全选';
  }
  updateMultiSelectCount();
}

async function openMultiMoveModal() {
  if (multiSelectIds.size === 0) return;
  const select = $('#moveWordbookSelect');
  // 填充词本列表
  let html = '<option value="">未归类</option>';
  wordbooks.forEach(b => {
    html += `<option value="${b.id}">${escapeHtml(b.name)}（${b.word_count || 0}词）</option>`;
  });
  select.innerHTML = html;
  // 修改确认按钮行为
  $('#moveConfirmBtn').onclick = handleMultiMove;
  $('#moveWordbookModal').classList.add('active');
}

async function handleMultiMove() {
  if (multiSelectIds.size === 0) return;
  const targetWordbookId = $('#moveWordbookSelect').value;
  const wbId = targetWordbookId ? parseInt(targetWordbookId) : null;
  try {
    showLoading(`正在移动 ${multiSelectIds.size} 个单词...`);
    // 使用批量API一次性移动，避免逐个请求太慢
    const ids = Array.from(multiSelectIds);
    const res = await api.batchMoveWords(ids, wbId);
    const moved = res.moved || ids.length;
    const errors = res.errors || 0;
    hideLoading();
    showToast(`成功移动 ${moved} 个单词${errors > 0 ? `，${errors}个失败` : ''}`, 'success');
    closeMoveWordbookModal();
    exitMultiSelectMode();
    // 恢复确认按钮行为
    $('#moveConfirmBtn').onclick = handleMoveWordbook;
    // 刷新
    await loadWordbooks();
    if ($('#page-library').classList.contains('active')) renderLibrary();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

async function handleMultiDelete() {
  if (multiSelectIds.size === 0) return;
  if (!confirm(`确定删除选中的 ${multiSelectIds.size} 个单词吗？`)) return;
  try {
    showLoading('删除中...');
    // 使用批量API一次性删除
    const ids = Array.from(multiSelectIds);
    const res = await api.batchDeleteWords(ids);
    hideLoading();
    showToast('批量删除成功', 'success');
    exitMultiSelectMode();
    if ($('#page-library').classList.contains('active')) renderLibrary();
    if ($('#page-home').classList.contains('active')) renderHome();
    // 无论当前在哪个页面，都刷新首页统计数据（确保状态变更后同步）
    refreshHomeStats();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 批量修改单词状态
function openMultiStatusModal() {
  if (multiSelectIds.size === 0) return;
  // 创建弹窗
  let modal = $('#multiStatusModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'multiStatusModal';
    modal.className = 'modal-overlay';
    modal.style.alignItems = 'center';
    modal.innerHTML = `
      <div class="modal-content" style="max-width:340px;text-align:center;">
        <h3 style="margin:0 0 16px;font-size:18px;">修改单词状态</h3>
        <p style="color:#666;margin:0 0 20px;font-size:14px;">将选中的 <b id="multiStatusCount">0</b> 个单词改为：</p>
        <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px;">
          <button class="btn-primary" data-status="new" style="width:100%;">未学习</button>
          <button class="btn-secondary" data-status="review" style="width:100%;">复习中</button>
          <button class="btn-secondary" data-status="mastered" style="width:100%;">已掌握</button>
        </div>
        <button class="btn-secondary" id="multiStatusCancel" style="width:100%;">取消</button>
      </div>
    `;
    document.body.appendChild(modal);
    modal.querySelector('#multiStatusCancel').addEventListener('click', () => {
      modal.style.display = 'none';
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });
    modal.querySelectorAll('[data-status]').forEach(btn => {
      btn.addEventListener('click', () => {
        const st = btn.getAttribute('data-status');
        modal.style.display = 'none';
        handleMultiStatus(st);
      });
    });
  }
  modal.querySelector('#multiStatusCount').textContent = multiSelectIds.size;
  modal.style.display = 'flex';
}

async function handleMultiStatus(newStatus) {
  if (multiSelectIds.size === 0) return;
  const statusLabel = { new: '未学习', review: '复习中', mastered: '已掌握' }[newStatus] || newStatus;
  try {
    showLoading(`正在修改 ${multiSelectIds.size} 个单词状态...`);
    // 使用批量API一次性更新，避免逐个请求太慢
    const ids = Array.from(multiSelectIds);
    const res = await api.batchUpdateStatus(ids, newStatus);
    const updated = res.updated || ids.length;
    const errors = res.errors || 0;
    hideLoading();
    showToast(`成功修改 ${updated} 个单词为「${statusLabel}」${errors > 0 ? `，${errors}个失败` : ''}`, 'success');
    exitMultiSelectMode();
    if ($('#page-library').classList.contains('active')) renderLibrary();
    if ($('#page-home').classList.contains('active')) renderHome();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

async function renderLibrary() {
  try {
    // 恢复搜索框和筛选标签可见性（从全局词本切回时需要恢复）
    const pageLib = $('#page-library');
    if (pageLib) {
      const searchBar = pageLib.querySelector('.search-bar');
      const filterTabs = pageLib.querySelector('.filter-tabs');
      if (searchBar) searchBar.style.display = '';
      if (filterTabs) filterTabs.style.display = '';
    }
    // 用骨架屏代替全屏loading
    const list = $('#libraryList');
    if (list) showSkeleton(list, 6);
    // 更新排序提示：自定义顺序需要选中具体词本
    const sortHintEl = $('#sortHint');
    if (sortHintEl) {
      if (librarySort === 'custom' && (libraryWordbook === '' || libraryWordbook === '0')) {
        sortHintEl.textContent = '自定义排序需先在上方选择一个具体单词本';
        sortHintEl.style.display = 'inline-block';
      } else if (librarySort === 'custom') {
        sortHintEl.textContent = '长按单词右侧的 ☰ 手柄，上下拖动即可排序';
        sortHintEl.style.display = 'inline-block';
      } else {
        sortHintEl.style.display = 'none';
      }
    }
    const params = {};
    if (libraryFilter !== 'all' && libraryFilter !== 'starred') params.status = libraryFilter;
    if (libraryFilter === 'starred') params.starred = 1;
    if (librarySearch) params.search = librarySearch;
    if (libraryWordbook !== '') params.wordbook_id = libraryWordbook;

    const words = await api.getWords(params);
    libraryData = sortLibraryData(words || []);

    if (libraryData.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <p>${librarySearch || libraryFilter !== 'all' || libraryWordbook !== '' ? '没有符合条件的单词' : '词库空空如也'}</p>
          <p class="empty-sub">点击右下角 + 添加单词</p>
        </div>`;
      return;
    }

    list.innerHTML = libraryData.map((word, i) => wordItemHtml(word, i + 1)).join('');
    // 恢复多选选中状态（防止下拉刷新等重渲染后丢失）
    if (multiSelectIds.size > 0) {
      document.querySelectorAll('.word-item[data-id]').forEach(item => {
        const id = parseInt(item.getAttribute('data-id'), 10);
        if (multiSelectIds.has(id)) item.classList.add('multi-selected');
      });
    }
    // 绑定点击查看详情
    let multiSelectMode = false;
    let selectedIds = new Set();
    
    list.querySelectorAll('.word-item').forEach(item => {
      // 长按进入多选模式（改进版：同时支持 touch 和 mouse）
      let pressTimer = null;
      let isLongPress = false;
      let startX = 0, startY = 0;
      let triggered = false;

      // 触摸事件（移动端）
      item.addEventListener('touchstart', (e) => {
        // 点击拖动排序手柄时，不进入长按多选（避免与拖动排序冲突）
        if (e.target.closest('.reorder-handle')) return;
        triggered = false;
        if (e.touches.length > 0) {
          startX = e.touches[0].clientX;
          startY = e.touches[0].clientY;
        }
        pressTimer = setTimeout(() => {
          triggered = true;
          isLongPress = true;
          // 震动反馈
          if (navigator.vibrate) navigator.vibrate(50);
          // 视觉反馈
          item.style.background = '#e0e7ff';
          setTimeout(() => { item.style.background = ''; }, 300);
          enterMultiSelectMode(item.dataset.id);
        }, 500);
      }, { passive: true });
      
      item.addEventListener('touchend', (e) => {
        if (pressTimer) { clearTimeout(pressTimer); pressTimer = null; }
        // 如果是长按触发的，阻止后续 click 事件
        if (triggered) {
          e.preventDefault();
          isLongPress = false;
        }
      });
      
      item.addEventListener('touchmove', (e) => {
        if (pressTimer && e.touches.length > 0) {
          const dx = Math.abs(e.touches[0].clientX - startX);
          const dy = Math.abs(e.touches[0].clientY - startY);
          // 移动超过 10px 就取消长按（避免滚动时误触发）
          if (dx > 10 || dy > 10) {
            clearTimeout(pressTimer);
            pressTimer = null;
          }
        }
      }, { passive: true });
      
      // 桌面端右键进入多选
      item.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        enterMultiSelectMode(item.dataset.id);
      });
      
      // 鼠标长按（桌面端测试用）
      let mouseTimer = null;
      item.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return; // 只处理左键
        // 点击拖动排序手柄时，不进入长按多选（避免与拖动排序冲突）
        if (e.target.closest('.reorder-handle')) return;
        triggered = false;
        mouseTimer = setTimeout(() => {
          triggered = true;
          enterMultiSelectMode(item.dataset.id);
        }, 500);
      });
      item.addEventListener('mouseup', (e) => {
        if (mouseTimer) { clearTimeout(mouseTimer); mouseTimer = null; }
        if (triggered) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
      item.addEventListener('mouseleave', () => {
        if (mouseTimer) { clearTimeout(mouseTimer); mouseTimer = null; }
      });
      
      // 点击事件
      item.addEventListener('click', (e) => {
        // 点击拖动排序手柄时，不打开详情
        if (e.target.closest('.reorder-handle')) { e.stopPropagation(); return; }
        // 如果是长按触发的，跳过本次 click
        if (triggered) {
          triggered = false;
          return;
        }
        // 检查是否在多选模式
        if ($('#multiSelectBar') && $('#multiSelectBar').style.display === 'flex') {
          e.stopPropagation();
          toggleMultiSelect(item.dataset.id, item);
        } else {
          openWordDetail(item.dataset.id);
        }
      });
    });
  } catch (err) {
    handleError(err);
  }
}

/**
 * 加载单词本列表并渲染筛选条
 */
async function loadWordbooks() {
  try {
    wordbooks = await api.listWordbooks();
    renderWordbookBar();
    // 同步更新文档导入页的下拉
    renderDocWordbookSelect();
  } catch (err) {
    console.warn('加载单词本失败', err);
  }
}

// 初始化学习页词书选择器
function initLearnWordbookSelector() {
  const select = $('#learnWordbookSelect');
  if (!select) return;
  let html = '<option value="">请选择词书</option>';
  wordbooks.forEach(b => {
    const total = b.word_count || 0;
    const learned = b.learned_count || 0;
    const newCnt = b.new_count !== undefined ? b.new_count : (total - learned);
    html += `<option value="${b.id}" ${learnWordbookId === String(b.id) ? 'selected' : ''}>${escapeHtml(b.name)}（已学${learned}/${total}）</option>`;
  });
  select.innerHTML = html;
  if (learnWordbookId !== '') {
    select.value = learnWordbookId;
  }
}

// 初始化复习页词书选择器
function initReviewWordbookSelector() {
  const select = $('#reviewWordbookSelect');
  if (!select) return;
  let html = '<option value="">请选择词书</option>';
  wordbooks.forEach(b => {
    const total = b.word_count || 0;
    const learned = b.learned_count || 0;
    html += `<option value="${b.id}" ${reviewWordbookId === String(b.id) ? 'selected' : ''}>${escapeHtml(b.name)}（已学${learned}/${total}）</option>`;
  });
  select.innerHTML = html;
  if (reviewWordbookId !== '') {
    select.value = reviewWordbookId;
  }
}

/**
 * 渲染词库页的单词本筛选条
 */
function renderWordbookBar() {
  const bar = $('#wordbookBar');
  if (!bar) return;
  // 固定的前两项 + 全局词本 + 单词本列表 + 加号
  let html = `
    <button class="wordbook-chip ${libraryWordbook === '' ? 'active' : ''}" data-wordbook="">全部</button>
    <button class="wordbook-chip ${libraryWordbook === '0' ? 'active' : ''}" data-wordbook="0">未归类</button>
    <button class="wordbook-chip ${libraryWordbook === 'global' ? 'active' : ''}" data-wordbook="global" style="border-color:#10b98140;color:#10b981">🌐 全局词本</button>
  `;
  if (wordbooks.length > 0) {
    html += `<span class="wordbook-chip-sep"></span>`;
    wordbooks.forEach(b => {
      const active = String(libraryWordbook) === String(b.id) ? 'active' : '';
      const total = b.word_count || 0;
      const learned = b.learned_count || 0;
      const progress = total > 0 ? `${learned}/${total}` : '';
      const count = total !== undefined ? `<span class="chip-count">${progress}</span>` : '';
      const sharedIcon = b.is_shared ? ' 🔗' : '';
      html += `<button class="wordbook-chip ${active}" data-wordbook="${b.id}" style="${active ? `border-color:${b.color};background:${b.color}` : `border-color:${b.color}40; color:${b.color}`}">${escapeHtml(b.name)}${sharedIcon}${count}</button>`;
    });
  }
  html += `<span class="wordbook-chip-sep"></span>`;
  html += `<button class="wordbook-chip wordbook-add" id="btnAddWordbook" title="新建单词本">+</button>`;
  // 选中具体单词本时显示编辑按钮
  const selectedBook = wordbooks.find(b => String(b.id) === String(libraryWordbook));
  if (selectedBook) {
    html += `<button class="wordbook-chip wordbook-edit" id="btnEditWordbook" title="编辑当前单词本">✎ 编辑</button>`;
  }
  bar.innerHTML = html;

  // 绑定 chip 点击
  bar.querySelectorAll('.wordbook-chip[data-wordbook]').forEach(chip => {
    chip.addEventListener('click', () => {
      libraryWordbook = chip.dataset.wordbook;
      localStorage.setItem('wordmemo_library_wordbook', libraryWordbook);
      renderWordbookBar();
      if (libraryWordbook === 'global') {
        renderGlobalWordbookView();
      } else {
        renderLibrary();
      }
    });
    // 长按编辑（移动端）
    let pressTimer = null;
    chip.addEventListener('touchstart', (e) => {
      const wbId = chip.dataset.wordbook;
      if (!wbId || wbId === '0' || wbId === 'global') return;
      pressTimer = setTimeout(() => {
        e.preventDefault();
        const book = wordbooks.find(b => String(b.id) === String(wbId));
        if (book) openWordbookModal(book);
      }, 600);
    });
    chip.addEventListener('touchend', () => { if (pressTimer) clearTimeout(pressTimer); });
    chip.addEventListener('touchmove', () => { if (pressTimer) clearTimeout(pressTimer); });
  });
  // 新建按钮
  const addBtn = bar.querySelector('#btnAddWordbook');
  if (addBtn) addBtn.addEventListener('click', () => openWordbookModal());
  // 编辑按钮
  const editBtn = bar.querySelector('#btnEditWordbook');
  if (editBtn && selectedBook) {
    editBtn.addEventListener('click', () => openWordbookModal(selectedBook));
  }
}

/* ====================================================
   全局词本（分享/导入）功能
   ==================================================== */

/**
 * 渲染全局词本视图：显示所有已分享的单词本列表
 */
async function renderGlobalWordbookView() {
  const list = $('#libraryList');
  if (!list) return;
  list.innerHTML = '<div class="empty-state"><p>加载全局词本...</p></div>';

  // 隐藏搜索框和筛选标签（全局词本不需要）
  const searchBar = list.parentElement.querySelector('.search-bar');
  const filterTabs = list.parentElement.querySelector('.filter-tabs');
  if (searchBar) searchBar.style.display = 'none';
  if (filterTabs) filterTabs.style.display = 'none';

  try {
    const globalBooks = await api.listGlobalWordbooks();
    if (!globalBooks || globalBooks.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <p>全局词本暂无内容</p>
          <p class="empty-sub">分享你的单词本到全局词本，供其他用户使用</p>
        </div>`;
      return;
    }

    list.innerHTML = globalBooks.map(book => {
      const total = book.word_count || 0;
      const learned = book.learned_count || 0;
      const ownerTag = book.is_owner ? '<span class="global-owner-tag">我的</span>' : `<span class="global-owner-tag global-owner-other">${escapeHtml(book.owner_name || '未知')}</span>`;
      return `
        <div class="global-wordbook-card" data-id="${book.id}">
          <div class="global-wordbook-info">
            <div class="global-wordbook-name">${escapeHtml(book.name)} ${ownerTag}</div>
            <div class="global-wordbook-desc">${escapeHtml(book.description || '暂无描述')}</div>
            <div class="global-wordbook-stats">
              <span>${total} 个单词</span>
              <span>已学 ${learned}</span>
            </div>
          </div>
          <button class="btn-primary btn-sm global-view-btn" data-id="${book.id}">查看</button>
        </div>
      `;
    }).join('');

    // 绑定查看按钮
    list.querySelectorAll('.global-view-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openGlobalWordbookDetail(parseInt(btn.dataset.id));
      });
    });
    list.querySelectorAll('.global-wordbook-card').forEach(card => {
      card.addEventListener('click', () => openGlobalWordbookDetail(parseInt(card.dataset.id)));
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state"><p>加载失败：${escapeHtml(err.message || '未知错误')}</p></div>`;
  }
}

/**
 * 打开全局词本详情弹窗：显示单词列表 + 导入按钮
 */
async function openGlobalWordbookDetail(bookId) {
  const modal = $('#globalWordbookModal');
  const titleEl = $('#globalWordbookModalTitle');
  const listEl = $('#globalWordbookList');
  if (!modal || !listEl) return;

  modal.classList.add('active');
  titleEl.textContent = '加载中...';
  listEl.innerHTML = '<div class="empty-state"><p>加载单词列表...</p></div>';

  try {
    const data = await api.getGlobalWordbookWords(bookId);
    if (!data) {
      listEl.innerHTML = '<div class="empty-state"><p>加载失败</p></div>';
      return;
    }

    const book = data.wordbook;
    const words = data.words || [];
    titleEl.textContent = book.name + (book.is_owner ? '（我的）' : `（${book.owner_name}）`);

    // 存储当前查看的全局词本ID
    modal.dataset.bookId = bookId;
    modal.dataset.isOwner = book.is_owner ? '1' : '0';

    if (words.length === 0) {
      listEl.innerHTML = '<div class="empty-state"><p>该词本暂无单词</p></div>';
      return;
    }

    listEl.innerHTML = words.map((word, i) => `
      <div class="word-item" data-id="${word.id}">
        <span class="word-num">${i + 1}</span>
        <div class="word-content">
          <div class="word-text">${escapeHtml(word.word)}</div>
          <div class="word-meaning">${escapeHtml(word.meaning || '暂无释义')}</div>
        </div>
      </div>
    `).join('');

    // 更新导入按钮区域
    const importArea = $('#globalWordbookImportArea');
    if (importArea) {
      if (book.is_owner) {
        // 所有者：显示取消分享按钮
        importArea.innerHTML = `
          <button class="btn-secondary" id="btnUnshareGlobal">取消分享</button>
          <span class="global-import-tip">这是你分享的词本，其他用户可以导入其中的单词</span>
        `;
        const unshareBtn = $('#btnUnshareGlobal');
        if (unshareBtn) {
          unshareBtn.addEventListener('click', () => handleUnshareWordbook(bookId));
        }
      } else {
        // 非所有者：显示导入按钮 + 目标词本选择
        const wordbookOptions = wordbooks.map(b =>
          `<option value="${b.id}">${escapeHtml(b.name)}</option>`
        ).join('');
        importArea.innerHTML = `
          <select class="form-input global-import-select" id="globalImportTarget">
            <option value="">导入到未归类</option>
            ${wordbookOptions}
          </select>
          <button class="btn-primary" id="btnImportAll">全部导入</button>
          <button class="btn-secondary" id="btnImportSelected">导入选中</button>
        `;
        const importAllBtn = $('#btnImportAll');
        if (importAllBtn) {
          importAllBtn.addEventListener('click', () => handleImportGlobalWords(bookId, null));
        }
        const importSelectedBtn = $('#btnImportSelected');
        if (importSelectedBtn) {
          importSelectedBtn.addEventListener('click', () => {
            const selectedIds = Array.from(listEl.querySelectorAll('.word-item.multi-selected'))
              .map(el => parseInt(el.dataset.id));
            if (selectedIds.length === 0) {
              showToast('请先长按选择单词', 'info');
              return;
            }
            handleImportGlobalWords(bookId, selectedIds);
          });
        }
        // 绑定长按多选
        listEl.querySelectorAll('.word-item').forEach(item => {
          let pressTimer = null;
          item.addEventListener('touchstart', (e) => {
            pressTimer = setTimeout(() => {
              item.classList.toggle('multi-selected');
              if (navigator.vibrate) navigator.vibrate(50);
            }, 500);
          }, { passive: true });
          item.addEventListener('touchend', () => { if (pressTimer) clearTimeout(pressTimer); });
          item.addEventListener('touchmove', () => { if (pressTimer) clearTimeout(pressTimer); });
          // 桌面端点击切换
          item.addEventListener('click', (e) => {
            if (listEl.querySelector('.word-item.multi-selected')) {
              item.classList.toggle('multi-selected');
            }
          });
        });
      }
    }
  } catch (err) {
    listEl.innerHTML = `<div class="empty-state"><p>加载失败：${escapeHtml(err.message || '未知错误')}</p></div>`;
  }
}

/**
 * 处理导入全局词本单词
 */
async function handleImportGlobalWords(bookId, wordIds) {
  const targetSelect = $('#globalImportTarget');
  const targetWordbookId = targetSelect ? targetSelect.value : '';

  try {
    showLoading();
    const res = await api.importGlobalWords(bookId, wordIds || [], targetWordbookId || null);
    hideLoading();
    if (res && res.success) {
      showToast(res.message || `导入完成：新增 ${res.added} 个单词`, 'success');
      // 刷新词库
      if (libraryWordbook !== 'global') renderLibrary();
      // 关闭弹窗
      closeGlobalWordbookModal();
    } else {
      showToast((res && res.error) || '导入失败', 'error');
    }
  } catch (err) {
    hideLoading();
    showToast(err.message || '导入失败', 'error');
  }
}

/**
 * 处理取消分享
 */
async function handleUnshareWordbook(bookId) {
  if (!confirm('确定取消分享该单词本吗？其他用户将无法再查看此词本。')) return;
  try {
    showLoading();
    const res = await api.unshareWordbook(bookId);
    hideLoading();
    if (res && res.success) {
      showToast('已取消分享', 'success');
      closeGlobalWordbookModal();
      // 刷新词本列表（更新分享图标）
      await loadWordbooks();
      renderGlobalWordbookView();
    } else {
      showToast((res && res.error) || '操作失败', 'error');
    }
  } catch (err) {
    hideLoading();
    showToast(err.message || '操作失败', 'error');
  }
}

/** 关闭全局词本详情弹窗 */
function closeGlobalWordbookModal() {
  const modal = $('#globalWordbookModal');
  if (modal) modal.classList.remove('active');
}

/**
 * 处理分享/取消分享单词本（在编辑弹窗中触发）
 */
async function handleToggleShare() {
  if (!editingWordbookId) return;
  const book = wordbooks.find(b => String(b.id) === String(editingWordbookId));
  if (!book) return;

  try {
    showLoading();
    if (book.is_shared) {
      // 取消分享
      const res = await api.unshareWordbook(editingWordbookId);
      hideLoading();
      if (res && res.success) {
        showToast('已取消分享', 'success');
        await loadWordbooks();
        // 更新弹窗中的分享按钮状态
        updateShareButtonState(false);
      } else {
        showToast((res && res.error) || '操作失败', 'error');
      }
    } else {
      // 分享
      const res = await api.shareWordbook(editingWordbookId);
      hideLoading();
      if (res && res.success) {
        showToast('已分享到全局词本', 'success');
        await loadWordbooks();
        updateShareButtonState(true);
      } else {
        showToast((res && res.error) || '操作失败', 'error');
      }
    }
  } catch (err) {
    hideLoading();
    showToast(err.message || '操作失败', 'error');
  }
}

/** 更新编辑弹窗中的分享按钮状态 */
function updateShareButtonState(isShared) {
  const btn = $('#wordbookShareBtn');
  if (!btn) return;
  if (isShared) {
    btn.textContent = '取消分享';
    btn.classList.add('btn-share-active');
  } else {
    btn.textContent = '分享到全局词本';
    btn.classList.remove('btn-share-active');
  }
}

/**
 * 渲染文档导入页和批量粘贴页的单词本下拉
 */
function renderDocWordbookSelect() {
  const html = `<option value="">默认（不归类）</option>` + wordbooks.map(b =>
    `<option value="${b.id}">${escapeHtml(b.name)}（${b.word_count || 0}词）</option>`
  ).join('');
  const docSel = $('#docWordbookSelect');
  if (docSel) docSel.innerHTML = html;
  const batchSel = $('#batchWordbookSelect');
  if (batchSel) batchSel.innerHTML = html;
  const scanSel = $('#scanWordbookSelect');
  if (scanSel) scanSel.innerHTML = html;
  const manualSel = $('#manualWordbookSelect');
  if (manualSel) manualSel.innerHTML = html;
}

/**
 * 打开单词本弹窗（新建或编辑）
 */
function openWordbookModal(book = null) {
  editingWordbookId = book ? book.id : null;
  const delBtn = $('#wordbookDeleteBtn');
  const shareBtn = $('#wordbookShareBtn');
  if (book) {
    $('#wordbookModalTitle').textContent = '编辑单词本';
    $('#wordbookNameInput').value = book.name || '';
    $('#wordbookDescInput').value = book.description || '';
    currentWordbookColor = book.color || '#4a7fff';
    if (delBtn) delBtn.style.display = '';  // 编辑时显示删除
    // 显示分享按钮并更新状态
    if (shareBtn) {
      shareBtn.style.display = '';
      updateShareButtonState(book.is_shared);
    }
  } else {
    $('#wordbookModalTitle').textContent = '新建单词本';
    $('#wordbookNameInput').value = '';
    $('#wordbookDescInput').value = '';
    currentWordbookColor = '#4a7fff';
    if (delBtn) delBtn.style.display = 'none';  // 新建时隐藏删除
    if (shareBtn) shareBtn.style.display = 'none';  // 新建时隐藏分享
  }
  // 更新颜色选中态
  $$('.color-dot').forEach(dot => {
    dot.classList.toggle('active', dot.dataset.color === currentWordbookColor);
  });
  $('#wordbookModal').classList.add('active');
  setTimeout(() => $('#wordbookNameInput').focus(), 200);
}

/**
 * 删除当前编辑的单词本
 */
async function handleDeleteWordbook() {
  if (!editingWordbookId) return;
  if (!confirm('确定删除该单词本吗？其中的单词不会被删除，会移到"未归类"。')) return;
  try {
    showLoading();
    const res = await api.deleteWordbook(editingWordbookId);
    hideLoading();
    if (res.success) {
      showToast('单词本已删除', 'success');
      closeWordbookModal();
      // 如果当前筛选的就是被删单词本，切回全部
      if (String(libraryWordbook) === String(editingWordbookId)) libraryWordbook = '';
      await loadWordbooks();
      renderLibrary();
    } else {
      showToast(res.error || '删除失败', 'error');
    }
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

/**
 * 关闭单词本弹窗
 */
function closeWordbookModal() {
  $('#wordbookModal').classList.remove('active');
  editingWordbookId = null;
}

/**
 * 保存单词本（新建或更新）
 */
async function handleSaveWordbook() {
  const name = $('#wordbookNameInput').value.trim();
  if (!name) {
    showToast('请输入单词本名称', 'error');
    return;
  }
  const description = $('#wordbookDescInput').value.trim();
  const data = { name, description, color: currentWordbookColor };
  try {
    showLoading();
    let res;
    if (editingWordbookId) {
      res = await api.updateWordbook(editingWordbookId, data);
    } else {
      res = await api.createWordbook(data);
    }
    hideLoading();
    if (res.success) {
      showToast(editingWordbookId ? '单词本已更新' : '单词本已创建', 'success');
      closeWordbookModal();
      await loadWordbooks();
    } else {
      showToast(res.error || '保存失败', 'error');
    }
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

/* ====================================================
   七、翻卡学习逻辑
   ==================================================== */

let learnWordbookId = '';  // 学习选中的词书ID，空=全部，0=未归类，具体数字=词本ID
let reviewWordbookId = ''; // 复习选中的词书ID（自动同步为学习词书）
let learnQueue = [];      // 今日学习队列
let learnIndex = 0;       // 当前索引
let learnFlipped = false; // 当前卡片是否翻转
let learnMode = 'flip';   // 学习模式：flip 翻卡 / choice 看词选义 / spell 拼写默写
let quizAnswered = false; // 测验题是否已作答（防止重复点击）
let learnedIds = new Set(); // 已标记为"已学会"的单词 ID，避免返回上一题后重复 submitReview
let autoNextTimer = null;   // 自动下一题的定时器（用于取消）
let learnRandomMode = false; // 学习随机模式：false=按顺序，true=随机（从设置页读取）
let reviewRandomMode = false; // 复习随机模式：false=按时间排序（昨天先于更早），true=随机
let learnStarredOnly = false; // 学习：仅看重点单词
let reviewStarredOnly = false; // 复习：仅看重点单词
let allLearnedIds = new Set(); // 本次学习会话中所有已学的单词ID（用于"已学会"标记）
let loadedWordIds = new Set(); // 当前会话中已加载到队列的单词ID（用于"加入新词"排除）
let learnSessionMode = 'new'; // 学习会话模式：new=未学习学习 / review_today=翻今天所有
let learnShuffleMode = false; // 学习页翻卡顺序：false=顺序，true=随机（仅打乱当前队列）
let learnOriginalQueue = []; // 保存原始顺序队列，用于切回顺序模式
let learnCompleteNotified = false; // 今日学习全部完成是否已提示（避免重复弹提示）

// 看词选义正确率统计（仅看词选义模式）
let learnChoiceCorrect = 0;   // 学习模式答对数
let learnChoiceTotal = 0;     // 学习模式总答题数
let reviewChoiceCorrect = 0;  // 复习模式答对数
let reviewChoiceTotal = 0;    // 复习模式总答题数

// 当前看义选词的完整选项缓存 [{word, meaning}]，用于答错时展示每个选项对应的释义
// （ECDICT 形近词干扰项不在队列里，必须用渲染时缓存的数据）
let reverseOptionsCache = [];

// 加载学习队列：返回词书内所有单词（未学习优先），按添加顺序分批
// append=true 时为"加入未学习"模式，只加载没学过的词(new状态)，追加到队列末尾
async function loadLearnQueue(append = false, addCount = null) {
  // 必须选择词书才能学习（重点学习/未选词书时例外：重点学习可复习全部词书的重点词）
  if (!learnWordbookId && learnWordbookId !== '0' && !learnStarredOnly) {
    showToast('请先选择一本词书再开始学习', 'error');
    return;
  }
  try {
    showLoading();
    learnSessionMode = 'new';
    const options = {
      random: learnRandomMode,
    };
    if (learnStarredOnly) options.starred = true;
    if (append) {
      // 加入未学习：只加载没学过的词(new状态)，排除已加载的
      options.new_only = true;
      options.exclude = Array.from(loadedWordIds);
      if (addCount) {
        options.limit = addCount;
      }
    }
    const res = await api.getLearnToday(learnWordbookId, options);
    const newWords = Array.isArray(res) ? res : (res.words || res.data || []);
    if (append) {
      // 加入未学习：只翻新加的词，替换队列（不拼接旧词）
      learnQueue = newWords;
      learnIndex = 0;
    } else {
      // 首次加载：替换队列
      learnQueue = newWords;
      learnIndex = 0;
      learnedIds = new Set();
      learnCompleteNotified = false; // 重置今日完成提示
      // 重置看词选义正确率
      learnChoiceCorrect = 0;
      learnChoiceTotal = 0;
    }
    // 记录已加载的单词ID
    if (!append) {
      loadedWordIds = new Set();
    }
    newWords.forEach(w => loadedWordIds.add(w.id));
    // 保存原始顺序，用于随机/顺序切换
    learnOriginalQueue = [...learnQueue];
    // 如果当前是随机模式，打乱队列
    if (learnShuffleMode && learnQueue.length > 1) {
      learnQueue = shuffleArray([...learnQueue]);
      learnIndex = 0;
    }
    if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
    hideLoading();
    if (newWords.length === 0) {
      if (append) {
        showToast('没有更多未学习的词了，这本词书已全部学完', 'info');
      } else if (learnStarredOnly) {
        showToast('暂无待学重点单词，可在词库中为单词标记★', 'info');
      } else if (learnSessionMode === 'review_today') {
        showToast('今天还没有学过的单词', 'info');
      } else {
        showToast('当前词书没有待学单词', 'info');
      }
    } else if (append) {
      showToast(`已加入 ${newWords.length} 个未学习单词`, 'success');
    }
    renderLearnCard();
    // 加入新词后自动刷新首页统计（非阻塞，不影响当前学习体验）
    if (append) {
      renderHome().catch(() => {});
    }
  } catch (err) {
    handleError(err);
  }
}

/**
 * 翻今天所有单词：加载今天学过的所有单词
 * 使用 /api/learn/today-words API，按当前词书过滤
 */
async function loadTodayAllWords() {
  try {
    showLoading();
    learnSessionMode = 'review_today';
    const res = await api.getTodayLearnedWords(learnWordbookId);
    const words = Array.isArray(res) ? res : (res.data || []);
    learnQueue = words;
    learnIndex = 0;
    learnedIds = new Set();
    // 保存原始顺序
    learnOriginalQueue = [...learnQueue];
    // 如果当前是随机模式，打乱队列
    if (learnShuffleMode && learnQueue.length > 1) {
      learnQueue = shuffleArray([...learnQueue]);
    }
    if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
    hideLoading();
    if (learnQueue.length === 0) {
      showToast('今天还没有学过的单词', 'info');
    }
    renderLearnCard();
  } catch (err) {
    handleError(err);
  }
}

// 渲染当前学习卡片
function renderLearnCard() {
  // 取消任何挂起的自动下一题
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
  const total = learnQueue.length;

  // 队列为空：显示空状态
  if (total === 0) {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnReverseCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'none';
    $('#learnExtraActions').style.display = 'none';
    $('#quizActions').style.display = 'none';
    $('#learnEmpty').style.display = 'block';
    $('#learnProgress').textContent = `0 / 0`;
    updateProgressRing(0, 0);
    const learnBadge = $('#learnStarBadge');
    if (learnBadge) learnBadge.style.display = 'none';
    return;
  }

  // 所有模式都循环：翻完从头再来
  if (learnIndex >= total) {
    learnIndex = 0;
  }

  const word = learnQueue[learnIndex];
  // 当前词是否为重点单词：显示/隐藏重点角标
  const learnBadge = $('#learnStarBadge');
  if (learnBadge) learnBadge.style.display = word.is_starred ? 'inline-block' : 'none';
  $('#learnProgress').textContent = `${learnIndex + 1} / ${total}`;
  // 更新环形进度条
  updateProgressRing(learnIndex + 1, total);
  $('#learnEmpty').style.display = 'none';

  // 根据模式显示对应卡片
  if (learnMode === 'flip') {
    $('#learnCard').style.display = 'block';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnReverseCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'flex';
    $('#learnExtraActions').style.display = 'flex';
    $('#quizActions').style.display = 'none';
    renderFlipCard(word);
  } else if (learnMode === 'choice') {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'flex';
    $('#learnReverseCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'none';
    $('#learnExtraActions').style.display = 'flex';
    $('#quizActions').style.display = 'flex';
    renderChoiceCard(word);
  } else if (learnMode === 'reverse') {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnReverseCard').style.display = 'flex';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'none';
    $('#learnExtraActions').style.display = 'flex';
    $('#quizActions').style.display = 'flex';
    renderReverseCard(word);
  } else if (learnMode === 'spell') {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnReverseCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'flex';
    $('#learnActions').style.display = 'none';
    $('#learnExtraActions').style.display = 'flex';
    $('#quizActions').style.display = 'flex';
    renderSpellCard(word);
  }
}

/**
 * 渲染卡片例句（专升本例句）
 * 在翻卡正面和背面都显示例句
 * @param {object} word - 单词对象
 * @param {string} frontId - 正面例句容器ID
 * @param {string} backId - 背面例句容器ID
 */
function renderCardExample(word, frontId, backId) {
  const frontEl = document.getElementById(frontId);
  const backEl = document.getElementById(backId);
  if (!frontEl || !backEl) return;

  const examples = word.examples || [];
  if (examples.length > 0) {
    const ex = examples[0]; // 卡片上只显示第一条例句，避免过长
    // 正面：只显示英文例句，不显示中文翻译（查看释义时才看到翻译）
    frontEl.innerHTML = '<p class="card-example-label">例句</p>' +
                        `<p class="card-example-en">${escapeHtml(ex.en || '')}</p>`;
    // 背面：显示英文+中文翻译
    backEl.innerHTML = '<p class="card-example-label">例句</p>' +
                       `<p class="card-example-en">${escapeHtml(ex.en || '')}</p>` +
                       (ex.zh ? `<p class="card-example-zh">${escapeHtml(ex.zh)}</p>` : '');
    frontEl.style.display = 'block';
    backEl.style.display = 'block';
  } else {
    frontEl.style.display = 'none';
    backEl.style.display = 'none';
  }
}

// 渲染翻卡模式
function renderFlipCard(word) {
  // 正面内容
  $('#learnWord').textContent = word.word;
  $('#learnPhonetic').textContent = word.phonetic || '';
  // 背面内容
  $('#learnWordBack').textContent = word.word;
  $('#learnPhoneticBack').textContent = word.phonetic || '';
  $('#learnMeaning').textContent = word.meaning || '暂无释义';
  // 拆解信息
  renderCardSplit($('#learnSplit'), word.split_data);
  // 记忆方法
  const mnemonicBox = $('#learnMnemonic');
  if (mnemonicBox) {
    if (word.mnemonic) {
      mnemonicBox.style.display = 'block';
      mnemonicBox.textContent = word.mnemonic;
    } else {
      mnemonicBox.style.display = 'none';
    }
  }
  // 例句（专升本）
  renderCardExample(word, 'learnExampleFront', 'learnExampleBack');
  // 重置翻转状态
  learnFlipped = false;
  $('#learnCard').classList.remove('flipped');
}

/**
 * 内置兜底干扰项词库：当后端和队列都取不到足够干扰项时使用，
 * 保证选择题始终能有 4 个选项（1 正确 + 3 干扰项）
 */
const BUILTIN_DISTRACTORS = [
  { word: 'begin', meaning: '开始' },
  { word: 'better', meaning: '更好的' },
  { word: 'before', meaning: '在…之前' },
  { word: 'behind', meaning: '在…后面' },
  { word: 'below', meaning: '在…下面' },
  { word: 'between', meaning: '在…之间' },
  { word: 'because', meaning: '因为' },
  { word: 'become', meaning: '变成' },
  { word: 'believe', meaning: '相信' },
  { word: 'worse', meaning: '更差的' },
  { word: 'worst', meaning: '最差的' },
  { word: 'wonder', meaning: '想知道' },
  { word: 'worry', meaning: '担心' },
  { word: 'world', meaning: '世界' },
  { word: 'while', meaning: '当…的时候' },
  { word: 'where', meaning: '在哪里' },
  { word: 'often', meaning: '经常' },
  { word: 'offer', meaning: '提供' },
  { word: 'order', meaning: '顺序；命令' },
  { word: 'other', meaning: '其他的' },
  { word: 'every', meaning: '每一个' },
  { word: 'never', meaning: '从不' },
  { word: 'number', meaning: '数字' },
  { word: 'person', meaning: '人' },
  { word: 'people', meaning: '人们' },
  { word: 'please', meaning: '请；使高兴' },
  { word: 'present', meaning: '礼物；现在的' },
  { word: 'problem', meaning: '问题' },
  { word: 'probably', meaning: '可能' },
  { word: 'question', meaning: '问题' },
  { word: 'quick', meaning: '快的' },
  { word: 'report', meaning: '报告' },
  { word: 'result', meaning: '结果' },
  { word: 'return', meaning: '返回；归还' },
  { word: 'reason', meaning: '原因' },
  { word: 'recent', meaning: '最近的' },
  { word: 'sudden', meaning: '突然的' },
  { word: 'suggest', meaning: '建议' },
  { word: 'support', meaning: '支持' },
  { word: 'surprise', meaning: '使惊讶' },
  { word: 'through', meaning: '穿过' },
  { word: 'though', meaning: '尽管' },
  { word: 'together', meaning: '一起' },
  { word: 'tomorrow', meaning: '明天' },
  { word: 'tonight', meaning: '今晚' },
  { word: 'usually', meaning: '通常' },
  { word: 'understand', meaning: '理解' },
  { word: 'university', meaning: '大学' },
  { word: 'whether', meaning: '是否' },
  { word: 'without', meaning: '没有' },
  { word: 'yesterday', meaning: '昨天' },
  { word: 'young', meaning: '年轻的' },
];

/**
 * 确保返回 3 个干扰项（过滤空值/重复/与正确答案相同）
 * 后端不足时依次用队列词、内置词库兜底，保证选择题始终有 4 个选项
 */
function ensureThreeDistractors(word, distractors) {
  const clean = (distractors || []).filter(o => o.word && o.word.trim() && o.word.trim() !== word.word.trim());
  const seen = new Set();
  const result = [];
  for (const o of clean) {
    const w = o.word.trim().toLowerCase();
    if (seen.has(w)) continue;
    seen.add(w);
    result.push({ word: o.word, meaning: o.meaning || '' });
  }
  // 用内置词库兜底补足到 3 个干扰项
  for (const o of BUILTIN_DISTRACTORS) {
    if (result.length >= 3) break;
    const w = o.word.toLowerCase();
    if (seen.has(w) || w === word.word.trim().toLowerCase()) continue;
    seen.add(w);
    result.push({ ...o });
  }
  return result.slice(0, 3);
}

/**
 * 渲染看词选义模式
 * 从所有已学单词中随机抽 3 个作为干扰项
 */
/**
 * 渲染看词选义卡片
 * 优先使用形近词（拼写相似的词）作为干扰项，让选择题更有挑战性
 */
async function renderChoiceCard(word) {
  quizAnswered = false;
  $('#choiceWord').textContent = word.word;
  $('#choicePhonetic').textContent = word.phonetic || '';
  $('#choiceFeedback').textContent = '';
  $('#choiceFeedback').className = 'quiz-feedback';

  // 显示正确率（基于今日学习单词总量：如学100个错1个=99%）
  const learnWrongCount = learnChoiceTotal - learnChoiceCorrect;
  const learnTotalWords = learnQueue.length > 0 ? learnQueue.length : 1;
  const accuracy = Math.max(0, Math.round((learnTotalWords - learnWrongCount) / learnTotalWords * 100));
  const feedback = $('#choiceFeedback');
  feedback.innerHTML = `<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;

  // 优先从后端获取形近词干扰项（拼写相似的词）
  let distractors = [];
  try {
    const excludeIds = learnQueue.map(w => w.id);
    const result = await api.getSimilarDistractors(word.word, learnWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取形近词干扰项失败，尝试随机干扰项', e);
    // 降级：使用随机干扰项
    try {
      const excludeIds = learnQueue.map(w => w.id);
      const result = await api.getDistractors(word.word, learnWordbookId, excludeIds, 3);
      distractors = result || [];
    } catch (e2) {
      console.warn('获取随机干扰项也失败，使用队列内词', e2);
    }
  }

  // 从队列补充后，用 ensureThreeDistractors 保证始终有 3 个干扰项（内置词库兜底）
  const queueDistractors = learnQueue
    .filter(w => w.word !== word.word && w.id !== word.id)
    .map(w => ({ word: w.word, meaning: w.meaning }));
  distractors = ensureThreeDistractors(word, [...distractors, ...queueDistractors]);

  // 正确答案始终包含，如果释义为空则用占位符
  const correctMeaning = (word.meaning && word.meaning.trim()) ? word.meaning : '（暂无释义）';
  let options = [{ word: word.word, meaning: correctMeaning }, ...distractors];
  // 打乱顺序
  options.sort(() => Math.random() - 0.5);

  const optionsEl = $('#choiceOptions');
  // 默认只显示释义，不显示单词
  optionsEl.innerHTML = options.map(opt => `
    <button class="quiz-option" data-word="${escapeHtml(opt.word)}">
      <span class="quiz-option-meaning">${escapeHtml(opt.meaning)}</span>
    </button>
  `).join('');

  // 绑定点击
  optionsEl.querySelectorAll('.quiz-option').forEach(btn => {
    btn.addEventListener('click', () => handleChoiceAnswer(btn, word));
  });
}

/**
 * 处理选义答题
 * 答对后自动进入下一题（延迟 900ms 让用户看到反馈）
 */
function handleChoiceAnswer(btn, currentWord) {
  if (quizAnswered) return;
  quizAnswered = true;

  const selectedWord = btn.dataset.word;
  const isCorrect = selectedWord === currentWord.word;
  const feedback = $('#choiceFeedback');
  const optionsEl = $('#choiceOptions');

  // 统计正确率
  learnChoiceTotal++;
  if (isCorrect) learnChoiceCorrect++;

  // 标记所有选项不可再点
  optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));

  // 计算正确率（基于今日学习单词总量）
  const learnWrongCount = learnChoiceTotal - learnChoiceCorrect;
  const learnTotalWords = learnQueue.length > 0 ? learnQueue.length : 1;
  const accuracy = Math.max(0, Math.round((learnTotalWords - learnWrongCount) / learnTotalWords * 100));

  if (isCorrect) {
    btn.classList.add('correct');
    feedback.className = 'quiz-feedback correct';
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span><span class="quiz-known-hint">点击「已学会」继续</span>`;
    playCorrectSound();
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记完成并进入下一题，
    // 符合"点学会才算学完"的要求，避免自动跳题导致无法标记当前词
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    // 选错后：所有选项显示单词+释义
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      const m = b.querySelector('.quiz-option-meaning') ? b.querySelector('.quiz-option-meaning').textContent : '';
      b.innerHTML = `<span class="quiz-option-word">${escapeHtml(w)}</span><span class="quiz-option-meaning">${escapeHtml(m)}</span>`;
      if (b.dataset.word === currentWord.word) b.classList.add('correct');
    });
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `回答错误<span class="feedback-meaning">正确答案：${escapeHtml(currentWord.word)} - ${escapeHtml(currentWord.meaning || '')}</span><span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;
    // 答错不自动跳，让用户看清楚正确答案，手动点"下一题"或"已学会"
  }
}

/**
 * 渲染看义选词模式（中→英）
 * 显示中文释义，选择对应的英文单词
 */
async function renderReverseCard(word) {
  quizAnswered = false;
  $('#reverseMeaning').textContent = word.meaning || '（暂无释义）';
  $('#reverseFeedback').textContent = '';
  $('#reverseFeedback').className = 'quiz-feedback';

  // 显示正确率
  const learnWrongCount = learnChoiceTotal - learnChoiceCorrect;
  const learnTotalWords = learnQueue.length > 0 ? learnQueue.length : 1;
  const accuracy = Math.max(0, Math.round((learnTotalWords - learnWrongCount) / learnTotalWords * 100));
  const feedback = $('#reverseFeedback');
  feedback.innerHTML = `<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;

  // 获取干扰项（其他英文单词）
  let distractors = [];
  try {
    const excludeIds = learnQueue.map(w => w.id);
    const result = await api.getDistractors(word.word, learnWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取干扰项失败，使用队列内词', e);
  }

  // 从队列补充后，用 ensureThreeDistractors 保证始终有 3 个干扰项（内置词库兜底）
  const queueDistractors = learnQueue
    .filter(w => w.word !== word.word && w.id !== word.id)
    .map(w => ({ word: w.word, meaning: w.meaning }));
  distractors = ensureThreeDistractors(word, [...distractors, ...queueDistractors]);

  // 正确答案
  let options = [{ word: word.word, meaning: word.meaning || '' }, ...distractors];
  options.sort(() => Math.random() - 0.5);
  // 缓存完整选项（含释义），供答错时展示每个选项对应的单词+释义
  reverseOptionsCache = options.map(o => ({ word: o.word, meaning: o.meaning || '' }));

  const optionsEl = $('#reverseOptions');
  // 默认只显示英文单词
  optionsEl.innerHTML = options.map(opt => `
    <button class="quiz-option" data-word="${escapeHtml(opt.word)}">
      <span class="quiz-option-word">${escapeHtml(opt.word)}</span>
    </button>
  `).join('');

  // 绑定点击
  optionsEl.querySelectorAll('.quiz-option').forEach(btn => {
    btn.addEventListener('click', () => handleReverseAnswer(btn, word));
  });
}

/**
 * 处理看义选词答题
 */
function handleReverseAnswer(btn, currentWord) {
  if (quizAnswered) return;
  quizAnswered = true;

  const selectedWord = btn.dataset.word;
  const optionsEl = $('#reverseOptions');
  const feedback = $('#reverseFeedback');
  learnChoiceTotal++;

  const learnWrongCount = learnChoiceTotal - learnChoiceCorrect;
  const learnTotalWords = learnQueue.length > 0 ? learnQueue.length : 1;
  const accuracy = Math.max(0, Math.round((learnTotalWords - learnWrongCount) / learnTotalWords * 100));

  if (selectedWord === currentWord.word) {
    learnChoiceCorrect++;
    btn.classList.add('correct');
    playCorrectSound();
    feedback.className = 'quiz-feedback correct';
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span><span class="quiz-known-hint">点击「已学会」继续</span>`;
    optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记完成并进入下一题
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    // 选错后：显示所有选项的单词+释义（使用渲染时缓存的完整选项数据）
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      const opt = reverseOptionsCache.find(o => o.word === w);
      const meaning = opt ? opt.meaning : '';
      b.innerHTML = `<span class="quiz-option-word">${escapeHtml(w)}</span><span class="quiz-option-meaning">${escapeHtml(meaning)}</span>`;
      if (w === currentWord.word) b.classList.add('correct');
    });
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `回答错误<span class="feedback-meaning">正确答案：${escapeHtml(currentWord.word)} - ${escapeHtml(currentWord.meaning || '')}</span><span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;
  }
}

/**
 * 渲染拼写默写模式
 */
function renderSpellCard(word) {
  quizAnswered = false;
  $('#spellMeaning').textContent = word.meaning || '暂无释义';
  $('#spellPhonetic').textContent = word.phonetic || '';
  $('#spellFeedback').textContent = '';
  $('#spellFeedback').className = 'quiz-feedback';
  const input = $('#spellInput');
  input.value = '';
  input.className = 'spell-input';
  input.disabled = false;
  // 自动聚焦
  setTimeout(() => input.focus(), 100);
  // 保存当前词用于校验
  input.dataset.answer = word.word;
}

/**
 * 处理拼写提交
 */
function handleSpellSubmit() {
  if (quizAnswered) return;
  const input = $('#spellInput');
  const answer = input.dataset.answer || '';
  const userAns = input.value.trim().toLowerCase();
  const correctAns = answer.toLowerCase();

  if (!userAns) {
    showToast('请输入单词', 'error');
    return;
  }

  quizAnswered = true;
  input.disabled = true;
  const feedback = $('#spellFeedback');

  if (userAns === correctAns) {
    input.classList.add('correct');
    feedback.className = 'quiz-feedback correct';
    feedback.textContent = '拼写正确！';
    playCorrectSound();
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记完成并进入下一题
  } else {
    input.classList.add('wrong');
    playWrongSound();
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `拼写错误<span class="feedback-meaning">正确答案：${escapeHtml(answer)}</span>`;
    // 答错不自动跳，手动点"下一题"
  }
}

/**
 * 切换学习模式
 */
function switchLearnMode(mode) {
  learnMode = mode;
  // 更新 tab 样式
  $$('.mode-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.mode === mode);
  });
  // 重新渲染当前词
  if (learnQueue.length > 0 && learnIndex < learnQueue.length) {
    renderLearnCard();
  }
}

/**
 * 测验模式"下一题"：仅跳到下一个单词（循环），不自动标记为已学会
 * 只有点击"已学会"按钮才会 submitReview 标记掌握
 */
function handleQuizNext() {
  // 取消挂起的自动下一题，防止回车+自动跳转双重触发
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
  // 跳到下一个，翻完循环
  learnIndex++;
  renderLearnCard();
}

/**
 * 测验模式"已学会"：标记当前单词已学会并跳到下一个（循环）
 * 只有明确点击"已学会"才提交复习评分，否则单词会继续出现在队列中
 */
async function handleQuizKnown() {
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
  const currentWord = learnQueue[learnIndex];
  if (currentWord && !learnedIds.has(currentWord.id)) {
    try {
      await api.submitReview(currentWord.id, 'good');
    } catch (e) {
      console.error('提交已学会失败', e);
    }
    learnedIds.add(currentWord.id);
    allLearnedIds.add(currentWord.id);
    // 实时刷新首页统计（非阻塞）
    refreshHomeStats();
  }
  // 跳到下一个，翻完循环
  learnIndex++;
  renderLearnCard();
}

/**
 * 返回上一题（所有模式循环）
 * 不重新 submitReview，只回看
 */
function handleLearnPrev() {
  if (learnQueue.length === 0) return;
  if (learnIndex === 0) {
    // 循环：第一题往前跳到最后一题
    learnIndex = learnQueue.length - 1;
    renderLearnCard();
    return;
  }
  learnIndex--;
  renderLearnCard();
}

/**
 * 渲染卡片背面的拆解信息
 * 显示每个部分的：当前部分 + 意思 + 原词→变形→当前 + 作用说明
 */
function renderCardSplit(container, splitData) {
  if (!splitData || splitData.length === 0) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = splitData.map(s => {
    // 判断是否有变形（原词与当前部分不同）
    const hasTransform = s.original && s.original !== s.part;
    // 变形链：原词 → 变形规则 → 当前部分
    const transformChain = hasTransform
      ? `<div class="split-transform">
           <span class="transform-original">${escapeHtml(s.original)}</span>
           <span class="transform-arrow">→</span>
           <span class="transform-rule">${escapeHtml(s.transform || '变形')}</span>
           <span class="transform-arrow">→</span>
           <span class="transform-current">${escapeHtml(s.part)}</span>
         </div>`
      : (s.transform && s.transform !== '原形不变'
         ? `<div class="split-transform"><span class="transform-rule">${escapeHtml(s.transform)}</span></div>`
         : '');
    // 原词释义（如果与当前部分意思不同才单独显示）
    const originalMeaning = (s.original_meaning && s.original_meaning !== s.meaning)
      ? `<div class="split-original-meaning">原词 ${escapeHtml(s.original)} 意思：${escapeHtml(s.original_meaning)}</div>`
      : '';
    return `
      <div class="split-item">
        <div class="split-part">${escapeHtml(s.part || '')}</div>
        ${s.meaning ? `<div class="split-meaning">${escapeHtml(s.meaning)}</div>` : ''}
        ${transformChain}
        ${originalMeaning}
        ${s.explain ? `<div class="split-explain">${escapeHtml(s.explain)}</div>` : ''}
      </div>
    `;
  }).join('');
}

// 翻转学习卡片
function flipLearnCard() {
  learnFlipped = !learnFlipped;
  $('#learnCard').classList.toggle('flipped', learnFlipped);
}

// 检查今日学习是否全部完成：队列中所有单词都已标记"已学会"
function checkLearnComplete() {
  if (learnCompleteNotified || learnQueue.length === 0) return;
  const allLearned = learnQueue.every(w => learnedIds.has(w.id));
  if (allLearned) {
    learnCompleteNotified = true;
    showToast(`🎉 今日 ${learnQueue.length} 个单词已全部学会，学习完成！`, 'success');
  }
}

// 学习：已学会，标记单词并跳到下一个（不从队列移除，保持循环翻卡）
// 学会的单词自动提交复习，状态变为 review，明天进入复习
async function handleLearnKnown() {
  const word = learnQueue[learnIndex];
  if (!word) return;
  // 成功动效：卡片飞出
  const cardEl = $('#learnCard');
  if (cardEl && learnMode === 'flip') {
    cardEl.classList.add('card-fly-out');
  }
  try {
    // 调用复习接口标记为 good（避免重复标记）
    if (!learnedIds.has(word.id)) {
      await api.submitReview(word.id, 'good');
      learnedIds.add(word.id);
      allLearnedIds.add(word.id); // 记录到全局已学集合
      // 实时刷新首页统计（非阻塞）
      refreshHomeStats();
    }
    // 跳到下一个，翻完循环
    learnIndex++;
    setTimeout(() => {
      if (cardEl) cardEl.classList.remove('card-fly-out');
      renderLearnCard();
    }, 300);
  } catch (err) {
    // 即使提交失败也继续
    console.error(err);
    learnIndex++;
    setTimeout(() => {
      if (cardEl) cardEl.classList.remove('card-fly-out');
      renderLearnCard();
    }, 300);
  }
}

// 学习页查看详情
function handleLearnDetail() {
  const word = learnQueue[learnIndex];
  if (word) openWordDetail(word.id);
}

/* ====================================================
   八、复习页逻辑
   ==================================================== */

let reviewQueue = [];      // 今日复习队列
let reviewIndex = 0;       // 当前索引
let reviewFlipped = false; // 当前卡片是否翻转
let reviewMode = 'flip';   // 复习模式：flip 翻卡 / choice 看词选义 / reverse 看义选词 / spell 拼写默写
let reviewQuizAnswered = false; // 复习测验题是否已作答
let reviewAutoNextTimer = null;  // 复习自动下一题定时器
let reviewAllMode = false;       // 自主复习模式：true=复习所有已学过的词（不受到期限制），false=仅到期
let reviewAllActive = false;     // 当前会话是否处于自主复习（用于中断恢复时区分）

// 保存复习位置到 localStorage（用于中断恢复）
function saveReviewPosition() {
  if (reviewQueue.length === 0) return;
  const position = {
    index: reviewIndex,
    queueLength: reviewQueue.length,
    wordbookId: reviewWordbookId,
    allMode: reviewAllMode,
    timestamp: Date.now()
  };
  localStorage.setItem('wordmemo_review_position', JSON.stringify(position));
}

// 恢复复习位置（从 localStorage）
function restoreReviewPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem('wordmemo_review_position') || 'null');
    if (!saved) return false;
    // 检查是否同词书、同模式、同队列长度、且不超过5分钟
    if (saved.wordbookId !== reviewWordbookId) return false;
    if (!!saved.allMode !== !!reviewAllMode) return false;
    if (saved.queueLength !== reviewQueue.length) return false;
    if (Date.now() - saved.timestamp > 5 * 60 * 1000) return false;
    // 恢复索引
    if (saved.index >= 0 && saved.index < reviewQueue.length) {
      reviewIndex = saved.index;
      return true;
    }
  } catch (e) {
    console.warn('恢复复习位置失败', e);
  }
  return false;
}

// 加载复习队列
// reviewAllMode: true=自主复习（所有已学过，不受到期限制），false=仅到期
async function loadReviewQueue() {
  try {
    showLoading();
    reviewAllActive = reviewAllMode;
    const reviewOpts = { random: reviewRandomMode };
    if (reviewStarredOnly) reviewOpts.starred = true;
    const res = reviewAllMode
      ? await api.getReviewAll(reviewWordbookId, reviewOpts)
      : await api.getReviewToday(reviewWordbookId, reviewOpts);
    reviewQueue = Array.isArray(res) ? res : (res.words || res.data || []);
    // 尝试恢复上次复习位置
    const restored = restoreReviewPosition();
    if (!restored) {
      reviewIndex = 0;
    }
    // 重置看词选义正确率
    reviewChoiceCorrect = 0;
    reviewChoiceTotal = 0;
    hideLoading();
    updateReviewEstimate(reviewQueue.length);
    renderReviewCard();
  } catch (err) {
    handleError(err);
  }
}

// 渲染当前复习卡片
function renderReviewCard() {
  // 取消挂起的自动下一题
  if (reviewAutoNextTimer) { clearTimeout(reviewAutoNextTimer); reviewAutoNextTimer = null; }
  const total = reviewQueue.length;
  // 队列为空：显示空状态
  if (total === 0) {
    $('#reviewCard').style.display = 'none';
    $('#reviewChoiceCard').style.display = 'none';
    $('#reviewReverseCard').style.display = 'none';
    $('#reviewSpellCard').style.display = 'none';
    $('#ratingActions').style.display = 'none';
    $('#reviewQuizActions').style.display = 'none';
    $('#reviewExtraActions').style.display = 'none';
    $('#reviewEmpty').style.display = 'block';
    $('#reviewProgress').textContent = `0 / 0`;
    const reviewBadgeEmpty = $('#reviewStarBadge');
    if (reviewBadgeEmpty) reviewBadgeEmpty.style.display = 'none';
    // 根据是否有复习中的单词显示不同提示
    const reviewTotal = homeStatsCache ? (homeStatsCache.review || 0) + (homeStatsCache.mastered || 0) : 0;
    const reviewEmptyEl = $('#reviewEmpty');
    if (reviewEmptyEl) {
      if (reviewAllMode) {
        reviewEmptyEl.innerHTML = '<p>没有可自主复习的单词</p><p class="empty-sub">先把单词学起来，学过的词都能在这里随时复习。</p>';
      } else if (reviewTotal > 0) {
        reviewEmptyEl.innerHTML = '<p>今日复习已完成</p><p class="empty-sub">没有到期的单词，' + reviewTotal + '个单词按艾宾浩斯曲线安排复习中，可点击"自主复习"随时回顾，继续保持！</p>';
      } else {
        reviewEmptyEl.innerHTML = '<p>今日复习已完成</p><p class="empty-sub">没有到期的单词，可点击"自主复习"随时回顾，继续保持！</p>';
      }
    }
    return;
  }
  // 循环：翻完从头再来
  if (reviewIndex >= total) {
    reviewIndex = 0;
  }
  if (reviewIndex < 0) {
    reviewIndex = total - 1;
  }

  const word = reviewQueue[reviewIndex];
  // 当前词是否为重点单词：显示/隐藏重点角标
  const reviewBadge = $('#reviewStarBadge');
  if (reviewBadge) reviewBadge.style.display = word.is_starred ? 'inline-block' : 'none';
  $('#reviewProgress').textContent = `${reviewIndex + 1} / ${total}`;
  $('#reviewEmpty').style.display = 'none';
  // 保存复习位置（用于中断恢复）
  saveReviewPosition();

  // 根据模式显示对应卡片
  if (reviewMode === 'flip') {
    $('#reviewCard').style.display = 'block';
    $('#reviewChoiceCard').style.display = 'none';
    $('#reviewReverseCard').style.display = 'none';
    $('#reviewSpellCard').style.display = 'none';
    $('#ratingActions').style.display = 'flex';
    $('#reviewQuizActions').style.display = 'none';
    $('#reviewExtraActions').style.display = 'flex';
    renderReviewFlipCard(word);
  } else if (reviewMode === 'choice') {
    $('#reviewCard').style.display = 'none';
    $('#reviewChoiceCard').style.display = 'flex';
    $('#reviewReverseCard').style.display = 'none';
    $('#reviewSpellCard').style.display = 'none';
    $('#ratingActions').style.display = 'none';
    $('#reviewQuizActions').style.display = 'flex';
    $('#reviewExtraActions').style.display = 'none';
    renderReviewChoiceCard(word);
  } else if (reviewMode === 'reverse') {
    $('#reviewCard').style.display = 'none';
    $('#reviewChoiceCard').style.display = 'none';
    $('#reviewReverseCard').style.display = 'flex';
    $('#reviewSpellCard').style.display = 'none';
    $('#ratingActions').style.display = 'none';
    $('#reviewQuizActions').style.display = 'flex';
    $('#reviewExtraActions').style.display = 'none';
    renderReviewReverseCard(word);
  } else if (reviewMode === 'spell') {
    $('#reviewCard').style.display = 'none';
    $('#reviewChoiceCard').style.display = 'none';
    $('#reviewReverseCard').style.display = 'none';
    $('#reviewSpellCard').style.display = 'flex';
    $('#ratingActions').style.display = 'none';
    $('#reviewQuizActions').style.display = 'flex';
    renderReviewSpellCard(word);
  }
}

// 渲染复习翻卡模式
function renderReviewFlipCard(word) {
  // 正面
  $('#reviewWord').textContent = word.word;
  $('#reviewPhonetic').textContent = word.phonetic || '';
  // 背面
  $('#reviewWordBack').textContent = word.word;
  $('#reviewMeaning').textContent = word.meaning || '暂无释义';
  renderCardSplit($('#reviewSplit'), word.split_data);

  // 记忆方法
  const reviewMnemonic = $('#reviewMnemonic');
  if (reviewMnemonic) {
    if (word.mnemonic) {
      reviewMnemonic.style.display = 'block';
      reviewMnemonic.textContent = word.mnemonic;
    } else {
      reviewMnemonic.style.display = 'none';
    }
  }

  // 例句（专升本）
  renderCardExample(word, 'reviewExampleFront', 'reviewExampleBack');

  // 重置翻转
  reviewFlipped = false;
  $('#reviewCard').classList.remove('flipped');
}

/**
 * 渲染复习看词选义卡片
 * 优先使用形近词作为干扰项
 */
async function renderReviewChoiceCard(word) {
  reviewQuizAnswered = false;
  $('#reviewChoiceWord').textContent = word.word;
  $('#reviewChoicePhonetic').textContent = word.phonetic || '';
  $('#reviewChoiceFeedback').textContent = '';
  $('#reviewChoiceFeedback').className = 'quiz-feedback';

  // 显示正确率（基于今日复习单词总量）
  const reviewWrongCount = reviewChoiceTotal - reviewChoiceCorrect;
  const reviewTotalWords = reviewQueue.length > 0 ? reviewQueue.length : 1;
  const accuracy = Math.max(0, Math.round((reviewTotalWords - reviewWrongCount) / reviewTotalWords * 100));
  $('#reviewChoiceFeedback').innerHTML = `<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;

  // 优先获取形近词干扰项
  let distractors = [];
  try {
    const excludeIds = reviewQueue.map(w => w.id);
    const result = await api.getSimilarDistractors(word.word, reviewWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取形近词干扰项失败，尝试随机干扰项', e);
    try {
      const excludeIds = reviewQueue.map(w => w.id);
      const result = await api.getDistractors(word.word, reviewWordbookId, excludeIds, 3);
      distractors = result || [];
    } catch (e2) {
      console.warn('获取随机干扰项也失败', e2);
    }
  }

  // 从队列补充后，用 ensureThreeDistractors 保证始终有 3 个干扰项（内置词库兜底）
  const queueDistractors = reviewQueue
    .filter(w => w.word !== word.word && w.id !== word.id)
    .map(w => ({ word: w.word, meaning: w.meaning }));
  distractors = ensureThreeDistractors(word, [...distractors, ...queueDistractors]);

  // 组合选项：正确答案始终包含
  const correctMeaning = (word.meaning && word.meaning.trim()) ? word.meaning : '（暂无释义）';
  let options = [{ word: word.word, meaning: correctMeaning }, ...distractors];
  options.sort(() => Math.random() - 0.5);

  const optionsEl = $('#reviewChoiceOptions');
  // 默认只显示释义，不显示单词
  optionsEl.innerHTML = options.map(opt => `
    <button class="quiz-option" data-word="${escapeHtml(opt.word)}">
      <span class="quiz-option-meaning">${escapeHtml(opt.meaning)}</span>
    </button>
  `).join('');

  optionsEl.querySelectorAll('.quiz-option').forEach(btn => {
    btn.addEventListener('click', () => handleReviewChoiceAnswer(btn, word));
  });
}

/**
 * 处理复习选义答题
 */
function handleReviewChoiceAnswer(btn, currentWord) {
  if (reviewQuizAnswered) return;
  reviewQuizAnswered = true;

  const selectedWord = btn.dataset.word;
  const isCorrect = selectedWord === currentWord.word;
  const feedback = $('#reviewChoiceFeedback');
  const optionsEl = $('#reviewChoiceOptions');

  // 统计正确率
  reviewChoiceTotal++;
  if (isCorrect) reviewChoiceCorrect++;

  optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));

  // 计算正确率（基于今日复习单词总量）
  const reviewWrongCount = reviewChoiceTotal - reviewChoiceCorrect;
  const reviewTotalWords = reviewQueue.length > 0 ? reviewQueue.length : 1;
  const accuracy = Math.max(0, Math.round((reviewTotalWords - reviewWrongCount) / reviewTotalWords * 100));

  if (isCorrect) {
    btn.classList.add('correct');
    feedback.className = 'quiz-feedback correct';
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span><span class="quiz-known-hint">点击「已学会」继续</span>`;
    playCorrectSound();
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记复习完成并进入下一题
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    // 选错后：所有选项显示单词+释义
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      const m = b.querySelector('.quiz-option-meaning') ? b.querySelector('.quiz-option-meaning').textContent : '';
      b.innerHTML = `<span class="quiz-option-word">${escapeHtml(w)}</span><span class="quiz-option-meaning">${escapeHtml(m)}</span>`;
      if (b.dataset.word === currentWord.word) b.classList.add('correct');
    });
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `回答错误<span class="feedback-meaning">正确答案：${escapeHtml(currentWord.word)} - ${escapeHtml(currentWord.meaning || '')}</span><span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;
  }
}

/**
 * 渲染复习看义选词卡片（中→英）
 */
async function renderReviewReverseCard(word) {
  reviewQuizAnswered = false;
  $('#reviewReverseMeaning').textContent = word.meaning || '（暂无释义）';
  $('#reviewReverseFeedback').textContent = '';
  $('#reviewReverseFeedback').className = 'quiz-feedback';

  // 显示正确率
  const reviewWrongCount = reviewChoiceTotal - reviewChoiceCorrect;
  const reviewTotalWords = reviewQueue.length > 0 ? reviewQueue.length : 1;
  const accuracy = Math.max(0, Math.round((reviewTotalWords - reviewWrongCount) / reviewTotalWords * 100));
  const feedback = $('#reviewReverseFeedback');
  feedback.innerHTML = `<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;

  // 获取干扰项
  let distractors = [];
  try {
    const excludeIds = reviewQueue.map(w => w.id);
    const result = await api.getDistractors(word.word, reviewWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取干扰项失败，使用队列内词', e);
  }

  // 从队列补充后，用 ensureThreeDistractors 保证始终有 3 个干扰项（内置词库兜底）
  const queueDistractors = reviewQueue
    .filter(w => w.word !== word.word && w.id !== word.id)
    .map(w => ({ word: w.word, meaning: w.meaning }));
  distractors = ensureThreeDistractors(word, [...distractors, ...queueDistractors]);

  let options = [{ word: word.word, meaning: word.meaning || '' }, ...distractors];
  options.sort(() => Math.random() - 0.5);
  // 缓存完整选项（含释义），供答错时展示每个选项对应的单词+释义
  reverseOptionsCache = options.map(o => ({ word: o.word, meaning: o.meaning || '' }));

  const optionsEl = $('#reviewReverseOptions');
  optionsEl.innerHTML = options.map(opt => `
    <button class="quiz-option" data-word="${escapeHtml(opt.word)}">
      <span class="quiz-option-word">${escapeHtml(opt.word)}</span>
    </button>
  `).join('');

  optionsEl.querySelectorAll('.quiz-option').forEach(btn => {
    btn.addEventListener('click', () => handleReviewReverseAnswer(btn, word));
  });
}

/**
 * 处理复习看义选词答题
 */
function handleReviewReverseAnswer(btn, currentWord) {
  if (reviewQuizAnswered) return;
  reviewQuizAnswered = true;

  const selectedWord = btn.dataset.word;
  const optionsEl = $('#reviewReverseOptions');
  const feedback = $('#reviewReverseFeedback');
  reviewChoiceTotal++;

  const reviewWrongCount = reviewChoiceTotal - reviewChoiceCorrect;
  const reviewTotalWords = reviewQueue.length > 0 ? reviewQueue.length : 1;
  const accuracy = Math.max(0, Math.round((reviewTotalWords - reviewWrongCount) / reviewTotalWords * 100));

  if (selectedWord === currentWord.word) {
    reviewChoiceCorrect++;
    btn.classList.add('correct');
    playCorrectSound();
    feedback.className = 'quiz-feedback correct';
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span><span class="quiz-known-hint">点击「已学会」继续</span>`;
    optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记复习完成并进入下一题
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    // 选错后：显示所有选项的单词+释义（使用渲染时缓存的完整选项数据）
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      const opt = reverseOptionsCache.find(o => o.word === w);
      const meaning = opt ? opt.meaning : '';
      b.innerHTML = `<span class="quiz-option-word">${escapeHtml(w)}</span><span class="quiz-option-meaning">${escapeHtml(meaning)}</span>`;
      if (w === currentWord.word) b.classList.add('correct');
    });
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `回答错误<span class="feedback-meaning">正确答案：${escapeHtml(currentWord.word)} - ${escapeHtml(currentWord.meaning || '')}</span><span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;
  }
}

/**
 * 渲染复习拼写默写卡片
 */
function renderReviewSpellCard(word) {
  reviewQuizAnswered = false;
  $('#reviewSpellMeaning').textContent = word.meaning || '暂无释义';
  $('#reviewSpellPhonetic').textContent = word.phonetic || '';
  $('#reviewSpellFeedback').textContent = '';
  $('#reviewSpellFeedback').className = 'quiz-feedback';
  const input = $('#reviewSpellInput');
  input.value = '';
  input.className = 'spell-input';
  input.disabled = false;
  setTimeout(() => input.focus(), 100);
  input.dataset.answer = word.word;
}

/**
 * 处理复习拼写提交
 */
function handleReviewSpellSubmit() {
  if (reviewQuizAnswered) return;
  const input = $('#reviewSpellInput');
  const answer = input.dataset.answer || '';
  const userAns = input.value.trim().toLowerCase();
  const correctAns = answer.toLowerCase();

  if (!userAns) {
    showToast('请输入单词', 'error');
    return;
  }

  reviewQuizAnswered = true;
  input.disabled = true;
  const feedback = $('#reviewSpellFeedback');

  if (userAns === correctAns) {
    input.classList.add('correct');
    feedback.className = 'quiz-feedback correct';
    feedback.textContent = '拼写正确！';
    playCorrectSound();
    // 答对后不自动跳转：由用户点击"已学会"确认后才标记复习完成并进入下一题
  } else {
    input.classList.add('wrong');
    playWrongSound();
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `拼写错误<span class="feedback-meaning">正确答案：${escapeHtml(answer)}</span>`;
  }
}

/**
 * 切换复习模式
 */
function switchReviewMode(mode) {
  reviewMode = mode;
  // 更新 tab 样式
  $$('#reviewModeTabs .mode-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.rmode === mode);
  });
  // 重新渲染当前词
  if (reviewQueue.length > 0 && reviewIndex < reviewQueue.length) {
    renderReviewCard();
  }
}

/**
 * 复习测验模式"下一题"：仅跳到下一个（循环），不自动标记
 * 只有点击"已学会"才提交复习评分
 */
function handleReviewQuizNext() {
  if (reviewAutoNextTimer) { clearTimeout(reviewAutoNextTimer); reviewAutoNextTimer = null; }
  reviewIndex++;
  renderReviewCard();
}

/**
 * 复习测验模式"已学会"：提交复习评分并跳到下一个（循环）
 * 只有明确点击"已学会"才记录本次复习完成
 */
async function handleReviewQuizKnown() {
  if (reviewAutoNextTimer) { clearTimeout(reviewAutoNextTimer); reviewAutoNextTimer = null; }
  const currentWord = reviewQueue[reviewIndex];
  if (currentWord) {
    try {
      await api.submitReview(currentWord.id, 'good');
      // 实时刷新首页统计（非阻塞）
      refreshHomeStats();
    } catch (e) {
      console.error(e);
    }
  }
  reviewIndex++;
  renderReviewCard();
}

/**
 * 复习测验模式"上一题"（循环）
 */
function handleReviewQuizPrev() {
  if (reviewQueue.length === 0) return;
  if (reviewIndex === 0) {
    reviewIndex = reviewQueue.length - 1;
    renderReviewCard();
    return;
  }
  reviewIndex--;
  renderReviewCard();
}

// 翻转复习卡片
function flipReviewCard() {
  reviewFlipped = !reviewFlipped;
  $('#reviewCard').classList.toggle('flipped', reviewFlipped);
}

// 提交复习评级
async function handleReviewRating(rating) {
  const word = reviewQueue[reviewIndex];
  if (!word) return;
  try {
    await api.submitReview(word.id, rating);
    // 评级为 again 时，将单词重新加入队列末尾（立即重看）
    if (rating === 'again') {
      reviewQueue.push(word);
    }
    // 评级为 hard 时，将单词插入到5个位置后（稍后重看）
    if (rating === 'hard') {
      const insertPos = Math.min(reviewIndex + 6, reviewQueue.length);
      reviewQueue.splice(insertPos, 0, word);
    }
    // 记录正确率到localStorage
    if (rating === 'again' || rating === 'hard') {
      incrementReviewWrongCount();
    }
    reviewIndex++;
    renderReviewCard();
    // 实时刷新首页统计（非阻塞）
    refreshHomeStats();
  } catch (err) {
    console.error(err);
    reviewIndex++;
    renderReviewCard();
  }
}

/* ====================================================
   九、统计页渲染
   ==================================================== */

/**
 * 渲染日历统计：显示当前月份每天的单词学习数量
 * 从 /api/stats/calendar 获取所有学习历史，在日历网格中标注
 */
async function renderCalendar() {
  const container = $('#statsCalendar');
  if (!container) return;

  try {
    const history = await api.getCalendarStats();
    // 将历史数据转为 { '2026-07-28': 5 } 的映射
    const historyMap = {};
    (history || []).forEach(h => {
      historyMap[h.date] = h.count;
    });

    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth(); // 0-based

    // 月份名称
    const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'];

    // 当月天数
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    // 当月第一天是星期几（0=周日）
    const firstDayOfWeek = new Date(year, month, 1).getDay();

    // 构建日历HTML
    let html = `<div class="calendar-header">${year}年${monthNames[month]}</div>`;
    html += '<div class="calendar-grid">';
    // 星期表头
    const weekDays = ['日', '一', '二', '三', '四', '五', '六'];
    weekDays.forEach(d => {
      html += `<div class="calendar-weekday">${d}</div>`;
    });
    // 空白格（月前的空位）
    for (let i = 0; i < firstDayOfWeek; i++) {
      html += '<div class="calendar-day calendar-day-empty"></div>';
    }
    // 每一天
    let monthTotal = 0;
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const count = historyMap[dateStr] || 0;
      monthTotal += count;
      const isToday = (day === today.getDate());
      let dayClass = 'calendar-day';
      if (isToday) dayClass += ' calendar-day-today';
      if (count > 0) dayClass += ' calendar-day-active';

      // 根据学习数量设置背景色深浅
      let bgStyle = '';
      if (count > 0) {
        if (count >= 30) bgStyle = 'background:#4CAF50;color:#fff;';
        else if (count >= 15) bgStyle = 'background:#81C784;color:#fff;';
        else if (count >= 5) bgStyle = 'background:#C8E6C9;color:#333;';
        else bgStyle = 'background:#E8F5E9;color:#333;';
      }

      html += `<div class="${dayClass}" style="${bgStyle}" title="${dateStr}: ${count}个单词">`;
      html += `<span class="calendar-day-num">${day}</span>`;
      if (count > 0) {
        html += `<span class="calendar-day-count">${count}</span>`;
      }
      html += '</div>';
    }
    html += '</div>';
    html += `<div class="calendar-summary">本月共学习 <strong>${monthTotal}</strong> 个单词</div>`;

    container.innerHTML = html;
  } catch (err) {
    console.warn('日历统计加载失败', err);
    container.innerHTML = '<p class="empty-sub">日历数据加载失败</p>';
  }
}

async function renderStats() {
  try {
    showLoading();
    let stats = homeStatsCache;
    if (!stats) {
      stats = await api.getStats(learnWordbookId);
      homeStatsCache = stats;
    }
    hideLoading();

    // 统计卡片
    $('#statsTotal').textContent = stats.total || 0;
    $('#statsMastered').textContent = stats.mastered || 0;
    $('#statsStreak').textContent = stats.streak_days || 0;
    $('#statsToday').textContent = stats.today_learned || 0;

    // 复习统计卡片
    const statsReviewToday = $('#statsReviewToday');
    if (statsReviewToday) statsReviewToday.textContent = stats.today_review_count || 0;
    const statsReviewAcc = $('#statsReviewAcc');
    if (statsReviewAcc) statsReviewAcc.textContent = (stats.today_review_accuracy || 0) + '%';
    const statsTotalReview = $('#statsTotalReview');
    if (statsTotalReview) statsTotalReview.textContent = stats.total_review_count || 0;
    const statsTotalReviewAcc = $('#statsTotalReviewAcc');
    if (statsTotalReviewAcc) statsTotalReviewAcc.textContent = (stats.total_review_accuracy || 0) + '%';

    // 7天学习柱状图
    // 后端 history 格式：[{date, count}, ...]，转为数字数组
    const statsHistory = (stats.history || []).map(h => h.count || 0);
    drawBarChart($('#statsBarChart'), statsHistory);

    // 单词状态饼图
    drawPieChart($('#statsPieChart'), {
      new: stats.new || 0,
      review: stats.review || 0,
      mastered: stats.mastered || 0
    });

    // 日历统计：显示每天学习单词数
    renderCalendar();

    // 热力图已移除
  } catch (err) {
    handleError(err);
  }
}

/**
 * 加载设置并填充表单
 */
async function loadSettings() {
  try {
    const s = await api.getSettings();
    const goalInput = $('#dailyGoalInput');
    if (goalInput) goalInput.value = s.daily_goal || 20;
    const reviewGoalInput = $('#dailyReviewGoalInput');
    if (reviewGoalInput) reviewGoalInput.value = s.daily_review_goal !== undefined ? s.daily_review_goal : 50;
    const strategySel = $('#reviewStrategySelect');
    if (strategySel) strategySel.value = s.review_strategy || 'standard';
    const antiToggle = $('#antiForgetToggle');
    if (antiToggle) antiToggle.checked = s.anti_forget !== undefined ? s.anti_forget : true;
    const antiIntervalInput = $('#antiForgetIntervalInput');
    if (antiIntervalInput) antiIntervalInput.value = s.anti_forget_interval || 30;
    updateAntiForgetRowVisibility();
    // 高亮当前策略行
    const currentStrategy = s.review_strategy || 'standard';
    ['relaxed', 'standard', 'strict'].forEach(name => {
      const row = $(`#strategy-row-${name}`);
      if (row) row.classList.toggle('active-strategy', name === currentStrategy);
    });
  } catch (err) {
    // 静默失败，不影响统计页
    console.warn('加载设置失败', err);
  }
}

/**
 * 防遗忘开关变化时，显示/隐藏回顾间隔行
 */
function updateAntiForgetRowVisibility() {
  const toggle = $('#antiForgetToggle');
  const row = $('#antiForgetIntervalRow');
  if (toggle && row) {
    row.style.display = toggle.checked ? '' : 'none';
  }
}

/**
 * 保存学习计划设置（每日新词目标 + 每日复习上限）
 */
async function handleSaveDailyGoal() {
  const input = $('#dailyGoalInput');
  if (!input) return;
  const goal = parseInt(input.value, 10);
  if (!goal || goal < 1 || goal > 200) {
    showToast('每日学习目标请输入 1-200 之间的数字', 'error');
    return;
  }
  const reviewInput = $('#dailyReviewGoalInput');
  const reviewGoal = reviewInput ? parseInt(reviewInput.value, 10) : 50;
  if (isNaN(reviewGoal) || reviewGoal < 0 || reviewGoal > 500) {
    showToast('每日复习上限请输入 0-500 之间的数字（0=不限）', 'error');
    return;
  }
  try {
    await api.updateSettings({ daily_goal: goal, daily_review_goal: reviewGoal });
    showToast(`已保存：每日学习 ${goal} 个，复习上限 ${reviewGoal === 0 ? '不限' : reviewGoal + ' 个'}`, 'success');
  } catch (err) {
    handleError(err);
  }
}

/**
 * 保存复习策略与防遗忘设置
 */
async function handleSaveReviewStrategy() {
  const strategySel = $('#reviewStrategySelect');
  const antiToggle = $('#antiForgetToggle');
  const antiIntervalInput = $('#antiForgetIntervalInput');
  if (!strategySel || !antiToggle) return;
  const strategy = strategySel.value;
  const anti = antiToggle.checked;
  const interval = antiIntervalInput ? parseInt(antiIntervalInput.value, 10) : 30;
  if (anti && (isNaN(interval) || interval < 1 || interval > 365)) {
    showToast('回顾间隔请输入 1-365 之间的天数', 'error');
    return;
  }
  try {
    await api.updateSettings({
      review_strategy: strategy,
      anti_forget: anti,
      anti_forget_interval: interval,
    });
    showToast('复习策略已保存', 'success');
    updateAntiForgetRowVisibility();
  } catch (err) {
    handleError(err);
  }
}

/**
 * 导出词库 - 相关逻辑
 * 支持按当前单词本/筛选条件导出，格式：CSV / TXT / Anki
 */

// 切换导出菜单显示
function toggleExportMenu() {
  const menu = $('#exportMenu');
  const isVisible = menu.style.display !== 'none';
  if (isVisible) {
    closeExportMenu();
  } else {
    // 更新提示文字：当前选中了哪个单词本
    const tip = $('#exportMenuTip');
    if (libraryWordbook === '') {
      tip.textContent = '导出全部单词';
    } else if (libraryWordbook === '0') {
      tip.textContent = '导出未归类单词';
    } else {
      const book = wordbooks.find(b => String(b.id) === String(libraryWordbook));
      tip.textContent = book ? `导出「${book.name}」单词` : '导出当前单词';
    }
    menu.style.display = 'block';
  }
}

// 关闭导出菜单
function closeExportMenu() {
  const menu = $('#exportMenu');
  if (menu) menu.style.display = 'none';
}

// 执行导出
async function handleExportWords(format) {
  closeExportMenu();

  // 构建查询参数（与当前词库筛选一致）
  const params = new URLSearchParams();
  params.set('format', format);
  if (libraryWordbook !== '') params.set('wordbook_id', libraryWordbook);
  if (libraryFilter !== 'all' && libraryFilter !== 'starred') params.set('status', libraryFilter);
  if (libraryFilter === 'starred') params.set('starred', '1');
  if (librarySearch) params.set('search', librarySearch);

  const url = `${api.baseURL}/words/export?${params.toString()}`;
  const fmtName = { csv: 'CSV', txt: 'TXT', anki: 'Anki' }[format] || format;

  try {
    showLoading(`正在导出 ${fmtName}...`);
    // 用fetch获取文件内容，再用Blob触发下载（更可靠，能正确处理中文文件名）
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `导出失败 (${res.status})`);
    }
    // 从响应头提取文件名
    const disposition = res.headers.get('Content-Disposition') || '';
    let filename = `wordmemo.${format === 'anki' ? 'txt' : format}`;
    const match = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/);
    if (match) {
      filename = decodeURIComponent(match[1]);
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
    hideLoading();
    showToast(`已导出 ${fmtName} 格式`, 'success');
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

/**
 * 导出词库为 CSV（设置页旧入口，保留兼容）
 */
function handleExportCsv() {
  handleExportWords('csv');
}

/**
 * 清空所有数据
 */
async function handleClearData() {
  if (!confirm('确定要清空所有单词和学习记录吗？此操作不可恢复！')) return;
  if (!confirm('再次确认：清空后所有数据将永久丢失，确定继续吗？')) return;
  try {
    showLoading();
    await api.clearAllWords();
    hideLoading();
    showToast('已清空所有数据', 'success');
    // 刷新当前页
    renderStats();
    loadSettings();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

/* ====================================================
   十、单词详情弹窗
   ==================================================== */

let currentDetailWord = null; // 当前查看的单词

/**
 * 打开单词详情
 * @param {number|string} id - 单词 ID
 */
async function openWordDetail(id) {
  try {
    showLoading();
    const word = await api.getWord(id);
    hideLoading();
    currentDetailWord = word;
    fillDetailModal(word);
    $('#wordDetailModal').classList.add('active');
    // 自动发音
    speakWord(word.word);
  } catch (err) {
    handleError(err);
  }
}

/**
 * 填充详情弹窗内容
 */
function fillDetailModal(word) {
  $('#modalWord').textContent = word.word;
  $('#modalPhonetic').textContent = word.phonetic || '';
  $('#modalMeaning').textContent = word.meaning || '暂无释义';

  // 词性标签：从释义中提取词性标记（n./v./adj./adv./prep./conj./pron./art./num./int.等）
  const posBadge = $('#modalPosBadge');
  const posMap = {
    'n.': '名词', 'v.': '动词', 'adj.': '形容词', 'adv.': '副词',
    'prep.': '介词', 'conj.': '连词', 'pron.': '代词', 'art.': '冠词',
    'num.': '数词', 'int.': '感叹词', 'aux.': '助动词', 'modal.': '情态动词',
  };
  let posLabel = '';
  if (word.meaning) {
    const m = word.meaning.trim().match(/^(n\.|v\.|adj\.|adv\.|prep\.|conj\.|pron\.|art\.|num\.|int\.|aux\.|modal\.)/);
    if (m && posMap[m[1]]) {
      posLabel = posMap[m[1]];
    }
  }
  if (posLabel) {
    posBadge.textContent = posLabel;
    posBadge.style.display = 'inline-block';
  } else {
    posBadge.style.display = 'none';
  }

  // 单词类型标签（基础词/复合词/派生词/变形词）
  const typeBadge = $('#modalWordTypeBadge');
  const wordType = word.word_type || '';
  const typeClassMap = {
    '基础词': 'type-basic',
    '复合词': 'type-compound',
    '派生词': 'type-derivative',
    '变形词': 'type-inflected',
    '动词': 'type-verb',
  };
  if (wordType && typeClassMap[wordType]) {
    typeBadge.textContent = wordType;
    typeBadge.className = 'word-type-badge ' + typeClassMap[wordType];
    typeBadge.style.display = 'inline-block';
  } else {
    typeBadge.style.display = 'none';
  }

  // 变形（时态/复数/比较级等，有什么显示什么，默认收起）
  const tensesSection = $('#modalTensesSection');
  const tensesGrid = $('#modalTenses');
  const tensesToggle = $('#modalTensesToggle');
  const tensesToggleText = tensesToggle.querySelector('.modal-tag-text');
  // 默认收起
  tensesGrid.style.display = 'none';
  tensesToggle.classList.remove('tenses-toggle-open');
  if (word.tenses) {
    const t = word.tenses;
    const inflType = t.inflection_type || 'tense';
    let items = [];
    let btnLabel = '变形';
    if (inflType === 'tense' && t.base) {
      btnLabel = '时态变形';
      items = [
        { label: '原形',     value: t.base },
        { label: '三单',     value: t.third_singular },
        { label: '过去式',   value: t.past },
        { label: '过去分词', value: t.past_participle },
        { label: '现在分词', value: t.present_participle },
      ].filter(it => it.value);
    } else if (inflType === 'plural' && (t.singular || t.plural)) {
      btnLabel = '复数变形';
      items = [
        { label: '单数', value: t.singular },
        { label: '复数', value: t.plural },
      ].filter(it => it.value);
    } else if (inflType === 'degree' && (t.positive || t.comparative || t.superlative)) {
      btnLabel = '级变化';
      items = [
        { label: '原级',   value: t.positive },
        { label: '比较级', value: t.comparative },
        { label: '最高级', value: t.superlative },
      ].filter(it => it.value);
    }
    if (items.length > 0) {
      tensesSection.style.display = 'block';
      tensesToggleText.textContent = btnLabel;
      tensesGrid.innerHTML = items.map((it) => {
        const isBase = it.label === '原形' || it.label === '单数' || it.label === '原级';
        return `<div class="tense-card ${isBase ? 'tense-base' : ''}">
          <span class="tense-label">${it.label}</span>
          <span class="tense-word">${escapeHtml(it.value)}</span>
        </div>`;
      }).join('');
      // 绑定展开/收起
      const toggleHandler = () => {
        const isOpen = tensesGrid.style.display !== 'none';
        if (isOpen) {
          tensesGrid.style.display = 'none';
          tensesToggle.classList.remove('tenses-toggle-open');
        } else {
          tensesGrid.style.display = 'grid';
          tensesToggle.classList.add('tenses-toggle-open');
        }
      };
      tensesToggle.onclick = toggleHandler;
    } else {
      tensesSection.style.display = 'none';
      tensesToggle.onclick = null;
    }
  } else {
    tensesSection.style.display = 'none';
    tensesToggle.onclick = null;
  }

  // 拆解
  const splitSection = $('#modalSplitSection');
  if (word.split_data && word.split_data.length > 0) {
    splitSection.style.display = 'block';
    $('#modalSplit').innerHTML = word.split_data.map(s => {
      // 判断是否有变形（原词与当前部分不同）
      const hasTransform = s.original && s.original !== s.part;
      // 变形链：原词 → 变形规则 → 当前部分
      const transformChain = hasTransform
        ? `<div class="split-transform">
             <span class="transform-original">${escapeHtml(s.original)}</span>
             <span class="transform-arrow">→</span>
             <span class="transform-rule">${escapeHtml(s.transform || '变形')}</span>
             <span class="transform-arrow">→</span>
             <span class="transform-current">${escapeHtml(s.part)}</span>
           </div>`
        : (s.transform && s.transform !== '原形不变'
           ? `<div class="split-transform"><span class="transform-rule">${escapeHtml(s.transform)}</span></div>`
           : '');
      // 原词释义（如果与当前部分意思不同才单独显示）
      const originalMeaning = (s.original_meaning && s.original_meaning !== s.meaning)
        ? `<div class="split-original-meaning">原词 ${escapeHtml(s.original)} 意思：${escapeHtml(s.original_meaning)}</div>`
        : '';
      return `
        <div class="split-item">
          <div class="split-part">${escapeHtml(s.part || '')}</div>
          ${s.meaning ? `<div class="split-meaning">${escapeHtml(s.meaning)}</div>` : ''}
          ${transformChain}
          ${originalMeaning}
          ${s.explain ? `<div class="split-explain">${escapeHtml(s.explain)}</div>` : ''}
        </div>
      `;
    }).join('');
  } else {
    splitSection.style.display = 'none';
  }

  // 词根词缀
  const morphSection = $('#modalMorphSection');
  if (word.morph_data && word.morph_data.length > 0) {
    morphSection.style.display = 'block';
    $('#modalMorph').innerHTML = word.morph_data.map(m => `
      <div class="morph-item">
        <span class="morph-type">${escapeHtml(m.type || '')}</span>
        <span class="morph-word">${escapeHtml(m.word || '')}</span>
        <span class="morph-meaning">${escapeHtml(m.meaning || '')}</span>
      </div>
    `).join('');
  } else {
    morphSection.style.display = 'none';
  }

  // 记忆方法
  const mnemonicSection = $('#modalMnemonicSection');
  if (word.mnemonic) {
    mnemonicSection.style.display = 'block';
    $('#modalMnemonic').textContent = word.mnemonic;
  } else {
    mnemonicSection.style.display = 'none';
  }

  // 例句
  const exampleSection = $('#modalExampleSection');
  if (word.examples && word.examples.length > 0) {
    exampleSection.style.display = 'block';
    $('#modalExamples').innerHTML = word.examples.map(ex => `
      <div class="example-item">
        <p class="example-en">${escapeHtml(ex.en || '')}</p>
        <p class="example-zh">${escapeHtml(ex.zh || '')}</p>
      </div>
    `).join('');
  } else {
    exampleSection.style.display = 'none';
  }

  // 学习状态信息已移除（用户要求不显示）

  // 重点标记按钮状态
  const starBtn = $('#modalStarBtn');
  if (starBtn) {
    const isStarred = !!word.is_starred;
    starBtn.textContent = isStarred ? '★ 取消重点' : '☆ 标重点';
    starBtn.classList.toggle('starred', isStarred);
  }
}

// 关闭详情弹窗
function closeDetailModal() {
  $('#wordDetailModal').classList.remove('active');
  currentDetailWord = null;
}

// 删除单词
async function handleDeleteWord() {
  if (!currentDetailWord) return;
  if (!confirm(`确定删除「${currentDetailWord.word}」吗？`)) return;
  try {
    showLoading('删除中...');
    await api.deleteWord(currentDetailWord.id);
    hideLoading();
    showToast('删除成功', 'success');
    closeDetailModal();
    // 刷新词库
    if ($('#page-library').classList.contains('active')) renderLibrary();
    if ($('#page-home').classList.contains('active')) renderHome();
  } catch (err) {
    handleError(err);
  }
}

// 打开编辑弹窗
function openEditModal() {
  if (!currentDetailWord) return;
  $('#editWord').value = currentDetailWord.word || '';
  $('#editPhonetic').value = currentDetailWord.phonetic || '';
  $('#editMeaning').value = currentDetailWord.meaning || '';
  $('#editStatus').value = currentDetailWord.status || 'new';
  $('#editModal').classList.add('active');
}

function closeEditModal() {
  $('#editModal').classList.remove('active');
}

// 保存编辑
async function handleSaveEdit() {
  if (!currentDetailWord) return;
  const data = {
    word: $('#editWord').value.trim(),
    phonetic: $('#editPhonetic').value.trim(),
    meaning: $('#editMeaning').value.trim(),
    status: $('#editStatus').value
  };
  if (!data.word) {
    showToast('单词不能为空', 'warning');
    return;
  }
  try {
    showLoading('保存中...');
    const updated = await api.updateWord(currentDetailWord.id, data);
    hideLoading();
    showToast('保存成功', 'success');
    closeEditModal();
    // 刷新详情（api.updateWord 返回 {success, data}，需取 data）
    if (updated && updated.data) {
      currentDetailWord = updated.data;
      fillDetailModal(updated.data);
    } else {
      closeDetailModal();
    }
    // 刷新列表
    if ($('#page-library').classList.contains('active')) renderLibrary();
    // 刷新首页统计（状态变更后同步今日已学等数据）
    refreshHomeStats();
  } catch (err) {
    handleError(err);
  }
}

/* ====================================================
   移动单词到其他词本
   ==================================================== */

// 切换单词重点标记
async function handleToggleStar() {
  if (!currentDetailWord) return;
  try {
    const res = await api.toggleStar(currentDetailWord.id);
    if (res && res.success) {
      currentDetailWord.is_starred = res.is_starred;
      // 更新按钮显示
      const btn = $('#modalStarBtn');
      if (btn) {
        btn.textContent = res.is_starred ? '★ 取消重点' : '☆ 标重点';
        btn.classList.toggle('starred', res.is_starred);
      }
      showToast(res.is_starred ? '已标记为重点单词' : '已取消重点标记', 'success');
      // 刷新列表
      if ($('#page-library').classList.contains('active')) renderLibrary();
      if ($('#page-home').classList.contains('active')) renderHome();
    }
  } catch (err) {
    handleError(err);
  }
}

async function handleRefreshExamples() {
  if (!currentDetailWord) return;
  const btn = $('#modalRefreshExamplesBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'AI生成中...';
  }
  try {
    const res = await fetch(`/api/words/${currentDetailWord.id}/refresh-examples`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();
    if (data.success && data.examples) {
      currentDetailWord.examples = data.examples;
      // 更新例句显示
      const exampleSection = $('#modalExampleSection');
      if (exampleSection) {
        exampleSection.style.display = 'block';
        $('#modalExamples').innerHTML = data.examples.map(ex => `
          <div class="example-item">
            <p class="example-en">${escapeHtml(ex.en || '')}</p>
            <p class="example-zh">${escapeHtml(ex.zh || '')}</p>
          </div>
        `).join('');
      }
      showToast('例句已更新', 'success');
    } else {
      showToast(data.error || '生成失败，请稍后重试', 'error');
    }
  } catch (err) {
    handleError(err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'AI生成更好的例句';
    }
  }
}

// 打开移动到词本弹窗（单个单词，从详情弹窗触发）
function openMoveWordbookModal() {
  if (!currentDetailWord) return;
  const select = $('#moveWordbookSelect');
  // 填充词本列表
  let html = '<option value="">未归类</option>';
  wordbooks.forEach(b => {
    const selected = currentDetailWord.wordbook_id === b.id ? 'selected' : '';
    html += `<option value="${b.id}" ${selected}>${escapeHtml(b.name)}（${b.word_count || 0}词）</option>`;
  });
  select.innerHTML = html;
  // 确保确认按钮绑定的是单个单词移动（避免多选模式遗留的 handleMultiMove）
  $('#moveConfirmBtn').onclick = handleMoveWordbook;
  $('#moveWordbookModal').classList.add('active');
}

function closeMoveWordbookModal() {
  $('#moveWordbookModal').classList.remove('active');
}

// 确认移动单词到词本
async function handleMoveWordbook() {
  if (!currentDetailWord) return;
  const targetWordbookId = $('#moveWordbookSelect').value;
  try {
    showLoading('移动中...');
    const data = { wordbook_id: targetWordbookId ? parseInt(targetWordbookId) : null };
    const res = await api.updateWord(currentDetailWord.id, data);
    hideLoading();
    showToast('已移动到新词本', 'success');
    closeMoveWordbookModal();
    // 刷新详情（res 格式 {success, data}，需取 data）
    if (res && res.data) {
      currentDetailWord = res.data;
      fillDetailModal(res.data);
    }
    // 刷新列表和词本条
    await loadWordbooks();
    if ($('#page-library').classList.contains('active')) renderLibrary();
    if ($('#page-home').classList.contains('active')) renderHome();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

/* ====================================================
   十一、Canvas 图表绘制
   ==================================================== */

/**
 * 设置 Canvas 高分辨率（适配 devicePixelRatio）
 */
function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = rect.width || canvas.parentElement.clientWidth;
  const h = rect.height || 160;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  return { ctx, width: w, height: h };
}

/**
 * 绘制折线图（学习曲线）
 * @param {HTMLCanvasElement} canvas
 * @param {number[]} data - 7天数据
 */
function drawLineChart(canvas, data) {
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);

  const padding = { top: 20, right: 16, bottom: 28, left: 32 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // 补齐7天数据
  const values = (data && data.length ? data : [0, 0, 0, 0, 0, 0, 0]).slice(-7);
  while (values.length < 7) values.unshift(0);

  const maxVal = Math.max(...values, 5);
  const stepX = chartW / (values.length - 1);

  // 绘制网格线
  ctx.strokeStyle = '#eee';
  ctx.lineWidth = 1;
  ctx.font = '10px sans-serif';
  ctx.fillStyle = '#aaa';
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartW, y);
    ctx.stroke();
    // Y轴刻度
    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillText(val, 6, y + 3);
  }

  // 渐变填充区域
  const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
  gradient.addColorStop(0, 'rgba(74,127,255,0.35)');
  gradient.addColorStop(1, 'rgba(74,127,255,0.02)');

  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top + chartH);
  values.forEach((v, i) => {
    const x = padding.left + stepX * i;
    const y = padding.top + chartH - (v / maxVal) * chartH;
    ctx.lineTo(x, y);
  });
  ctx.lineTo(padding.left + chartW, padding.top + chartH);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  // 绘制折线
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = padding.left + stepX * i;
    const y = padding.top + chartH - (v / maxVal) * chartH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#4a7fff';
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // 绘制数据点
  values.forEach((v, i) => {
    const x = padding.left + stepX * i;
    const y = padding.top + chartH - (v / maxVal) * chartH;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.strokeStyle = '#4a7fff';
    ctx.lineWidth = 2;
    ctx.stroke();
  });

  // X轴标签
  const days = ['7天前', '6天前', '5天前', '4天前', '3天前', '昨天', '今天'];
  ctx.fillStyle = '#aaa';
  ctx.textAlign = 'center';
  values.forEach((v, i) => {
    const x = padding.left + stepX * i;
    ctx.fillText(days[i], x, height - 8);
  });
}

/**
 * 绘制柱状图（7天学习量）
 */
function drawBarChart(canvas, data) {
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);

  const padding = { top: 20, right: 16, bottom: 28, left: 32 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const values = (data && data.length ? data : [0, 0, 0, 0, 0, 0, 0]).slice(-7);
  while (values.length < 7) values.unshift(0);

  const maxVal = Math.max(...values, 5);
  const barW = chartW / values.length * 0.55;
  const gap = chartW / values.length;

  // 网格线
  ctx.strokeStyle = '#eee';
  ctx.lineWidth = 1;
  ctx.font = '10px sans-serif';
  ctx.fillStyle = '#aaa';
  ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartW, y);
    ctx.stroke();
    const val = Math.round(maxVal - (maxVal / 4) * i);
    ctx.fillText(val, padding.left - 4, y + 3);
  }

  const days = ['7天前', '6天前', '5天前', '4天前', '3天前', '昨天', '今天'];

  // 绘制圆角柱
  values.forEach((v, i) => {
    const x = padding.left + gap * i + (gap - barW) / 2;
    const barH = (v / maxVal) * chartH;
    const y = padding.top + chartH - barH;

    // 渐变
    const grad = ctx.createLinearGradient(0, y, 0, y + barH);
    grad.addColorStop(0, '#6f99ff');
    grad.addColorStop(1, '#4a7fff');
    ctx.fillStyle = grad;

    // 圆角矩形
    drawRoundRect(ctx, x, y, barW, Math.max(barH, 2), 4);
    ctx.fill();

    // 顶部数值
    if (v > 0) {
      ctx.fillStyle = '#4a7fff';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(v, x + barW / 2, y - 4);
    }

    // X轴标签
    ctx.fillStyle = '#aaa';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(days[i], x + barW / 2, height - 8);
  });
}

/**
 * 绘制圆角矩形辅助函数
 */
function drawRoundRect(ctx, x, y, w, h, r) {
  if (h < r * 2) r = h / 2;
  if (w < r * 2) r = w / 2;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, 0);
  ctx.arcTo(x, y + h, x, y, 0);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * 绘制饼图（单词状态分布）
 */
function drawPieChart(canvas, data) {
  if (!canvas) return;
  const { ctx, width, height } = setupCanvas(canvas);
  ctx.clearRect(0, 0, width, height);

  const total = data.new + data.review + data.mastered;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 2 - 12;

  // 空数据提示
  if (total === 0) {
    ctx.fillStyle = '#ccc';
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('暂无数据', cx, cy);
    return;
  }

  const segments = [
    { value: data.new, color: '#4a7fff', label: '未学习' },
    { value: data.review, color: '#ff9f0a', label: '复习中' },
    { value: data.mastered, color: '#34c759', label: '已掌握' }
  ].filter(s => s.value > 0);

  let startAngle = -Math.PI / 2;
  segments.forEach(seg => {
    const angle = (seg.value / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, startAngle, startAngle + angle);
    ctx.closePath();
    ctx.fillStyle = seg.color;
    ctx.fill();
    startAngle += angle;
  });

  // 中心白圆（甜甜圈效果）
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 0.55, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.fill();

  // 中心文字
  ctx.fillStyle = '#1a1a2e';
  ctx.font = 'bold 20px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(total, cx, cy - 6);
  ctx.fillStyle = '#8e8e93';
  ctx.font = '11px sans-serif';
  ctx.fillText('总词数', cx, cy + 12);

  // 渲染图例
  const legend = $('#pieLegend');
  legend.innerHTML = segments.map(seg => `
    <div class="legend-item">
      <span class="legend-dot" style="background:${seg.color}"></span>
      ${seg.label} (${seg.value})
    </div>
  `).join('');
}

/* ====================================================
   十二、顶部状态栏时间更新
   ==================================================== */
function updateStatusBarTime() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  $('#statusTime').textContent = `${h}:${m}`;
}

/* ====================================================
   十三、事件绑定与初始化
   ==================================================== */
function bindEvents() {
  // 底部 TabBar 切换
  $$('.tab-item').forEach(tab => {
    tab.addEventListener('click', () => switchPage(tab.dataset.page));
  });

  // 首页操作按钮
  $('#btnStartLearn').addEventListener('click', () => {
    learnQueue = []; // 重置队列以重新加载
    learnStarredOnly = false; // 普通学习
    switchPage('learn');
    updateLearnModeUI(); // 同步学习范围提示（普通学习隐藏）
  });
  $('#btnStartReview').addEventListener('click', () => {
    reviewQueue = [];
    reviewStarredOnly = false; // 普通复习
    reviewAllMode = false; // 普通复习：仅今日到期（避免上次"重点复习/自主复习"的状态残留）
    switchPage('review');
    // 进入时同步复习范围 UI（默认今日到期）
    updateReviewModeUI();
  });

  // 重点单词学习/复习
  // 重点单词是当前词本内的"子词本"：重点学习/复习只作用于当前所选词本内的重点单词，
  // 与主词本分开。若未选词本，则作用于全部词本的重点单词。
  const btnLearnStarred = $('#btnLearnStarred');
  if (btnLearnStarred) {
    btnLearnStarred.addEventListener('click', () => {
      learnQueue = [];
      learnStarredOnly = true; // 仅重点单词
      // 保留当前所选词本，只学习该词本内的重点单词（重点单词是该词本的子词本）
      switchPage('learn');
      // 同步学习范围提示
      updateLearnModeUI();
    });
  }
  const btnReviewStarred = $('#btnReviewStarred');
  if (btnReviewStarred) {
    btnReviewStarred.addEventListener('click', () => {
      reviewQueue = [];
      reviewStarredOnly = true; // 仅重点单词
      // 保留当前所选词本，只复习该词本内的重点单词（重点单词是该词本的子词本）
      // 重点复习使用自主复习：所有重点词都可复习，不受到期限制（避免"没有到期重点词"）
      reviewAllMode = true;
      switchPage('review');
      // 同步复习范围 UI
      updateReviewModeUI();
    });
  }
  $('#goLibraryFromHome').addEventListener('click', () => switchPage('library'));

  // 录入方式切换
  $$('.tab-switch-item').forEach(t => {
    t.addEventListener('click', () => switchInputTab(t.dataset.inputTab));
  });

  // 手动添加
  $('#btnManualAdd').addEventListener('click', handleManualAdd);

  // 批量添加
  $('#btnBatchAdd').addEventListener('click', handleBatchAdd);
  $('#btnBatchPreview').addEventListener('click', handleBatchPreview);
  $('#btnBatchConfirm').addEventListener('click', handleBatchConfirm);

  // 文档导入
  $('#docUploadArea').addEventListener('click', handleDocFilePick);
  $('#docFileInput').addEventListener('change', handleDocFileChange);
  $('#btnDocCancel').addEventListener('click', handleDocCancel);
  $('#btnDocImport').addEventListener('click', handleDocImport);
  // 拖拽上传
  const docArea = $('#docUploadArea');
  docArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    docArea.classList.add('dragover');
  });
  docArea.addEventListener('dragleave', () => {
    docArea.classList.remove('dragover');
  });
  docArea.addEventListener('drop', (e) => {
    e.preventDefault();
    docArea.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleDocUpload(file);
  });
  // 文档导入：新建单词本按钮
  $('#btnNewWordbook').addEventListener('click', () => openWordbookModal());
  // 单词本弹窗
  $('#wordbookCloseBtn').addEventListener('click', closeWordbookModal);
  $('#wordbookCancelBtn').addEventListener('click', closeWordbookModal);
  $('#wordbookSaveBtn').addEventListener('click', handleSaveWordbook);
  $('#wordbookDeleteBtn').addEventListener('click', handleDeleteWordbook);
  // 分享按钮
  const shareBtn = $('#wordbookShareBtn');
  if (shareBtn) shareBtn.addEventListener('click', handleToggleShare);
  // 全局词本弹窗
  const globalCloseBtn = $('#globalWordbookCloseBtn');
  if (globalCloseBtn) globalCloseBtn.addEventListener('click', closeGlobalWordbookModal);
  const globalOverlay = $('#globalWordbookModal');
  if (globalOverlay) {
    globalOverlay.addEventListener('click', (e) => {
      if (e.target === globalOverlay) closeGlobalWordbookModal();
    });
  }
  $('#wordbookNameInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSaveWordbook();
  });
  // 颜色选择
  $$('.color-dot').forEach(dot => {
    dot.addEventListener('click', () => {
      currentWordbookColor = dot.dataset.color;
      $$('.color-dot').forEach(d => d.classList.remove('active'));
      dot.classList.add('active');
    });
  });

  // 扫描录入（AI/OCR识图）
  $('#scanArea').addEventListener('click', handleScanPick);
  $('#scanInput').addEventListener('change', handleScanChange);
  $('#btnScanRecognize').addEventListener('click', handleScanRecognize);
  $('#btnScanCheckAll').addEventListener('click', (e) => { e.stopPropagation(); handleScanCheckAll(); });
  $('#btnScanAddSelected').addEventListener('click', handleScanAddSelected);

  // 扫描模式切换（极速OCR / AI精准）
  $$('.scan-mode-item').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      $$('.scan-mode-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      scanMode = btn.dataset.scanMode;
      // 更新提示文字
      const tip = $('#scanModeTip');
      if (tip) {
        if (scanMode === 'ocr') {
          // 查询当月OCR用量并显示
          try {
            const usage = await api.ocrUsage();
            if (usage && usage.success) {
              const userRem = usage.user_remaining;
              const globalRem = usage.global_remaining;
              // 优先检查全局是否用完
              if (globalRem <= 0) {
                tip.textContent = `全局OCR次数已用完（${usage.global_limit}次/月），请使用AI精准模式`;
                showToast('全局OCR次数已用完，已切换到AI精准模式', 'warning');
                scanMode = 'ai';
                $$('.scan-mode-item').forEach(b => {
                  b.classList.toggle('active', b.dataset.scanMode === 'ai');
                });
                tip.textContent = '拍照或选择图片，AI视觉识别单词和手写内容（每张约20秒）';
              } else if (!usage.is_admin && userRem <= 0) {
                tip.textContent = `您本月OCR次数已用完（${usage.user_limit}次），请使用AI精准模式`;
                showToast('个人OCR次数已用完，已切换到AI精准模式', 'warning');
                scanMode = 'ai';
                $$('.scan-mode-item').forEach(b => {
                  b.classList.toggle('active', b.dataset.scanMode === 'ai');
                });
                tip.textContent = '拍照或选择图片，AI视觉识别单词和手写内容（每张约20秒）';
              } else {
                const userText = usage.is_admin
                  ? `管理员不限`
                  : `个人剩余 ${userRem}/${usage.user_limit}`;
                tip.textContent = `OCR极速识别（每张约2秒）｜全局 ${usage.global_count}/${usage.global_limit}，${userText}`;
              }
            } else {
              tip.textContent = '拍照或选择图片，OCR极速识别单词+本地词典释义（每张约2秒）';
            }
          } catch {
            tip.textContent = '拍照或选择图片，OCR极速识别单词+本地词典释义（每张约2秒）';
          }
        } else {
          tip.textContent = '拍照或选择图片，AI视觉识别单词和手写内容（每张约20秒）';
        }
      }
      // 更新识别按钮文字
      const recognizeBtn = $('#btnScanRecognize');
      if (recognizeBtn) {
        recognizeBtn.textContent = scanMode === 'ocr' ? '极速识别' : 'AI识别';
      }
    });
  });

  // 添加更多图片按钮
  const btnScanAddMore = $('#btnScanAddMore');
  if (btnScanAddMore) {
    btnScanAddMore.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      $('#scanInput').click();
    });
  }

  // 词库搜索（输入防抖）
  let searchTimer = null;
  $('#searchInput').addEventListener('input', (e) => {
    librarySearch = e.target.value.trim();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderLibrary, 350);
  });

  // 词库筛选
  $$('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      libraryFilter = tab.dataset.status;
      renderLibrary();
    });
  });

  // 词库排序
  $('#sortSelect').addEventListener('change', (e) => {
    librarySort = e.target.value;
    // 自定义顺序需要先选中具体词本才能在列表中显示上移/下移按钮
    if (librarySort === 'custom' && (libraryWordbook === '' || libraryWordbook === '0')) {
      showToast('自定义顺序需要先在上方选择一个具体单词本', 'warning');
    }
    renderLibrary();
  });

  // 自定义顺序：长按 ☰ 手柄拖动排序
  initDragReorder();

  // 设置：学习计划（失焦/改变保存）
  $('#dailyGoalInput').addEventListener('change', handleSaveDailyGoal);
  $('#dailyGoalInput').addEventListener('blur', handleSaveDailyGoal);
  $('#dailyReviewGoalInput').addEventListener('change', handleSaveDailyGoal);
  $('#dailyReviewGoalInput').addEventListener('blur', handleSaveDailyGoal);
  // 设置：学习取词顺序（本地保存，不存后端）
  const learnOrderSel = $('#learnOrderSelect');
  if (learnOrderSel) {
    // 从 localStorage 读取上次设置
    const savedOrder = localStorage.getItem('wordmemo_learn_order');
    if (savedOrder === 'random') {
      learnRandomMode = true;
      learnOrderSel.value = 'random';
    }
    learnOrderSel.addEventListener('change', (e) => {
      learnRandomMode = e.target.value === 'random';
      localStorage.setItem('wordmemo_learn_order', e.target.value);
      showToast(learnRandomMode ? '已切换为随机取词' : '已切换为顺序取词', 'success');
    });
  }
  // 设置：复习顺序（本地保存，不存后端）
  const reviewOrderSel = $('#reviewOrderSelect');
  if (reviewOrderSel) {
    const savedReviewOrder = localStorage.getItem('wordmemo_review_order');
    if (savedReviewOrder === 'random') {
      reviewRandomMode = true;
      reviewOrderSel.value = 'random';
    }
    reviewOrderSel.addEventListener('change', (e) => {
      reviewRandomMode = e.target.value === 'random';
      localStorage.setItem('wordmemo_review_order', e.target.value);
      showToast(reviewRandomMode ? '已切换为随机复习' : '已切换为按时间复习', 'success');
    });
  }
  // 设置：复习策略与防遗忘
  $('#reviewStrategySelect').addEventListener('change', () => {
    handleSaveReviewStrategy();
    // 更新策略表高亮
    const sel = $('#reviewStrategySelect');
    if (sel) {
      ['relaxed', 'standard', 'strict'].forEach(name => {
        const row = $(`#strategy-row-${name}`);
        if (row) row.classList.toggle('active-strategy', name === sel.value);
      });
    }
  });
  $('#antiForgetToggle').addEventListener('change', handleSaveReviewStrategy);
  $('#antiForgetIntervalInput').addEventListener('change', handleSaveReviewStrategy);
  $('#antiForgetIntervalInput').addEventListener('blur', handleSaveReviewStrategy);
  // 设置：导出 CSV
  $('#exportCsvBtn').addEventListener('click', handleExportCsv);
  // 设置：清空数据
  $('#clearDataBtn').addEventListener('click', handleClearData);

  // 词库页：导出按钮
  $('#btnExport').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleExportMenu();
  });
  // 导出菜单：点击格式项
  $$('.export-menu-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      handleExportWords(item.dataset.format);
    });
  });
  // 点击页面其他区域关闭导出菜单
  document.addEventListener('click', (e) => {
    const dropdown = $('#exportDropdown');
    if (dropdown && !dropdown.contains(e.target)) {
      closeExportMenu();
    }
  });

  // 浮动添加按钮 -> 可拖动，点击跳转录入页
  const fabAdd = $('#fabAdd');
  if (fabAdd) {
    // 恢复上次位置
    const savedPos = localStorage.getItem('wordmemo_fab_pos');
    if (savedPos) {
      try {
        const pos = JSON.parse(savedPos);
        fabAdd.style.right = 'auto';
        fabAdd.style.left = pos.left + 'px';
        fabAdd.style.top = pos.top + 'px';
      } catch (e) {}
    }

    let fabDragging = false;
    let fabMoved = false;
    let fabStartX = 0, fabStartY = 0;
    let fabStartLeft = 0, fabStartTop = 0;

    // 触摸拖动
    fabAdd.addEventListener('touchstart', (e) => {
      if (e.touches.length === 0) return;
      fabDragging = true;
      fabMoved = false;
      fabStartX = e.touches[0].clientX;
      fabStartY = e.touches[0].clientY;
      const rect = fabAdd.getBoundingClientRect();
      fabStartLeft = rect.left;
      fabStartTop = rect.top;
      fabAdd.style.right = 'auto';
      fabAdd.style.transition = 'none';
      fabAdd.classList.add('fab-dragging');
      e.stopPropagation();
    }, { passive: true });

    fabAdd.addEventListener('touchmove', (e) => {
      if (!fabDragging || e.touches.length === 0) return;
      const dx = e.touches[0].clientX - fabStartX;
      const dy = e.touches[0].clientY - fabStartY;
      if (Math.abs(dx) > 5 || Math.abs(dy) > 5) fabMoved = true;
      let newLeft = fabStartLeft + dx;
      let newTop = fabStartTop + dy;
      const btnW = fabAdd.offsetWidth;
      const btnH = fabAdd.offsetHeight;
      newLeft = Math.max(8, Math.min(window.innerWidth - btnW - 8, newLeft));
      newTop = Math.max(8, Math.min(window.innerHeight - btnH - 8, newTop));
      fabAdd.style.left = newLeft + 'px';
      fabAdd.style.top = newTop + 'px';
      e.stopPropagation();
    }, { passive: true });

    fabAdd.addEventListener('touchend', (e) => {
      fabAdd.style.transition = '';
      fabAdd.classList.remove('fab-dragging');
      if (fabDragging && !fabMoved) {
        switchPage('input');
      }
      if (fabMoved) {
        const rect = fabAdd.getBoundingClientRect();
        localStorage.setItem('wordmemo_fab_pos', JSON.stringify({
          left: rect.left,
          top: rect.top,
        }));
      }
      fabDragging = false;
      fabMoved = false;
      e.stopPropagation();
    });

    // 鼠标拖动（桌面端）
    let fabMouseDragging = false;
    fabAdd.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      fabMouseDragging = true;
      fabMoved = false;
      fabStartX = e.clientX;
      fabStartY = e.clientY;
      const rect = fabAdd.getBoundingClientRect();
      fabStartLeft = rect.left;
      fabStartTop = rect.top;
      fabAdd.style.right = 'auto';
      fabAdd.style.transition = 'none';
      fabAdd.classList.add('fab-dragging');
      e.preventDefault();
      e.stopPropagation();
    });

    document.addEventListener('mousemove', (e) => {
      if (!fabMouseDragging) return;
      const dx = e.clientX - fabStartX;
      const dy = e.clientY - fabStartY;
      if (Math.abs(dx) > 5 || Math.abs(dy) > 5) fabMoved = true;
      let newLeft = fabStartLeft + dx;
      let newTop = fabStartTop + dy;
      const btnW = fabAdd.offsetWidth;
      const btnH = fabAdd.offsetHeight;
      newLeft = Math.max(8, Math.min(window.innerWidth - btnW - 8, newLeft));
      newTop = Math.max(8, Math.min(window.innerHeight - btnH - 8, newTop));
      fabAdd.style.left = newLeft + 'px';
      fabAdd.style.top = newTop + 'px';
    });

    document.addEventListener('mouseup', (e) => {
      if (!fabMouseDragging) return;
      fabAdd.style.transition = '';
      fabAdd.classList.remove('fab-dragging');
      if (!fabMoved) {
        switchPage('input');
      }
      if (fabMoved) {
        const rect = fabAdd.getBoundingClientRect();
        localStorage.setItem('wordmemo_fab_pos', JSON.stringify({
          left: rect.left,
          top: rect.top,
        }));
      }
      fabMouseDragging = false;
      fabMoved = false;
    });
  }

  // 学习翻卡
  $('#learnCard').addEventListener('click', flipLearnCard);
  $('#btnLearnKnown').addEventListener('click', handleLearnKnown);
  $('#btnLearnDetail').addEventListener('click', handleLearnDetail);
  $('#btnLearnPrev').addEventListener('click', handleLearnPrev);
  $('#learnClose').addEventListener('click', () => {
    // 退出学习时重置会话
    allLearnedIds = new Set();
    loadedWordIds = new Set();
    learnQueue = [];
    learnIndex = 0;
    switchPage('home');
  });
  // 学习页词书选择（必须选择词书才能学习）
  const learnWbSelect = $('#learnWordbookSelect');
  if (learnWbSelect) {
    learnWbSelect.addEventListener('change', (e) => {
      learnWordbookId = e.target.value;
      localStorage.setItem('wordmemo_learn_wordbook', learnWordbookId);
      // 同步到复习词书
      reviewWordbookId = learnWordbookId;
      localStorage.setItem('wordmemo_review_wordbook', reviewWordbookId);
      const reviewWbSel = $('#reviewWordbookSelect');
      if (reviewWbSel) reviewWbSel.value = learnWordbookId;
      // 重置队列
      allLearnedIds = new Set();
      loadedWordIds = new Set();
      learnQueue = [];
      learnIndex = 0;
      if (learnWordbookId !== '') {
        loadLearnQueue();
      } else {
        // 未选词书时显示空状态
        renderLearnCard();
        showToast('请选择一本词书', 'info');
      }
      // 同步学习范围提示（重点单词作用域跟随词书变化）
      updateLearnModeUI();
    });
  }
  // 翻卡模式：加入新词按钮（普通按钮）
  const btnLearnAddNew = $('#btnLearnAddNew');
  if (btnLearnAddNew) {
    btnLearnAddNew.addEventListener('click', () => {
      const countStr = prompt('要加入多少个未学习单词？', '10');
      if (countStr !== null) {
        const count = parseInt(countStr, 10);
        if (!isNaN(count) && count > 0) {
          loadLearnQueue(true, count);
        } else if (countStr.trim() !== '') {
          showToast('请输入有效的数字', 'error');
        }
      }
    });
  }
  // 复习页：加入新词按钮
  const btnReviewAddNew = $('#btnReviewAddNew');
  if (btnReviewAddNew) {
    btnReviewAddNew.addEventListener('click', () => {
      // 切到学习页并加入新词
      switchPage('learn');
      if (learnWordbookId !== '') {
        const countStr = prompt('要加入多少个未学习单词？', '10');
        if (countStr !== null) {
          const count = parseInt(countStr, 10);
          if (!isNaN(count) && count > 0) {
            loadLearnQueue(true, count);
          } else if (countStr.trim() !== '') {
            showToast('请输入有效的数字', 'error');
          }
        }
      } else {
        showToast('请先选择一本词书', 'info');
      }
    });
  }
  // 翻卡模式：翻今天所有按钮（卡片中）
  const reviewTodayBtn = $('#btnLearnReviewToday');
  if (reviewTodayBtn) {
    reviewTodayBtn.addEventListener('click', () => {
      loadTodayAllWords();
    });
  }
  // 空状态：加入新词按钮
  const learnAddMoreBtn = $('#learnAddMoreBtn');
  if (learnAddMoreBtn) {
    learnAddMoreBtn.addEventListener('click', () => {
      const countStr = prompt('要加入多少个未学习单词？', '10');
      if (countStr !== null) {
        const count = parseInt(countStr, 10);
        if (!isNaN(count) && count > 0) {
          loadLearnQueue(true, count);
        } else if (countStr.trim() !== '') {
          showToast('请输入有效的数字', 'error');
        }
      }
    });
  }
  // 空状态：翻今天所有按钮
  const learnReviewTodayBtn = $('#learnReviewTodayBtn');
  if (learnReviewTodayBtn) {
    learnReviewTodayBtn.addEventListener('click', () => {
      loadTodayAllWords();
    });
  }
  // 复习页词书选择（同步回学习词书）
  const reviewWbSelect = $('#reviewWordbookSelect');
  if (reviewWbSelect) {
    reviewWbSelect.addEventListener('change', (e) => {
      reviewWordbookId = e.target.value;
      localStorage.setItem('wordmemo_review_wordbook', reviewWordbookId);
      // 同步到学习词书
      learnWordbookId = reviewWordbookId;
      localStorage.setItem('wordmemo_learn_wordbook', learnWordbookId);
      const learnWbSel = $('#learnWordbookSelect');
      if (learnWbSel) learnWbSel.value = reviewWordbookId;
      reviewQueue = [];
      reviewIndex = 0;
      loadReviewQueue();
    });
  }
  // 复习页：随机/顺序切换按钮
  const reviewOrderBtn = $('#btnReviewOrder');
  if (reviewOrderBtn) {
    // 初始化按钮文字和样式（和学习页一致）
    reviewOrderBtn.textContent = reviewRandomMode ? '随机' : '顺序';
    if (reviewRandomMode) reviewOrderBtn.classList.add('active');
    reviewOrderBtn.addEventListener('click', () => {
      reviewRandomMode = !reviewRandomMode;
      localStorage.setItem('wordmemo_review_order', reviewRandomMode ? 'random' : 'sequential');
      reviewOrderBtn.textContent = reviewRandomMode ? '随机' : '顺序';
      reviewOrderBtn.classList.toggle('active', reviewRandomMode);
      // 同步设置页的下拉
      const reviewOrderSel = $('#reviewOrderSelect');
      if (reviewOrderSel) reviewOrderSel.value = reviewRandomMode ? 'random' : 'sequential';
      showToast(reviewRandomMode ? '已切换为随机复习' : '已切换为顺序复习（优先最近的）', 'success');
      // 重新加载复习队列
      reviewQueue = [];
      reviewIndex = 0;
      loadReviewQueue();
    });
  }
  // 学习卡发音（阻止冒泡避免翻卡）
  $('#learnSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const word = learnQueue[learnIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });

  // 学习模式切换（仅学习页的 mode-tab）
  $$('#learnModeTabs .mode-tab').forEach(tab => {
    tab.addEventListener('click', () => switchLearnMode(tab.dataset.mode));
  });
  // 学习页顺序/随机翻卡切换
  const learnOrderToggle = $('#learnOrderToggle');
  if (learnOrderToggle) {
    learnOrderToggle.addEventListener('click', () => {
      learnShuffleMode = !learnShuffleMode;
      if (learnShuffleMode) {
        // 切到随机：打乱当前队列
        learnOriginalQueue = [...learnQueue];
        learnQueue = shuffleArray([...learnQueue]);
        learnIndex = 0;
        learnOrderToggle.textContent = '随机';
        learnOrderToggle.classList.add('active');
        showToast('已切换为随机翻卡', 'success');
      } else {
        // 切回顺序：恢复原始顺序
        if (learnOriginalQueue.length > 0) {
          learnQueue = [...learnOriginalQueue];
        }
        learnIndex = 0;
        learnOrderToggle.textContent = '顺序';
        learnOrderToggle.classList.remove('active');
        showToast('已切换为顺序翻卡', 'success');
      }
      renderLearnCard();
    });
  }
  // 看词选义发音
  $('#choiceSpeakBtn').addEventListener('click', (e) => {
    const word = learnQueue[learnIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });
  // 拼写默写
  $('#spellSpeakBtn').addEventListener('click', (e) => {
    const input = $('#spellInput');
    const answer = input.dataset.answer;
    if (answer) speakWord(answer, e.currentTarget);
  });
  $('#spellSubmitBtn').addEventListener('click', handleSpellSubmit);
  $('#spellSkipBtn').addEventListener('click', () => {
    // 跳过：直接显示答案
    if (quizAnswered) return;
    quizAnswered = true;
    const input = $('#spellInput');
    const answer = input.dataset.answer || '';
    input.disabled = true;
    const feedback = $('#spellFeedback');
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `已跳过<span class="feedback-meaning">正确答案：${escapeHtml(answer)}</span>`;
  });
  // 拼写输入框回车提交
  $('#spellInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (quizAnswered) {
        handleQuizNext();
      } else {
        handleSpellSubmit();
      }
    }
  });
  // 测验模式操作按钮
  $('#btnQuizDetail').addEventListener('click', handleLearnDetail);
  $('#btnQuizKnown').addEventListener('click', handleQuizKnown);
  $('#btnQuizSkip').addEventListener('click', handleQuizNext);
  $('#btnQuizPrev').addEventListener('click', handleLearnPrev);

  // 复习翻卡
  $('#reviewCard').addEventListener('click', flipReviewCard);
  // 复习翻卡模式：评分按钮（仅 data-rating 的按钮提交评分）
  $$('#ratingActions .rating-btn[data-rating]').forEach(btn => {
    btn.addEventListener('click', () => handleReviewRating(btn.dataset.rating));
  });
  // 复习翻卡模式：上一个/下一个按钮
  const btnReviewPrev = $('#btnReviewPrev');
  if (btnReviewPrev) btnReviewPrev.addEventListener('click', handleReviewQuizPrev);
  const btnReviewNext = $('#btnReviewNext');
  if (btnReviewNext) btnReviewNext.addEventListener('click', () => {
    // 下一个：直接跳到下一个词，不提交评分
    if (reviewQueue.length === 0) return;
    reviewIndex++;
    renderReviewCard();
  });
  $('#reviewClose').addEventListener('click', () => {
    reviewQueue = [];
    reviewIndex = 0;
    switchPage('home');
  });
  // 复习卡发音
  $('#reviewSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const word = reviewQueue[reviewIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });

  // 复习模式切换
  $$('#reviewModeTabs .mode-tab').forEach(tab => {
    tab.addEventListener('click', () => switchReviewMode(tab.dataset.rmode));
  });
  // 复习看词选义发音
  $('#reviewChoiceSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const word = reviewQueue[reviewIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });
  // 复习拼写默写
  $('#reviewSpellSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const input = $('#reviewSpellInput');
    const answer = input.dataset.answer;
    if (answer) speakWord(answer, e.currentTarget);
  });
  $('#reviewSpellSubmitBtn').addEventListener('click', handleReviewSpellSubmit);
  $('#reviewSpellSkipBtn').addEventListener('click', () => {
    if (reviewQuizAnswered) return;
    reviewQuizAnswered = true;
    const input = $('#reviewSpellInput');
    const answer = input.dataset.answer || '';
    input.disabled = true;
    const feedback = $('#reviewSpellFeedback');
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `已跳过<span class="feedback-meaning">正确答案：${escapeHtml(answer)}</span>`;
  });
  $('#reviewSpellInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (reviewQuizAnswered) {
        handleReviewQuizNext();
      } else {
        handleReviewSpellSubmit();
      }
    }
  });
  // 复习测验操作按钮
  $('#btnReviewQuizPrev').addEventListener('click', handleReviewQuizPrev);
  $('#btnReviewQuizDetail').addEventListener('click', () => {
    const word = reviewQueue[reviewIndex];
    if (word) openWordDetail(word.id);
  });
  $('#btnReviewQuizKnown').addEventListener('click', handleReviewQuizKnown);
  $('#btnReviewQuizSkip').addEventListener('click', handleReviewQuizNext);

  // 复习页：自主复习切换（所有已学过的词，不受到期限制）
  const btnReviewAll = $('#btnReviewAll');
  if (btnReviewAll) {
    btnReviewAll.addEventListener('click', () => {
      reviewAllMode = !reviewAllMode;
      // 手动切换自主复习时，重置为重点词过滤，回到"所有已学过的词"的全局复习
      reviewStarredOnly = false;
      updateReviewModeUI();
      reviewQueue = [];
      loadReviewQueue();
    });
  }

  // 音标点击发音（所有音标元素都可点击）
  const phoneticHandler = (getWord) => (e) => {
    e.stopPropagation();
    const w = getWord();
    if (w) speakWord(typeof w === 'string' ? w : w.word, e.currentTarget);
  };
  // 学习翻卡正面音标
  $('#learnPhonetic').addEventListener('click', phoneticHandler(() => {
    const w = learnQueue[learnIndex]; return w ? w.word : '';
  }));
  // 学习翻卡背面音标
  $('#learnPhoneticBack').addEventListener('click', phoneticHandler(() => {
    const w = learnQueue[learnIndex]; return w ? w.word : '';
  }));
  // 看词选义音标
  $('#choicePhonetic').addEventListener('click', phoneticHandler(() => {
    const w = learnQueue[learnIndex]; return w ? w.word : '';
  }));
  // 拼写默写音标
  $('#spellPhonetic').addEventListener('click', phoneticHandler(() => {
    const w = learnQueue[learnIndex]; return w ? w.word : '';
  }));
  // 复习卡音标
  $('#reviewPhonetic').addEventListener('click', phoneticHandler(() => {
    const w = reviewQueue[reviewIndex]; return w ? w.word : '';
  }));
  // 详情弹窗音标
  $('#modalPhonetic').addEventListener('click', phoneticHandler(() => {
    return $('#modalWord').textContent;
  }));

  // 详情弹窗
  $('#modalCloseBtn').addEventListener('click', closeDetailModal);
  $('#wordDetailModal').addEventListener('click', (e) => {
    if (e.target.id === 'wordDetailModal') closeDetailModal();
  });
  $('#modalDeleteBtn').addEventListener('click', handleDeleteWord);
  $('#modalEditBtn').addEventListener('click', openEditModal);
  // 移动到词本（统一用 onclick 避免与多选模式的 onclick 冲突）
  $('#modalMoveBtn').addEventListener('click', openMoveWordbookModal);
  // 重点标记按钮
  const modalStarBtn = $('#modalStarBtn');
  if (modalStarBtn) {
    modalStarBtn.addEventListener('click', handleToggleStar);
  }
  // AI刷新例句按钮
  const refreshExBtn = $('#modalRefreshExamplesBtn');
  if (refreshExBtn) {
    refreshExBtn.addEventListener('click', handleRefreshExamples);
  }
  $('#moveCloseBtn').addEventListener('click', closeMoveWordbookModal);
  $('#moveCancelBtn').addEventListener('click', closeMoveWordbookModal);
  $('#moveWordbookModal').addEventListener('click', (e) => {
    if (e.target.id === 'moveWordbookModal') closeMoveWordbookModal();
  });
  $('#moveConfirmBtn').onclick = handleMoveWordbook;
  // 词本选择弹窗
  const wbSelectConfirm = $('#wordbookSelectConfirm');
  if (wbSelectConfirm) {
    wbSelectConfirm.addEventListener('click', () => {
      const selected = document.querySelector('input[name="wordbookSelect"]:checked');
      if (selected) {
        learnWordbookId = selected.value;
        localStorage.setItem('wordmemo_learn_wordbook', learnWordbookId);
        reviewWordbookId = learnWordbookId;
        localStorage.setItem('wordmemo_review_wordbook', reviewWordbookId);
        $('#wordbookSelectModal').style.display = 'none';
        $('#wordbookSelectModal').classList.remove('active');
        // 同步下拉框
        const learnWbSel = $('#learnWordbookSelect');
        if (learnWbSel) learnWbSel.value = learnWordbookId;
        const reviewWbSel = $('#reviewWordbookSelect');
        if (reviewWbSel) reviewWbSel.value = reviewWordbookId;
        renderHome();
      } else {
        showToast('请选择一个词本', 'warning');
      }
    });
  }
  const wbSelectCreate = $('#wordbookSelectCreate');
  if (wbSelectCreate) {
    wbSelectCreate.addEventListener('click', async () => {
      const name = $('#wordbookSelectNewName').value.trim();
      if (!name) {
        showToast('请输入词本名称', 'warning');
        return;
      }
      try {
        const res = await api.createWordbook({ name });
        if (res && res.success) {
          await loadWordbooks();
          $('#wordbookSelectNewName').value = '';
          showToast('词本创建成功', 'success');
          // 刷新弹窗列表
          showWordbookSelectModal();
        }
      } catch (err) {
        handleError(err);
      }
    });
  }
  // 详情弹窗发音
  $('#modalSpeakBtn').addEventListener('click', (e) => {
    const wordText = $('#modalWord').textContent;
    speakWord(wordText, e.currentTarget);
  });

  // 编辑弹窗
  $('#editCloseBtn').addEventListener('click', closeEditModal);
  $('#editCancelBtn').addEventListener('click', closeEditModal);
  $('#editModal').addEventListener('click', (e) => {
    if (e.target.id === 'editModal') closeEditModal();
  });
  $('#editSaveBtn').addEventListener('click', handleSaveEdit);

  // 窗口大小变化时重绘图表
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      // 后端 history 字段为 [{date, count}, ...]，需转为数字数组
      const histArr = (homeStatsCache && homeStatsCache.history || []).map(h => h.count || 0);
      if ($('#page-home').classList.contains('active') && homeStatsCache) {
        drawLineChart($('#homeLineChart'), histArr);
      }
      if ($('#page-stats').classList.contains('active') && homeStatsCache) {
        // 统计页可能用了独立缓存，重新拉取以保险
        renderStats();
      }
    }, 200);
  });

  // 签到按钮
  const btnCheckin = $('#btnCheckin');
  if (btnCheckin) {
    btnCheckin.addEventListener('click', handleCheckin);
  }

  // 设置页退出登录按钮
  const btnLogoutSettings = $('#btnLogoutSettings');
  if (btnLogoutSettings) {
    btnLogoutSettings.addEventListener('click', () => {
      if (confirm('确定退出登录吗？')) handleLogout();
    });
  }

  // 保存昵称
  const btnSaveNickname = $('#btnSaveNickname');
  if (btnSaveNickname) {
    btnSaveNickname.addEventListener('click', async () => {
      const nickname = $('#nicknameInput').value.trim();
      try {
        btnSaveNickname.disabled = true;
        btnSaveNickname.textContent = '保存中...';
        const res = await api.updateProfile({ nickname });
        if (res && res.success) {
          currentUser = res.data;
          saveUserCache(currentUser);
          $('#settingsUsername').textContent = currentUser.nickname || currentUser.username;
          showToast('昵称已保存', 'success');
        }
      } catch (err) {
        handleError(err);
      } finally {
        btnSaveNickname.disabled = false;
        btnSaveNickname.textContent = '保存';
      }
    });
  }

  // 保存安全问题
  const btnSaveSecurity = $('#btnSaveSecurity');
  if (btnSaveSecurity) {
    btnSaveSecurity.addEventListener('click', async () => {
      const question = $('#secQuestionInput').value.trim();
      const answer = $('#secAnswerInput').value.trim();
      if (!answer) { showToast('请输入安全问题答案', 'warning'); return; }
      try {
        btnSaveSecurity.disabled = true;
        btnSaveSecurity.textContent = '保存中...';
        const res = await api.updateProfile({ security_question: question, security_answer: answer });
        if (res && res.success) {
          currentUser = res.data;
          saveUserCache(currentUser);
          showToast('安全问题已保存', 'success');
        }
      } catch (err) {
        handleError(err);
      } finally {
        btnSaveSecurity.disabled = false;
        btnSaveSecurity.textContent = '保存';
      }
    });
  }

  // 修改密码
  const btnChangePassword = $('#btnChangePassword');
  if (btnChangePassword) {
    btnChangePassword.addEventListener('click', async () => {
      const oldPwd = $('#oldPasswordInput').value;
      const newPwd = $('#newPasswordInput').value;
      const confirmPwd = $('#confirmPasswordInput').value;
      if (!oldPwd) { showToast('请输入旧密码', 'warning'); return; }
      if (newPwd.length < 6) { showToast('新密码至少6位', 'warning'); return; }
      if (newPwd !== confirmPwd) { showToast('两次输入的新密码不一致', 'warning'); return; }
      try {
        btnChangePassword.disabled = true;
        btnChangePassword.textContent = '修改中...';
        const res = await api.changePassword(oldPwd, newPwd);
        if (res && res.success) {
          showToast('密码修改成功', 'success');
          $('#oldPasswordInput').value = '';
          $('#newPasswordInput').value = '';
          $('#confirmPasswordInput').value = '';
        }
      } catch (err) {
        handleError(err);
      } finally {
        btnChangePassword.disabled = false;
        btnChangePassword.textContent = '修改密码';
      }
    });
  }

  // 复习卡片左右滑动切换（上一个/下一个）
  const reviewStage = $('#reviewStage');
  if (reviewStage) {
    let touchStartX = 0;
    let touchStartY = 0;
    let touchMoved = false;
    reviewStage.addEventListener('touchstart', (e) => {
      if (e.touches.length === 0) return;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchMoved = false;
    }, { passive: true });
    reviewStage.addEventListener('touchmove', (e) => {
      if (e.touches.length === 0) return;
      const dx = e.touches[0].clientX - touchStartX;
      const dy = e.touches[0].clientY - touchStartY;
      if (Math.abs(dx) > 10 || Math.abs(dy) > 10) touchMoved = true;
    }, { passive: true });
    reviewStage.addEventListener('touchend', (e) => {
      if (!touchMoved) return;
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      // 水平滑动且大于阈值
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
        if (dx > 0) {
          // 右滑 → 上一个
          handleReviewQuizPrev();
        } else {
          // 左滑 → 下一个
          if (reviewQueue.length === 0) return;
          reviewIndex++;
          renderReviewCard();
        }
      }
    }, { passive: true });
  }
}

/* ====================================================
   本地缓存（乐观渲染）：首次打开秒显示上次数据，后台再拉最新
   ==================================================== */
const HOME_CACHE_KEY = 'wordmemo_home_cache';
const USER_CACHE_KEY = 'wordmemo_user_cache';

/** 保存首页数据到 localStorage */
function saveHomeCache(stats, words) {
  try {
    localStorage.setItem(HOME_CACHE_KEY, JSON.stringify({ stats, words, ts: Date.now() }));
  } catch (e) { /* localStorage 满或不可用，忽略 */ }
}

/** 读取首页缓存数据 */
function loadHomeCache() {
  try {
    const raw = localStorage.getItem(HOME_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) { return null; }
}

/** 保存用户信息到 localStorage */
function saveUserCache(user) {
  try {
    localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
  } catch (e) {}
}

/** 读取用户缓存 */
function loadUserCache() {
  try {
    const raw = localStorage.getItem(USER_CACHE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) { return null; }
}

/** 清除用户缓存（退出登录时调用） */
function clearUserCache() {
  try {
    localStorage.removeItem(USER_CACHE_KEY);
  } catch (e) {}
}

/**
 * 清除所有用户相关缓存（登录/注册/退出时调用）
 * 1. 清除 localStorage 首页缓存（防止新用户看到旧用户数据）
 * 2. 通知 Service Worker 清空 API 缓存
 */
function clearAllUserDataCache() {
  try {
    localStorage.removeItem(HOME_CACHE_KEY);
    localStorage.removeItem(USER_CACHE_KEY);
  } catch (e) {}
  // 通知 Service Worker 清空 API 缓存
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_API_CACHE' });
  }
}

/**
 * 用缓存数据立即渲染首页（乐观渲染，不等网络）
 */
function renderHomeFromCache() {
  const cache = loadHomeCache();
  if (!cache || !cache.stats) return false;

  const stats = cache.stats;
  const words = cache.words || [];

  // 更新欢迎语
  updateGreeting();

  // 连续天数
  $('#streakNum').textContent = stats.streak_days || 0;
  // 同步签到按钮状态
  updateCheckinUI(stats.checked_in, stats.streak_days);

  // 今日概览
  $('#todayLearned').textContent = stats.today_learned || 0;
  $('#todayReviewCount').textContent = stats.today_review || 0;
  $('#todayNewCount').textContent = stats.pending_today !== undefined ? stats.pending_today : (stats.new || 0);

  // 操作按钮描述
  const mDailyGoal = stats.daily_goal || 20;
  const mPendingToday = stats.pending_today !== undefined ? stats.pending_today : Math.max(0, mDailyGoal - (stats.today_learned || 0));
  const mNewWordsLeft = stats.new || 0;
  if (mNewWordsLeft > 0) {
    $('#learnDesc').textContent = `${mPendingToday}个待学`;
  } else if (mPendingToday > 0) {
    $('#learnDesc').textContent = `词本已学完`;
  } else {
    $('#learnDesc').textContent = `今日已完成`;
  }
  $('#reviewDesc').textContent = `${stats.today_review || 0}个单词待复习`;

  // 统计卡片
  $('#statTotal').textContent = stats.total || 0;
  $('#statNew').textContent = stats.new || 0;
  $('#statReview').textContent = stats.review || 0;
  $('#statMastered').textContent = stats.mastered || 0;

  // 概览数字点击跳转
  bindOverviewClicks();

  // 统计卡片点击跳转
  bindStatCardClicks();

  // 学习曲线
  const historyArr = (stats.history || []).map(h => h.count || 0);
  drawLineChart($('#homeLineChart'), historyArr);

  // 今日单词列表
  const list = $('#todayWordList');
  if (words && words.length > 0) {
    list.innerHTML = words.map((word, i) => wordItemHtml(word, i + 1)).join('');
    list.querySelectorAll('.word-item').forEach(item => {
      item.addEventListener('click', () => openWordDetail(item.dataset.id));
    });
  } else {
    list.innerHTML = '<div class="empty-state"><p>暂无单词，快去添加吧</p></div>';
  }

  return true;
}

/**
 * 静默刷新首页数据：只更新数字，不触发完整重渲染（避免闪烁）
 * 拉取最新stats后，对比缓存，仅在数据变化时更新DOM文本
 */
async function refreshHomeDataSilently() {
  try {
    const stats = await api.getStats(learnWordbookId);
    if (!stats) return;

    // 保存最新缓存
    const words = await api.getWords({ status: 'new' }).catch(() => []);
    saveHomeCache(stats, words);

    // 静默更新首页数字（不触发动画/重绘）
    const updateText = (id, val) => {
      const el = $('#' + id);
      if (el && el.textContent != val) el.textContent = val;
    };
    updateText('streakNum', stats.streak_days || 0);
    updateText('todayLearned', stats.today_learned || 0);
    updateText('todayReviewCount', stats.today_review || 0);
    updateText('todayNewCount', stats.pending_today !== undefined ? stats.pending_today : (stats.new || 0));
    updateText('statTotal', stats.total || 0);
    updateText('statNew', stats.new || 0);
    updateText('statReview', stats.review || 0);
    updateText('statMastered', stats.mastered || 0);

    // 更新签到状态
    updateCheckinUI(stats.checked_in, stats.streak_days);

    // 更新操作按钮描述
    const dailyGoal = stats.daily_goal || 20;
    const sPendingToday = stats.pending_today !== undefined ? stats.pending_today : Math.max(0, dailyGoal - (stats.today_learned || 0));
    const sNewWordsLeft = stats.new || 0;
    const learnDesc = $('#learnDesc');
    if (learnDesc) {
      if (sNewWordsLeft > 0) {
        learnDesc.textContent = `${sPendingToday}个待学`;
      } else if (sPendingToday > 0) {
        learnDesc.textContent = `词本已学完`;
      } else {
        learnDesc.textContent = `今日已完成`;
      }
    }
    const reviewDesc = $('#reviewDesc');
    if (reviewDesc) reviewDesc.textContent = `${stats.today_review || 0}个单词待复习`;
  } catch (e) {
    console.log('Silent refresh failed:', e);
  }
}

// 检查是否需要选择词本
async function checkWordbookSelection() {
  const savedWb = localStorage.getItem('wordmemo_learn_wordbook');
  if (savedWb !== null && savedWb !== '') {
    return; // 已选择过词本
  }
  // 等待词本列表加载
  if (!wordbooks || wordbooks.length === 0) {
    await loadWordbooks();
  }
  if (wordbooks.length === 0) {
    // 没有词本，直接弹窗让用户创建
    showWordbookSelectModal();
  } else {
    showWordbookSelectModal();
  }
}

function showWordbookSelectModal() {
  const modal = $('#wordbookSelectModal');
  if (!modal) return;
  const list = $('#wordbookSelectList');
  let html = '<div style="display:flex;flex-direction:column;gap:8px">';
  wordbooks.forEach(b => {
    html += `<label style="display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer" class="wordbook-select-item">
      <input type="radio" name="wordbookSelect" value="${b.id}" style="width:18px;height:18px">
      <span>${escapeHtml(b.name)}（${b.word_count || 0}词）</span>
    </label>`;
  });
  // "未归类" 选项
  html += `<label style="display:flex;align-items:center;gap:8px;padding:10px;border:1px solid #e5e7eb;border-radius:8px;cursor:pointer" class="wordbook-select-item">
    <input type="radio" name="wordbookSelect" value="0" style="width:18px;height:18px">
    <span>未归类</span>
  </label>`;
  html += '</div>';
  list.innerHTML = html;
  modal.style.display = 'flex';
  modal.classList.add('active');
}

/**
 * 应用初始化
 */
async function init() {
  // 从 localStorage 恢复词书选择
  learnWordbookId = localStorage.getItem('wordmemo_learn_wordbook') || '';
  reviewWordbookId = localStorage.getItem('wordmemo_review_wordbook') || '';
  libraryWordbook = localStorage.getItem('wordmemo_library_wordbook') || '';
  bindEvents();
  bindAuthEvents();
  // 初始化下拉刷新和页面滑动切换
  initPullRefresh();
  initPageSwipe();
  // 初始化安卓返回键处理
  initBackButtonHandler();

  // 后台预热请求：唤醒 Render 服务（不阻塞 UI）
  fetch(api.baseURL + '/api/stats', { credentials: 'include' })
    .then(() => console.log('[warmup] 服务已唤醒'))
    .catch(() => {});

  // 保活心跳：每 3 分钟静默请求一次 /api/stats
  setInterval(() => {
    fetch(api.baseURL + '/api/stats', { credentials: 'include' })
      .then(() => console.log('[keepalive] 心跳'))
      .catch(() => {});
  }, 3 * 60 * 1000);

  // 乐观渲染：先用缓存用户信息显示状态栏，再用缓存数据渲染首页
  const cachedUser = loadUserCache();
  if (cachedUser) {
    currentUser = cachedUser;
    onLoginSuccess();
    // 立即用缓存渲染首页（秒开）
    renderHomeFromCache();
  }

  // 后台检查登录状态并拉取最新数据
  // 如果有缓存，不阻塞 UI；如果没有缓存，必须等待结果
  if (cachedUser) {
    // 有缓存：后台静默验证登录状态，不阻塞初始化
    checkAuthStatus().then(loggedIn => {
      if (loggedIn) {
        // 后台静默更新首页数据
        refreshHomeDataSilently();
        // 检查是否需要选择词本
        checkWordbookSelection();
        // 后台加载词本列表
        loadWordbooks();
      }
    });
  } else {
    // 无缓存：必须等待登录状态确认
    const loggedIn = await checkAuthStatus();
    if (loggedIn) {
      const cached = loadHomeCache();
      if (!cached || !cached.stats) {
        renderHome();
      } else {
        refreshHomeDataSilently();
      }
      checkWordbookSelection();
    }
  }

  // 标记应用已初始化，之后页面切换才播放动画
  document.body.classList.add('app-initialized');
}

/** 绑定认证相关事件 */
function bindAuthEvents() {
  // 登录/注册 Tab 切换
  document.querySelectorAll('.login-tab').forEach(tab => {
    tab.addEventListener('click', () => switchLoginTab(tab.dataset.loginTab));
  });
  // 登录按钮
  const btnLogin = document.getElementById('btnLogin');
  if (btnLogin) btnLogin.addEventListener('click', handleLogin);
  // 注册按钮
  const btnRegister = document.getElementById('btnRegister');
  if (btnRegister) btnRegister.addEventListener('click', handleRegister);
  // 回车提交
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', (e) => { e.preventDefault(); handleLogin(); });
  }
  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', (e) => { e.preventDefault(); handleRegister(); });
  }
  // 密码强度实时检测
  const regPassword = document.getElementById('registerPassword');
  if (regPassword) {
    regPassword.addEventListener('input', (e) => {
      const val = e.target.value;
      const strengthEl = document.getElementById('passwordStrength');
      const textEl = document.getElementById('passwordStrengthText');
      if (!val) {
        if (strengthEl) strengthEl.style.display = 'none';
        if (textEl) textEl.style.display = 'none';
        return;
      }
      const result = checkPasswordStrength(val);
      if (strengthEl) {
        strengthEl.style.display = 'flex';
        const bars = strengthEl.querySelectorAll('.password-strength-bar');
        bars.forEach((bar, i) => {
          bar.className = 'password-strength-bar' + (i < result.bars ? ' active ' + result.level : '');
        });
      }
      if (textEl) {
        textEl.style.display = 'block';
        textEl.textContent = `密码强度：${result.text}`;
        textEl.style.color = result.level === 'weak' ? 'var(--danger)' : result.level === 'medium' ? 'var(--warning)' : 'var(--success)';
      }
    });
  }
}

// DOM 就绪后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
