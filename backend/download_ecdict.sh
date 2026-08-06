#!/bin/bash
# 部署时下载 ECDICT 词典数据库（stardict.db）
# 词典文件 206MB，超出 GitHub 文件大小限制，不能随代码提交
# 部署时从 GitHub Release 下载
# 优化：增加重试机制、下载校验、清理临时文件

set -e

# 使用绝对路径，避免 cd 后相对路径解析错误导致误报
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
DB_PATH="$DATA_DIR/stardict.db"
ZIP_PATH="$DATA_DIR/ecdict.zip"

# 如果已存在则跳过
if [ -f "$DB_PATH" ]; then
    echo "[ecdict] 词典数据库已存在，跳过下载"
    exit 0
fi

mkdir -p "$DATA_DIR"

# 从 GitHub Release 下载 ecdict.zip
# Release URL 格式: https://github.com/QGE-k/wordmemo/releases/download/v1.0/ecdict.zip
# 可通过环境变量 ECDICT_DOWNLOAD_URL 覆盖默认地址
ECDICT_URL="${ECDICT_DOWNLOAD_URL:-https://github.com/QGE-k/wordmemo/releases/download/v1.0/ecdict.zip}"

echo "[ecdict] 正在从 $ECDICT_URL 下载词典数据库..."

# 下载（支持重定向，失败自动重试3次）
MAX_RETRIES=3
for i in 1 2 3; do
    echo "[ecdict] 下载尝试 $i/$MAX_RETRIES ..."
    if curl -L --retry 3 --retry-delay 5 -o "$ZIP_PATH" "$ECDICT_URL"; then
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "[ecdict] 下载失败，词典功能将不可用（可回退到 AI 查询）"
        exit 1
    fi
    sleep 5
done

# 校验下载文件大小（应大于 100MB，避免下载到错误页面）
if [ -f "$ZIP_PATH" ]; then
    SIZE=$(stat -c%s "$ZIP_PATH" 2>/dev/null || wc -c < "$ZIP_PATH")
    if [ "$SIZE" -lt 100000000 ]; then
        echo "[ecdict] 警告: 下载文件大小异常 ($SIZE 字节)，可能下载到了错误页面"
        rm -f "$ZIP_PATH"
        exit 1
    fi
    echo "[ecdict] 下载完成: $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"
fi

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