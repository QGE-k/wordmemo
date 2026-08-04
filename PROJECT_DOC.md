# WordMemo 项目记录汇报文档

> **版本**：v1.0 | **更新日期**：2026-08-03 | **代码规模**：~16,000 行
> **用途**：项目开发记录、架构说明、维护指南，方便日后修改和云服务部署

---

## 目录

1. [项目概述](#1-项目概述)
2. [开发历程与里程碑](#2-开发历程与里程碑)
3. [技术架构](#3-技术架构)
4. [目录结构](#4-目录结构)
5. [数据库模型](#5-数据库模型)
6. [API 接口清单](#6-api-接口清单)
7. [核心业务逻辑](#7-核心业务逻辑)
8. [服务模块详解](#8-服务模块详解)
9. [前端设计](#9-前端设计)
10. [配置说明](#10-配置说明)
11. [部署指南](#11-部署指南)
12. [经验教训与踩坑记录](#12-经验教训与踩坑记录)
13. [常见问题](#13-常见问题)
14. [后续开发备忘](#14-后续开发备忘)

---

## 1. 项目概述

WordMemo 是一款专为**江西专升本英语考试**设计的智能背单词应用。系统集成本地词典查询、AI 深度词法分析、OCR 扫描录入、艾宾浩斯间隔复习算法，支持多用户数据隔离和管理员后台管理。

### 核心功能

| 模块 | 功能 |
|------|------|
| 单词学习 | 翻卡 / 看词选义 / 看义选词 / 拼写默写 |
| 复习系统 | 艾宾浩斯间隔复习，四级评级（again/hard/good/easy） |
| 词典查询 | ECDICT 本地词典 77 万词条，毫秒级查询 |
| AI 分析 | Agnes AI 单词拆解、词根词缀、记忆法、例句生成 |
| OCR 录入 | 百度高精度 OCR + AI 视觉识别双模式 |
| 文档导入 | 支持 txt / docx / xlsx / pdf 格式 |
| 词本管理 | 创建词本、全局分享、导入他人词本 |
| 用户系统 | 注册登录、数据隔离、管理员后台 |
| 移动端 | PWA 离线 + Android WebView 原生壳 |

### 技术栈

- **后端**：Python 3.11 + Flask 3.0 + SQLAlchemy
- **数据库**：SQLite（本地开发）/ PostgreSQL（Neon 云端）
- **前端**：原生 HTML / CSS / JavaScript（无框架，PWA）
- **AI**：Agnes AI（兼容 OpenAI 接口）
- **OCR**：百度智能云通用文字识别高精度版
- **词典**：ECDICT 开源英汉词典（77 万词条，812MB）
- **部署**：Render（Web 服务）+ Neon（数据库）+ UptimeRobot（保活）
- **移动端**：Android Kotlin WebView 原生封装

---

## 2. 开发历程与里程碑

### 关键开发节点

| 阶段 | 内容 | 状态 |
|------|------|------|
| 初始版本 | Flask 后端 + 原生前端，基础 CRUD 和学习功能 | ✅ 完成 |
| AI 集成 | Agnes AI 单词拆解分析，例句生成 | ✅ 完成 |
| 词典优化 | ECDICT 集成，替代 AI 做核心查询，解决超时问题 | ✅ 完成 |
| OCR 录入 | 百度 OCR + AI 视觉识别双模式 | ✅ 完成 |
| 文档导入 | txt/docx/xlsx/pdf 多格式支持 | ✅ 完成 |
| 用户系统 | 注册登录、数据隔离、管理员后台 | ✅ 完成 |
| 复习算法 | 艾宾浩斯间隔复习，三级策略，防遗忘机制 | ✅ 完成 |
| 统计优化 | 时区修正、用户隔离、状态变更同步 | ✅ 完成 |
| PWA + Android | Service Worker 离线缓存 + Android WebView 壳 | ✅ 完成 |
| 云端部署 | Render + Neon + UptimeRobot 方案 | ✅ 完成 |

### 关键问题修复记录

1. **AI 分析超时** → 改为 ECDICT 优先的三级降级策略
2. **复习队列无限增长** → 按 `next_review` 过滤，只返回到期单词
3. **今日已学时区 bug** → 新增 `get_today_utc_range()` 统一 UTC 比较
4. **统计数据不按用户隔离** → 所有查询添加 `user_id` 过滤
5. **OCR 413 错误** → `params=` 改为 `data=` 发送 base64 数据
6. **状态变更统计不同步** → `update_learn_history()` 支持负数
7. **Service Worker 缓存旧数据** → `cache: 'no-store'` + 版本号管理

---

## 3. 技术架构

### 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                       客户端                              │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │  浏览器 PWA   │    │ Android WebView│                  │
│  │  (Service    │    │  (Kotlin 壳)  │                   │
│  │   Worker)    │    │              │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │     HTTP API      │                            │
└─────────┼──────────────────┼───────────────────────────┘
          │                  │
┌─────────▼──────────────────▼───────────────────────────┐
│              Render Web Service (Flask)                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  app.py (4060行, 65+ API 路由)                    │    │
│  │  ├── 认证 API (注册/登录/密码重置)                 │    │
│  │  ├── 单词管理 API (CRUD/批量/导出)                │    │
│  │  ├── OCR/AI API (扫描识别/视觉识别)               │    │
│  │  ├── 学习/复习 API (队列/评分/统计)               │    │
│  │  ├── 词本管理 API (创建/分享/导入)                │    │
│  │  └── 管理员 API (用户管理/密码重置)               │    │
│  └─────────────────┬───────────────────────────────┘    │
│                    │                                     │
│  ┌─────────────────▼───────────────────────────────┐    │
│  │              服务层 (services/)                    │    │
│  │  ├── DictionaryService  ECDICT 77万词条           │    │
│  │  ├── AIService          Agnes AI 拆解分析          │    │
│  │  ├── OCRService         百度高精度OCR              │    │
│  │  └── DocImportService   文档解析导入               │    │
│  └─────────────────┬───────────────────────────────┘    │
│                    │                                     │
│  ┌─────────────────▼───────────────────────────────┐    │
│  │              数据层                               │    │
│  │  ├── SQLite (本地 wordmemo.db)                   │    │
│  │  ├── PostgreSQL (Neon 云端)                       │    │
│  │  └── ECDICT (stardict.db 812MB)                  │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
         │                                    │
         ▼                                    ▼
  ┌──────────────┐                   ┌──────────────┐
  │  Agnes AI    │                   │  百度智能云   │
  │  API         │                   │  OCR API     │
  └──────────────┘                   └──────────────┘
```

### 请求处理流程

1. 前端通过 `WordAPI` 类封装所有 HTTP 请求
2. Service Worker 对只读 GET API 做网络优先 + 缓存兜底
3. 写操作（POST/PUT/DELETE）纯网络不缓存
4. 后端通过 `get_current_user_id()` 获取 session 中的用户 ID 实现数据隔离
5. 所有 API 响应头设置 `Cache-Control: no-store, no-cache, must-revalidate`

### 单词分析三级降级策略

```
输入单词
    │
    ▼
┌─────────────────────┐
│ ECDICT 本地词典      │ ── 命中 ──→ 返回 (source=dictionary, ~2.8ms)
│ 77万词条             │
└─────────┬───────────┘
          │ 未命中
          ▼
┌─────────────────────┐
│ Agnes AI 分析       │ ── 成功 ──→ 返回 (source=ai, ~3-10s)
│ timeout=120s        │
└─────────┬───────────┘
          │ 失败/超时
          ▼
┌─────────────────────┐
│ 规则分析             │ ──→ 返回 (source=rules, <1ms)
│ 前缀/后缀/复合词     │
└─────────────────────┘
```

---

## 4. 目录结构

```
wordmemo/
├── .github/workflows/
│   └── build-apk.yml                 # GitHub Actions 构建 APK
├── android/                          # Android 原生壳（Kotlin WebView）
│   └── app/src/main/
│       ├── java/com/wordmemo/app/
│       │   ├── MainActivity.kt       # WebView 容器主活动
│       │   └── SplashActivity.kt     # 启动屏
│       ├── res/                      # 图标、主题、配置
│       └── AndroidManifest.xml
├── backend/                          # Flask 后端
│   ├── app.py                        # ★ 主应用 (4060行, 65+ API 路由)
│   ├── config.py                     # 配置类（环境变量读取）
│   ├── models.py                     # 6 个数据模型定义 (298行)
│   ├── run.py                        # 启动入口
│   ├── requirements.txt              # Python 依赖
│   ├── .env / .env.example           # 环境变量（.env 被 gitignore）
│   ├── Procfile                      # gunicorn 部署命令
│   ├── runtime.txt                   # python-3.11.9
│   ├── render.yaml                   # Render 一键部署配置
│   ├── download_ecdict.sh            # ECDICT 词典下载脚本
│   ├── services/                     # 服务模块
│   │   ├── dictionary_service.py     # ★ ECDICT 词典 + 规则分析 (4861行)
│   │   ├── ai_service.py             # Agnes AI 集成 (762行)
│   │   ├── ocr_service.py            # 百度 OCR (375行)
│   │   └── doc_import_service.py     # 文档解析 (192行)
│   ├── data/                         # 数据文件（gitignore）
│   │   ├── stardict.db               # ECDICT 词典 812MB
│   │   ├── ecdict.zip                # 词典压缩包（部署用）
│   │   └── ocr_usage.json            # OCR 用量记录
│   ├── instance/                     # SQLite 数据库（gitignore）
│   │   └── wordmemo.db
│   └── static/                       # 前端部署副本（= frontend/ 的拷贝）
│       ├── index.html
│       ├── assets/{app.js, style.css}
│       ├── sw.js                     # Service Worker
│       ├── manifest.json             # PWA 配置
│       └── icons/                    # PWA 图标
├── frontend/                         # 前端源文件
│   ├── index.html                    # 主页面 (1128行, 7个页面区块)
│   ├── assets/
│   │   ├── app.js                    # ★ 全部前端逻辑 (6800+行)
│   │   └── style.css                 # 样式表 (3879行)
│   ├── sw.js                         # Service Worker (180行)
│   └── manifest.json
├── DEPLOY.md                         # 部署指南（详细版）
├── README.md                         # 项目说明
├── PROJECT_DOC.md                    # ← 本文档
└── .gitignore                        # 排除 .env / data/ / instance/ / *.db
```

### 重要说明

- `frontend/` 是源文件目录，`backend/static/` 是部署副本
- 修改前端代码后，需要同步到 `backend/static/`
- `app.py` 的 `serve_index` 等路由从 `static/` 目录提供前端文件
- ECDICT 词典文件（812MB）不入 Git，通过 GitHub Release 分发

---

## 5. 数据库模型

系统使用 SQLAlchemy ORM，定义 6 个数据模型。支持 SQLite（本地）和 PostgreSQL（Neon 云端）双数据库，通过环境变量 `DATABASE_URL` 切换。

### 5.1 User（用户模型）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `username` | String(80) unique | 用户名（2-20字符） |
| `salt` | String(32) | 密码盐值（16字节随机hex） |
| `password_hash` | String(64) | SHA256 哈希 |
| `role` | String(20) | 角色：admin / user |
| `nickname` | String(80) | 显示昵称 |
| `created_at` | DateTime | 注册时间 |
| `security_question` | String(255) | 安全问题（密码重置用） |
| `security_answer` | String(255) | 安全问题答案 |
| `is_active` | Boolean | 账号启用状态 |

- 密码存储：SHA256(密码 + 随机盐值)，不可逆
- 第一个注册的用户自动成为 admin
- 管理员可禁用/启用账号、重置任意用户密码

### 5.2 Word（单词模型）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 自增主键 |
| `word` | String(255) | 单词文本（可含词组如 "sports meeting"） |
| `phonetic` | String(255) | 音标 |
| `meaning` | Text | 中文释义 |
| `status` | String(20) | 学习状态：`new` / `review` / `mastered` |
| `word_type` | String(50) | 类型：复合词 / 派生词 / 基础词 |
| `split_data` | JSON | 复合词拆解数据 |
| `morph_data` | JSON | 词根词缀分析 |
| `examples` | JSON | 例句列表 `[{en, zh}]` |
| `tenses` | JSON | 动词时态变形（五种形态） |
| `mnemonic` | Text | AI 生成的记忆口诀 |
| `added_at` | DateTime | 添加时间 |
| `last_review` | DateTime | 上次复习时间（**UTC 存储**） |
| `next_review` | DateTime | 下次复习时间（艾宾浩斯） |
| `review_count` | Integer | 复习次数 |
| `wrong_count` | Integer | 错误次数（again/hard 累加） |
| `wordbook_id` | Integer FK | 所属单词本 |
| `user_id` | Integer FK | 所属用户 |
| `is_starred` | Boolean | 是否为重点单词 |

- **唯一约束**：`(word, user_id)` 联合唯一 — 同一用户下单词不重复
- `split_data` 结构：`[{part, meaning, original, original_meaning, transform, explain}]`
- `tenses` 结构：`{base, third_singular, past, past_participle, present_participle}`（仅动词有）

### 5.3 其他模型

| 模型 | 表名 | 关键字段 | 说明 |
|------|------|---------|------|
| **LearnHistory** | `learn_history` | date, count, correct_count, total_count, checked_in, user_id | 每日学习记录，`(date, user_id)` 联合唯一 |
| **LearnSession** | `learn_sessions` | date, duration_minutes, user_id | 学习时长记录 |
| **Setting** | `settings` | daily_goal, daily_review_goal, review_strategy, anti_forget, anti_forget_interval | 全局设置（单行表 id=1） |
| **Wordbook** | `wordbooks` | name, description, color, user_id, is_shared, shared_at | 单词本，支持分享到全局 |

### 数据库连接池配置

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_pre_ping': True,   # 连接前检测，避免用已断开的连接
    'pool_recycle': 270,     # 270秒回收（适配 Neon 5分钟休眠）
    'pool_size': 4,          # 连接池大小
    'max_overflow': 2,       # 最大溢出连接
}
```

### 自动迁移机制

应用启动时自动执行所有迁移函数（`ensure_*_column`、`fix_*_constraint`），用 `inspect` 检查列/索引是否存在，不存在则 `ALTER TABLE ADD COLUMN`。无需手动运行迁移脚本。

现有迁移函数：
- `ensure_mnemonic_column()` — 添加 mnemonic 字段
- `ensure_wordbook_column()` — 添加 wordbook_id 字段
- `ensure_settings_columns()` — 添加复习策略等设置字段
- `ensure_tenses_column()` — 添加 tenses 字段
- `ensure_user_id_columns()` — 添加 user_id 到各表
- `ensure_user_security_columns()` — 添加安全问题字段
- `ensure_user_active_column()` — 添加 is_active 字段
- `ensure_word_wrong_count_column()` — 添加 wrong_count 字段
- `ensure_word_starred_column()` — 添加 is_starred 字段
- `ensure_learn_history_accuracy_columns()` — 添加准确率字段
- `ensure_learn_history_checkin_column()` — 添加签到字段
- `ensure_learn_history_user_id_column()` — 添加 user_id 到学习历史
- `ensure_wordbook_shared_columns()` — 添加分享字段

---

## 6. API 接口清单

系统共定义 **65+ 个 API 路由**，按功能模块分组如下：

### 6.1 认证 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/auth/register` | POST | 注册（首个用户自动 admin） |
| `/api/auth/login` | POST | 登录（SHA256+盐校验） |
| `/api/auth/logout` | POST | 退出登录 |
| `/api/auth/me` | GET | 获取当前用户信息 |
| `/api/auth/reset_password` | POST | 通过安全问题重置密码 |
| `/api/auth/profile` | PUT | 修改昵称、安全问题 |
| `/api/auth/change-password` | PUT | 修改密码（需验证旧密码） |

### 6.2 单词管理 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/words` | GET | 获取单词列表（支持 status/search/wordbook_id/starred 过滤） |
| `/api/words` | POST | 添加单词（自动三级分析） |
| `/api/words/batch` | POST | 批量添加（5线程并发分析） |
| `/api/words/<id>` | GET / PUT / DELETE | 单词详情 / 更新 / 删除 |
| `/api/words/lookup` | GET | ECDICT 本地词典快速查词 |
| `/api/words/<id>/star` | POST | 切换单词重点标记 |
| `/api/words/batch-update-status` | POST | 批量更新状态（同步 LearnHistory） |
| `/api/words/batch-move` | POST | 批量移动到词本 |
| `/api/words/batch-delete` | POST | 批量删除 |
| `/api/words/<id>/refresh-examples` | POST | AI 重新生成例句 |
| `/api/words/refresh-all-examples` | POST | 批量刷新所有例句 |
| `/api/words/distractors` | GET | 获取随机干扰项（看词选义） |
| `/api/words/similar-distractors` | GET | 获取形近词干扰项（编辑距离） |
| `/api/words/check_duplicate` | GET | 检查单词是否已存在 |
| `/api/words/clear` | DELETE | 清空所有单词 |
| `/api/words/export` | GET | 导出 CSV/TXT/Anki |

### 6.3 词本管理 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/wordbooks` | GET / POST | 获取词本列表 / 创建词本 |
| `/api/wordbooks/<id>` | PUT / DELETE | 更新词本 / 删除词本 |
| `/api/wordbooks/<id>/words` | GET | 获取词本内单词 |
| `/api/wordbooks/<id>/share` | POST / DELETE | 分享到全局 / 取消分享 |
| `/api/global-wordbooks` | GET | 获取全局共享词本列表 |
| `/api/global-wordbooks/<id>/words` | GET | 查看共享词本单词 |
| `/api/global-wordbooks/<id>/import` | POST | 导入共享词本到自己的词库 |

### 6.4 OCR / AI / 文档导入 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/ocr/scan-preview` | POST | 极速 OCR 预览（百度OCR + ECDICT，~2s） |
| `/api/ocr/recognize` | POST | OCR 识别（旧接口） |
| `/api/ocr/add-words` | POST | OCR 识别 + 词典 + AI 分析 + 批量写库 |
| `/api/ocr/usage` | GET | 查询当月 OCR 用量 |
| `/api/ai/recognize-image` | POST | AI 视觉识别（~20s/张，支持手写体） |
| `/api/import/preview` | POST | 文档解析预览（txt/docx/xlsx/pdf） |
| `/api/import/confirm` | POST | 确认导入单词到词库 |

### 6.5 学习 / 复习 / 统计 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/learn/today` | GET | 获取学习队列（按状态优先级排序） |
| `/api/learn/today-words` | GET | 获取今天已学过的单词 |
| `/api/review/today` | GET | 获取到期复习队列（next_review <= now） |
| `/api/review/<id>` | POST | 提交复习评分（艾宾浩斯算法） |
| `/api/stats` | GET | 统计数据（各状态数量/今日已学/待复习/7天历史/热力图） |
| `/api/stats/enhanced` | GET | 增强统计（准确率/时长/难度分布/遗忘曲线） |
| `/api/stats/calendar` | GET | 日历视图学习历史 |
| `/api/checkin` | POST | 每日签到 |
| `/api/checkin/status` | GET | 获取签到状态 |
| `/api/settings` | GET / PUT | 获取/更新设置 |

### 6.6 管理员 API

| 路径 | 方法 | 功能 |
|------|------|------|
| `/api/admin/users` | GET | 获取所有用户列表及统计 |
| `/api/admin/users/<id>/words` | GET | 查看指定用户词库 |
| `/api/admin/users/<id>` | DELETE | 删除用户及所有数据 |
| `/api/admin/reset_user_password` | POST | 重置任意用户密码 |
| `/api/admin/toggle_user` | POST | 启用/禁用账号 |
| `/api/admin/user_stats/<id>` | GET | 获取用户学习统计 |

### 6.7 静态文件路由

| 路径 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 主页面 index.html |
| `/assets/<path>` | GET | JS/CSS 静态资源 |
| `/manifest.json` | GET | PWA 配置 |
| `/sw.js` | GET | Service Worker |
| `/icons/<path>` | GET | PWA 图标 |
| `/.well-known/assetlinks.json` | GET | Android Deep Link 配置 |

---

## 7. 核心业务逻辑

### 7.1 艾宾浩斯复习算法

复习评分采用四级评级制（类似 Anki），后端 `submit_review()` 函数实现完整算法：

| 评分 | 含义 | 间隔 | 状态 |
|------|------|------|------|
| `again` | 不会 | 1 分钟后重新出现 | review |
| `hard` | 困难 | 1 天后 | review |
| `good` | 一般 | 按复习次数递增间隔 | review |
| `easy` | 简单 | 最长间隔，达阈值则 mastered | review / mastered |

三种复习策略：

| 策略 | 间隔天数数组 | easy 掌握阈值 |
|------|-------------|--------------|
| 宽松 (relaxed) | [2, 5, 10, 20, 45] | 3 次 |
| 标准 (standard) — 默认 | [1, 3, 7, 14, 30] | 4 次 |
| 严格 (strict) | [1, 2, 4, 7, 15] | 6 次 |

**防遗忘机制（anti_forget）**：开启后，已掌握（mastered）的单词会按 `anti_forget_interval`（默认 30 天）再次安排回顾。已掌握单词选"不会"则降级回 review，选其他则继续按间隔安排。

**复习队列排序**：`/api/review/today` 只返回 `next_review <= 当前时间` 的到期单词，按 `next_review` 升序排列（过期最久的排最前面）。

### 7.2 今日已学统计与时区处理

**关键设计：`get_today_utc_range()`**

`last_review` 存储的是 `datetime.utcnow()`（UTC 时间），但用户看到的"今天"是本地日期（`date.today()`）。**不能直接用本地午夜和 UTC 时间比较**，否则 UTC+8 凌晨 0~8 点学习的单词不会被计入"今日已学"。

解决方案：`get_today_utc_range()` 将本地午夜转换为 UTC 范围 `(today_start_utc, today_end_utc)`，所有时间比较都在 UTC 基准下进行。

```python
def get_today_utc_range():
    today_local = date.today()
    today_start_local = datetime.combine(today_local, datetime.min.time())
    utc_offset = datetime.now() - datetime.utcnow()  # e.g. timedelta(hours=8)
    today_start_utc = today_start_local - utc_offset
    today_end_utc = today_start_utc + timedelta(days=1)
    return today_start_utc, today_end_utc
```

**状态变更与统计同步**：

- `new → review/mastered`（首次学习）：`update_learn_history(+1)`
- `review/mastered → new`（改回未学习）：若 `last_review` 在今天，`update_learn_history(-1)`
- `update_learn_history()` 支持负数，内部用 `max(0, count + delta)` 防止负数

### 7.3 统计接口逻辑

`/api/stats` 接口必须接收 `wordbook_id` 参数，返回选中词本的真实数据：

| 字段 | 计算方式 |
|------|---------|
| `total` | 词本内总词数 |
| `new` | 状态为 new 的词数 |
| `reviewing` | 状态为 review 的词数 |
| `mastered` | 状态为 mastered 的词数 |
| `today_learned` | 今天 last_review 在 UTC 范围内的词数 |
| `today_review` | 与复习接口一致（含防遗忘的已掌握词回顾） |
| `pending_today` | `max(0, daily_goal - today_learned)` |

### 7.4 单词拆解三级优先

单词拆解遵循三级优先级：

1. **复合词**：如 "sports meeting" → sports + meeting
2. **屈折变形**：如 "running" → run + -ing
3. **基础词**：不拆解，直接返回

查词优先级链（`lookup()` 方法）：

1. 手工词典 `DICTIONARY`（含编辑过的精确拆解数据）
2. 名词复数形式（加 s/es/ies）
3. 动词 ing 形式
4. 动词时态变形表 `VERB_TENSES`
5. 形容词比较级/最高级 `ADJ_DEGREES`
6. ECDICT SQLite 查询
7. 有道词典在线查询（带内存缓存）

### 7.5 OCR 双模式识别

| 模式 | 技术 | 速度 | 适用场景 | 限额 |
|------|------|------|---------|------|
| 极速 OCR | 百度高精度 OCR + ECDICT | ~2s/张 | 印刷体单词表、课本 | 全局 800次/月 + 用户 50次/月 |
| AI 精准 | Agnes AI 视觉识别 | ~20s/张 | 手写笔记、混合内容 | 无限制 |

OCR 用量持久化到 `data/ocr_usage.json`，每月自动重置。超限时前端自动切换到 AI 精准模式。

---

## 8. 服务模块详解

### 8.1 DictionaryService（词典服务）

**文件**：`backend/services/dictionary_service.py`（4861 行，项目中最大的文件）

**核心功能**：
- 懒加载 ECDICT SQLite 数据库连接（双重检查锁，线程安全）
- 77 万词条毫秒级查询（2.8ms/词）
- 手工词典 `DICTIONARY` 存储编辑过的精确拆解数据
- 释义覆盖表 `MEANING_OVERRIDES` 确保短语组件用常用释义
- 前缀/后缀/复合词规则分析（AI 不可用时的兜底方案）
- 在线查词缓存（有道词典，带内存缓存）

**关键数据结构**：

```python
# 手工词典示例
DICTIONARY = {
    'sports meeting': {
        'phonetic': '/spɔːts ˈmiːtɪŋ/',
        'meaning': 'n. 运动会',
        'type': '复合词',
        'split': [
            {'part': 'sports', 'meaning': 'n. 运动', 'original': 'sport',
             'original_meaning': 'n. 运动', 'transform': '加-s变复数',
             'explain': '复数形式作定语，修饰meeting'},
            {'part': 'meeting', 'meaning': 'n. 聚会，会议', 'original': 'meeting',
             'original_meaning': 'n. 聚会，会议', 'transform': '原形不变',
             'explain': '复合词的核心名词'}
        ],
        'mnemonic': '运动会就是运动的聚会',
        'examples': [{'en': '...', 'zh': '...'}]
    }
}

# 释义覆盖表（确保短语组件用常用释义）
MEANING_OVERRIDES = {
    'be': 'v. 是，存在',
    'take': 'v. 拿，取',
    'care': 'n. 关心，照顾',
    'look': 'v. 看',
    # ...
}
```

### 8.2 AIService（AI 分析服务）

**文件**：`backend/services/ai_service.py`（762 行）

| 方法 | 功能 | 参数 |
|------|------|------|
| `analyze_word(word)` | 深度词法分析（拆解/记忆法/例句/时态） | temperature=0.3, max_tokens=16000, timeout=120s |
| `generate_examples(word, meaning)` | 轻量级例句生成（2个专升本例句） | temperature=0.8, max_tokens=2000, timeout=60s |
| `recognize_image(image_base64)` | AI 视觉识别图片中单词 | temperature=0.1, max_tokens=16000, timeout=120s |

**AI 提示词核心规则**：
- 释义优先规则：split 中每个部分的 meaning 必须是最常用释义
- 前缀同化规则：识别拉丁语前缀同化变化（如 success = suc- + cess）
- 基础词不拆解规则：无法拆解的单词标注为"基础词"
- 10 种禁止的模板句型（避免例句雷同）
- 两个例句必须来自不同话题领域

### 8.3 OCRService（百度 OCR 服务）

**文件**：`backend/services/ocr_service.py`（375 行）

- 使用百度智能云**通用文字识别高精度版**
- access_token 30 天有效，带缓存，提前 1 小时过期刷新
- 图片压缩：最长边 1280px，JPEG 质量 80
- 月限额：全局 800 次 + 普通用户 50 次（管理员不限）
- 用量持久化到 `data/ocr_usage.json`，每月自动重置
- **关键修复**：base64 图片数据必须用 `data=` 发送（POST body），不能用 `params=`（会追加到 URL 导致 413 错误）

### 8.4 DocImportService（文档导入）

**文件**：`backend/services/doc_import_service.py`（192 行）

- 支持格式：txt / docx / xlsx / pdf
- txt 多编码尝试：utf-8 → gbk → gb2312 → latin-1
- docx 使用 python-docx（提取段落 + 表格）
- xlsx 使用 openpyxl（遍历所有工作表）
- pdf 使用 pdfplumber（逐页提取文本）
- 内置 70+ 噪声词过滤表（the/a/an/and 等无意义词）
- 复合词最多 3 个部分（2 个空格），避免整句被当成单词

---

## 9. 前端设计

前端为纯原生 JS 单页应用（无 React/Vue 等框架），`app.js` 6800+ 行包含全部前端逻辑。

### 9.1 页面结构

| 页面 | ID | 核心功能 |
|------|----|---------|
| 首页 | `page-home` | 今日概览（已学/待复习/待学）+ 操作按钮 + 统计卡片 + 7天曲线图 |
| 录入页 | `page-input` | 4 种录入方式：手动输入 / 批量粘贴 / 文档导入 / 扫描录入 |
| 词库页 | `page-library` | 词本筛选 + 搜索 + 筛选标签 + 排序 + 导出（CSV/TXT/Anki） |
| 学习页 | `page-learn` | 4 种模式：翻卡 / 看词选义 / 看义选词 / 拼写默写 |
| 复习页 | `page-review` | 4 种模式 + 评分（不记得/模糊/记得） |
| 统计页 | `page-stats` | 统计卡片 + 柱状图 + 饼图 + 日历热力图 |
| 设置页 | `page-settings` | 学习计划 / 复习策略 / 账户管理 / 词库管理 |
| 管理员页 | `page-admin` | 用户管理列表（仅 admin 可见） |

### 9.2 Service Worker 缓存策略

| 资源类型 | 策略 | 说明 |
|---------|------|------|
| 核心静态资源 | 网络优先 + 缓存兜底 | install 时预缓存 5 个核心文件 |
| 只读 GET API | 网络优先 + 缓存兜底 | 7 个白名单 API，TTL 5 分钟，`cache: 'no-store'` |
| 写操作 API | 纯网络 | POST/PUT/DELETE 不缓存 |

**缓存版本管理**：
- 当前版本：`CACHE_NAME = 'wordmemo-v59'`，`API_CACHE_NAME = 'wordmemo-api-v58'`
- 每次修改前端代码后，需要同步更新 SW 版本号和 `index.html` 中的 `?v=` 参数
- 用户强制刷新（Ctrl+Shift+R）后加载新版本
- 用户切换时发送 `CLEAR_API_CACHE` 消息清空 API 缓存

### 9.3 前端关键函数

| 函数 | 功能 |
|------|------|
| `WordAPI` 类 | 封装全部 65+ API 调用 |
| `renderHome()` / `refreshHomeStats()` | 首页渲染 / 统计数据刷新 |
| `loadLearnQueue()` / `renderFlipCard()` | 学习队列加载 / 翻卡渲染 |
| `loadReviewQueue()` / `handleReviewRating()` | 复习队列加载 / 艾宾浩斯评分 |
| `drawLineChart()` / `drawBarChart()` / `drawPieChart()` | Canvas 手绘图表（无第三方库） |
| `handleScanRecognize()` | OCR/AI 双模式扫描识别 |
| `handleSaveEdit()` / `handleMultiStatus()` | 单词编辑保存 / 批量状态变更（含 refreshHomeStats） |

### 9.4 Android WebView 壳

- **包名**：`com.wordmemo.app`
- **最低 SDK**：24（Android 7.0）
- **目标 SDK**：34（Android 14）
- **版本**：1.3.0 (versionCode=5)
- **核心文件**：`MainActivity.kt`（WebView 容器）、`SplashActivity.kt`（启动屏）
- **构建**：通过 GitHub Actions（`.github/workflows/build-apk.yml`）自动构建 APK
- **依赖**：androidx.core / androidx.appcompat / androidx.webkit

---

## 10. 配置说明

### 10.1 环境变量

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `AGNES_API_KEY` | 是（AI功能） | Agnes AI API 密钥 |
| `AGNES_BASE_URL` | 否 | AI 接口地址，默认 `https://apihub.agnes-ai.com/v1` |
| `AGNES_MODEL` | 否 | 模型名，默认 `agnes-2.0-flash` |
| `BAIDU_OCR_API_KEY` | 是（OCR） | 百度智能云 API Key |
| `BAIDU_OCR_SECRET_KEY` | 是（OCR） | 百度智能云 Secret Key |
| `DATABASE_URL` | 否 | 数据库连接串，留空则用 SQLite。云端填 Neon PostgreSQL 连接串 |
| `SECRET_KEY` | 否 | 应用密钥，本地可不填，部署时建议随机值 |

### 10.2 Python 依赖

```python
# backend/requirements.txt
Flask==3.0.0               # Web 框架
Flask-SQLAlchemy==3.1.1     # ORM
Flask-CORS==4.0.0          # 跨域支持
requests==2.31.0           # HTTP 请求（AI/OCR/在线查词）
Pillow==10.4.0             # 图片压缩
gunicorn==21.2.0           # WSGI 服务器（部署用）
python-dotenv==1.0.0       # .env 文件加载
psycopg2-binary==2.9.9     # PostgreSQL 驱动
python-docx==1.1.0         # Word 文档解析
openpyxl==3.1.2            # Excel 文件解析
pdfplumber==0.10.3         # PDF 文件解析
```

### 10.3 .env 文件示例

```bash
# backend/.env（被 gitignore，不会提交）
AGNES_API_KEY=你的API密钥
AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_MODEL=agnes-2.0-flash
# BAIDU_OCR_API_KEY=你的百度OCR Key
# BAIDU_OCR_SECRET_KEY=你的百度OCR Secret
# DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/wordmemo?sslmode=require
# SECRET_KEY=随机字符串
```

---

## 11. 部署指南

### 11.1 本地开发

```bash
# 1. 进入后端目录
cd backend

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量（可选，仅 AI/OCR 功能需要）
copy .env.example .env
# 编辑 .env 填入 AGNES_API_KEY 等

# 4. 启动服务
python run.py
# 或: python app.py

# 5. 浏览器访问
# http://localhost:5000
```

**注意**：
- 本地默认使用 SQLite（`instance/wordmemo.db`），无需配置 `DATABASE_URL`
- ECDICT 词典文件（`data/stardict.db`，812MB）需单独下载
- 不要双击 `index.html` 打开（相对路径会失效），必须通过 `http://localhost:5000` 访问

### 11.2 云端部署（Render + Neon）

**架构**：GitHub（存代码）→ Render（跑应用）→ Neon（存数据）+ UptimeRobot（保活）

**Render 免费版限制及对策**：

| 限制 | 影响 | 对策 |
|------|------|------|
| 15分钟无访问休眠 | 首次访问等30-60秒冷启动 | UptimeRobot 每5分钟唤醒 |
| 自带 PostgreSQL 30天删除 | 数据全丢 | 改用 Neon 数据库 |
| 无持久化磁盘 | 重新部署丢本地文件 | 图片识别完即丢弃，不存本地 |

**部署步骤**：

1. **创建 Neon 数据库**：注册 neon.tech → Create Project → 复制 Connection string
2. **推送代码到 GitHub**：创建 wordmemo 仓库 → push 代码
3. **Render 创建 Web Service**：
   - Root Directory: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 app:app`
4. **配置环境变量**：`AGNES_API_KEY`、`DATABASE_URL`（Neon 连接串）、`SECRET_KEY`
5. **配置 UptimeRobot**：每5分钟访问一次 Render 网址，防止休眠
6. **手机安装 PWA**：浏览器打开网址 → 添加到主屏幕

### 11.3 render.yaml 一键部署

```yaml
services:
  - type: web
    name: wordmemo
    runtime: python
    plan: free
    buildCommand: pip install -r backend/requirements.txt && bash backend/download_ecdict.sh
    startCommand: cd backend && gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 app:app
    healthCheckPath: /api/stats
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.9
      - key: AGNES_API_KEY
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: SECRET_KEY
        generateValue: true
```

### 11.4 ECDICT 词典部署

`data/stardict.db`（812MB）太大无法放入 Git 仓库：
1. 压缩为 `ecdict.zip`（约 206MB）
2. 上传到 GitHub Release（tag v1.0）
3. 部署时通过 `download_ecdict.sh` 脚本自动下载解压

```bash
# download_ecdict.sh 核心逻辑
wget -q "https://github.com/用户名/wordmemo/releases/download/v1.0/ecdict.zip"
unzip -q ecdict.zip -d data/
```

### 11.5 Neon 数据库保活

Neon 免费版 5 分钟无活动会休眠，应用启动时自动创建 daemon 线程 `_neon_keepalive`，每 240 秒执行 `SELECT 1` 保持连接活跃。仅在使用远程数据库时启动。

### 11.6 账号信息

| 用户名 | 角色 | 密码 | 说明 |
|--------|------|------|------|
| `testuser` | admin | `123456` | 管理员账号（已重置） |
| `admin` | user | `admin123` | 普通用户 |
| `demo` | user | 未知 | 演示账号 |
| `demo1` | user | `123456` | 演示账号 |

---

## 12. 经验教训与踩坑记录

### 12.1 AI 分析超时问题

- **问题**：最初所有单词分析都调用 AI，导致添加单词时频繁超时、释义缺失
- **解决**：改为三级降级策略，ECDICT 本地词典（2.8ms/词）优先，仅在词典无结果时调用 AI
- **教训**：核心数据查询不应该依赖外部 API，必须有本地兜底方案

### 12.2 复习队列无限增长

- **问题**：原复习逻辑不按 `next_review` 过滤，所有学过的词每天都出现，队列只增不减且后面的词永远复习不到
- **解决**：复习接口 `/api/review/today` 只返回 `next_review <= 当前时间` 的到期单词，按 `next_review` 升序排列
- **教训**：复习算法要遵循艾宾浩斯曲线，未到期的单词不应出现

### 12.3 今日已学时区 bug

- **问题**：`last_review` 存储为 UTC 时间，但统计用本地 `date.today()` 做范围比较，导致 UTC+8 凌晨 0~8 点学习的单词不计入"今日已学"
- **解决**：新增 `get_today_utc_range()` 函数，将本地午夜转换为 UTC 范围后再比较
- **教训**：时间存储和比较必须统一时区基准，UTC 存储则 UTC 比较

### 12.4 统计数据不按用户隔离

- **问题**：统计接口未按 `user_id` 过滤，用户看到其他用户的单词数据
- **解决**：所有查询添加 `user_id` 过滤条件，包括 Word、LearnHistory、Wordbook 等所有涉及用户数据的表
- **教训**：多用户系统必须在每个数据查询中强制用户隔离

### 12.5 OCR base64 数据发送方式错误

- **问题**：百度 OCR 用 `requests.post(params=)` 发送 base64 图片数据，追加到 URL 导致 413 Request Entity Too Large
- **解决**：改为 `data=` 在 POST body 中发送，并增加图片压缩（1280px + JPEG 80%）
- **教训**：大数据必须放在 POST body 中，不能追加到 URL

### 12.6 状态变更统计不同步

- **问题**：将单词改回"未学习"后，"今日已学"数量不减少，因为 LearnHistory 只增不减
- **解决**：`update_learn_history()` 支持负数参数，状态变更时同步增减；前端状态变更后调用 `refreshHomeStats()` 刷新统计
- **教训**：状态变更是双向的，统计逻辑必须支持增减

### 12.7 Service Worker 缓存旧数据

- **问题**：API 响应被 Service Worker 缓存，用户切换后看到旧用户数据，统计不更新
- **解决**：
  - API 请求使用 `cache: 'no-store'` 绕过浏览器缓存
  - 用户切换时发送 `CLEAR_API_CACHE` 消息清空缓存
  - API 响应头设 `Cache-Control: no-store, no-cache, must-revalidate`
- **教训**：PWA 缓存策略要区分只读和写操作，用户切换时必须清缓存

### 12.8 单词拆解释义问题

- **问题**：ECDICT 返回的释义可能是生僻释义，不适合专升本考试
- **解决**：
  - 添加 `MEANING_OVERRIDES` 释义覆盖表，确保短语组件用常用释义
  - AI 提示词增加"释义优先规则"，要求使用最常用释义
  - 手工词典 `DICTIONARY` 存储编辑过的精确拆解数据
- **教训**：词典释义需要根据使用场景优化，不能直接使用原始数据

---

## 13. 常见问题

### Q: 如何添加新的单词拆解数据？

在 `dictionary_service.py` 的 `DICTIONARY` 字典中添加条目，格式参考 `'sports meeting'` 的结构。重启服务后，新单词会优先从手工词典获取拆解数据。

### Q: 如何修改复习间隔？

在 `app.py` 的 `submit_review()` 函数中修改 `strategy_config` 字典。三种策略（relaxed/standard/strict）的间隔数组和 easy 阈值均可调整。

### Q: 如何更新前端代码？

1. 修改 `frontend/` 下的源文件
2. 同步到 `backend/static/`
3. 更新 `sw.js` 中的 `CACHE_NAME` 版本号
4. 更新 `index.html` 中的 `?v=` 参数
5. 用户强制刷新（Ctrl+Shift+R）后生效

### Q: 如何重置用户密码？

- 管理员可在管理员页面重置任意用户密码
- 或直接操作数据库：

```python
import hashlib, os
salt = os.urandom(16).hex()
password_hash = hashlib.sha256(('新密码' + salt).encode()).hexdigest()
# UPDATE users SET salt=?, password_hash=? WHERE username=?
```

### Q: OCR 月限额如何调整？

在 `ocr_service.py` 中修改 `GLOBAL_MONTHLY_LIMIT`（全局）和 `USER_MONTHLY_LIMIT`（单用户）常量。用量记录持久化在 `data/ocr_usage.json`，删除该文件可重置计数。

### Q: 数据库迁移如何工作？

应用启动时自动执行所有迁移函数（`ensure_*_column`、`fix_*_constraint`），用 `inspect` 检查列/索引是否存在，不存在则 `ALTER TABLE ADD COLUMN`。无需手动运行迁移脚本。

### Q: 如何备份单词数据？

- 应用内"词库页"右上角导出按钮支持 CSV/TXT/Anki 格式
- Neon 控制台支持按时间点恢复（PITR）

### Q: Neon 连接失败怎么办？

确认 `DATABASE_URL` 填的是 Neon 连接串（不是 Render 的），末尾 `?sslmode=require` 必须保留。Neon 强制 SSL 连接。

### Q: 如何查看服务日志？

- 本地：终端直接查看输出
- Render：Dashboard → 你的服务 → Logs 标签页
- 500 错误多与环境变量配置有关（`DATABASE_URL`、`AGNES_API_KEY`）

---

## 14. 后续开发备忘

### 可扩展方向

1. **词频排序**：按专升本真题词频排序学习队列
2. **语音朗读**：集成 TTS 朗读单词和例句
3. **错题本**：独立错题集合，针对性复习
4. **学习小组**：多人共享词本、排行榜
5. **暗色主题**：夜间模式适配
6. **iOS 原生壳**：Swift WebView 封装

### 维护注意事项

- 修改前端代码后必须同步 `frontend/` → `backend/static/`
- 修改 API 后检查 Service Worker 的 `CACHEABLE_API` 白名单是否需要更新
- 添加新数据库字段后必须编写对应的 `ensure_*_column()` 迁移函数
- ECDICT 词典更新后需重新上传到 GitHub Release
- 百度 OCR 免费额度每月 1000 次，应用内限制 800 次留余量

### 关键文件快速索引

| 需求 | 文件 | 关键函数/位置 |
|------|------|-------------|
| 添加 API 路由 | `backend/app.py` | `@app.route()` |
| 修改复习算法 | `backend/app.py` | `submit_review()` |
| 修改统计逻辑 | `backend/app.py` | `/api/stats` 路由 |
| 添加词典条目 | `backend/services/dictionary_service.py` | `DICTIONARY` 字典 |
| 修改 AI 提示词 | `backend/services/ai_service.py` | `system_prompt` |
| 修改 OCR 限额 | `backend/services/ocr_service.py` | `GLOBAL_MONTHLY_LIMIT` |
| 修改前端页面 | `frontend/index.html` + `frontend/assets/app.js` | 对应 `page-*` 区块 |
| 修改缓存策略 | `frontend/sw.js` | `CACHE_NAME` / `CACHEABLE_API` |
| 修改数据库模型 | `backend/models.py` | 对应 Model 类 |
| 修改配置 | `backend/config.py` + `backend/.env` | `Config` 类 |
| Android 配置 | `android/app/build.gradle` | `versionCode` / `versionName` |
| 部署配置 | `render.yaml` + `DEPLOY.md` | 环境变量 / 启动命令 |

---

> **文档维护**：本文档随项目开发持续更新，修改代码后请同步更新对应章节。
> 如需查看可视化版本的技术文档，请打开 `wordmemo-doc/wordmemo-doc.html`。
