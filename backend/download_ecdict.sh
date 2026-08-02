#!/bin/bash
# 部署时下载 ECDICT 词典数据库（stardict.db）
# 词典文件 206MB，超出 GitHub 文件大小限制，不能随代码提交
# 部署时从 GitHub Release 下载

set -e

DATA_DIR="$(dirname "$0")/data"
DB_PATH="$DATA_DIR/stardict.db"

# 如果已存在则跳过
if [ -f "$DB_PATH" ]; then
    echo "[ecdict] 词典数据库已存在，跳过下载"
    exit 0
fi

mkdir -p "$DATA_DIR"

# 从 GitHub Release 下载 ecdict.zip
# Release URL 格式: https://github.com/QGE-k/wordmemo/releases/download/v1.0/ecdict.zip
ECDICT_URL="${ECDICT_DOWNLOAD_URL:-https://github.com/QGE-k/wordmemo/releases/download/v1.0/ecdict.zip}"

echo "[ecdict] 正在从 $ECDICT_URL 下载词典数据库..."

# 下载（支持重定向）
curl -L -o "$DATA_DIR/ecdict.zip" "$ECDICT_URL"

# 解压
echo "[ecdict] 正在解压..."
cd "$DATA_DIR"
unzip -o ecdict.zip
rm -f ecdict.zip

# 验证
if [ -f "$DB_PATH" ]; then
    SIZE=$(du -h "$DB_PATH" | cut -f1)
    echo "[ecdict] 词典数据库下载完成: $DB_PATH ($SIZE)"
else
    echo "[ecdict] 警告: 下载后未找到 stardict.db，词典功能将不可用"
    echo "[ecdict] 应用仍可正常运行，但单词释义将回退到 AI 查询"
fi
