/* ====================================================
   背单词应用 - 主逻辑
   连接 Flask 后端 API（相对路径 /api，本地与部署后通用）
   本地开发：通过 http://localhost:5000/ 访问前端
   ==================================================== */

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

    try {
      const res = await fetch(url, { ...options, headers });

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
  async getReviewToday() {
    const res = await this.request('/review/today');
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
  async getLearnToday() {
    const res = await this.request('/learn/today');
    return res && res.data ? res.data : (Array.isArray(res) ? res : []);
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
}

// 创建全局 API 实例
const api = new WordAPI();

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
  showToast(err.message || '操作失败', 'error');
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
  return { new: '新词', review: '复习中', mastered: '已掌握' }[status] || status;
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

/**
 * 单词发音（使用浏览器内置 TTS，免费零成本）
 * @param {string} word - 要发音的单词
 * @param {HTMLElement} [btn] - 触发按钮，用于播放动画
 */
function speakWord(word, btn) {
  if (!word) return;
  if (!('speechSynthesis' in window)) {
    showToast('浏览器不支持语音播放', 'error');
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
function wordItemHtml(word) {
  // 查找所属单词本
  const book = word.wordbook_id ? wordbooks.find(b => b.id === word.wordbook_id) : null;
  const bookTag = book ? `<span class="word-book-tag" style="border-color:${book.color}40;color:${book.color}">${escapeHtml(book.name)}</span>` : '';
  return `
    <div class="word-item" data-id="${word.id}">
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
  $$('.page').forEach(p => p.classList.remove('active'));
  // 显示目标页面
  const target = $('#page-' + pageName);
  if (target) target.classList.add('active');

  // 更新顶部标题
  $('#statusTitle').textContent = PAGE_TITLES[pageName] || '背单词';

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
      break;
    case 'library':
      loadWordbooks();
      renderLibrary();
      break;
    case 'learn':
      // 进入学习页时自动加载今日新词
      if (learnQueue.length === 0) loadLearnQueue();
      break;
    case 'review':
      if (reviewQueue.length === 0) loadReviewQueue();
      break;
    case 'input':
      // 进入录入页时刷新单词本下拉
      loadWordbooks();
      break;
    case 'stats':
      renderStats();
      loadSettings();
      break;
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

    // 连续天数（后端暂未返回，默认0）
    $('#streakNum').textContent = stats.streak_days || 0;

    // 今日概览
    $('#todayLearned').textContent = stats.today_learned || 0;
    $('#todayReviewCount').textContent = stats.today_review || 0;
    // today_new 后端用 new 字段（新单词总数）代替
    $('#todayNewCount').textContent = stats.new || 0;

    // 操作按钮描述
    $('#learnDesc').textContent = `${stats.new || 0}个新词待学`;
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
      list.innerHTML = words.slice(0, 5).map(wordItemHtml).join('');
      // 绑定点击事件查看详情
      list.querySelectorAll('.word-item').forEach(item => {
        item.addEventListener('click', () => openWordDetail(item.dataset.id));
      });
    } else {
      list.innerHTML = '<div class="empty-state"><p>暂无单词，快去添加吧</p></div>';
    }
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
    handleError(err);
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
  $('#scanInput').click();
}

// 预览选择的图片
function handleScanChange(e) {
  const file = e.target.files[0];
  if (!file) return;
  // 生成预览
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = $('#scanPreview');
    img.src = ev.target.result;
    img.style.display = 'block';
    $('.scan-placeholder').style.display = 'none';
  };
  reader.readAsDataURL(file);
  // 缓存文件对象
  scanFile = file;
  // 清除上一次的识别结果
  scanRecognizedWords = [];
  $('#scanConfirm').style.display = 'none';
  $('#scanResult').style.display = 'none';
}

let scanFile = null; // 当前选择的图片文件
let scanRecognizedWords = []; // AI识别到的单词列表 [{word, meaning, checked}]

// AI识别图片中的单词
async function handleScanRecognize() {
  if (!scanFile) {
    showToast('请先选择图片', 'warning');
    return;
  }
  try {
    showLoading('AI识别中...');
    const res = await api.aiRecognizeImage(scanFile);
    hideLoading();
    if (!res.success) {
      showToast(res.error || '识别失败', 'error');
      return;
    }
    scanRecognizedWords = (res.words || []).map(w => ({
      word: (w.word || '').trim().toLowerCase(),
      meaning: (w.meaning || '').trim(),
      checked: true, // 默认全选
    }));
    renderScanWords();
  } catch (err) {
    hideLoading();
    handleError(err);
  }
}

// 渲染识别到的单词列表（可勾选确认）
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
    <label class="scan-word-item" data-index="${i}">
      <input type="checkbox" class="scan-word-check" ${w.checked ? 'checked' : ''} data-index="${i}">
      <div class="scan-word-info">
        <span class="scan-word-text">${escapeHtml(w.word)}</span>
        ${w.meaning
          ? `<span class="scan-word-meaning">${escapeHtml(w.meaning)}</span>`
          : '<span class="scan-word-meaning scan-word-meaning-empty">无释义</span>'}
      </div>
    </label>
  `).join('');

  // 绑定勾选事件
  $$('.scan-word-check').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(e.target.dataset.index);
      scanRecognizedWords[idx].checked = e.target.checked;
      updateScanCheckAllState();
    });
  });

  updateScanCheckAllState();
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

  // 获取选择的单词本
  const scanWordbookId = ($('#scanWordbookSelect') || {}).value || null;

  // 所有单词都走批量接口，后端会自动用AI/词典分析每个单词
  // 图片识别的meaning仅用于确认列表展示，不直接入库（后端分析更全面）
  const wordsToAdd = selected.map(w => w.word);

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

async function renderLibrary() {
  try {
    showLoading();
    const params = {};
    if (libraryFilter !== 'all') params.status = libraryFilter;
    if (librarySearch) params.search = librarySearch;
    if (libraryWordbook !== '') params.wordbook_id = libraryWordbook;

    const words = await api.getWords(params);
    libraryData = sortLibraryData(words || []);
    hideLoading();

    const list = $('#libraryList');
    if (libraryData.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <p>${librarySearch || libraryFilter !== 'all' || libraryWordbook !== '' ? '没有符合条件的单词' : '词库空空如也'}</p>
          <p class="empty-sub">点击右下角 + 添加单词</p>
        </div>`;
      return;
    }

    list.innerHTML = libraryData.map(wordItemHtml).join('');
    // 绑定点击查看详情
    list.querySelectorAll('.word-item').forEach(item => {
      item.addEventListener('click', () => openWordDetail(item.dataset.id));
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
      const count = b.word_count !== undefined ? `<span class="chip-count">${b.word_count}</span>` : '';
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

let learnQueue = [];      // 今日新词队列
let learnIndex = 0;       // 当前索引
let learnFlipped = false; // 当前卡片是否翻转
let learnMode = 'flip';   // 学习模式：flip 翻卡 / choice 看词选义 / spell 拼写默写
let quizAnswered = false; // 测验题是否已作答（防止重复点击）
let learnedIds = new Set(); // 已标记为"已学会"的单词 ID，避免返回上一题后重复 submitReview
let autoNextTimer = null;   // 自动下一题的定时器（用于取消）

// 加载今日新词队列
async function loadLearnQueue() {
  try {
    showLoading();
    const res = await api.getLearnToday();
    // 兼容返回数组或 {words:[...]}
    learnQueue = Array.isArray(res) ? res : (res.words || res.data || []);
    learnIndex = 0;
    learnedIds = new Set();  // 重置已学记录
    if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
    hideLoading();
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
  if (learnIndex >= total) {
    // 学习完成
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'none';
    $('#quizActions').style.display = 'none';
    $('#learnEmpty').style.display = 'block';
    $('#learnProgress').textContent = `${total} / ${total}`;
    showToast('今日新词已学完', 'success');
    return;
  }

  const word = learnQueue[learnIndex];
  $('#learnProgress').textContent = `${learnIndex + 1} / ${total}`;
  $('#learnEmpty').style.display = 'none';

  // 根据模式显示对应卡片
  if (learnMode === 'flip') {
    $('#learnCard').style.display = 'block';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'flex';
    $('#quizActions').style.display = 'none';
    renderFlipCard(word);
  } else if (learnMode === 'choice') {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'flex';
    $('#learnSpellCard').style.display = 'none';
    $('#learnActions').style.display = 'none';
    $('#quizActions').style.display = 'flex';
    renderChoiceCard(word);
  } else if (learnMode === 'spell') {
    $('#learnCard').style.display = 'none';
    $('#learnChoiceCard').style.display = 'none';
    $('#learnSpellCard').style.display = 'flex';
    $('#learnActions').style.display = 'none';
    $('#quizActions').style.display = 'flex';
    renderSpellCard(word);
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
  // 重置翻转状态
  learnFlipped = false;
  $('#learnCard').classList.remove('flipped');
}

/**
 * 渲染看词选义模式
 * 从所有已学单词中随机抽 3 个作为干扰项
 */
function renderChoiceCard(word) {
  quizAnswered = false;
  $('#choiceWord').textContent = word.word;
  $('#choicePhonetic').textContent = word.phonetic || '';
  $('#choiceFeedback').textContent = '';
  $('#choiceFeedback').className = 'quiz-feedback';

  // 从队列中随机抽 3 个干扰项的释义（包含当前词共 4 个）
  const otherWords = learnQueue.filter(w => w.word !== word.word);
  const distractors = [];
  while (distractors.length < 3 && otherWords.length > 0) {
    const idx = Math.floor(Math.random() * otherWords.length);
    distractors.push(otherWords[idx]);
    otherWords.splice(idx, 1);
  }
  // 如果队列不够 4 个，补充演示词释义
  while (distractors.length < 3) {
    distractors.push({ meaning: '（无）', word: '_dummy' + distractors.length });
  }

  const options = [word, ...distractors];
  // 打乱顺序
  options.sort(() => Math.random() - 0.5);

  const optionsEl = $('#choiceOptions');
  optionsEl.innerHTML = options.map(opt => `
    <button class="quiz-option" data-word="${escapeHtml(opt.word)}">${escapeHtml(opt.meaning || '（无释义）')}</button>
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

  // 标记所有选项不可再点
  optionsEl.querySelectorAll('.quiz-option').forEach(b => b.classList.add('disabled'));

  if (isCorrect) {
    btn.classList.add('correct');
    feedback.className = 'quiz-feedback correct';
    feedback.textContent = '回答正确！';
    // 答对自动下一题
    autoNextTimer = setTimeout(() => {
      autoNextTimer = null;
      handleQuizNext();
    }, 900);
  } else {
    btn.classList.add('wrong');
    // 标出正确答案
    optionsEl.querySelectorAll('.quiz-option').forEach(b => {
      if (b.dataset.word === currentWord.word) b.classList.add('correct');
    });
    feedback.className = 'quiz-feedback wrong';
    feedback.innerHTML = `回答错误<span class="feedback-meaning">正确答案：${escapeHtml(currentWord.meaning || '')}</span>`;
    // 答错不自动跳，让用户看清楚正确答案，手动点"下一题"
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
    // 答对自动下一题
    autoNextTimer = setTimeout(() => {
      autoNextTimer = null;
      handleQuizNext();
    }, 900);
  } else {
    input.classList.add('wrong');
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
 * 测验模式"下一题"：标记已学会并进入下一个
 * 使用 learnedIds 防止返回上一题后重复 submitReview
 */
async function handleQuizNext() {
  // 取消挂起的自动下一题，防止回车+自动跳转双重触发
  if (autoNextTimer) { clearTimeout(autoNextTimer); autoNextTimer = null; }
  const currentWord = learnQueue[learnIndex];
  if (currentWord && !learnedIds.has(currentWord.id)) {
    await api.submitReview(currentWord.id, 'good');
    learnedIds.add(currentWord.id);
  }
  learnIndex++;
  renderLearnCard();
}

/**
 * 返回上一题（测验模式与翻卡模式共用）
 * 不重新 submitReview，只回看
 */
function handleLearnPrev() {
  if (learnIndex === 0) {
    showToast('已经是第一题了', 'info');
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

// 学习：已学会，进入下一个
// 使用 learnedIds 防止返回上一题后重复 submitReview
async function handleLearnKnown() {
  const word = learnQueue[learnIndex];
  if (!word) return;
  try {
    // 调用复习接口标记为 good（避免重复标记）
    if (!learnedIds.has(word.id)) {
      await api.submitReview(word.id, 'good');
      learnedIds.add(word.id);
    }
    learnIndex++;
    renderLearnCard();
  } catch (err) {
    // 即使提交失败也继续下一张，避免卡住
    console.error(err);
    learnIndex++;
    renderLearnCard();
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

// 加载今日复习队列
async function loadReviewQueue() {
  try {
    showLoading();
    const res = await api.getReviewToday();
    reviewQueue = Array.isArray(res) ? res : (res.words || res.data || []);
    reviewIndex = 0;
    hideLoading();
    renderReviewCard();
  } catch (err) {
    handleError(err);
  }
}

// 渲染当前复习卡片
function renderReviewCard() {
  const total = reviewQueue.length;
  if (reviewIndex >= total) {
    $('#reviewCard').style.display = 'none';
    $('#ratingActions').style.display = 'none';
    $('#reviewEmpty').style.display = 'block';
    $('#reviewProgress').textContent = `${total} / ${total}`;
    if (total > 0) showToast('今日复习已完成', 'success');
    return;
  }

  const word = reviewQueue[reviewIndex];
  $('#reviewProgress').textContent = `${reviewIndex + 1} / ${total}`;
  $('#reviewEmpty').style.display = 'none';
  $('#reviewCard').style.display = 'block';
  $('#ratingActions').style.display = 'flex';

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

  // 重置翻转
  reviewFlipped = false;
  $('#reviewCard').classList.remove('flipped');
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
    // 评级为 again 时，将单词重新加入队列末尾
    if (rating === 'again') {
      reviewQueue.push(word);
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
    showToast('每日新词目标请输入 1-200 之间的数字', 'error');
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
    showToast(`已保存：每日新词 ${goal} 个，复习上限 ${reviewGoal === 0 ? '不限' : reviewGoal + ' 个'}`, 'success');
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

  // 时态变形（仅动词显示，默认收起）
  const tensesSection = $('#modalTensesSection');
  const tensesGrid = $('#modalTenses');
  const tensesToggle = $('#modalTensesToggle');
  // 默认收起（每次打开详情卡片都重置为收起状态）
  tensesGrid.style.display = 'none';
  tensesToggle.classList.remove('tenses-toggle-open');
  if (word.tenses && word.tenses.base) {
    tensesSection.style.display = 'block';
    const t = word.tenses;
    const items = [
      { label: '原形',     value: t.base },
      { label: '三单',     value: t.third_singular },
      { label: '过去式',   value: t.past },
      { label: '过去分词', value: t.past_participle },
      { label: '现在分词', value: t.present_participle },
    ].filter(it => it.value);
    tensesGrid.innerHTML = items.map((it, idx) => {
      const isBase = it.label === '原形';
      return `<div class="tense-card ${isBase ? 'tense-base' : ''}">
        <span class="tense-label">${it.label}</span>
        <span class="tense-word">${escapeHtml(it.value)}</span>
      </div>`;
    }).join('');
    // 绑定展开/收起事件（先移除旧事件避免重复绑定）
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

  // 学习状态信息
  $('#modalStatusInfo').innerHTML = `
    <div class="status-info-row"><span class="status-info-label">状态</span><span class="status-info-value">${statusText(word.status)}</span></div>
    <div class="status-info-row"><span class="status-info-label">添加时间</span><span class="status-info-value">${formatDate(word.added_at)}</span></div>
    <div class="status-info-row"><span class="status-info-label">上次复习</span><span class="status-info-value">${formatDate(word.last_review)}</span></div>
    <div class="status-info-row"><span class="status-info-label">复习次数</span><span class="status-info-value">${word.review_count || 0}</span></div>
    <div class="status-info-row"><span class="status-info-label">下次复习</span><span class="status-info-value">${formatDate(word.next_review)}</span></div>
  `;
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
    { value: data.new, color: '#4a7fff', label: '新词' },
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
  // 设置：复习策略与防遗忘
  $('#reviewStrategySelect').addEventListener('change', handleSaveReviewStrategy);
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

  // 浮动添加按钮 -> 跳转录入页
  $('#fabAdd').addEventListener('click', () => switchPage('input'));

  // 学习翻卡
  $('#learnCard').addEventListener('click', flipLearnCard);
  $('#btnLearnKnown').addEventListener('click', handleLearnKnown);
  $('#btnLearnDetail').addEventListener('click', handleLearnDetail);
  $('#btnLearnPrev').addEventListener('click', handleLearnPrev);
  $('#learnClose').addEventListener('click', () => switchPage('home'));
  // 学习卡发音（阻止冒泡避免翻卡）
  $('#learnSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const word = learnQueue[learnIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });

  // 学习模式切换
  $$('.mode-tab').forEach(tab => {
    tab.addEventListener('click', () => switchLearnMode(tab.dataset.mode));
  });
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
  $$('.rating-btn').forEach(btn => {
    btn.addEventListener('click', () => handleReviewRating(btn.dataset.rating));
  });
  $('#reviewClose').addEventListener('click', () => switchPage('home'));
  // 复习卡发音
  $('#reviewSpeakBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    const word = reviewQueue[reviewIndex];
    if (word) speakWord(word.word, e.currentTarget);
  });

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
}

/**
 * 应用初始化
 */
function init() {
  bindEvents();
  updateStatusBarTime();
  // 每分钟更新状态栏时间
  setInterval(updateStatusBarTime, 60000);
  // 默认加载首页
  renderHome();
}

// DOM 就绪后初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
