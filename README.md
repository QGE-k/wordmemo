# 词记 WordMemo - 智能单词记忆系统

## 项目简介
一个智能英语单词记忆应用，支持扫描单词书、AI拆解复合词和词根词缀、艾宾浩斯间隔复习。

## 技术栈
- **后端**：Python + Flask + SQLAlchemy + SQLite
- **前端**：HTML + CSS + JavaScript（移动端优先单页应用）
- **OCR**：百度智能云通用文字识别（高精度版）
- **AI**：Agnes AI（兼容OpenAI接口，用于单词拆解分析）

## 项目结构
```
wordmemo/
├── backend/              # 后端
│   ├── services/         # 服务层
│   │   ├── ocr_service.py       # 百度OCR服务
│   │   ├── ai_service.py        # Agnes AI单词分析服务
│   │   └── dictionary_service.py # 本地词典（AI降级方案）
│   ├── app.py            # Flask主应用
│   ├── models.py         # 数据库模型
│   ├── config.py         # 配置文件
│   ├── requirements.txt  # Python依赖
│   └── run.py            # 启动脚本
└── frontend/             # 前端
    ├── index.html        # 主页面
    └── assets/
        ├── style.css     # 样式表
        └── app.js        # 主逻辑
```

## 快速开始

### 1. 安装后端依赖
```bash
cd wordmemo/backend
pip install -r requirements.txt
```

### 2. 配置API密钥（可选）
不配置也能用，AI分析会降级到本地词典，OCR功能不可用。

#### 方式一：环境变量（推荐）
```powershell
# Windows PowerShell
$env:BAIDU_OCR_API_KEY = "你的百度OCR API Key"
$env:BAIDU_OCR_SECRET_KEY = "你的百度OCR Secret Key"
$env:AGNES_API_KEY = "你的Agnes AI API Key"
$env:AGNES_MODEL = "claude-sonnet-4-5"  # 或其他模型
```

#### 方式二：直接修改config.py
编辑 `backend/config.py`，填入你的API Key。

### 3. 启动后端
```bash
python run.py
```
后端运行在 http://localhost:5000，首次启动会自动创建SQLite数据库并插入20个演示单词。

### 4. 打开前端
直接用浏览器打开 `frontend/index.html`，或用本地静态服务器：
```bash
cd frontend
python -m http.server 8080
```
然后访问 http://localhost:8080

## API密钥获取方式

### 百度OCR（通用文字识别高精度版）
1. 访问 https://console.bce.baidu.com/ai/
2. 创建"文字识别"应用
3. 获取 API Key 和 Secret Key
4. 高精度版每天免费500次，足够个人使用

### Agnes AI
1. 访问 https://agnes-ai.com
2. 注册账号
3. 在控制台获取 API Key
4. 全模态API无限期免费

## 功能模块
1. **首页** - 今日学习概览、统计卡片、学习曲线
2. **单词录入** - 手动输入/批量粘贴/扫描识别
3. **词库** - 搜索、筛选、单词详情
4. **背单词** - 翻卡学习，AI拆解显示
5. **复习** - 艾宾浩斯间隔复习，4档评级
6. **统计** - 学习数据可视化

## 核心特性
- 扫描单词书，自动识别英文单词
- AI拆解复合词（sports meeting → sports + meeting）
- AI分析词根词缀（meeting → meet + -ing）
- 艾宾浩斯间隔复习算法
- 移动端优先设计
- 本地词典降级方案（无API Key也能用）
