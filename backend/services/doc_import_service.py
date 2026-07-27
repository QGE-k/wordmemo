"""
文档导入解析服务
支持 txt / docx / xlsx / pdf 格式，提取单词并过滤非单词内容
"""
import re
import io

# 单词正则：允许字母、连字符、空格（复合词如 "sports meeting"）
# 不允许纯数字、特殊符号、中文
WORD_PATTERN = re.compile(
    r'^[a-zA-Z][a-zA-Z\-]*'           # 第一个字符必须是字母
    r'(?:\s[a-zA-Z][a-zA-Z\-]*)*'      # 后续可以是空格+字母（复合词）
    r'$'
)

# 用来从任意文本中抽取候选 token
TOKEN_PATTERN = re.compile(r'[a-zA-Z][a-zA-Z\- ]{0,39}[a-zA-Z]')

# 常见无意义词/误识别噪声
NOISE_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'on', 'at',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'do', 'does', 'did', 'will', 'would', 'can', 'could', 'should', 'may',
    'might', 'must', 'this', 'that', 'these', 'those', 'it', 'its', 'as',
    'for', 'with', 'by', 'from', 'about', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off',
    'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
    'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
    'so', 'than', 'too', 'very', 'just', 'also', 'page', 'chapter',
    'http', 'https', 'www', 'com', 'org', 'net', 'email', 'tel',
}


def is_valid_word(text):
    """
    判断是否为有效英文单词
    - 长度 1-40
    - 字母开头
    - 允许连字符和空格（复合词）
    - 过滤噪声词
    - 复合词最多 3 个部分（2 个空格），避免整句被当成单词
    """
    if not text:
        return False
    text = text.strip()
    if len(text) < 1 or len(text) > 40:
        return False
    if not WORD_PATTERN.match(text):
        return False
    # 复合词空格数不能超过 2（最多 3 个部分），避免整句被当成单词
    if text.count(' ') > 2:
        return False
    # 全小写后检查噪声词（整体）
    if text.lower() in NOISE_WORDS:
        return False
    # 复合词的每个部分都不能是噪声词
    parts = text.split()
    for part in parts:
        if part.lower() in NOISE_WORDS:
            return False
    # 至少包含一个元音（避免类似 "bcdfg" 这种无意义字母组合）
    if not re.search(r'[aeiouAEIOU]', text):
        # 但允许少数无元音的合法词（如 my, by, fly, cry, rhythm）
        allowed_no_vowel = {'my', 'by', 'fly', 'cry', 'dry', 'gym', 'rhythm',
                            'why', 'shy', 'sky', 'sly', 'try', 'pty', 'nth'}
        if text.lower() not in allowed_no_vowel:
            return False
    return True


def extract_words_from_text(text):
    """
    从任意文本中提取候选单词列表
    返回去重后的有序列表（保持出现顺序）
    """
    if not text:
        return []
    # 用非字母字符分割出候选 token（保留内部空格和连字符）
    # 先按换行/制表符/中文字符/标点（除空格和连字符外）分割
    raw_tokens = re.split(r'[\n\r\t,;:。，；：、！？!?"\'\(\)\[\]\{\}<>【】《》·…—\*#+/\\|]+', text)
    seen = set()
    result = []
    for token in raw_tokens:
        token = token.strip()
        if not token:
            continue
        # 复合词：可能包含空格，如 "sports meeting"
        # 也可能整段是 "apple n.苹果"，需要拆出 "apple"
        # 先按空格分割，取第一个英文部分
        parts = token.split()
        # 尝试整体作为单词
        if is_valid_word(token):
            key = token.lower()
            if key not in seen:
                seen.add(key)
                result.append(token)
            continue
        # 整体不合法，尝试每个部分
        for part in parts:
            # 去除尾部标点
            part = re.sub(r'[^a-zA-Z\- ]+$', '', part)
            part = re.sub(r'^[^a-zA-Z\- ]+', '', part)
            if is_valid_word(part):
                key = part.lower()
                if key not in seen:
                    seen.add(key)
                    result.append(part)
    return result


def parse_txt(file_bytes):
    """解析 txt 文件（尝试多种编码）"""
    for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_bytes.decode('utf-8', errors='ignore')


def parse_docx(file_bytes):
    """解析 Word docx 文件"""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs]
    # 表格中的文字
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.append(cell.text)
    return '\n'.join(paragraphs)


def parse_xlsx(file_bytes):
    """解析 Excel xlsx 文件"""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    texts = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    texts.append(str(cell))
    wb.close()
    return '\n'.join(texts)


def parse_pdf(file_bytes):
    """解析 PDF 文件"""
    import pdfplumber
    texts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ''
            texts.append(page_text)
    return '\n'.join(texts)


def parse_document(file_bytes, filename):
    """
    根据文件扩展名解析文档，返回提取的单词列表
    返回: (words_list, raw_text)
    """
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if ext == 'txt':
        text = parse_txt(file_bytes)
    elif ext == 'docx':
        text = parse_docx(file_bytes)
    elif ext in ('xlsx', 'xls'):
        text = parse_xlsx(file_bytes)
    elif ext == 'pdf':
        text = parse_pdf(file_bytes)
    else:
        raise ValueError(f'不支持的文件格式：{ext}（支持 txt/docx/xlsx/pdf）')

    words = extract_words_from_text(text)
    return words, text


def parse_document_preview(file_bytes, filename, max_raw=500):
    """
    解析文档并返回预览信息（不导入，仅展示）
    返回: {words, total, filtered, raw_preview}
    """
    words, raw_text = parse_document(file_bytes, filename)
    return {
        'words': words,
        'total': len(words),
        'raw_preview': raw_text[:max_raw] if raw_text else '',
        'raw_length': len(raw_text) if raw_text else 0,
    }
