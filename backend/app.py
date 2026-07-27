"""
WordMemo 背单词应用 - Flask主应用
提供单词管理、OCR识别、AI分析、复习算法等API接口
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config
from models import db, Word, LearnHistory, Setting, Wordbook
from services.ocr_service import OCRService
from services.ai_service import AIService
from services.dictionary_service import DictionaryService
from services.doc_import_service import parse_document, parse_document_preview

# 创建Flask应用
app = Flask(__name__)
# 加载配置
app.config.from_object(Config)

# 启用CORS，允许前端跨域访问
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 初始化数据库
db.init_app(app)

# 初始化服务实例
ocr_service = OCRService()
ai_service = AIService()
dictionary_service = DictionaryService()


# ==================== 工具函数 ====================

def allowed_file(filename):
    """检查上传的文件是否为允许的扩展名"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def analyze_word_with_fallback(word):
    """
    分析单词：优先使用AI，AI不可用时降级到本地词典，再降级到规则分析

    参数:
        word: 要分析的单词

    返回:
        dict: 分析结果，包含 phonetic, meaning, type, split, morph, examples
    """
    # 优先尝试AI服务
    if ai_service.is_available():
        try:
            result = ai_service.analyze_word(word)
            return result, 'ai'
        except Exception as e:
            print(f"[警告] AI分析失败，降级到本地词典: {e}")

    # 尝试本地词典查询
    result = dictionary_service.lookup(word)
    if result:
        return result, 'dictionary'

    # 最后使用规则分析
    result = dictionary_service.analyze_with_rules(word)
    return result, 'rules'


def init_demo_data():
    """初始化演示数据：在数据库为空时插入预置单词"""
    if Word.query.count() == 0:
        print("[初始化] 数据库为空，正在插入演示单词数据...")
        demo_words = dictionary_service.get_demo_words()
        for word_data in demo_words:
            word = Word(
                word=word_data['word'],
                phonetic=word_data['phonetic'],
                meaning=word_data['meaning'],
                word_type=word_data['word_type'],
                split_data=word_data['split_data'],
                morph_data=word_data['morph_data'],
                examples=word_data['examples'],
                status='new',
            )
            db.session.add(word)
        db.session.commit()
        print(f"[初始化] 已插入 {len(demo_words)} 个演示单词")


def upgrade_split_data():
    """
    数据迁移：升级已存在单词的拆解数据和记忆方法到新结构
    - split_data 补全 original/original_meaning/transform 字段，派生词也填 split
    - 新增 mnemonic（记忆方法）字段
    对本地词典中已有的单词，用新词典数据覆盖更新。
    """
    upgraded = 0
    for word in Word.query.all():
        dict_data = dictionary_service.lookup(word.word)
        if not dict_data:
            continue
        # 检查是否需要升级
        need_upgrade = False
        if not word.split_data:
            need_upgrade = True
        elif isinstance(word.split_data, list) and word.split_data:
            first = word.split_data[0]
            if isinstance(first, dict) and 'original' not in first:
                need_upgrade = True
            # 派生词旧数据 split 为空，新数据应该有内容
            elif not word.split_data and dict_data.get('split'):
                need_upgrade = True
        # mnemonic 为空也需要升级
        if not word.mnemonic and dict_data.get('mnemonic'):
            need_upgrade = True
        # tenses 为空且词典有时态数据也需要升级
        if not word.tenses and dict_data.get('tenses'):
            need_upgrade = True

        if need_upgrade:
            word.split_data = dict_data.get('split', [])
            word.morph_data = dict_data.get('morph', word.morph_data or [])
            if dict_data.get('mnemonic'):
                word.mnemonic = dict_data['mnemonic']
            if dict_data.get('tenses'):
                word.tenses = dict_data['tenses']
            upgraded += 1

    if upgraded > 0:
        db.session.commit()
        print(f"[迁移] 已升级 {upgraded} 个单词的拆解数据和记忆方法")


def fix_empty_meanings():
    """
    数据迁移：修复 meaning 为空的单词
    对这些单词重新分析，补充 meaning/phonetic/mnemonic/tenses 等空字段
    优先用 AI 分析，AI 不可用时降级到字典/规则分析（至少给出兜底释义）
    """
    fixed = 0
    # 查找 meaning 为空的单词
    empty_words = Word.query.filter(
        db.or_(Word.meaning.is_(None), Word.meaning == '')
    ).all()

    for word in empty_words:
        try:
            analysis, source = analyze_word_with_fallback(word.word)
            updated = False
            # 只补充空字段，不覆盖已有数据
            new_meaning = analysis.get('meaning', '')
            if new_meaning and (not word.meaning or word.meaning.strip() == ''):
                word.meaning = new_meaning
                updated = True
            if not word.phonetic and analysis.get('phonetic'):
                word.phonetic = analysis['phonetic']
                updated = True
            if not word.mnemonic and analysis.get('mnemonic'):
                word.mnemonic = analysis['mnemonic']
                updated = True
            if not word.tenses and analysis.get('tenses'):
                word.tenses = analysis['tenses']
                updated = True
            if not word.split_data and analysis.get('split'):
                word.split_data = analysis['split']
                updated = True
            if updated:
                fixed += 1
        except Exception as e:
            print(f"[迁移] 修复 '{word.word}' 失败: {e}")

    if fixed > 0:
        db.session.commit()
        print(f"[迁移] 已修复 {fixed} 个空释义单词")


def update_learn_history(count=1):
    """更新今日学习历史记录"""
    today = date.today()
    history = LearnHistory.query.filter_by(date=today).first()
    if history:
        history.count += count
    else:
        history = LearnHistory(date=today, count=count)
        db.session.add(history)
    db.session.commit()


# ==================== 单词管理API ====================

@app.route('/api/words', methods=['GET'])
def get_words():
    """
    获取所有单词
    支持查询参数过滤：
    - status: 按状态过滤（new/review/mastered）
    - search: 按单词或释义搜索
    - wordbook_id: 按单词本过滤（传 0 或不传=全部，传具体 id=该单词本）
    """
    # 获取查询参数
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    wordbook_id = request.args.get('wordbook_id', '').strip()

    # 构建查询
    query = Word.query
    if status:
        query = query.filter(Word.status == status)
    if search:
        query = query.filter(
            db.or_(
                Word.word.contains(search),
                Word.meaning.contains(search),
            )
        )
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter(Word.wordbook_id == int(wordbook_id))
        except ValueError:
            pass

    # 按添加时间倒序排列
    words = query.order_by(Word.added_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in words],
        'total': len(words),
    })


@app.route('/api/words', methods=['POST'])
def add_word():
    """
    添加单个单词
    请求体JSON: {"word": "单词文本"}
    自动调用AI或本地词典进行分析
    """
    data = request.get_json()
    if not data or not data.get('word'):
        return jsonify({'success': False, 'error': '请提供单词'}), 400

    word_text = data['word'].strip().lower()
    if not word_text:
        return jsonify({'success': False, 'error': '单词不能为空'}), 400

    # 检查单词是否已存在
    existing = Word.query.filter_by(word=word_text).first()
    if existing:
        return jsonify({'success': False, 'error': '该单词已存在', 'data': existing.to_dict()}), 409

    # 分析单词（AI优先，降级到词典和规则）
    analysis, source = analyze_word_with_fallback(word_text)

    # 创建单词记录
    word = Word(
        word=word_text,
        phonetic=analysis.get('phonetic', ''),
        meaning=analysis.get('meaning', ''),
        word_type=analysis.get('type', '基础词'),
        split_data=analysis.get('split', []),
        morph_data=analysis.get('morph', []),
        mnemonic=analysis.get('mnemonic', ''),
        examples=analysis.get('examples', []),
        tenses=analysis.get('tenses'),
        status='new',
    )
    db.session.add(word)
    db.session.commit()

    # 更新今日学习历史
    update_learn_history(1)

    return jsonify({
        'success': True,
        'data': word.to_dict(),
        'source': source,  # 告知前端分析来源：ai/dictionary/rules
    }), 201


@app.route('/api/words/batch', methods=['POST'])
def batch_add_words():
    """
    批量添加单词（并发优化版）
    请求体JSON: {"words": ["word1", "word2", ...]}

    优化点：
    1. 先过滤已存在单词，避免无效 AI 调用
    2. 本地词典有的词直接用，不调 AI
    3. 用线程池并发调用 AI 分析，最多 5 个并发
    4. 最后统一写入数据库
    """
    data = request.get_json()
    if not data or not data.get('words'):
        return jsonify({'success': False, 'error': '请提供单词列表'}), 400

    words_list = data['words']
    if not isinstance(words_list, list):
        return jsonify({'success': False, 'error': 'words必须是数组'}), 400

    # 可选：单词本 ID
    wordbook_id = data.get('wordbook_id')
    if wordbook_id is not None:
        book = Wordbook.query.get(wordbook_id)
        if not book:
            return jsonify({'success': False, 'error': '指定的单词本不存在'}), 400

    added = []
    skipped = []
    failed = []

    # 第一步：过滤已存在的单词，收集待分析的单词
    pending = []  # [(word_text, analysis_or_None)]
    for raw_word in words_list:
        word_text = str(raw_word).strip().lower()
        if not word_text:
            continue
        existing = Word.query.filter_by(word=word_text).first()
        if existing:
            skipped.append(word_text)
            continue
        # 先查本地词典（毫秒级，不耗时间）
        dict_result = dictionary_service.lookup(word_text)
        if dict_result:
            pending.append((word_text, dict_result))
        else:
            pending.append((word_text, None))

    # 第二步：对本地词典没有的词，用线程池并发调 AI
    ai_pending = [(w, None) for w, a in pending if a is None]
    if ai_pending:
        def _analyze(word_text):
            try:
                return word_text, analyze_word_with_fallback(word_text)
            except Exception as e:
                return word_text, e

        # 最多 5 个并发线程
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_analyze, [w for w, _ in ai_pending]))

        # 把 AI 结果合并回 pending
        ai_map = {}
        for word_text, result in results:
            ai_map[word_text] = result
        new_pending = []
        for word_text, _ in pending:
            if word_text in ai_map:
                new_pending.append((word_text, ai_map[word_text]))
            else:
                # 本地词典命中的，保持原样
                for w, a in pending:
                    if w == word_text and a is not None:
                        new_pending.append((word_text, a))
                        break
        pending = new_pending

    # 第三步：统一写入数据库
    for word_text, analysis_or_error in pending:
        if isinstance(analysis_or_error, Exception):
            failed.append({'word': word_text, 'error': str(analysis_or_error)})
            continue
        if not analysis_or_error:
            failed.append({'word': word_text, 'error': '分析失败'})
            continue
        analysis = analysis_or_error[0] if isinstance(analysis_or_error, tuple) else analysis_or_error
        try:
            word = Word(
                word=word_text,
                phonetic=analysis.get('phonetic', ''),
                meaning=analysis.get('meaning', ''),
                word_type=analysis.get('type', '基础词'),
                split_data=analysis.get('split', []),
                morph_data=analysis.get('morph', []),
                mnemonic=analysis.get('mnemonic', ''),
                examples=analysis.get('examples', []),
                tenses=analysis.get('tenses'),
                status='new',
                wordbook_id=wordbook_id,
            )
            db.session.add(word)
            added.append(word_text)
        except Exception as e:
            failed.append({'word': word_text, 'error': str(e)})

    db.session.commit()
    if added:
        update_learn_history(len(added))

    return jsonify({
        'success': True,
        'added': added,
        'skipped': skipped,
        'failed': failed,
        'added_count': len(added),
        'skipped_count': len(skipped),
        'failed_count': len(failed),
    }), 201


@app.route('/api/words/<int:word_id>', methods=['GET'])
def get_word(word_id):
    """获取单个单词详情"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    return jsonify({'success': True, 'data': word.to_dict()})


@app.route('/api/words/<int:word_id>', methods=['PUT'])
def update_word(word_id):
    """
    更新单词信息
    可更新字段：word, phonetic, meaning, status, split_data, morph_data, examples
    """
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无更新数据'}), 400

    # 更新允许修改的字段
    updatable_fields = ['word', 'phonetic', 'meaning', 'status',
                        'split_data', 'morph_data', 'examples', 'word_type']
    for field in updatable_fields:
        if field in data:
            setattr(word, field, data[field])

    db.session.commit()
    return jsonify({'success': True, 'data': word.to_dict()})


@app.route('/api/words/<int:word_id>', methods=['DELETE'])
def delete_word(word_id):
    """删除单词"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404

    db.session.delete(word)
    db.session.commit()
    return jsonify({'success': True, 'message': '单词已删除'})


# ==================== 文档导入API ====================

ALLOWED_DOC_EXT = {'txt', 'docx', 'xlsx', 'xls', 'pdf'}
MAX_DOC_SIZE = 20 * 1024 * 1024  # 20MB


# ==================== 单词本API ====================

@app.route('/api/wordbooks', methods=['GET'])
def list_wordbooks():
    """获取所有单词本列表（含单词数）"""
    books = Wordbook.query.order_by(Wordbook.created_at.desc()).all()
    return jsonify({
        'success': True,
        'data': [b.to_dict(include_count=True) for b in books]
    })


@app.route('/api/wordbooks', methods=['POST'])
def create_wordbook():
    """创建单词本"""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': '请输入单词本名称'}), 400
    if len(name) > 100:
        return jsonify({'success': False, 'error': '名称过长（最多100字符）'}), 400
    description = (data.get('description') or '').strip()
    color = (data.get('color') or '#4a7fff').strip()
    book = Wordbook(name=name, description=description, color=color)
    db.session.add(book)
    db.session.commit()
    return jsonify({'success': True, 'data': book.to_dict()})


@app.route('/api/wordbooks/<int:book_id>', methods=['PUT'])
def update_wordbook(book_id):
    """更新单词本"""
    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    data = request.get_json() or {}
    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'success': False, 'error': '名称不能为空'}), 400
        book.name = name[:100]
    if 'description' in data:
        book.description = (data['description'] or '').strip()[:255]
    if 'color' in data:
        book.color = (data['color'] or '#4a7fff').strip()
    db.session.commit()
    return jsonify({'success': True, 'data': book.to_dict()})


@app.route('/api/wordbooks/<int:book_id>', methods=['DELETE'])
def delete_wordbook(book_id):
    """删除单词本（其中的单词移到默认，不删除单词）"""
    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    # 把单词本里的单词的 wordbook_id 置空
    Word.query.filter_by(wordbook_id=book_id).update({'wordbook_id': None})
    db.session.delete(book)
    db.session.commit()
    return jsonify({'success': True, 'message': '单词本已删除'})


@app.route('/api/wordbooks/<int:book_id>/words', methods=['GET'])
def get_wordbook_words(book_id):
    """获取某单词本下的所有单词"""
    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    words = Word.query.filter_by(wordbook_id=book_id).order_by(Word.added_at.desc()).all()
    return jsonify({
        'success': True,
        'data': {
            'wordbook': book.to_dict(),
            'words': [w.to_dict() for w in words]
        }
    })


@app.route('/api/import/preview', methods=['POST'])
def import_preview():
    """
    文档导入预览：上传文档，解析并返回提取的单词列表（不写入数据库）
    让用户确认后再导入
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '请上传文件'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    filename = secure_filename(file.filename) or file.filename
    ext = filename.lower().rsplit('.', 1)[-1] if '.' in filename else ''
    if ext not in ALLOWED_DOC_EXT:
        return jsonify({'success': False, 'error': f'不支持的格式：{ext}，支持 txt/docx/xlsx/pdf'}), 400

    file_bytes = file.read()
    if len(file_bytes) > MAX_DOC_SIZE:
        return jsonify({'success': False, 'error': '文件过大，最大支持 20MB'}), 400

    try:
        result = parse_document_preview(file_bytes, filename)
        return jsonify({
            'success': True,
            'data': {
                'filename': filename,
                'words': result['words'],
                'total': result['total'],
                'raw_preview': result['raw_preview'],
                'raw_length': result['raw_length'],
            }
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'解析失败：{str(e)}'}), 500


@app.route('/api/import/confirm', methods=['POST'])
def import_confirm():
    """
    确认导入：接收单词列表，批量添加到词库
    请求体: {"words": ["word1", "word2", ...]}
    复用批量添加逻辑
    """
    data = request.get_json()
    if not data or not data.get('words'):
        return jsonify({'success': False, 'error': '请提供单词列表'}), 400

    # 复用批量添加逻辑
    words_list = data['words']
    if not isinstance(words_list, list):
        return jsonify({'success': False, 'error': 'words必须是数组'}), 400

    # 单词本 ID（可选，导入的单词会归入此单词本）
    wordbook_id = data.get('wordbook_id')
    if wordbook_id is not None:
        # 校验单词本存在
        book = Wordbook.query.get(wordbook_id)
        if not book:
            return jsonify({'success': False, 'error': '指定的单词本不存在'}), 400

    added = []
    skipped = []
    failed = []

    pending = []
    for raw_word in words_list:
        word_text = str(raw_word).strip().lower()
        if not word_text:
            continue
        existing = Word.query.filter_by(word=word_text).first()
        if existing:
            skipped.append(word_text)
            continue
        dict_result = dictionary_service.lookup(word_text)
        if dict_result:
            pending.append((word_text, dict_result))
        else:
            pending.append((word_text, None))

    ai_pending = [(w, None) for w, a in pending if a is None]
    if ai_pending:
        def _analyze(word_text):
            try:
                return word_text, analyze_word_with_fallback(word_text)
            except Exception as e:
                return word_text, e

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_analyze, [w for w, _ in ai_pending]))

        ai_map = {}
        for word_text, result in results:
            ai_map[word_text] = result
        new_pending = []
        for word_text, _ in pending:
            if word_text in ai_map:
                new_pending.append((word_text, ai_map[word_text]))
            else:
                for w, a in pending:
                    if w == word_text and a is not None:
                        new_pending.append((word_text, a))
                        break
        pending = new_pending

    for word_text, analysis in pending:
        try:
            if isinstance(analysis, Exception):
                failed.append(word_text)
                continue
            if analysis is None:
                failed.append(word_text)
                continue
            # analyze_word_with_fallback 返回 (dict, source) 元组，需取出字典
            if isinstance(analysis, tuple):
                analysis = analysis[0] if analysis else {}
            if not isinstance(analysis, dict) or not analysis:
                failed.append(word_text)
                continue
            word = Word(
                word=word_text,
                phonetic=analysis.get('phonetic', ''),
                meaning=analysis.get('meaning', ''),
                word_type=analysis.get('type', '基础词'),
                split_data=analysis.get('split', []),
                morph_data=analysis.get('morph', []),
                mnemonic=analysis.get('mnemonic', ''),
                examples=analysis.get('examples', []),
                tenses=analysis.get('tenses'),
                status='new',
                wordbook_id=wordbook_id,
            )
            db.session.add(word)
            added.append(word_text)
        except Exception as e:
            failed.append(word_text)

    try:
        db.session.commit()
        # 更新学习历史
        if added:
            update_learn_history(len(added))
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'保存失败：{str(e)}'}), 500

    return jsonify({
        'success': True,
        'data': {
            'added': added,
            'added_count': len(added),
            'skipped': skipped,
            'skipped_count': len(skipped),
            'failed': failed,
            'failed_count': len(failed),
        }
    })


# ==================== OCR识别API ====================

@app.route('/api/ocr/recognize', methods=['POST'])
def ocr_recognize():
    """
    OCR识别接口：上传图片，返回识别出的单词列表
    不添加到词库，仅返回识别结果
    """
    # 检查是否有文件上传
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '请上传图片文件'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式，请上传png/jpg/jpeg/bmp格式'}), 400

    # 检查OCR服务是否可用
    if not ocr_service.is_available():
        return jsonify({
            'success': False,
            'error': '百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY',
        }), 503

    # 确保上传目录存在
    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)

    # 安全保存文件
    filename = secure_filename(file.filename)
    # 添加时间戳避免文件名冲突
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    filepath = os.path.join(upload_folder, timestamp + filename)
    file.save(filepath)

    try:
        # 调用OCR识别
        words = ocr_service.recognize(image_path=filepath)
        return jsonify({
            'success': True,
            'words': words,
            'count': len(words),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'OCR识别失败: {str(e)}'}), 500
    finally:
        # 识别完成后删除临时文件
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/ocr/add-words', methods=['POST'])
def ocr_add_words():
    """
    OCR识别并直接添加到词库
    上传图片 -> OCR识别 -> 分析单词 -> 添加到数据库
    """
    # 检查是否有文件上传
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '请上传图片文件'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式'}), 400

    # 检查OCR服务是否可用
    if not ocr_service.is_available():
        return jsonify({
            'success': False,
            'error': '百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY',
        }), 503

    # 确保上传目录存在
    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)

    # 安全保存文件
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    filepath = os.path.join(upload_folder, timestamp + filename)
    file.save(filepath)

    try:
        # 1. OCR识别
        words = ocr_service.recognize(image_path=filepath)

        if not words:
            return jsonify({'success': True, 'words': [], 'message': '未识别到英文单词', 'added': []})

        # 2. 逐个分析并添加到词库
        added = []
        skipped = []
        failed = []

        for word_text in words:
            word_text = word_text.strip().lower()
            if not word_text:
                continue

            existing = Word.query.filter_by(word=word_text).first()
            if existing:
                skipped.append(word_text)
                continue

            try:
                analysis, source = analyze_word_with_fallback(word_text)
                word = Word(
                    word=word_text,
                    phonetic=analysis.get('phonetic', ''),
                    meaning=analysis.get('meaning', ''),
                    word_type=analysis.get('type', '基础词'),
                    split_data=analysis.get('split', []),
                    morph_data=analysis.get('morph', []),
                    mnemonic=analysis.get('mnemonic', ''),
                    examples=analysis.get('examples', []),
                    tenses=analysis.get('tenses'),
                    status='new',
                )
                db.session.add(word)
                added.append(word_text)
            except Exception as e:
                failed.append({'word': word_text, 'error': str(e)})

        db.session.commit()

        # 更新今日学习历史
        if added:
            update_learn_history(len(added))

        return jsonify({
            'success': True,
            'words': words,
            'added': added,
            'skipped': skipped,
            'failed': failed,
            'added_count': len(added),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'OCR识别失败: {str(e)}'}), 500
    finally:
        # 删除临时文件
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/ai/recognize-image', methods=['POST'])
def ai_recognize_image():
    """
    AI视觉识别接口：上传图片，用大模型识别图片中的英语单词和中文释义
    不添加到词库，仅返回识别结果供用户确认
    """
    data = request.get_json()
    if not data or not data.get('image'):
        return jsonify({'success': False, 'error': '请提供图片数据'}), 400

    image_base64 = data['image']

    # 检查AI服务是否可用
    if not ai_service.is_available():
        return jsonify({'success': False, 'error': 'AI服务未配置，请检查API Key'}), 503

    try:
        words = ai_service.recognize_image(image_base64)
        return jsonify({
            'success': True,
            'words': words,
            'count': len(words),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'AI识别失败: {str(e)}'}), 500


# ==================== 统计API ====================

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计数据：各状态单词数量、今日复习数、学习历史等"""
    # 各状态单词数量
    total = Word.query.count()
    new_count = Word.query.filter_by(status='new').count()
    review_count = Word.query.filter_by(status='review').count()
    mastered_count = Word.query.filter_by(status='mastered').count()

    # 今日待复习数量
    now = datetime.utcnow()
    today_review = Word.query.filter(
        Word.next_review.isnot(None),
        Word.next_review <= now,
        Word.status != 'mastered',
    ).count()

    # 今日新词数量
    today = date.today()
    today_history = LearnHistory.query.filter_by(date=today).first()
    today_learned = today_history.count if today_history else 0

    # 最近7天学习历史
    seven_days_ago = today - timedelta(days=6)
    history = LearnHistory.query.filter(
        LearnHistory.date >= seven_days_ago
    ).order_by(LearnHistory.date).all()

    history_data = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        count = 0
        for h in history:
            if h.date == d:
                count = h.count
                break
        history_data.append({'date': d.isoformat(), 'count': count})

    # 计算 streak_days（连续学习天数）：从今天往前数，连续有学习记录的天数
    # 学习记录定义：当天 learned > 0 即算有学习
    all_history = LearnHistory.query.filter(LearnHistory.count > 0).order_by(LearnHistory.date.desc()).all()
    streak_days = 0
    check_date = today
    for h in all_history:
        if h.date == check_date:
            streak_days += 1
            check_date = check_date - timedelta(days=1)
        elif h.date < check_date:
            # 中断了
            break

    # 学习热力图数据：最近 35 天（5 周）的学习记录
    thirty_five_days_ago = today - timedelta(days=34)
    heatmap_history = LearnHistory.query.filter(
        LearnHistory.date >= thirty_five_days_ago
    ).order_by(LearnHistory.date).all()
    heatmap_data = []
    for i in range(35):
        d = thirty_five_days_ago + timedelta(days=i)
        count = 0
        for h in heatmap_history:
            if h.date == d:
                count = h.count
                break
        heatmap_data.append({'date': d.isoformat(), 'count': count})

    return jsonify({
        'success': True,
        'data': {
            'total': total,
            'new': new_count,
            'review': review_count,
            'mastered': mastered_count,
            'today_review': today_review,
            'today_learned': today_learned,
            'history': history_data,
            'streak_days': streak_days,
            'learn_history': heatmap_data,
        }
    })


# ==================== 复习API（艾宾浩斯遗忘曲线） ====================

@app.route('/api/review/today', methods=['GET'])
def get_today_review():
    """
    获取今日待复习单词列表
    返回 next_review 时间已到期的单词（状态不为mastered）
    防遗忘开启时，已掌握(mastered)单词到期也会进入复习队列
    可通过 ?limit= 控制数量；不传则使用设置的每日复习上限（daily_review_goal，0=不限）
    """
    now = datetime.utcnow()
    setting = get_setting()
    anti_forget = setting.anti_forget if setting.anti_forget is not None else True

    if anti_forget:
        # 防遗忘开启：所有到期单词都进入队列（含mastered）
        words = Word.query.filter(
            Word.next_review.isnot(None),
            Word.next_review <= now,
        ).order_by(Word.next_review).all()
    else:
        # 防遗忘关闭：仅未掌握的到期单词
        words = Word.query.filter(
            Word.next_review.isnot(None),
            Word.next_review <= now,
            Word.status != 'mastered',
        ).order_by(Word.next_review).all()

    # 每日复习上限
    limit = request.args.get('limit', None, type=int)
    if limit is None:
        limit = setting.daily_review_goal or 0
    if limit and limit > 0:
        words = words[:limit]

    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in words],
        'total': len(words),
    })


@app.route('/api/review/<int:word_id>', methods=['POST'])
def submit_review(word_id):
    """
    提交复习结果
    请求体JSON: {"rating": "again/hard/good/easy"}

    艾宾浩斯复习算法（间隔随策略调整）：
    - again: 1分钟后重新出现（重新记忆）
    - hard: 1天后复习
    - good: 根据复习次数递增间隔天数
    - easy: 较长间隔后复习，达到阈值标记为mastered

    复习策略 review_strategy：
    - relaxed(宽松): 间隔更长 [2,5,10,20,45] 天，easy 阈值 3 次
    - standard(标准): [1,3,7,14,30] 天，easy 阈值 4 次
    - strict(严格): 间隔更短 [1,2,4,7,15] 天，easy 阈值 6 次

    防遗忘 anti_forget：
    - 开启时，已 mastered 单词 easy 评分后按 anti_forget_interval 天后再次回顾
    - 关闭时，mastered 单词不再安排复习
    """
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404

    data = request.get_json()
    if not data or not data.get('rating'):
        return jsonify({'success': False, 'error': '请提供复习评分'}), 400

    rating = data['rating'].lower().strip()
    if rating not in ('again', 'hard', 'good', 'easy'):
        return jsonify({'success': False, 'error': '评分必须是 again/hard/good/easy 之一'}), 400

    setting = get_setting()
    strategy = setting.review_strategy or 'standard'
    anti_forget = setting.anti_forget if setting.anti_forget is not None else True
    anti_forget_interval = setting.anti_forget_interval or 30

    # 不同策略的复习间隔（天）与 easy 掌握阈值
    strategy_config = {
        'relaxed':  {'intervals': [2, 5, 10, 20, 45], 'easy_threshold': 3},
        'standard': {'intervals': [1, 3, 7, 14, 30],  'easy_threshold': 4},
        'strict':   {'intervals': [1, 2, 4, 7, 15],   'easy_threshold': 6},
    }
    cfg = strategy_config.get(strategy, strategy_config['standard'])
    good_intervals = cfg['intervals']
    easy_threshold = cfg['easy_threshold']

    now = datetime.utcnow()
    was_mastered = (word.status == 'mastered')

    # 记录本次复习
    word.last_review = now
    word.review_count = (word.review_count or 0) + 1

    # 防遗忘：已掌握单词的回顾，只按 anti_forget_interval 安排，不改变状态
    if was_mastered and anti_forget:
        if rating == 'again':
            # 已掌握但忘了，降级回复习中
            word.status = 'review'
            word.next_review = now + timedelta(days=1)
        else:
            # 回顾成功，继续按防遗忘间隔安排
            word.next_review = now + timedelta(days=anti_forget_interval)
    else:
        if rating == 'again':
            # 不会，1分钟后重新出现（重新记忆）
            word.next_review = now + timedelta(minutes=1)
            word.status = 'review'

        elif rating == 'hard':
            # 困难，1天后复习
            word.next_review = now + timedelta(days=1)
            word.status = 'review'

        elif rating == 'good':
            # 一般，根据复习次数选择间隔
            interval_index = min(word.review_count - 1, len(good_intervals) - 1)
            days = good_intervals[interval_index]
            word.next_review = now + timedelta(days=days)
            word.status = 'review'

        elif rating == 'easy':
            # 简单，间隔为最长一档
            days = good_intervals[-1]
            word.next_review = now + timedelta(days=days)
            # 复习达到阈值标记为已掌握
            if word.review_count >= easy_threshold:
                word.status = 'mastered'
                # 防遗忘开启：mastered 后按防遗忘间隔安排回顾；关闭则不再安排
                if anti_forget:
                    word.next_review = now + timedelta(days=anti_forget_interval)
                else:
                    word.next_review = None
            else:
                word.status = 'review'

    db.session.commit()

    return jsonify({
        'success': True,
        'data': word.to_dict(),
        'message': f'复习已记录，下次复习时间：{word.next_review.strftime("%Y-%m-%d %H:%M") if word.next_review else "不再提醒"}',
    })


# ==================== 学习队列API ====================

def get_setting():
    """获取全局设置（单行表，id=1）"""
    setting = Setting.query.get(1)
    if not setting:
        setting = Setting(id=1, daily_goal=20)
        db.session.add(setting)
        db.session.commit()
    return setting


@app.route('/api/learn/today', methods=['GET'])
def get_today_learn():
    """
    获取今日新词学习队列
    返回状态为new的单词（按添加时间正序）
    可通过 ?limit= 参数控制返回数量；不传则使用设置的 daily_goal
    """
    limit = request.args.get('limit', None, type=int)
    if limit is None:
        limit = get_setting().daily_goal

    # 获取状态为new的单词
    words = Word.query.filter_by(status='new').order_by(
        Word.added_at.asc()
    ).limit(limit).all()

    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in words],
        'total': len(words),
    })


# ==================== 设置管理 ====================

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取用户设置"""
    return jsonify({'success': True, 'data': get_setting().to_dict()})


@app.route('/api/settings', methods=['PUT'])
def update_settings():
    """更新用户设置"""
    data = request.get_json() or {}
    setting = get_setting()
    if 'daily_goal' in data:
        try:
            goal = int(data['daily_goal'])
            if goal < 1 or goal > 200:
                return jsonify({'success': False, 'error': '每日新词目标应在 1-200 之间'}), 400
            setting.daily_goal = goal
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': '每日新词目标必须是数字'}), 400
    if 'daily_review_goal' in data:
        try:
            rgoal = int(data['daily_review_goal'])
            if rgoal < 0 or rgoal > 500:
                return jsonify({'success': False, 'error': '每日复习上限应在 0-500 之间（0=不限）'}), 400
            setting.daily_review_goal = rgoal
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': '每日复习上限必须是数字'}), 400
    if 'review_strategy' in data:
        strat = str(data['review_strategy']).lower().strip()
        if strat not in ('relaxed', 'standard', 'strict'):
            return jsonify({'success': False, 'error': '复习策略必须是 relaxed/standard/strict 之一'}), 400
        setting.review_strategy = strat
    if 'anti_forget' in data:
        setting.anti_forget = bool(data['anti_forget'])
    if 'anti_forget_interval' in data:
        try:
            iv = int(data['anti_forget_interval'])
            if iv < 1 or iv > 365:
                return jsonify({'success': False, 'error': '防遗忘间隔应在 1-365 天之间'}), 400
            setting.anti_forget_interval = iv
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': '防遗忘间隔必须是数字'}), 400
    db.session.commit()
    return jsonify({'success': True, 'data': setting.to_dict()})


@app.route('/api/words/clear', methods=['DELETE'])
def clear_all_words():
    """清空所有单词数据（含学习历史，不可恢复）"""
    try:
        db.session.query(Word).delete()
        db.session.query(LearnHistory).delete()
        db.session.commit()
        return jsonify({'success': True, 'message': '已清空所有数据'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/words/export', methods=['GET'])
def export_words_csv():
    """
    导出单词为多种格式
    查询参数：
    - format: csv（默认）/ txt / anki
    - wordbook_id: 按单词本过滤（不传=全部，0=未归类，具体id=该单词本）
    - status: 按状态过滤（new/review/mastered）
    - search: 搜索关键词
    """
    import csv
    import io
    from flask import Response

    # 解析查询参数
    fmt = request.args.get('format', 'csv').lower()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    # 构建查询
    query = Word.query
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter(Word.wordbook_id == int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter(Word.wordbook_id.is_(None))
    if status:
        query = query.filter(Word.status == status)
    if search:
        query = query.filter(
            db.or_(
                Word.word.contains(search),
                Word.meaning.contains(search),
            )
        )

    # 获取单词本名称用于文件名
    book_name = '全部单词'
    if wordbook_id and wordbook_id != '0':
        book = Wordbook.query.get(int(wordbook_id))
        if book:
            book_name = book.name
    elif wordbook_id == '0':
        book_name = '未归类'

    words = query.order_by(Word.added_at.desc()).all()

    if not words:
        return jsonify({'success': False, 'error': '没有可导出的单词'}), 400

    # 根据格式生成内容
    if fmt == 'txt':
        # TXT格式：每行 "word meaning"，兼容扇贝/有道等导入
        output = io.StringIO()
        for w in words:
            line = f"{w.word}"
            if w.meaning:
                line += f" {w.meaning}"
            output.write(line + '\n')
        content = output.getvalue()
        output.close()
        filename = f'{book_name}.txt'
        mimetype = 'text/plain; charset=utf-8'

    elif fmt == 'anki':
        # Anki制表符格式：word \t meaning，可直接导入Anki
        output = io.StringIO()
        # Anki导入需要的第一行字段名（可选）
        for w in words:
            meaning = w.meaning or ''
            output.write(f"{w.word}\t{meaning}\n")
        content = output.getvalue()
        output.close()
        filename = f'{book_name}_anki.txt'
        mimetype = 'text/plain; charset=utf-8'

    else:
        # CSV格式（默认）：完整字段，Excel友好
        output = io.StringIO()
        # 写入 UTF-8 BOM 让 Excel 正确识别中文
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['单词', '音标', '释义', '类型', '记忆方法', '状态', '添加时间', '复习次数'])
        for w in words:
            writer.writerow([
                w.word, w.phonetic or '', w.meaning or '', w.word_type or '',
                w.mnemonic or '', w.status,
                w.added_at.strftime('%Y-%m-%d %H:%M') if w.added_at else '',
                w.review_count or 0,
            ])
        content = output.getvalue()
        output.close()
        filename = f'{book_name}.csv'
        mimetype = 'text/csv; charset=utf-8'

    # 文件名编码处理（RFC 5987）
    from urllib.parse import quote
    encoded_filename = quote(filename)

    return Response(
        content,
        mimetype=mimetype,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}; filename={encoded_filename}"
        }
    )


# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({'success': False, 'error': '接口不存在'}), 404


@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    db.session.rollback()
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500


@app.errorhandler(413)
def too_large(error):
    """文件过大错误处理"""
    return jsonify({'success': False, 'error': '上传文件过大，最大支持16MB'}), 413


# ==================== 应用初始化 ====================

def ensure_mnemonic_column():
    """
    数据库迁移：为 words 表添加 mnemonic 列（如果不存在）
    SQLAlchemy 的 db.create_all() 不会自动给已存在的表添加新列，需要手动迁移
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('words')]
    if 'mnemonic' not in columns:
        print("[迁移] 检测到 words 表缺少 mnemonic 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN mnemonic TEXT DEFAULT ''"))
            conn.commit()
        print("[迁移] mnemonic 列添加完成")


def ensure_wordbook_column():
    """
    数据库迁移：为 words 表添加 wordbook_id 列（如果不存在）
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('words')]
    if 'wordbook_id' not in columns:
        print("[迁移] 检测到 words 表缺少 wordbook_id 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN wordbook_id INTEGER"))
            conn.commit()
        print("[迁移] wordbook_id 列添加完成")


def ensure_settings_columns():
    """
    数据库迁移：为 settings 表添加新列（复习计划/防遗忘相关）
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('settings')]
    new_cols = [
        ('daily_review_goal', 'INTEGER DEFAULT 50'),
        ('review_strategy', "VARCHAR(20) DEFAULT 'standard'"),
        ('anti_forget', 'BOOLEAN DEFAULT 1'),
        ('anti_forget_interval', 'INTEGER DEFAULT 30'),
    ]
    for col_name, col_def in new_cols:
        if col_name not in columns:
            print(f"[迁移] 检测到 settings 表缺少 {col_name} 列，正在添加...")
            with db.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def}"))
                conn.commit()
            print(f"[迁移] {col_name} 列添加完成")


def ensure_tenses_column():
    """
    数据库迁移：为 words 表添加 tenses 列（动词时态变形数据）
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('words')]
    if 'tenses' not in columns:
        print("[迁移] 检测到 words 表缺少 tenses 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN tenses JSON"))
            conn.commit()
        print("[迁移] tenses 列添加完成")


with app.app_context():
    # 创建数据库表（含新的 wordbooks 表）
    db.create_all()
    # 迁移：为新版本添加 mnemonic 列
    ensure_mnemonic_column()
    # 迁移：为新版本添加 wordbook_id 列
    ensure_wordbook_column()
    # 迁移：为 settings 表添加复习计划/防遗忘相关列
    ensure_settings_columns()
    # 迁移：为 words 表添加 tenses 列（动词时态变形）
    ensure_tenses_column()
    # 插入演示数据
    init_demo_data()
    # 升级已有单词的拆解数据和记忆方法到新结构
    upgrade_split_data()
    # 修复 meaning 为空的旧数据单词
    fix_empty_meanings()


# ==================== 前端静态文件服务 ====================
# 生产环境下由后端直接托管前端文件，部署后只需一个服务（同源，无需CORS）
# 本地开发也可通过 http://localhost:5000/ 直接访问前端
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))


@app.route('/')
def serve_index():
    """根路径返回前端首页"""
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """前端静态资源（css/js）"""
    return send_from_directory(os.path.join(FRONTEND_DIR, 'assets'), filename)


@app.route('/manifest.json')
def serve_manifest():
    """PWA manifest 配置"""
    return send_from_directory(FRONTEND_DIR, 'manifest.json')


@app.route('/sw.js')
def serve_sw():
    """PWA service worker"""
    return send_from_directory(FRONTEND_DIR, 'sw.js')


@app.route('/icons/<path:filename>')
def serve_icons(filename):
    """PWA 图标"""
    return send_from_directory(os.path.join(FRONTEND_DIR, 'icons'), filename)


# ==================== TWA (Trusted Web Activity) 验证 ====================
# 用于 Android APK 全屏运行验证，移除浏览器地址栏
# 路径必须为 /.well-known/assetlinks.json
@app.route('/.well-known/assetlinks.json')
def serve_assetlinks():
    """Android Digital Asset Links - TWA 全屏验证文件"""
    assetlinks = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.wordmemo.app",
            "sha256_cert_fingerprints": [
                "1C:96:82:23:88:2C:FB:B5:BE:D3:7A:5B:52:71:A9:A4:BA:25:05:8A:E9:85:69:A5:E5:20:80:DE:D2:03:61:34"
            ]
        }
    }]
    return jsonify(assetlinks), 200, {'Content-Type': 'application/json'}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
