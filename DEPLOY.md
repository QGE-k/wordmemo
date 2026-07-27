# WordMemo 部署指南

把背单词应用部署到 Render + Neon，部署后无需开电脑，手机/电脑浏览器打开网址就能用，手机还能"添加到桌面"当 App 用。

---

## 整体架构

```
GitHub (存代码)  ──→  Render Web Service (跑后端Flask + 托管前端, 免费)
                         │
                         └──→ Neon PostgreSQL (存单词数据, 永久免费不删除)

UptimeRobot (每5分钟访问一次网址) ──→ 防止 Render 服务休眠
```

**为什么数据库单独用 Neon 而不是 Render 自带的？**
Render 免费 PostgreSQL **30天后会被强制删除**，数据全丢。Neon 免费 PostgreSQL **永久免费、不删除、不休眠**，0.5GB 存储对背单词应用够用很久（能存上百万个单词）。所以把数据库拆到 Neon，彻底避开 Render 的 30 天限制。

---

## Render 免费版三大坑及对策（必读）

| 坑 | 影响 | 对策 | 是否解决 |
|----|------|------|---------|
| 15分钟无访问休眠 | 首次访问等30-60秒冷启动 | UptimeRobot 每5分钟唤醒 | ✅ 解决 |
| 自带 PostgreSQL 30天删除 | 单词数据全丢 | **改用 Neon 数据库** | ✅ 解决 |
| 无持久化磁盘，重新部署丢本地文件 | 上传的图片丢失 | 本应用图片识别完即丢弃，不存本地 | ✅ 不受影响 |

---

## 第一步：注册账号

需要三个账号：

1. **GitHub**（存代码）：https://github.com → Sign up
2. **Render**（跑应用）：https://render.com → 用 GitHub 登录
3. **Neon**（存数据）：https://neon.tech → 用 GitHub 登录（推荐）

---

## 第二步：创建 Neon 数据库（先做这个！）

1. 登录 Neon → 点 `Create New Project`
2. 填写：
   - **Project name**：`wordmemo`
   - **Postgres version**：选最新的（默认即可）
   - **Region**：选 `AWS Asia Pacific (Singapore)` 或离你近的
3. 点 `Create project`
4. 创建完成后，页面会显示连接串，找到 **`Connection string`**，格式类似：
   ```
   postgresql://user:password@ep-xxx.ap-southeast-1.aws.neon.tech/wordmemo?sslmode=require
   ```
5. **复制这个连接串备用**（这就是待会要填到 Render 的 `DATABASE_URL`）

> Neon 免费版：0.5GB 存储、永久免费、不删除数据、不休眠。对你这个应用绰绰有余。
> ⚠️ 注意连接串里有 `?sslmode=require`，要保留，Neon 强制 SSL 连接。

---

## 第三步：把代码推送到 GitHub

### 方式 A：用 GitHub Desktop（推荐新手）

1. 下载安装 GitHub Desktop：https://desktop.github.com/
2. 登录你的 GitHub 账号
3. 点 `File` → `New Repository` → 名字填 `wordmemo` → Local path 选 `wordmemo` 文件夹的**父目录** → Create
4. GitHub Desktop 左侧列出所有改动文件，底部 summary 填 `初始化项目` → 点 `Commit to main`
5. 点 `Publish repository` → 取消勾选 `Keep this code private`（或保留私有）→ Publish

### 方式 B：用命令行（熟悉 Git 用）

在 `wordmemo` 文件夹内打开终端：
```bash
git init
git add .
git commit -m "初始化项目"
git branch -M main
git remote add origin https://github.com/你的用户名/wordmemo.git
git push -u origin main
```
> 先在 GitHub 网站创建一个名为 `wordmemo` 的空仓库（不要勾选 README）。

---

## 第四步：在 Render 创建 Web Service

1. Render 顶部菜单点 `New` → `Web Service`
2. 连接 GitHub 仓库：
   - 点 `Build and deploy from a Git repository` → Next
   - 找到并选中 `wordmemo` 仓库（看不到就点 `Configure account` 授权）
3. 填写服务配置：
   - **Name**：`wordmemo`（会变成网址的一部分）
   - **Region**：和 Neon 选同一区域（如 Singapore）
   - **Root Directory**：`backend` ⚠️ **必须填这个！**（后端代码在 backend 子目录）
   - **Runtime**：`Python 3`
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 app:app`
   - **Instance Type**：`Free`
4. 先别急着创建，往下滚动配置环境变量（见第五步）

> ⚠️ 注意：**不要**在 Render 创建 PostgreSQL 数据库！数据库已经用 Neon 了。

---

## 第五步：配置环境变量（关键！）

在创建 Web Service 的页面，找到 `Environment Variables` 区域，添加：

| Key | Value | 说明 |
|-----|-------|------|
| `AGNES_API_KEY` | 你的 Agnes AI API Key | AI 单词分析/识别，必填 |
| `AGNES_BASE_URL` | `https://apihub.agnes-ai.com/v1` | AI 接口地址，默认已对 |
| `AGNES_MODEL` | `agnes-2.0-flash` | 文本模型，默认已对 |
| `DATABASE_URL` | 粘贴第二步复制的 **Neon 连接串** | 连接 Neon 数据库，必填 |
| `SECRET_KEY` | 随便填一串字符，如 `wordmemo-2024-secret-xyz` | 应用密钥 |

> ⚠️ `DATABASE_URL` 必须填 Neon 的连接串，**不要**填 Render 的。连接串末尾的 `?sslmode=require` 要保留。

填完环境变量后，点页面最底部的 `Create Web Service`。

---

## 第六步：等待部署完成并验证

1. 创建后自动开始部署，页面显示构建日志（Build logs）
2. 等待 2-5 分钟，看到 `Your service is live` 表示成功
3. 页面顶部显示你的网址，类似 `https://wordmemo-xxxx.onrender.com`
4. 点开网址，能看到背单词首页就成功了
5. 第一次打开可能慢（30-50秒冷启动），属正常现象
6. **验证数据库连接**：在应用里手动添加一个单词，刷新页面还在，说明 Neon 数据库连通了

---

## 第七步：配置定时唤醒（解决冷启动）

Render 免费版 15 分钟无访问会休眠。用 UptimeRobot 每 5 分钟访问一次保持唤醒：

1. 打开 https://uptimerobot.com → 注册账号（免费）
2. 点 `Add New Monitor`
3. 填写：
   - **Monitor Type**：`HTTP(s)`
   - **Friendly Name**：`wordmemo`
   - **URL**：你的 Render 网址（如 `https://wordmemo-xxxx.onrender.com`）
   - **Monitoring Interval**：`5 minutes`
4. 点 `Create Monitor`

配置后服务一直保持唤醒，访问速度正常。

---

## 第八步：手机安装为 App（PWA）

部署成功后，手机浏览器打开网址，可以"添加到桌面"当原生 App 用：

### 安卓（Chrome 浏览器）
1. 用 Chrome 打开你的网址
2. 点右上角三个点 → `添加到主屏幕` → 确定
3. 桌面出现"背单词"图标，点开即全屏 App 体验

### 苹果（Safari 浏览器）
1. 用 Safari 打开你的网址
2. 点底部分享按钮（向上箭头）→ `添加到主屏幕` → 确定
3. 桌面出现图标，点开即用

> 苹果必须用 Safari，Chrome 不行（苹果限制）。

---

## 数据备份建议

虽然 Neon 不会删数据，但建议定期备份以防万一：

1. 用应用的"导出"功能（词库页右上角导出按钮），导出 CSV/TXT/Anki 格式
2. 重要节点（如学完一本词书）导出一次存本地
3. Neon 控制台也支持按时间点恢复（PITR），免费版可回溯到历史某时刻

---

## 本地开发说明

部署后，本地开发方式略有变化（API 改成了相对路径）：

### 启动后端
```bash
cd backend
python run.py
```

### 访问前端
**不要**双击 `index.html` 打开（相对路径会失效）。改为浏览器访问：
```
http://localhost:5000/
```
后端现在同时托管前端文件，一个服务搞定。

### 本地环境变量（可选）
本地要用 AI 功能，在 `backend` 目录创建 `.env` 文件（已被 gitignore，不会提交）：
```
AGNES_API_KEY=你的key
```
本地数据库默认用 SQLite（`wordmemo.db`），无需配 `DATABASE_URL`。

---

## 常见问题

### Q: 部署后访问报 500 错误？
A: 检查 Render 的 Logs 标签页，多半是环境变量没配对，特别是 `DATABASE_URL`（Neon 连接串）和 `AGNES_API_KEY`。

### Q: 数据库连接失败？
A: 确认 `DATABASE_URL` 填的是 Neon 的连接串（不是 Render 的），且末尾 `?sslmode=require` 保留。Neon 强制 SSL。

### Q: AI 识别/分析功能不工作？
A: 检查 `AGNES_API_KEY` 环境变量是否填了正确的值。

### Q: 网址打开很慢（30秒以上）？
A: Render 免费版冷启动。按第七步配 UptimeRobot 定时唤醒即可。

### Q: 数据会被删除吗？
A: **不会**。数据存在 Neon，Neon 免费版永久免费、不删除数据。Render 服务就算删了重建，数据都在 Neon 上。

### Q: Neon 免费版 0.5GB 够用吗？
A: 绰绰有余。一个单词算 500 字节，0.5GB 能存 100 万个单词。普通人一辈子也背不了这么多。

### Q: 想彻底避免冷启动？
A: Render 升级到 Starter（$7/月）永不休眠。或改用腾讯云轻量服务器（38元/年起，国内访问快、无休眠，但要自己运维）。
