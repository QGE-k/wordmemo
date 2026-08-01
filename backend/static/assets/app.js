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

    // 超时控制：15秒后自动中断，避免 Neon 休眠时页面永久卡住
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    try {
      const res = await fetch(url, { ...options, headers, credentials: 'include', signal: controller.signal });
      clearTimeout(timeoutId);

      // 处理 HTTP 错误状态码
      if (!res.ok) {
        let errMsg = `请求失败 (${res.status})`;
        try {
          const errData = await res.json();
          errMsg = errData.error || errData.message || errMsg;
        } catch (e) { /* 非 JSON 错误体则用默认消息 */ }
        throw new Error(errMsg);
      }

      // 解析 JSON 响应
      const text = await res.text();
      return text ? JSON.parse(text) : null;
    } catch (err) {
      clearTimeout(timeoutId);
      // 超时中断
      if (err.name === 'AbortError') {
        throw new Error('请求超时，请稍后重试');
      }
      // 网络错误（无法连接服务器）
      if (err instanceof TypeError && err.message.includes('Failed to fetch')) {
        throw new Error('无法连接服务器，请确认后端已启动');
      }
      throw err;
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
    const query = qs.toString();
    const res = await this.request('/words' + (query ? '?' + query : ''));
    // 后端返回 {success, data, total}，提取 data 数组
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 添加单个单词
  // 返回值：{success, data, source}
  async addWord(word, phonetic = '', meaning = '') {
    const res = await this.request('/words', {
      method: 'POST',
      body: JSON.stringify({ word, phonetic, meaning })
    });
    return res;  // 返回完整响应（含 source 字段）
  }

  // 批量添加单词（可选 wordbook_id 指定单词本）
  // 返回值：{success, added, skipped, failed, added_count, ...}
  async addWordsBatch(words, wordbookId) {
    const payload = { words };
    if (wordbookId) payload.wordbook_id = wordbookId;
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

  // 批量移动单词到词本
  batchMoveWords(wordIds, wordbookId) {
    return this.request('/words/batch-move', {
      method: 'POST',
      body: JSON.stringify({ word_ids: wordIds, wordbook_id: wordbookId })
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
  async getStats() {
    const res = await this.request('/stats');
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
    const qs = params.length > 0 ? '?' + params.join('&') : '';
    const res = await this.request('/review/today' + qs);
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
    const qs = params.length > 0 ? '?' + params.join('&') : '';
    const res = await this.request('/learn/today' + qs);
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
  }

  // 获取随机干扰项（用于看词选义模式）
  async getDistractors(wordbookId, excludeIds = [], limit = 3) {
    let params = [];
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
      // 确实未登录：清除缓存，显示登录弹窗
      currentUser = null;
      clearUserCache();
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
  // 管理员显示管理 Tab
  const adminTab = document.querySelector('.tab-admin-only');
  if (adminTab) {
    adminTab.style.display = currentUser.role === 'admin' ? 'flex' : 'none';
  }
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
  currentUser = null;
  clearUserCache(); // 清除用户缓存
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
        <div class="admin-user-actions">
          <button class="btn-secondary btn-sm admin-detail-btn" data-user-id="${user.id}">查看详情</button>
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
    if (diff > 60 && diff < 200) {
      indicator.style.display = 'flex';
      indicator.style.top = (diff / 4) + 'px';
    }
  }, { passive: true });

  appContent.addEventListener('touchend', (e) => {
    if (!pullRefreshState.pulling) return;
    const diff = (e.changedTouches[0].clientY - pullRefreshState.startY);
    indicator.style.top = '';
    if (diff > 80) {
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
  el.textContent = `预计 ${minutes} 分钟`;
  el.style.display = 'block';
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
  return `
    <div class="word-item" data-id="${word.id}">
      ${num}
      <div class="word-info">
        <div class="word-text">
          ${word.phonetic ? `<span class="word-phonetic-sm">${escapeHtml(word.phonetic)}</span>` : ''}
          ${escapeHtml(word.word)}
          ${bookTag}
        </div>
        <div class="word-meaning">${escapeHtml(word.meaning || '暂无释义')}</div>
      </div>
      <span class="word-status ${word.status}">${statusText(word.status)}</span>
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
      // 复习词书自动同步为学习词书
      reviewWordbookId = learnWordbookId;
      initReviewWordbookSelector();
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
    // 并行请求统计与今日单词
    const [stats, words] = await Promise.all([
      api.getStats(),
      api.getWords()
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
    // today_new 后端用 new 字段（新单词总数）代替
    $('#todayNewCount').textContent = stats.new || 0;

    // 操作按钮描述：显示每天计划学多少 + 还有多少待学/待复习
    const dailyGoal = stats.daily_goal || 20;
    $('#learnDesc').textContent = `每天学${dailyGoal}个，还有${stats.new || 0}个待学`;
    $('#reviewDesc').textContent = `${stats.today_review || 0}个单词待复习`;

    // 统计卡片
    $('#statTotal').textContent = stats.total || 0;
    $('#statNew').textContent = stats.new || 0;
    $('#statReview').textContent = stats.review || 0;
    $('#statMastered').textContent = stats.mastered || 0;

    // 首页概览数字可点击跳转
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
      // 待学新词 → 跳转学习页
      overviewItems[2].style.cursor = 'pointer';
      overviewItems[2].onclick = () => {
        learnQueue = [];
        switchPage('learn');
      };
    }
    // 统计卡片也可点击
    const statCards = document.querySelectorAll('.stat-card');
    if (statCards.length >= 4) {
      statCards[0].style.cursor = 'pointer'; // 总词数 → 词库
      statCards[0].onclick = () => switchPage('library');
      statCards[1].style.cursor = 'pointer'; // 新词 → 学习
      statCards[1].onclick = () => { learnQueue = []; switchPage('learn'); };
      statCards[2].style.cursor = 'pointer'; // 复习中 → 复习
      statCards[2].onclick = () => { reviewQueue = []; switchPage('review'); };
      statCards[3].style.cursor = 'pointer'; // 已掌握 → 词库
      statCards[3].onclick = () => switchPage('library');
    }

    // 学习曲线折线图
    // 后端 history 格式：[{date, count}, ...]，需转为数字数组
    const historyArr = (stats.history || []).map(h => h.count || 0);
    drawLineChart($('#homeLineChart'), historyArr);

    // 今日单词列表（取前 5 个）
    const list = $('#todayWordList');
    if (words && words.length > 0) {
      list.innerHTML = words.slice(0, 5).map((word, i) => wordItemHtml(word, i + 1)).join('');
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

  if (!word) {
    showToast('请输入单词', 'warning');
    return;
  }

  // 去重检查
  const isDup = await checkWordDuplicate(word, '');
  if (isDup) {
    showToast(`单词 "${word}" 已存在`, 'warning');
    return;
  }

  try {
    showLoading('添加中...');
    await api.addWord(word, phonetic, meaning);
    hideLoading();
    showToast('添加成功', 'success');

    // 清空输入框
    $('#manualWord').value = '';
    $('#manualPhonetic').value = '';
    $('#manualMeaning').value = '';
  } catch (err) {
    handleError(err);
  }
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
  batchPreviewWords = lines.map(line => {
    const idx = line.search(/\s/);
    if (idx > 0) {
      return { word: line.slice(0, idx).trim(), meaning: line.slice(idx + 1).trim() };
    }
    return { word: line, meaning: '' };
  }).filter(w => w.word);

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
        await api.addWord(w.word, '', w.meaning);
        added++;
      } catch (e) { /* 单个失败继续 */ }
    }
    hideLoading();
    showToast(`成功添加 ${added} 个单词`, 'success');
    $('#batchText').value = '';
    $('#batchPreview').style.display = 'none';
    batchPreviewWords = [];
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

  // 解析每行：支持 "word" 或 "word meaning" 格式
  const lines = text.split(/\n+/).map(l => l.trim()).filter(Boolean);
  const words = lines.map(line => {
    // 第一个空格分隔单词与释义
    const idx = line.search(/\s/);
    if (idx > 0) {
      return {
        word: line.slice(0, idx).trim(),
        meaning: line.slice(idx + 1).trim()
      };
    }
    return { word: line, meaning: '' };
  }).filter(w => w.word);

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
        await api.addWord(w.word, '', w.meaning);
        added++;
      } catch (e) { /* 单个失败继续 */ }
    }

    hideLoading();
    showToast(`成功添加 ${added} 个单词`, 'success');
    $('#batchText').value = '';
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
  try {
    showLoading('正在导入单词...');
    const res = await api.importConfirm(docPendingWords, wordbookId);
    hideLoading();

    if (!res.success) {
      showToast(res.error || '导入失败', 'error');
      return;
    }

    const d = res.data;
    // 渲染结果
    const resultHtml = `
      <div class="result-row">
        <span>成功导入</span>
        <span class="result-added">${d.added_count} 个</span>
      </div>
      ${d.skipped_count > 0 ? `
      <div class="result-row">
        <span>已存在跳过</span>
        <span class="result-skipped">${d.skipped_count} 个</span>
      </div>` : ''}
      ${d.failed_count > 0 ? `
      <div class="result-row">
        <span>导入失败</span>
        <span class="result-failed">${d.failed_count} 个</span>
      </div>` : ''}
    `;
    $('#docResult').innerHTML = resultHtml;
    $('#docResult').style.display = 'block';
    $('#docPreview').style.display = 'none';

    showToast(`成功导入 ${d.added_count} 个单词`, 'success');
    // 清空待导入列表
    docPendingWords = [];
    // 刷新单词本列表（更新计数）
    loadWordbooks();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 扫描录入：选择图片
function handleScanPick() {
  // 如果已有识别结果，直接清空重新选（不用confirm，避免WebView不弹窗导致卡死）
  if (scanRecognizedWords.length > 0 || scanFiles.length > 0) {
    resetScan();
  }
  $('#scanInput').click();
}

// 预览选择的图片
function handleScanChange(e) {
  const files = Array.from(e.target.files || []);
  if (files.length === 0) return;
  // 添加到图片数组（累加，支持多张）
  scanFiles = scanFiles.concat(files);
  // 更新预览区域：显示所有图片缩略图
  updateScanPreview();
  // 清除上一次的识别结果
  scanRecognizedWords = [];
  $('#scanConfirm').style.display = 'none';
  $('#scanResult').style.display = 'none';
  // 重置 input value 允许重复选同一文件
  e.target.value = '';
}

function updateScanPreview() {
  const placeholder = $('.scan-placeholder');
  const preview = $('#scanPreview');
  const cancelBtn = $('#scanCancelBtn');
  if (scanFiles.length === 0) {
    placeholder.style.display = '';
    preview.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'none';
    return;
  }
  placeholder.style.display = 'none';
  if (cancelBtn) cancelBtn.style.display = 'block';
  // 只显示第一张作为主预览，加数量标记
  const reader = new FileReader();
  reader.onload = (ev) => {
    preview.src = ev.target.result;
    preview.style.display = 'block';
  };
  reader.readAsDataURL(scanFiles[0]);
  // 如果有多张，在扫描区显示数量提示
  let countBadge = $('#scanCountBadge');
  if (!countBadge) {
    countBadge = document.createElement('div');
    countBadge.id = 'scanCountBadge';
    countBadge.style.cssText = 'position:absolute;top:8px;right:8px;background:rgba(79,70,229,0.9);color:#fff;border-radius:12px;padding:2px 10px;font-size:13px;font-weight:600';
    $('#scanArea').style.position = 'relative';
    $('#scanArea').appendChild(countBadge);
  }
  countBadge.textContent = scanFiles.length + '张图片';
  countBadge.style.display = scanFiles.length > 1 ? 'block' : 'none';
}

function resetScan() {
  scanFiles = [];
  scanRecognizedWords = [];
  $('#scanPreview').style.display = 'none';
  $('.scan-placeholder').style.display = '';
  $('#scanConfirm').style.display = 'none';
  $('#scanResult').style.display = 'none';
  const cancelBtn = $('#scanCancelBtn');
  if (cancelBtn) cancelBtn.style.display = 'none';
  const badge = $('#scanCountBadge');
  if (badge) badge.style.display = 'none';
}

let scanFiles = []; // 多张图片文件数组
let scanRecognizedWords = []; // AI识别到的单词列表 [{word, meaning, checked}]

// AI识别图片中的单词
async function handleScanRecognize() {
  if (scanFiles.length === 0) {
    showToast('请先选择图片', 'warning');
    return;
  }
  try {
    showLoading('AI识别中...');
    // 逐张识别，合并结果
    let allWords = [];
    for (let i = 0; i < scanFiles.length; i++) {
      showLoading(`AI识别中... (${i + 1}/${scanFiles.length})`);
      const res = await api.aiRecognizeImage(scanFiles[i]);
      if (res.success && res.words && res.words.length > 0) {
        allWords = allWords.concat(res.words);
      } else if (res.success === false) {
        // API返回了明确的错误
        throw new Error(res.error || 'AI识别失败');
      }
    }
    hideLoading();
    
    // 处理识别结果：支持 / 分隔的多词组拆分
    const expandedWords = [];
    allWords.forEach(w => {
      const wordStr = (w.word || '').trim();
      const meaningStr = (w.meaning || '').trim();
      if (wordStr.includes('/')) {
        // 拆分斜杠分隔的词组
        // 处理 call on/upon sb -> call on sb + call upon sb
        const parts = wordStr.split('/').map(s => s.trim()).filter(s => s);
        if (parts.length >= 2) {
          // 检查是否是 call on/upon sb 这种模式：前半部分有完整词组，后半部分是替换词
          const firstPart = parts[0];
          const lastPart = parts[parts.length - 1];
          // 尝试找到共同前缀和后缀
          // 模式1: "call on/upon sb" -> "call on sb" + "call upon sb"
          const firstWords = firstPart.split(' ');
          if (firstWords.length >= 2) {
            const prefix = firstWords.slice(0, -1).join(' '); // "call"
            const suffix = firstWords[firstWords.length - 1]; // "on"
            const altWord = lastPart; // "upon sb" or just "upon"
            // 生成两个词组
            const word1 = (prefix + ' ' + suffix + ' ' + firstPart.replace(prefix + ' ' + suffix, '').trim()).trim().replace(/\s+/g, ' ');
            // 更简单的方式：直接用 parts 组合
            // call on/upon sb -> parts = ["call on", "upon sb"]
            // 需要组合成 "call on sb" 和 "call upon sb"
            const lastWordOfFirst = firstWords[firstWords.length - 1]; // "on"
            const remainingAfterSlash = lastPart.split(' ').slice(1).join(' '); // "sb"
            const combined1 = firstPart + (remainingAfterSlash ? ' ' + remainingAfterSlash : ''); // "call on sb"
            const combined2 = prefix + ' ' + lastPart; // "call upon sb"
            expandedWords.push({ word: combined1.toLowerCase(), meaning: meaningStr, checked: true, starred: false });
            expandedWords.push({ word: combined2.toLowerCase(), meaning: meaningStr, checked: true, starred: false });
          } else {
            // 简单拆分
            parts.forEach(part => {
              expandedWords.push({ word: part.toLowerCase(), meaning: meaningStr, checked: true, starred: false });
            });
          }
        } else {
          parts.forEach(part => {
            expandedWords.push({ word: part.toLowerCase(), meaning: meaningStr, checked: true, starred: false });
          });
        }
      } else {
        expandedWords.push({ word: wordStr.toLowerCase(), meaning: meaningStr, checked: true, starred: false });
      }
    });
    
    // 去重（同名的词组只保留一个）
    const seen = new Set();
    scanRecognizedWords = expandedWords.filter(w => {
      if (seen.has(w.word)) return false;
      seen.add(w.word);
      return true;
    });
    
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
  const allChecked = scanRecognizedWords.every(w => w.checked);
  scanRecognizedWords.forEach(w => { w.checked = !allChecked; });
  $$('.scan-word-check').forEach(cb => { cb.checked = !allChecked; });
  updateScanCheckAllState();
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
  const wordsToAdd = selected.map(w => ({ word: w.word, starred: w.starred || false }));

  try {
    showLoading(`正在添加 ${selected.length} 个单词...`);
    const res = await api.addWordsBatch(wordsToAdd, scanWordbookId);
    hideLoading();
    renderScanAddResult({
      added: res.added_count || (res.added || []).length,
      skipped: res.skipped_count || (res.skipped || []).length,
      failed: res.failed_count || (res.failed || []).length,
      addedWords: res.added || [],
      skippedWords: res.skipped || [],
      words: selected,
    });
    // 添加成功后清空图片和识别结果
    resetScan();
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
    case 'added_desc':
    default:
      sorted.sort((a, b) => new Date(b.added_at) - new Date(a.added_at));
      break;
  }
  return sorted;
}

// ====== 词库多选模式 ======
let multiSelectIds = new Set();

function enterMultiSelectMode(firstId) {
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
  const allSelected = allItems.length > 0 && allItems.length === multiSelectIds.size;
  if (allSelected) {
    // 如果已经全选了，点击则取消全选
    multiSelectIds.clear();
    document.querySelectorAll('.word-item.multi-selected').forEach(el => el.classList.remove('multi-selected'));
    if (allBtn) allBtn.textContent = '全选';
  } else {
    // 全选
    allItems.forEach(item => {
      const id = parseInt(item.getAttribute('data-id'), 10);
      if (!isNaN(id)) {
        multiSelectIds.add(id);
        item.classList.add('multi-selected');
      }
    });
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
    // 用骨架屏代替全屏loading
    const list = $('#libraryList');
    if (list) showSkeleton(list, 6);
    const params = {};
    if (libraryFilter !== 'all') params.status = libraryFilter;
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
  // 固定的前两项 + 单词本列表 + 加号
  let html = `
    <button class="wordbook-chip ${libraryWordbook === '' ? 'active' : ''}" data-wordbook="">全部</button>
    <button class="wordbook-chip ${libraryWordbook === '0' ? 'active' : ''}" data-wordbook="0">未归类</button>
  `;
  if (wordbooks.length > 0) {
    html += `<span class="wordbook-chip-sep"></span>`;
    wordbooks.forEach(b => {
      const active = String(libraryWordbook) === String(b.id) ? 'active' : '';
      const total = b.word_count || 0;
      const learned = b.learned_count || 0;
      const progress = total > 0 ? `${learned}/${total}` : '';
      const count = total !== undefined ? `<span class="chip-count">${progress}</span>` : '';
      html += `<button class="wordbook-chip ${active}" data-wordbook="${b.id}" style="${active ? `border-color:${b.color};background:${b.color}` : `border-color:${b.color}40; color:${b.color}`}">${escapeHtml(b.name)}${count}</button>`;
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
      renderWordbookBar();
      renderLibrary();
    });
    // 长按编辑（移动端）
    let pressTimer = null;
    chip.addEventListener('touchstart', (e) => {
      const wbId = chip.dataset.wordbook;
      if (!wbId || wbId === '0') return;
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
}

/**
 * 打开单词本弹窗（新建或编辑）
 */
function openWordbookModal(book = null) {
  editingWordbookId = book ? book.id : null;
  const delBtn = $('#wordbookDeleteBtn');
  if (book) {
    $('#wordbookModalTitle').textContent = '编辑单词本';
    $('#wordbookNameInput').value = book.name || '';
    $('#wordbookDescInput').value = book.description || '';
    currentWordbookColor = book.color || '#4a7fff';
    if (delBtn) delBtn.style.display = '';  // 编辑时显示删除
  } else {
    $('#wordbookModalTitle').textContent = '新建单词本';
    $('#wordbookNameInput').value = '';
    $('#wordbookDescInput').value = '';
    currentWordbookColor = '#4a7fff';
    if (delBtn) delBtn.style.display = 'none';  // 新建时隐藏删除
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
let allLearnedIds = new Set(); // 本次学习会话中所有已学的单词ID（用于"已学会"标记）
let loadedWordIds = new Set(); // 当前会话中已加载到队列的单词ID（用于"加入新词"排除）
let learnSessionMode = 'new'; // 学习会话模式：new=未学习学习 / review_today=翻今天所有
let learnShuffleMode = false; // 学习页翻卡顺序：false=顺序，true=随机（仅打乱当前队列）
let learnOriginalQueue = []; // 保存原始顺序队列，用于切回顺序模式

// 看词选义正确率统计（仅看词选义模式）
let learnChoiceCorrect = 0;   // 学习模式答对数
let learnChoiceTotal = 0;     // 学习模式总答题数
let reviewChoiceCorrect = 0;  // 复习模式答对数
let reviewChoiceTotal = 0;    // 复习模式总答题数

// 加载学习队列：返回词书内所有单词（未学习优先），按添加顺序分批
// append=true 时为"加入未学习"模式，只加载没学过的词(new状态)，追加到队列末尾
async function loadLearnQueue(append = false, addCount = null) {
  // 必须选择词书才能学习
  if (!learnWordbookId && learnWordbookId !== '0') {
    showToast('请先选择一本词书再开始学习', 'error');
    return;
  }
  try {
    showLoading();
    learnSessionMode = 'new';
    const options = {
      random: learnRandomMode,
    };
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
      } else {
        showToast('当前词书没有单词', 'info');
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
    return;
  }

  // 所有模式都循环：翻完从头再来
  if (learnIndex >= total) {
    learnIndex = 0;
  }

  const word = learnQueue[learnIndex];
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
      const result = await api.getDistractors(learnWordbookId, excludeIds, 3);
      distractors = result || [];
    } catch (e2) {
      console.warn('获取随机干扰项也失败，使用队列内词', e2);
    }
  }

  // 如果后端干扰项不够3个，从当前队列补充
  if (distractors.length < 3) {
    const otherWords = learnQueue.filter(w => w.word !== word.word && w.id !== word.id);
    while (distractors.length < 3 && otherWords.length > 0) {
      const idx = Math.floor(Math.random() * otherWords.length);
      const w = otherWords[idx];
      distractors.push({ word: w.word, meaning: w.meaning });
      otherWords.splice(idx, 1);
    }
  }

  // 过滤干扰项：单词和释义都不能为空
  distractors = distractors.filter(opt => opt.word && opt.word.trim() && opt.meaning && opt.meaning.trim());
  // 去重：干扰项不能和正确答案相同
  distractors = distractors.filter(opt => opt.word.trim() !== word.word.trim());

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
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;
    playCorrectSound();
    // 答对自动下一题
    autoNextTimer = setTimeout(() => {
      autoNextTimer = null;
      handleQuizNext();
    }, 900);
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
    // 答错不自动跳，让用户看清楚正确答案，手动点"下一题"
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
    const result = await api.getDistractors(learnWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取干扰项失败，使用队列内词', e);
  }

  // 从队列中补充干扰项
  if (distractors.length < 3) {
    const otherWords = learnQueue.filter(w => w.word !== word.word && w.id !== word.id);
    while (distractors.length < 3 && otherWords.length > 0) {
      const idx = Math.floor(Math.random() * otherWords.length);
      const w = otherWords[idx];
      distractors.push({ word: w.word, meaning: w.meaning });
      otherWords.splice(idx, 1);
    }
  }

  // 过滤：单词不能为空，不能和正确答案相同
  distractors = distractors.filter(opt => opt.word && opt.word.trim() && opt.word.trim() !== word.word.trim());
  distractors = distractors.slice(0, 3);

  // 正确答案
  let options = [{ word: word.word, meaning: word.meaning || '' }, ...distractors];
  options.sort(() => Math.random() - 0.5);

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
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${learnTotalWords}词，错${learnWrongCount}个）</span>`;
    optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));
    // 答对自动跳下一题
    autoNextTimer = setTimeout(() => {
      handleQuizNext();
    }, 900);
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    // 选错后：显示所有选项的释义
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      // 从选项数据中找释义
      const opt = currentWord.word === w ? currentWord : null;
      let meaning = '';
      // 尝试从队列中找释义
      const queueWord = learnQueue.find(qw => qw.word === w);
      if (queueWord) meaning = queueWord.meaning || '';
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
    // 答对自动下一题
    autoNextTimer = setTimeout(() => {
      autoNextTimer = null;
      handleQuizNext();
    }, 900);
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
 * 测验模式"下一题"：标记已学会并跳到下一个（循环）
 * 使用 learnedIds 防止返回上一题后重复 submitReview
 */
async function handleQuizNext() {
  // 取消挂起的自动下一题，防止回车+自动跳转双重触发
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
  const currentWord = learnQueue[learnIndex];
  if (currentWord && !learnedIds.has(currentWord.id)) {
    await api.submitReview(currentWord.id, 'good');
    learnedIds.add(currentWord.id);
    allLearnedIds.add(currentWord.id);
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

// 保存复习位置到 localStorage（用于中断恢复）
function saveReviewPosition() {
  if (reviewQueue.length === 0) return;
  const position = {
    index: reviewIndex,
    queueLength: reviewQueue.length,
    wordbookId: reviewWordbookId,
    timestamp: Date.now()
  };
  localStorage.setItem('wordmemo_review_position', JSON.stringify(position));
}

// 恢复复习位置（从 localStorage）
function restoreReviewPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem('wordmemo_review_position') || 'null');
    if (!saved) return false;
    // 检查是否同词书、同队列长度、且不超过5分钟
    if (saved.wordbookId !== reviewWordbookId) return false;
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

// 加载今日复习队列
async function loadReviewQueue() {
  try {
    showLoading();
    const res = await api.getReviewToday(reviewWordbookId, { random: reviewRandomMode });
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
      const result = await api.getDistractors(reviewWordbookId, excludeIds, 3);
      distractors = result || [];
    } catch (e2) {
      console.warn('获取随机干扰项也失败', e2);
    }
  }

  // 如果不够3个，从当前队列补充
  if (distractors.length < 3) {
    const otherWords = reviewQueue.filter(w => w.word !== word.word && w.id !== word.id);
    while (distractors.length < 3 && otherWords.length > 0) {
      const idx = Math.floor(Math.random() * otherWords.length);
      const w = otherWords[idx];
      distractors.push({ word: w.word, meaning: w.meaning });
      otherWords.splice(idx, 1);
    }
  }

  // 组合选项：过滤干扰项空值，正确答案始终包含
  distractors = distractors.filter(opt => opt.word && opt.word.trim() && opt.meaning && opt.meaning.trim());
  distractors = distractors.filter(opt => opt.word.trim() !== word.word.trim());
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
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;
    playCorrectSound();
    reviewAutoNextTimer = setTimeout(() => {
      reviewAutoNextTimer = null;
      handleReviewQuizNext();
    }, 900);
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
    const result = await api.getDistractors(reviewWordbookId, excludeIds, 3);
    distractors = result || [];
  } catch (e) {
    console.warn('获取干扰项失败，使用队列内词', e);
  }

  // 从队列中补充干扰项
  if (distractors.length < 3) {
    const otherWords = reviewQueue.filter(w => w.word !== word.word && w.id !== word.id);
    while (distractors.length < 3 && otherWords.length > 0) {
      const idx = Math.floor(Math.random() * otherWords.length);
      const w = otherWords[idx];
      distractors.push({ word: w.word, meaning: w.meaning });
      otherWords.splice(idx, 1);
    }
  }

  // 过滤
  distractors = distractors.filter(opt => opt.word && opt.word.trim() && opt.word.trim() !== word.word.trim());
  distractors = distractors.slice(0, 3);

  let options = [{ word: word.word, meaning: word.meaning || '' }, ...distractors];
  options.sort(() => Math.random() - 0.5);

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
    feedback.innerHTML = `回答正确！<span class="quiz-accuracy">正确率：${accuracy}%（${reviewTotalWords}词，错${reviewWrongCount}个）</span>`;
    optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));
    reviewAutoNextTimer = setTimeout(() => {
      handleReviewQuizNext();
    }, 900);
  } else {
    btn.classList.add('wrong');
    playWrongSound();
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      const w = b.dataset.word;
      let meaning = '';
      const queueWord = reviewQueue.find(qw => qw.word === w);
      if (queueWord) meaning = queueWord.meaning || '';
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
    reviewAutoNextTimer = setTimeout(() => {
      reviewAutoNextTimer = null;
      handleReviewQuizNext();
    }, 900);
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
 * 复习测验模式"下一题"：提交复习评级并跳到下一个（循环）
 */
async function handleReviewQuizNext() {
  if (reviewAutoNextTimer) { clearTimeout(reviewAutoNextTimer); reviewAutoNextTimer = null; }
  const currentWord = reviewQueue[reviewIndex];
  if (currentWord) {
    try {
      await api.submitReview(currentWord.id, 'good');
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
      stats = await api.getStats();
      homeStatsCache = stats;
    }
    hideLoading();

    // 统计卡片
    $('#statsTotal').textContent = stats.total || 0;
    $('#statsMastered').textContent = stats.mastered || 0;
    $('#statsStreak').textContent = stats.streak_days || 0;
    $('#statsToday').textContent = stats.today_learned || 0;

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
  if (libraryFilter !== 'all') params.set('status', libraryFilter);
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
    // 刷新详情
    if (updated) {
      currentDetailWord = updated;
      fillDetailModal(updated);
    } else {
      closeDetailModal();
    }
    // 刷新列表
    if ($('#page-library').classList.contains('active')) renderLibrary();
  } catch (err) {
    handleError(err);
  }
}

/* ====================================================
   移动单词到其他词本
   ==================================================== */

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
    const updated = await api.updateWord(currentDetailWord.id, data);
    hideLoading();
    showToast('已移动到新词本', 'success');
    closeMoveWordbookModal();
    // 刷新详情
    if (updated) {
      currentDetailWord = updated;
      fillDetailModal(updated);
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
    switchPage('learn');
  });
  $('#btnStartReview').addEventListener('click', () => {
    reviewQueue = [];
    switchPage('review');
  });
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

  // 扫描录入（AI识图）
  $('#scanArea').addEventListener('click', handleScanPick);
  $('#scanInput').addEventListener('change', handleScanChange);
  $('#btnScanRecognize').addEventListener('click', handleScanRecognize);
  $('#btnScanCheckAll').addEventListener('click', handleScanCheckAll);
  $('#btnScanAddSelected').addEventListener('click', handleScanAddSelected);

  // 取消照片按钮：阻止冒泡，避免触发 scanArea 的选图
  const scanCancelBtn = $('#scanCancelBtn');
  if (scanCancelBtn) {
    scanCancelBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      e.preventDefault();
      resetScan();
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
    renderLibrary();
  });

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
      // 同步到复习词书
      reviewWordbookId = learnWordbookId;
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
      // 同步到学习词书
      learnWordbookId = reviewWordbookId;
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
  $('#btnQuizKnown').addEventListener('click', handleQuizNext);
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
  $('#btnReviewQuizNext').addEventListener('click', handleReviewQuizNext);

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
  $('#moveCloseBtn').addEventListener('click', closeMoveWordbookModal);
  $('#moveCancelBtn').addEventListener('click', closeMoveWordbookModal);
  $('#moveWordbookModal').addEventListener('click', (e) => {
    if (e.target.id === 'moveWordbookModal') closeMoveWordbookModal();
  });
  $('#moveConfirmBtn').onclick = handleMoveWordbook;
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
  $('#todayNewCount').textContent = stats.new || 0;

  // 操作按钮描述
  $('#learnDesc').textContent = `${stats.new || 0}个待学`;
  $('#reviewDesc').textContent = `${stats.today_review || 0}个单词待复习`;

  // 统计卡片
  $('#statTotal').textContent = stats.total || 0;
  $('#statNew').textContent = stats.new || 0;
  $('#statReview').textContent = stats.review || 0;
  $('#statMastered').textContent = stats.mastered || 0;

  // 学习曲线
  const historyArr = (stats.history || []).map(h => h.count || 0);
  drawLineChart($('#homeLineChart'), historyArr);

  // 今日单词列表
  const list = $('#todayWordList');
  if (words && words.length > 0) {
    list.innerHTML = words.slice(0, 5).map((word, i) => wordItemHtml(word, i + 1)).join('');
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
    const stats = await api.getStats();
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
    updateText('todayNewCount', stats.new || 0);
    updateText('statTotal', stats.total || 0);
    updateText('statNew', stats.new || 0);
    updateText('statReview', stats.review || 0);
    updateText('statMastered', stats.mastered || 0);

    // 更新签到状态
    updateCheckinUI(stats.checked_in, stats.streak_days);

    // 更新操作按钮描述
    const dailyGoal = stats.daily_goal || 20;
    const learnDesc = $('#learnDesc');
    if (learnDesc) learnDesc.textContent = `${stats.new || 0}个待学`;
    const reviewDesc = $('#reviewDesc');
    if (reviewDesc) reviewDesc.textContent = `${stats.today_review || 0}个单词待复习`;
  } catch (e) {
    console.log('Silent refresh failed:', e);
  }
}

/**
 * 应用初始化
 */
async function init() {
  bindEvents();
  bindAuthEvents();
  // 初始化下拉刷新和页面滑动切换
  initPullRefresh();
  initPageSwipe();
  // 初始化安卓返回键处理
  initBackButtonHandler();

  // 乐观渲染：先用缓存用户信息显示状态栏，再用缓存数据渲染首页
  const cachedUser = loadUserCache();
  if (cachedUser) {
    currentUser = cachedUser;
    onLoginSuccess();
    // 立即用缓存渲染首页（秒开）
    renderHomeFromCache();
  }

  // 后台检查登录状态并拉取最新数据
  const loggedIn = await checkAuthStatus();
  if (loggedIn) {
    // 只在缓存为空或数据变化时才重新渲染，避免闪烁
    const cached = loadHomeCache();
    if (!cached || !cached.stats) {
      // 没有缓存数据，必须从网络渲染
      renderHome();
    } else {
      // 有缓存数据，后台静默更新（不触发完整重渲染）
      refreshHomeDataSilently();
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
