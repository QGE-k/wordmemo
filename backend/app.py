"""
WordMemo 背单词应用 - Flask主应用
提供单词管理、OCR识别、AI分析、复习算法等API接口
"""
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, date

from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

from sqlalchemy import case

from config import Config
from models import db, Word, LearnHistory, Setting, Wordbook, User, LearnSession
from services.ocr_service import OCRService
from services.ai_service import AIService
from services.dictionary_service import DictionaryService
from services.doc_import_service import parse_document, parse_document_preview

# 创建Flask应用
app = Flask(__name__)
# 加载配置
app.config.from_object(Config)
# session 密钥
app.secret_key = os.environ.get('SECRET_KEY', 'wordmemo-dev-secret-key-2024')
# session 过期时间：登录后 7 天内有效（需在登录时设置 session.permanent = True 生效）
app.permanent_session_lifetime = timedelta(days=7)

# 启用CORS，允许前端跨域访问（支持 credentials）
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)


@app.after_request
def set_api_cache_headers(response):
    """缓存控制：API 和静态资源都不缓存，确保总是拿到最新版本"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif request.path.startswith('/assets/') or request.path.endswith('.html') or request.path.endswith('/sw.js'):
        # 静态资源（JS/CSS/HTML/SW）：每次都验证，防止旧缓存
        response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response


# 初始化数据库
db.init_app(app)

# 初始化服务实例
ocr_service = OCRService()
ai_service = AIService()
dictionary_service = DictionaryService()


# ==================== Neon 数据库保活 ====================
# Neon 免费版计算节点 5 分钟无活动后休眠，下次查询需 3-5 秒唤醒。
# 后台线程每 4 分钟执行一次轻量查询，保持计算节点热度。
def _neon_keepalive():
    while True:
        time.sleep(240)  # 每 4 分钟
        try:
            with app.app_context():
                db.session.execute(db.text('SELECT 1'))
                db.session.commit()
        except Exception:
            pass  # 保活失败不影响正常使用


# 仅在使用远程数据库（Neon/PostgreSQL）时启动保活线程
if Config.DATABASE_URL:
    _keepalive_thread = threading.Thread(target=_neon_keepalive, daemon=True)
    _keepalive_thread.start()


# ==================== 工具函数 ====================

def allowed_file(filename):
    """检查上传的文件是否为允许的扩展名"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def get_current_user():
    """获取当前登录用户，未登录返回 None"""
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)


def get_current_user_id():
    """获取当前登录用户ID，未登录返回 None（兼容旧数据）"""
    return session.get('user_id')


def require_login():
    """要求登录，未登录返回错误响应"""
    if not session.get('user_id'):
        return jsonify({'success': False, 'error': '请先登录'}), 401
    return None


def require_admin():
    """要求管理员权限"""
    user = get_current_user()
    if not user or user.role != 'admin':
        return jsonify({'success': False, 'error': '需要管理员权限'}), 403
    return None


# ==================== 认证 API ====================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """用户注册"""
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'error': '请提供用户名和密码'}), 400

    username = data['username'].strip()
    password = data['password']

    if len(username) < 2 or len(username) > 20:
        return jsonify({'success': False, 'error': '用户名长度需2-20个字符'}), 400
    if len(password) < 6:
        return jsonify({'success': False, 'error': '密码至少6个字符'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'error': '用户名已存在'}), 409

    # 安全问题及答案（用于密码重置，可选；未提供时使用默认问题且答案为空）
    security_question = (data.get('security_question') or 'What is your favorite color?').strip()
    security_answer = (data.get('security_answer') or '').strip()

    # 第一个注册的用户自动成为管理员
    is_first = User.query.count() == 0
    user = User(
        username=username,
        nickname=data.get('nickname', username),
        role='admin' if is_first else 'user',
        security_question=security_question,
        security_answer=security_answer,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    session['user_id'] = user.id
    session.permanent = True
    return jsonify({'success': True, 'data': user.to_dict()}), 201


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """用户登录"""
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'success': False, 'error': '请提供用户名和密码'}), 400

    user = User.query.filter_by(username=data['username'].strip()).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'success': False, 'error': '用户名或密码错误'}), 401

    # 账号被禁用不允许登录（is_active 为 None 时按启用处理，兼容旧数据）
    if user.is_active is False:
        return jsonify({'success': False, 'error': '该账号已被禁用，请联系管理员'}), 403

    session['user_id'] = user.id
    # 启用永久会话，配合 app.permanent_session_lifetime 实现 7 天有效期
    session.permanent = True
    return jsonify({'success': True, 'data': user.to_dict()})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """退出登录"""
    session.pop('user_id', None)
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """获取当前登录用户信息"""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': '未登录'}), 401
    return jsonify({'success': True, 'data': user.to_dict()})


@app.route('/api/auth/reset_password', methods=['POST'])
def auth_reset_password():
    """
    密码重置：通过安全问题答案重置密码（简单版）
    请求体JSON: {"username": "xxx", "new_password": "xxx", "security_answer": "xxx"}
    校验规则：
    - 用户必须存在
    - 新密码至少 6 个字符
    - 若用户设置了安全问题答案，需与提交的 security_answer 匹配（不区分大小写）
    - 旧用户未设置安全问题答案时，要求提供非空答案作为兜底校验
    """
    data = request.get_json()
    if not data or not data.get('username') or not data.get('new_password'):
        return jsonify({'success': False, 'error': '请提供用户名和新密码'}), 400

    username = data['username'].strip()
    new_password = data['new_password']
    security_answer = (data.get('security_answer') or '').strip()

    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少6个字符'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    # 安全问题答案校验
    stored_answer = (user.security_answer or '').strip()
    if stored_answer:
        # 已设置安全问题：答案需匹配（不区分大小写）
        if stored_answer.lower() != security_answer.lower():
            return jsonify({'success': False, 'error': '安全问题答案不正确'}), 403
    else:
        # 旧用户未设置安全问题答案：要求提供非空答案作为兜底
        if not security_answer:
            return jsonify({
                'success': False,
                'error': '该账号未设置安全问题，请联系管理员重置密码',
            }), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({'success': True, 'message': '密码已重置，请使用新密码登录'})


@app.route('/api/auth/profile', methods=['PUT'])
def auth_update_profile():
    """用户修改个人信息（昵称、安全问题）
    请求体JSON: {"nickname": "xxx", "security_question": "xxx", "security_answer": "xxx"}
    """
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': '请先登录'}), 401

    data = request.get_json() or {}
    changed = False

    if 'nickname' in data:
        nickname = data['nickname'].strip()
        if len(nickname) > 80:
            return jsonify({'success': False, 'error': '昵称最多80个字符'}), 400
        user.nickname = nickname
        changed = True

    if 'security_question' in data:
        user.security_question = data['security_question'].strip() or 'What is your favorite color?'
        changed = True

    if 'security_answer' in data:
        user.security_answer = data['security_answer'].strip()
        changed = True

    if changed:
        db.session.commit()

    return jsonify({'success': True, 'data': user.to_dict(), 'message': '个人信息已更新'})


@app.route('/api/auth/change-password', methods=['PUT'])
def auth_change_password():
    """用户修改密码（需验证旧密码）
    请求体JSON: {"old_password": "xxx", "new_password": "xxx"}
    """
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': '请先登录'}), 401

    data = request.get_json() or {}
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')

    if not old_password:
        return jsonify({'success': False, 'error': '请输入旧密码'}), 400
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少6个字符'}), 400

    if not user.check_password(old_password):
        return jsonify({'success': False, 'error': '旧密码不正确'}), 403

    user.set_password(new_password)
    db.session.commit()
    return jsonify({'success': True, 'message': '密码修改成功'})


@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    """管理员：获取所有用户列表及其学习统计"""
    err = require_admin()
    if err:
        return err

    users = User.query.order_by(User.created_at.desc()).all()
    # 管理员可查看完整信息：含安全问题、密码哈希、OCR用量等
    result = []
    for u in users:
        info = u.to_dict(include_stats=True)
        info['security_answer'] = u.security_answer or ''
        info['password_hash'] = u.password_hash
        info['salt'] = u.salt
        info['is_active'] = u.is_active if u.is_active is not None else True
        result.append(info)
    return jsonify({
        'success': True,
        'data': result,
    })


@app.route('/api/admin/users/<int:user_id>/words', methods=['GET'])
def admin_user_words(user_id):
    """管理员：查看指定用户的词库"""
    err = require_admin()
    if err:
        return err

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    words = Word.query.filter_by(user_id=user_id).order_by(Word.added_at.desc()).all()
    wordbooks = Wordbook.query.filter_by(user_id=user_id).all()
    return jsonify({
        'success': True,
        'data': {
            'user': target_user.to_dict(),
            'word_count': len(words),
            'mastered_count': sum(1 for w in words if w.status == 'mastered'),
            'wordbooks': [wb.to_dict(include_count=True) for wb in wordbooks],
            'recent_words': [w.to_dict() for w in words[:50]],
        },
    })


@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    """管理员：删除用户及其所有数据"""
    err = require_admin()
    if err:
        return err

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    # 不能删除自己
    current = get_current_user_id()
    if current == user_id:
        return jsonify({'success': False, 'error': '不能删除当前登录的管理员账号'}), 400

    # 删除用户的所有单词、词书
    Word.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    Wordbook.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    db.session.delete(target_user)
    db.session.commit()

    return jsonify({'success': True, 'message': f'已删除用户 {target_user.username}'})


@app.route('/api/admin/reset_user_password', methods=['POST'])
def admin_reset_user_password():
    """管理员：重置任意用户的密码
    请求体JSON: {"user_id": 1, "new_password": "xxx"}
    """
    err = require_admin()
    if err:
        return err

    data = request.get_json() or {}
    user_id = data.get('user_id')
    new_password = data.get('new_password')

    if not user_id:
        return jsonify({'success': False, 'error': '请提供 user_id'}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'error': '新密码至少6个字符'}), 400

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    target_user.set_password(new_password)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'已重置用户 {target_user.username} 的密码',
    })


@app.route('/api/admin/toggle_user', methods=['POST'])
def admin_toggle_user():
    """管理员：启用/禁用用户账号
    请求体JSON: {"user_id": 1, "is_active": true/false}
    不传 is_active 时按当前状态取反（切换）
    """
    err = require_admin()
    if err:
        return err

    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': '请提供 user_id'}), 400

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    current = get_current_user_id()
    if current == user_id:
        return jsonify({'success': False, 'error': '不能禁用当前登录的管理员账号'}), 400

    if 'is_active' in data:
        target_user.is_active = bool(data['is_active'])
    else:
        # 未指定则切换当前状态（None 视为启用）
        target_user.is_active = False if target_user.is_active is not False else True

    db.session.commit()
    return jsonify({
        'success': True,
        'data': target_user.to_dict(),
        'message': f'用户 {target_user.username} 已{"启用" if target_user.is_active else "禁用"}',
    })


@app.route('/api/admin/user_stats/<int:user_id>', methods=['GET'])
def admin_user_stats(user_id):
    """管理员：获取指定用户的详细学习统计"""
    err = require_admin()
    if err:
        return err

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': '用户不存在'}), 404

    # 单词统计
    words = Word.query.filter_by(user_id=user_id).all()
    total = len(words)
    new_count = sum(1 for w in words if w.status == 'new')
    review_count = sum(1 for w in words if w.status == 'review')
    mastered_count = sum(1 for w in words if w.status == 'mastered')
    # 高频错词（wrong_count > 0）
    wrong_words = [w for w in words if (w.wrong_count or 0) > 0]
    total_wrong = sum((w.wrong_count or 0) for w in words)
    total_reviews = sum((w.review_count or 0) for w in words)

    # 单词本统计
    wordbooks = Wordbook.query.filter_by(user_id=user_id).all()

    # 最近 7 天学习历史（按目标用户过滤）
    today = date.today()
    seven_days_ago = today - timedelta(days=6)
    history = LearnHistory.query.filter(
        LearnHistory.date >= seven_days_ago,
        LearnHistory.user_id == user_id,
    ).order_by(LearnHistory.date).all()
    history_data = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        count = 0
        correct = 0
        total_rev = 0
        for h in history:
            if h.date == d:
                count = h.count or 0
                correct = h.correct_count or 0
                total_rev = h.total_count or 0
                break
        accuracy = round(correct / total_rev * 100, 1) if total_rev else 0.0
        history_data.append({
            'date': d.isoformat(),
            'count': count,
            'correct_count': correct,
            'total_count': total_rev,
            'accuracy': accuracy,
        })

    # 平均准确率
    sum_correct = sum(h['correct_count'] for h in history_data)
    sum_total = sum(h['total_count'] for h in history_data)
    avg_accuracy = round(sum_correct / sum_total * 100, 1) if sum_total else 0.0

    return jsonify({
        'success': True,
        'data': {
            'user': target_user.to_dict(),
            'word_stats': {
                'total': total,
                'new': new_count,
                'review': review_count,
                'mastered': mastered_count,
            },
            'review_stats': {
                'total_reviews': total_reviews,
                'wrong_word_count': len(wrong_words),
                'total_wrong_count': total_wrong,
                'avg_accuracy': avg_accuracy,
            },
            'wordbook_count': len(wordbooks),
            'recent_wrong_words': [
                {'word': w.word, 'wrong_count': w.wrong_count, 'review_count': w.review_count}
                for w in sorted(wrong_words, key=lambda x: x.wrong_count or 0, reverse=True)[:20]
            ],
            'history': history_data,
        },
    })


def analyze_word_with_fallback(word):
    """
    分析单词：优先使用本地词典（ECDICT，毫秒级），词典没有再调 AI，最后规则分析

    参数:
        word: 要分析的单词

    返回:
        dict: 分析结果，包含 phonetic, meaning, type, split, morph, examples
    """
    # 1. 先查本地词典（ECDICT + 内置词典，毫秒级，覆盖 77 万词条）
    result = dictionary_service.lookup(word)
    if result:
        return result, 'dictionary'

    # 2. 词典没有的词，尝试 AI 服务（慢，但能处理生僻词和新词）
    if ai_service.is_available():
        try:
            result = ai_service.analyze_word(word)
            return result, 'ai'
        except Exception as e:
            print(f"[警告] AI分析失败，降级到规则分析: {e}")

    # 3. 最后使用规则分析
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
    数据迁移：修复 meaning 为空或"暂无释义"的单词
    对这些单词重新分析，补充 meaning/phonetic/mnemonic/tenses 等空字段
    优先用 AI 分析，AI 不可用时降级到字典/规则分析（至少给出兜底释义）
    对"暂无释义"的单词，同时覆盖更新例句和记忆方法（之前的模板数据质量差）
    """
    fixed = 0
    # 查找 meaning 为空或包含"暂无释义"的单词
    empty_words = Word.query.filter(
        db.or_(
            Word.meaning.is_(None),
            Word.meaning == '',
            Word.meaning.like('%暂无释义%'),
        )
    ).all()

    for word in empty_words:
        try:
            was_no_meaning = word.meaning and '暂无释义' in word.meaning
            analysis, source = analyze_word_with_fallback(word.word)
            new_meaning = analysis.get('meaning', '')
            updated = False
            # 有有效释义时更新（跳过仍然为空或"暂无释义"的结果）
            if new_meaning and '暂无释义' not in new_meaning:
                word.meaning = new_meaning
                updated = True
            if not word.phonetic and analysis.get('phonetic'):
                word.phonetic = analysis['phonetic']
                updated = True
            # 对"暂无释义"单词：强制覆盖记忆方法（之前的模板数据差）
            if was_no_meaning and analysis.get('mnemonic'):
                word.mnemonic = analysis['mnemonic']
                updated = True
            elif not word.mnemonic and analysis.get('mnemonic'):
                word.mnemonic = analysis['mnemonic']
                updated = True
            if (not word.tenses or (isinstance(word.tenses, dict) and not word.tenses.get('inflection_type'))) and analysis.get('tenses'):
                word.tenses = analysis['tenses']
                updated = True
            if was_no_meaning or not word.split_data:
                if analysis.get('split'):
                    word.split_data = analysis['split']
                    updated = True
            # 对"暂无释义"单词：强制覆盖例句（之前的模板例句语法错误）
            if was_no_meaning and analysis.get('examples'):
                word.examples = analysis['examples']
                updated = True
            elif not word.examples and analysis.get('examples'):
                word.examples = analysis['examples']
                updated = True
            if updated:
                fixed += 1
                print(f"[迁移] 已修复 '{word.word}': {new_meaning[:40]}")
        except Exception as e:
            print(f"[迁移] 修复 '{word.word}' 失败: {e}")

    if fixed > 0:
        db.session.commit()
        print(f"[迁移] 已修复 {fixed} 个空释义/暂无释义单词")


def fix_broken_meanings():
    """
    数据迁移：修复释义异常的单词
    1. 释义包含 OCR 数字artifact（如 "更差的2"）→ 重新查词典
    2. 变形词（worse/better/best 等）缺少或错误的 tenses → 修复
    3. 释义为纯英文（无中文字符）→ 重新查词典
    4. tenses 类型与单词不符（如 worse 显示 plural 而非 degree）→ 修复
    """
    fixed = 0
    for word in Word.query.all():
        need_fix = False
        meaning = word.meaning or ''

        # 1. 释义为空
        if not meaning.strip():
            need_fix = True
        # 2. 释义末尾有数字（OCR artifact，如 "更差的2"）
        elif re.search(r'[\u4e00-\u9fff]\d+$', meaning.strip()):
            need_fix = True
        # 3. 释义没有中文字符（纯英文或乱码）
        elif meaning.strip() and not any('\u4e00' <= c <= '\u9fff' for c in meaning):
            need_fix = True

        # 4. 检查 tenses 数据是否需要修复
        # 变形词缺少 tenses，或 tenses 类型错误（如 worse 显示 plural 而非 degree）
        word_lower = word.word.lower().strip()
        reverse_adj = dictionary_service.REVERSE_ADJ_DEGREES.get(word_lower)
        tenses_wrong = False
        if reverse_adj:
            # 这是一个不规则形容词变形词，tenses 应该是 degree 类型
            if not word.tenses or word.tenses.get('inflection_type') != 'degree':
                tenses_wrong = True
                need_fix = True
        elif not word.tenses and not need_fix:
            # 非变形词但缺少 tenses，尝试补充
            dict_result = dictionary_service.lookup(word.word)
            if dict_result and dict_result.get('tenses'):
                word.tenses = dict_result['tenses']
                if dict_result.get('split') and not word.split_data:
                    word.split_data = dict_result['split']
                if dict_result.get('type') and word.word_type == '基础词':
                    word.word_type = dict_result['type']
                if dict_result.get('mnemonic') and not word.mnemonic:
                    word.mnemonic = dict_result['mnemonic']
                fixed += 1
            continue

        if not need_fix:
            continue

        try:
            analysis, source = analyze_word_with_fallback(word.word)
            new_meaning = analysis.get('meaning', '')
            if new_meaning:
                word.meaning = new_meaning
            if analysis.get('phonetic') and (not word.phonetic or word.phonetic == ''):
                word.phonetic = analysis['phonetic']
            if analysis.get('tenses'):
                word.tenses = analysis['tenses']
            if analysis.get('split'):
                word.split_data = analysis['split']
            if analysis.get('type'):
                word.word_type = analysis['type']
            if analysis.get('mnemonic'):
                word.mnemonic = analysis['mnemonic']
            if analysis.get('examples'):
                word.examples = analysis['examples']
            fixed += 1
        except Exception as e:
            print(f"[迁移] 修复异常释义 '{word.word}' 失败: {e}")

    if fixed > 0:
        db.session.commit()
        print(f"[迁移] 已修复 {fixed} 个异常释义/变形单词")


def force_upgrade_all_tenses():
    """
    强制升级所有单词的 tenses 数据和释义精简
    1. 用新的 _clean_meaning 逻辑更新所有单词的释义（精简为1-2条考试常考释义）
    2. 用新的 _get_inflections 逻辑补全所有单词的 tenses（支持 a. 前缀的形容词等）
    3. 确保 tenses 包含 inflection_type 字段
    4. 修复碎片化/垃圾释义（如短语返回的 "冠\n姣姣者"）
    """
    upgraded = 0
    for word in Word.query.all():
        need_upgrade = False
        dict_data = dictionary_service.lookup(word.word)

        # 检查存储的释义是否是垃圾释义（碎片化、无词性前缀、过短）
        stored_meaning = word.meaning or ''
        is_garbage = False
        if stored_meaning:
            import re as _re
            # 去掉词性前缀后检查
            content = _re.sub(r'^[a-z]+\.\s*', '', stored_meaning).strip()
            chars = [c for c in content if '\u4e00' <= c <= '\u9fff']
            if len(chars) <= 3:
                is_garbage = True
            elif '\n' in content:
                lines_c = [l.strip() for l in content.split('\n') if l.strip()]
                if all(len(l) <= 3 for l in lines_c):
                    is_garbage = True

        # 如果释义是垃圾且词典查不到（短语被质量检查过滤），用 AI 重新分析
        if is_garbage and not dict_data:
            try:
                analysis, source = analyze_word_with_fallback(word.word)
                if analysis:
                    new_meaning = analysis.get('meaning', '')
                    if new_meaning and new_meaning != stored_meaning:
                        word.meaning = new_meaning
                        need_upgrade = True
                    if analysis.get('tenses'):
                        word.tenses = analysis['tenses']
                        need_upgrade = True
                    if analysis.get('split'):
                        word.split_data = analysis['split']
                        need_upgrade = True
                    if analysis.get('type'):
                        word.word_type = analysis['type']
                        need_upgrade = True
                    if analysis.get('mnemonic') and not word.mnemonic:
                        word.mnemonic = analysis['mnemonic']
                        need_upgrade = True
                    if analysis.get('examples'):
                        word.examples = analysis['examples']
                        need_upgrade = True
            except Exception as e:
                print(f"[迁移] AI重分析 '{word.word}' 失败: {e}")
            if need_upgrade:
                upgraded += 1
            continue

        if not dict_data:
            continue

        # 1. 更新释义（应用新的精简逻辑）
        new_meaning = dict_data.get('meaning', '')
        if new_meaning and new_meaning != word.meaning:
            word.meaning = new_meaning
            need_upgrade = True

        # 2. 更新 tenses（应用新的变形检测逻辑）
        new_tenses = dict_data.get('tenses')
        if new_tenses:
            # 检查是否需要更新：tenses 为空、缺少 inflection_type、或类型不匹配
            if not word.tenses:
                need_upgrade = True
            elif not word.tenses.get('inflection_type'):
                need_upgrade = True
            elif word.tenses.get('inflection_type') != new_tenses.get('inflection_type'):
                need_upgrade = True

            if need_upgrade:
                word.tenses = new_tenses

        # 3. 更新 split 数据（确保变形词的 split 正确）
        new_split = dict_data.get('split', [])
        if new_split and new_split != word.split_data:
            word.split_data = new_split
            need_upgrade = True

        # 4. 更新 word_type
        new_type = dict_data.get('type', '')
        if new_type and new_type != word.word_type:
            word.word_type = new_type
            need_upgrade = True

        # 5. 更新 mnemonic
        new_mnemonic = dict_data.get('mnemonic', '')
        if new_mnemonic and not word.mnemonic:
            word.mnemonic = new_mnemonic
            need_upgrade = True

        if need_upgrade:
            upgraded += 1

    if upgraded > 0:
        db.session.commit()
        print(f"[迁移] 已升级 {upgraded} 个单词的释义精简和变形数据")


def get_today_utc_range():
    """获取本地今天对应的 UTC 时间范围（start_utc, end_utc）

    last_review 存储的是 datetime.utcnow() 的值（UTC 时间），
    但用户看到的"今天"是本地日期（date.today()）。
    直接用本地午夜和 UTC 时间比较会导致时区错位：
      - UTC+8 凌晨 0~8 点学习的单词不会被计入"今日已学"
      - 跨天时可能把昨天的单词算到今天

    此函数将本地午夜转换为 UTC，确保比较基准一致。
    """
    today_local = date.today()
    today_start_local = datetime.combine(today_local, datetime.min.time())
    utc_offset = datetime.now() - datetime.utcnow()  # e.g. timedelta(hours=8)
    today_start_utc = today_start_local - utc_offset
    today_end_utc = today_start_utc + timedelta(days=1)
    return today_start_utc, today_end_utc


def update_learn_history(count=1):
    """更新今日学习历史记录（按用户隔离）

    count > 0：新增学习记录
    count < 0：撤销学习记录（如将单词改回未学习时减回计数）
    """
    today = date.today()
    user_id = get_current_user_id()
    history = LearnHistory.query.filter_by(date=today, user_id=user_id).first()
    if history:
        history.count = max(0, history.count + count)
    else:
        if count > 0:
            history = LearnHistory(date=today, count=count, user_id=user_id)
            db.session.add(history)
    db.session.commit()


def update_review_accuracy(is_correct):
    """更新今日复习准确率统计（correct_count/total_count）
    参数:
        is_correct: 本次复习是否正确（rating 为 good/easy 视为正确，again/hard 视为错误）
    """
    today = date.today()
    user_id = get_current_user_id()
    history = LearnHistory.query.filter_by(date=today, user_id=user_id).first()
    if not history:
        history = LearnHistory(date=today, count=0, user_id=user_id)
        db.session.add(history)
    history.total_count = (history.total_count or 0) + 1
    if is_correct:
        history.correct_count = (history.correct_count or 0) + 1
    db.session.commit()


def get_checkin_status():
    """获取今日签到状态和连续签到天数（按用户隔离）
    签到状态基于 checked_in 字段（用户手动点击签到），而非学习记录
    连续天数逻辑：
      - 今天已签到：从今天往前数连续签到天数
      - 今天未签到但昨天签到了：从昨天往前数（显示待延续的streak，签到后+1）
      - 最后一次签到在2天前或更早：streak=0（已断签）
    """
    today = date.today()
    user_id = get_current_user_id()
    today_history = LearnHistory.query.filter_by(date=today, user_id=user_id).first()
    checked_in = today_history is not None and today_history.checked_in == True

    # 获取当前用户的已签到记录（按日期降序）
    checkin_query = LearnHistory.query.filter(LearnHistory.checked_in == True)
    if user_id:
        checkin_query = checkin_query.filter_by(user_id=user_id)
    all_checkins = checkin_query.order_by(LearnHistory.date.desc()).all()

    streak_days = 0
    if checked_in:
        # 今天已签到：从今天开始往前数
        check_date = today
    elif all_checkins and all_checkins[0].date == today - timedelta(days=1):
        # 今天未签到但昨天签到了：从昨天开始往前数（待延续的streak）
        check_date = today - timedelta(days=1)
    else:
        # 最后一次签到在2天前或更早，或者从未签到：streak=0
        return checked_in, 0

    for h in all_checkins:
        if h.date == check_date:
            streak_days += 1
            check_date = check_date - timedelta(days=1)
        elif h.date < check_date:
            break

    return checked_in, streak_days


def fill_missing_examples():
    """
    数据迁移：为没有例句的单词补充专升本例句
    同时修复旧的低质量模板例句（如 "It is important to {word} in our daily life."）
    优先使用本地词典的专升本例句库
    """
    import json

    filled = 0
    fixed = 0

    # 旧模板的特征字符串，用于检测低质量例句
    BAD_PATTERNS = [
        'It is important to',
        'Students should learn how to',
        'is very important in modern society',
        'We should pay more attention to the',
        'to learn English well.',
        'student in our class.',
        # 旧模板系统生成的特征
        'is very important to us',
        'I learned a lot from this',
        'has changed our lives',
        'I usually ',
        'her English skills',
        'She is a very ',
        'This book is very ',
        'The weather today is quite ',
        'He spoke ',
        'She always listens ',
        # 新增模板特征
        'We should do our best',
        'We should try our best',
        'plays an important role',
        'We should ',
        'It is necessary to',
        'is one of the most important',
        'in our daily life',
        'in modern society',
        'is look up to',
    ]

    def is_bad_example(examples):
        """检测是否是旧模板生成的低质量例句"""
        if not examples:
            return True
        try:
            if isinstance(examples, str):
                ex_list = json.loads(examples)
            else:
                ex_list = examples
            if not ex_list or not isinstance(ex_list, list):
                return True
            for ex in ex_list:
                en = ex.get('en', '') if isinstance(ex, dict) else ''
                for pattern in BAD_PATTERNS:
                    if pattern in en:
                        return True
        except Exception:
            return True
        return False

    # 查找所有需要修复的单词：例句为空 或 例句是旧模板生成的
    all_words = Word.query.all()

    for word in all_words:
        try:
            need_fix = False
            if not word.examples or word.examples == '[]':
                need_fix = True
            elif is_bad_example(word.examples):
                need_fix = True

            if not need_fix:
                continue

            # 先查本地词典的专升本例句库
            dict_data = dictionary_service.lookup(word.word)
            if dict_data and dict_data.get('examples'):
                # 确认不是旧模板例句
                if not is_bad_example(dict_data['examples']):
                    word.examples = dict_data['examples']
                    if not word.examples or word.examples == '[]':
                        filled += 1
                    else:
                        fixed += 1
                    continue

            # 词典没有好例句，用规则分析获取例句
            rule_data = dictionary_service.analyze_with_rules(word.word)
            if rule_data and rule_data.get('examples'):
                if not is_bad_example(rule_data['examples']):
                    word.examples = rule_data['examples']
                    if not word.examples or word.examples == '[]':
                        filled += 1
                    else:
                        fixed += 1
                    continue

            # 最后用 _get_zhuanshenben_examples 直接获取
            zs_examples = dictionary_service._get_zhuanshenben_examples(
                word.word, word.meaning or ''
            )
            if zs_examples and not is_bad_example(zs_examples):
                word.examples = zs_examples
                fixed += 1

        except Exception as e:
            print(f"[迁移] 补充例句 '{word.word}' 失败: {e}")

    if filled > 0 or fixed > 0:
        db.session.commit()
        print(f"[迁移] 补充 {filled} 个空例句，修复 {fixed} 个低质量例句")


# ==================== 单词管理API ====================

@app.route('/api/words', methods=['GET'])
def get_words():
    """
    获取所有单词
    支持查询参数过滤：
    - status: 按状态过滤（new/review/mastered）
    - search: 按单词或释义搜索
    - wordbook_id: 按单词本过滤（传 0 或不传=全部，传具体 id=该单词本）
    - starred: 按重点标记过滤（传 1=只看重点单词）
    """
    # 获取查询参数
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    starred = request.args.get('starred', '').strip()

    # 构建查询
    query = Word.query
    user_id = get_current_user_id()
    if user_id:
        query = query.filter_by(user_id=user_id)
    if status:
        query = query.filter(Word.status == status)
    if search:
        query = query.filter(
            db.or_(
                Word.word.contains(search),
                Word.meaning.contains(search),
            )
        )
    if wordbook_id:
        if wordbook_id == '0':
            # 未归类：wordbook_id 为 NULL
            query = query.filter(Word.wordbook_id.is_(None))
        else:
            try:
                query = query.filter(Word.wordbook_id == int(wordbook_id))
            except ValueError:
                pass
    if starred == '1':
        query = query.filter(Word.is_starred == True)

    # 按添加时间正序排列（先添加的排前面）
    words = query.order_by(Word.added_at.asc()).all()

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

    # 校验：必须是有效的英文单词或短语（只允许英文字母、空格、连字符）
    # 拒纯数字、中文、特殊符号等非英文内容
    import re
    # 允许：英文字母、空格（短语）、连字符（如 well-known）、撇号（如 don't）
    if not re.match(r"^[a-z][a-z\s\-'']*$", word_text):
        return jsonify({'success': False, 'error': '请输入有效的英文单词或短语（仅支持英文字母）'}), 400
    # 长度校验
    if len(word_text) < 1 or len(word_text) > 100:
        return jsonify({'success': False, 'error': '单词长度不合法'}), 400
    # 去除多余空格
    word_text = re.sub(r'\s+', ' ', word_text).strip()

    # 检查单词是否已存在（按词本去重）
    user_id = get_current_user_id()
    wordbook_id = data.get('wordbook_id')
    # 统一处理 wordbook_id：字符串 '0'、整数 0、空字符串 都视为"未归类"
    if wordbook_id is not None and wordbook_id != '' and str(wordbook_id) != '0':
        wordbook_id = int(wordbook_id)
        book = Wordbook.query.get(wordbook_id)
        if not book:
            return jsonify({'success': False, 'error': '指定的单词本不存在'}), 400
        if user_id and book.user_id and book.user_id != user_id:
            return jsonify({'success': False, 'error': '无权访问该单词本'}), 403
    else:
        wordbook_id = None
    # 按词本去重
    if wordbook_id:
        existing = Word.query.filter_by(word=word_text, user_id=user_id, wordbook_id=wordbook_id).first() if user_id else Word.query.filter_by(word=word_text, wordbook_id=wordbook_id).first()
    else:
        existing = Word.query.filter_by(word=word_text, user_id=user_id, wordbook_id=None).first() if user_id else Word.query.filter_by(word=word_text, wordbook_id=None).first()
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
        user_id=user_id,
        wordbook_id=wordbook_id,
    )
    db.session.add(word)
    db.session.commit()

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
    user_id = get_current_user_id()
    wordbook_id = data.get('wordbook_id')
    # 统一处理 wordbook_id：字符串 '0'、整数 0、空字符串 都视为"未归类"
    if wordbook_id is not None and wordbook_id != '' and str(wordbook_id) != '0':
        wordbook_id = int(wordbook_id)
        book = Wordbook.query.get(wordbook_id)
        if not book:
            return jsonify({'success': False, 'error': '指定的单词本不存在'}), 400
        if user_id and book.user_id and book.user_id != user_id:
            return jsonify({'success': False, 'error': '无权访问该单词本'}), 403
    else:
        wordbook_id = None

    added = []
    skipped = []
    failed = []

    # 第一步：过滤已存在的单词，收集待分析的单词
    pending = []  # [(word_text, analysis_or_None, is_starred)]
    for raw_word in words_list:
        # 支持 string 和 {word, starred} 两种格式
        if isinstance(raw_word, dict):
            word_text = str(raw_word.get('word', '')).strip().lower()
            is_starred = bool(raw_word.get('starred', False))
            client_meaning = str(raw_word.get('meaning', '')).strip()
        else:
            word_text = str(raw_word).strip().lower()
            is_starred = False
            client_meaning = ''
        if not word_text:
            continue
        # 校验：只允许英文单词/短语
        if not re.match(r"^[a-z][a-z\s\-'']*$", word_text):
            failed.append({'word': word_text, 'error': '非有效英文单词'})
            continue
        word_text = re.sub(r'\s+', ' ', word_text).strip()
        # 按词本去重：同一词本内不允许重复，不同词本可以有相同单词
        if wordbook_id:
            if user_id:
                existing = Word.query.filter_by(word=word_text, user_id=user_id, wordbook_id=wordbook_id).first()
            else:
                existing = Word.query.filter_by(word=word_text, wordbook_id=wordbook_id).first()
        else:
            # 未归类：只在未归类中查重
            if user_id:
                existing = Word.query.filter_by(word=word_text, user_id=user_id, wordbook_id=None).first()
            else:
                existing = Word.query.filter_by(word=word_text, wordbook_id=None).first()
        if existing:
            skipped.append(word_text)
            continue
        # 先查本地词典（毫秒级，不耗时间）
        dict_result = dictionary_service.lookup(word_text)
        if dict_result and dict_result.get('meaning') and '暂无释义' not in dict_result.get('meaning', ''):
            # 词典有有效释义，直接使用
            pending.append((word_text, dict_result, is_starred, client_meaning))
        else:
            # 词典无释义或释义为空：标记需要 AI 分析
            # 保留 client_meaning 作为兜底
            pending.append((word_text, None, is_starred, client_meaning))

    # 第二步：对本地词典没有的词，用线程池并发调 AI
    # 同时：对词典有释义但例句是模板的词，并发调 AI 生成高质量例句
    ai_pending = [(w, m) for w, a, _, m in pending if a is None]
    # 找出词典命中但例句是模板的词，需要 AI 生成例句
    example_refresh_pending = []
    for w, a, _, _ in pending:
        if a is not None and isinstance(a, dict):
            examples = a.get('examples', [])
            if dictionary_service.is_template_examples(examples):
                example_refresh_pending.append((w, a.get('meaning', '')))

    if ai_pending:
        def _analyze(args):
            word_text, client_meaning = args
            try:
                result = analyze_word_with_fallback(word_text)
                # 词典/AI 释义优先，扫描释义仅在无释义或"暂无释义"时兜底
                if client_meaning and isinstance(result, tuple):
                    meaning = result[0].get('meaning', '')
                    if not meaning or '暂无释义' in meaning:
                        result[0]['meaning'] = client_meaning
                return word_text, result
            except Exception as e:
                return word_text, e

        # 最多 5 个并发线程
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(_analyze, ai_pending))

        # 把 AI 结果合并回 pending
        ai_map = {}
        for word_text, result in results:
            ai_map[word_text] = result
        new_pending = []
        for word_text, _, starred, client_meaning in pending:
            if word_text in ai_map:
                new_pending.append((word_text, ai_map[word_text], starred, client_meaning))
            else:
                # 本地词典命中的，保持原样
                for w, a, s, m in pending:
                    if w == word_text and a is not None:
                        new_pending.append((word_text, a, s, m))
                        break
        pending = new_pending

    # 第二步B：对词典命中但例句是模板的词，用 AI 生成高质量例句
    if example_refresh_pending and ai_service.is_available():
        def _gen_examples(args):
            word_text, meaning = args
            try:
                examples = ai_service.generate_examples(word_text, meaning)
                return word_text, examples
            except Exception as e:
                return word_text, []

        with ThreadPoolExecutor(max_workers=3) as executor:
            ex_results = list(executor.map(_gen_examples, example_refresh_pending))

        # 把 AI 生成的例句合并回 pending
        ex_map = {}
        for word_text, examples in ex_results:
            if examples:
                ex_map[word_text] = examples
        if ex_map:
            new_pending = []
            for word_text, analysis, starred, client_meaning in pending:
                if word_text in ex_map and isinstance(analysis, dict):
                    analysis['examples'] = ex_map[word_text]
                new_pending.append((word_text, analysis, starred, client_meaning))
            pending = new_pending

    # 第三步：统一写入数据库
    for word_text, analysis_or_error, is_starred, _ in pending:
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
                user_id=user_id,
                is_starred=is_starred,
            )
            db.session.add(word)
            added.append(word_text)
        except Exception as e:
            failed.append({'word': word_text, 'error': str(e)})

    db.session.commit()

    return jsonify({
        'success': True,
        'added': added,
        'skipped': skipped,
        'failed': failed,
        'added_count': len(added),
        'skipped_count': len(skipped),
        'failed_count': len(failed),
    }), 201


@app.route('/api/words/<int:word_id>/refresh-examples', methods=['POST'])
def refresh_word_examples(word_id):
    """用 AI 重新生成单词的高质量例句"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403

    if not ai_service.is_available():
        return jsonify({'success': False, 'error': 'AI服务不可用，请配置API Key'}), 503

    try:
        examples = ai_service.generate_examples(word.word, word.meaning or '')
        if examples:
            word.examples = examples
            db.session.commit()
            return jsonify({'success': True, 'examples': examples})
        else:
            return jsonify({'success': False, 'error': 'AI生成例句失败，请稍后重试'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/words/refresh-all-examples', methods=['POST'])
def refresh_all_examples():
    """批量刷新所有模板例句的单词（用 AI 重新生成高质量例句）"""
    if not ai_service.is_available():
        return jsonify({'success': False, 'error': 'AI服务不可用'}), 503

    user_id = get_current_user_id()
    # 查找所有例句是模板的单词
    if user_id:
        words = Word.query.filter_by(user_id=user_id).all()
    else:
        words = Word.query.all()

    refresh_list = []
    for word in words:
        if dictionary_service.is_template_examples(word.examples):
            refresh_list.append((word, word.meaning or ''))

    if not refresh_list:
        return jsonify({'success': True, 'message': '没有需要刷新的例句', 'refreshed': 0})

    def _gen(args):
        word, meaning = args
        try:
            examples = ai_service.generate_examples(word.word, meaning)
            return word, examples
        except Exception:
            return word, []

    refreshed = 0
    # 每次处理5个，避免超时
    batch_size = 5
    for i in range(0, len(refresh_list), batch_size):
        batch = refresh_list[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(_gen, batch))
        for word, examples in results:
            if examples:
                word.examples = examples
                refreshed += 1
        db.session.commit()

    return jsonify({'success': True, 'refreshed': refreshed, 'total': len(refresh_list)})


@app.route('/api/words/<int:word_id>', methods=['GET'])
def get_word(word_id):
    """获取单个单词详情"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403
    return jsonify({'success': True, 'data': word.to_dict()})


@app.route('/api/words/lookup', methods=['GET'])
def lookup_word():
    """快速查询单词释义（从ECDICT本地词典，用于OCR扫描后补充释义）"""
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify({'success': True, 'meaning': '', 'phonetic': ''})

    result = dictionary_service.lookup(q)
    if result and result.get('meaning'):
        return jsonify({
            'success': True,
            'word': q,
            'meaning': result.get('meaning', ''),
            'phonetic': result.get('phonetic', ''),
        })
    return jsonify({'success': True, 'word': q, 'meaning': '', 'phonetic': ''})


@app.route('/api/words/<int:word_id>', methods=['PUT'])
def update_word(word_id):
    """
    更新单词信息
    可更新字段：word, phonetic, meaning, status, split_data, morph_data, examples
    """
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '无更新数据'}), 400

    # 更新允许修改的字段
    updatable_fields = ['word', 'phonetic', 'meaning', 'status',
                        'split_data', 'morph_data', 'examples', 'word_type',
                        'wordbook_id']
    for field in updatable_fields:
        if field in data:
            val = data[field]
            if field == 'wordbook_id':
                # 允许设为 None（移出单词本）或指定单词本 ID
                if val is None or val == '' or val == 0:
                    word.wordbook_id = None
                else:
                    # 验证单词本存在且属于当前用户
                    book = Wordbook.query.get(val)
                    if book and (not user_id or not book.user_id or book.user_id == user_id):
                        word.wordbook_id = book.id
                    else:
                        return jsonify({'success': False, 'error': '单词本不存在或无权访问'}), 400
            elif field == 'status':
                old_status = word.status
                old_last_review = word.last_review
                word.status = val
                # 状态变更时同步更新 last_review 和 LearnHistory，确保今日已学统计准确
                if val == 'new':
                    # 改回未学习：如果 last_review 是今天，减回 LearnHistory 计数
                    if old_last_review:
                        today_start_utc, today_end_utc = get_today_utc_range()
                        if today_start_utc <= old_last_review < today_end_utc and old_status != 'new':
                            update_learn_history(-1)
                    # 清空 last_review，不计入今日已学
                    word.last_review = None
                    word.next_review = None
                    word.review_count = 0
                elif val in ('review', 'mastered') and not word.last_review:
                    # 首次学习：设置 last_review 为当前时间，增加 LearnHistory 计数
                    word.last_review = datetime.utcnow()
                    if old_status == 'new':
                        update_learn_history(1)
            else:
                setattr(word, field, val)

    db.session.commit()
    return jsonify({'success': True, 'data': word.to_dict()})


@app.route('/api/words/<int:word_id>', methods=['DELETE'])
def delete_word(word_id):
    """删除单词"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403

    db.session.delete(word)
    db.session.commit()
    return jsonify({'success': True, 'message': '单词已删除'})


@app.route('/api/words/<int:word_id>/star', methods=['POST'])
def toggle_word_star(word_id):
    """切换单词重点标记"""
    word = Word.query.get(word_id)
    if not word:
        return jsonify({'success': False, 'error': '单词不存在'}), 404
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403

    word.is_starred = not word.is_starred
    db.session.commit()
    return jsonify({'success': True, 'is_starred': word.is_starred})


@app.route('/api/words/batch-update-status', methods=['POST'])
def batch_update_status():
    """批量更新单词状态
    请求体: {"word_ids": [1,2,3], "status": "new"}
    支持状态: new, review, mastered
    """
    data = request.get_json()
    if not data or 'word_ids' not in data or 'status' not in data:
        return jsonify({'success': False, 'error': '缺少 word_ids 或 status 参数'}), 400

    word_ids = data['word_ids']
    new_status = data['status']

    if not isinstance(word_ids, list) or len(word_ids) == 0:
        return jsonify({'success': False, 'error': 'word_ids 必须是非空列表'}), 400

    if new_status not in ('new', 'review', 'mastered'):
        return jsonify({'success': False, 'error': 'status 必须是 new/review/mastered'}), 400

    user_id = get_current_user_id()
    now = datetime.utcnow()
    today_start_utc, today_end_utc = get_today_utc_range()
    updated = 0
    errors = 0
    learn_history_delta = 0  # 累积 LearnHistory 增减量
    for wid in word_ids:
        word = Word.query.get(wid)
        if not word:
            errors += 1
            continue
        if user_id and word.user_id and word.user_id != user_id:
            errors += 1
            continue
        old_status = word.status
        old_last_review = word.last_review
        word.status = new_status
        # 状态变更时同步更新 last_review 和 LearnHistory
        if new_status == 'new':
            # 改回未学习：如果 last_review 是今天，减回 LearnHistory 计数
            if old_last_review and today_start_utc <= old_last_review < today_end_utc and old_status != 'new':
                learn_history_delta -= 1
            # 清空学习记录，不计入今日已学
            word.last_review = None
            word.next_review = None
            word.review_count = 0
        elif new_status in ('review', 'mastered') and not word.last_review:
            # 首次学习：设置 last_review
            word.last_review = now
            if old_status == 'new':
                learn_history_delta += 1
        updated += 1

    # 批量更新 LearnHistory（一次提交，避免循环内多次 commit）
    if learn_history_delta != 0:
        update_learn_history(learn_history_delta)

    db.session.commit()
    return jsonify({
        'success': True,
        'updated': updated,
        'errors': errors,
        'message': f'成功更新 {updated} 个单词状态'
    })


@app.route('/api/words/batch-move', methods=['POST'])
def batch_move_words():
    """批量移动单词到指定词本
    请求体: {"word_ids": [1,2,3], "wordbook_id": 5}
    wordbook_id 为 null/0/"" 时移至未归类
    """
    data = request.get_json()
    if not data or 'word_ids' not in data:
        return jsonify({'success': False, 'error': '缺少 word_ids 参数'}), 400

    word_ids = data['word_ids']
    if not isinstance(word_ids, list) or len(word_ids) == 0:
        return jsonify({'success': False, 'error': 'word_ids 必须是非空列表'}), 400

    wb_id_raw = data.get('wordbook_id')
    user_id = get_current_user_id()

    # 验证目标词本
    if wb_id_raw is None or wb_id_raw == '' or wb_id_raw == 0:
        target_wb_id = None
    else:
        target_wb_id = int(wb_id_raw)
        book = Wordbook.query.get(target_wb_id)
        if not book:
            return jsonify({'success': False, 'error': '单词本不存在'}), 400
        if user_id and book.user_id and book.user_id != user_id:
            return jsonify({'success': False, 'error': '无权访问该单词本'}), 403

    moved = 0
    errors = 0
    for wid in word_ids:
        word = Word.query.get(wid)
        if not word:
            errors += 1
            continue
        if user_id and word.user_id and word.user_id != user_id:
            errors += 1
            continue
        word.wordbook_id = target_wb_id
        moved += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'moved': moved,
        'errors': errors,
        'message': f'成功移动 {moved} 个单词'
    })


@app.route('/api/words/batch-delete', methods=['POST'])
def batch_delete_words():
    """批量删除单词
    请求体: {"word_ids": [1,2,3]}
    """
    data = request.get_json()
    if not data or 'word_ids' not in data:
        return jsonify({'success': False, 'error': '缺少 word_ids 参数'}), 400

    word_ids = data['word_ids']
    if not isinstance(word_ids, list) or len(word_ids) == 0:
        return jsonify({'success': False, 'error': 'word_ids 必须是非空列表'}), 400

    user_id = get_current_user_id()
    deleted = 0
    errors = 0
    for wid in word_ids:
        word = Word.query.get(wid)
        if not word:
            errors += 1
            continue
        if user_id and word.user_id and word.user_id != user_id:
            errors += 1
            continue
        db.session.delete(word)
        deleted += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'deleted': deleted,
        'errors': errors,
        'message': f'成功删除 {deleted} 个单词'
    })


@app.route('/api/words/distractors', methods=['GET'])
def get_distractors():
    """获取随机干扰项释义（用于看词选义模式）
    可通过 ?wordbook_id= 按词书过滤
    可通过 ?exclude=1,2,3 排除指定ID
    可通过 ?limit= 控制数量（默认3）
    """
    user_id = get_current_user_id()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    limit = request.args.get('limit', 3, type=int)

    query = Word.query.filter(Word.meaning.isnot(None), Word.meaning != '')
    if user_id:
        query = query.filter_by(user_id=user_id)
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter_by(wordbook_id=int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter_by(wordbook_id=None)

    exclude_ids = request.args.get('exclude', '').strip()
    if exclude_ids:
        try:
            id_list = [int(x) for x in exclude_ids.split(',') if x.strip()]
            if id_list:
                query = query.filter(~Word.id.in_(id_list))
        except ValueError:
            pass

    words = query.order_by(db.func.random()).limit(limit).all()
    return jsonify({
        'success': True,
        'data': [{'word': w.word, 'meaning': w.meaning} for w in words],
    })


def _levenshtein(s1, s2):
    """计算两个字符串的编辑距离（Levenshtein distance）"""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _word_similarity(target, candidate):
    """
    计算两个单词的相似度分数（0~1，越高越相似）
    综合考虑：编辑距离、共同前缀、共同后缀、长度比
    """
    target = target.lower().strip()
    candidate = candidate.lower().strip()
    if target == candidate:
        return 0.0  # 完全相同不计

    # 编辑距离
    dist = _levenshtein(target, candidate)
    max_len = max(len(target), len(candidate))
    if max_len == 0:
        return 0.0

    # 基础相似度：1 - 编辑距离/最大长度
    base_sim = 1.0 - (dist / max_len)

    # 共同前缀长度
    prefix_len = 0
    for i in range(min(len(target), len(candidate))):
        if target[i] == candidate[i]:
            prefix_len += 1
        else:
            break

    # 共同后缀长度
    suffix_len = 0
    for i in range(1, min(len(target), len(candidate)) + 1):
        if target[-i] == candidate[-i]:
            suffix_len += 1
        else:
            break

    # 前缀和后缀加权（长前缀/后缀说明词形很像）
    prefix_bonus = prefix_len / max_len * 0.3
    suffix_bonus = suffix_len / max_len * 0.2

    # 长度接近加分
    len_ratio = min(len(target), len(candidate)) / max_len
    len_bonus = len_ratio * 0.1

    score = base_sim + prefix_bonus + suffix_bonus + len_bonus

    # 编辑距离为1-2的词优先（如 suppose/propose/oppose）
    if dist <= 2:
        score += 0.3
    elif dist <= 3:
        score += 0.15

    return score


@app.route('/api/words/similar-distractors', methods=['GET'])
def get_similar_distractors():
    """获取形近词干扰项（用于看词选义模式）
    根据目标单词的拼写相似度，从词书中找出最容易混淆的词作为干扰项
    可通过 ?word= 指定目标单词
    可通过 ?wordbook_id= 按词书过滤
    可通过 ?exclude=1,2,3 排除指定ID
    可通过 ?limit= 控制数量（默认3）
    """
    user_id = get_current_user_id()
    target_word = request.args.get('word', '').strip()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    limit = request.args.get('limit', 3, type=int)

    if not target_word:
        return jsonify({'success': False, 'error': '缺少 word 参数'}), 400

    # 查询词书内所有有释义的词（排除目标词本身）
    query = Word.query.filter(
        Word.meaning.isnot(None),
        Word.meaning != '',
        Word.word != target_word,
    )
    if user_id:
        query = query.filter_by(user_id=user_id)
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter_by(wordbook_id=int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter_by(wordbook_id=None)

    exclude_ids = request.args.get('exclude', '').strip()
    if exclude_ids:
        try:
            id_list = [int(x) for x in exclude_ids.split(',') if x.strip()]
            if id_list:
                query = query.filter(~Word.id.in_(id_list))
        except ValueError:
            pass

    all_words = query.all()

    if not all_words:
        return jsonify({'success': True, 'data': []})

    # 计算每个词与目标词的相似度，排序取最相似的
    scored = []
    for w in all_words:
        score = _word_similarity(target_word, w.word)
        scored.append((w, score))

    # 按相似度降序排序
    scored.sort(key=lambda x: x[1], reverse=True)

    # 取前 limit 个最相似的词
    similar_words = scored[:limit]

    # 如果相似词不够，用随机词补充
    if len(similar_words) < limit:
        used_ids = {w.id for w, _ in similar_words}
        remaining = [w for w in all_words if w.id not in used_ids]
        import random as _random
        _random.shuffle(remaining)
        for w in remaining[:limit - len(similar_words)]:
            similar_words.append((w, 0.0))

    return jsonify({
        'success': True,
        'data': [{'word': w.word, 'meaning': w.meaning} for w, _ in similar_words],
    })


@app.route('/api/words/check_duplicate', methods=['GET'])
def check_duplicate_word():
    """检查单词是否已在指定单词本中存在
    查询参数:
    - word: 要检查的单词文本（必填）
    - wordbook_id: 单词本 ID（不传或 0=未归类，具体 id=该单词本）
    返回: {"exists": true/false, "word": {...}|null}
    """
    word_text = (request.args.get('word', '') or '').strip().lower()
    wordbook_id_raw = (request.args.get('wordbook_id', '') or '').strip()

    if not word_text:
        return jsonify({'success': False, 'error': '请提供 word 参数'}), 400

    # 规范化空白字符，与 add_word 保持一致
    word_text = re.sub(r'\s+', ' ', word_text).strip()

    user_id = get_current_user_id()

    # 解析 wordbook_id：空/0 = 未归类（NULL），具体数字 = 该单词本
    wordbook_id = None
    if wordbook_id_raw and wordbook_id_raw != '0':
        try:
            wordbook_id = int(wordbook_id_raw)
        except ValueError:
            return jsonify({'success': False, 'error': 'wordbook_id 必须是整数'}), 400

    # 按词本去重查询（与 add_word 的查重逻辑一致）
    query = Word.query.filter(Word.word == word_text)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if wordbook_id is None:
        query = query.filter(Word.wordbook_id.is_(None))
    else:
        query = query.filter_by(wordbook_id=wordbook_id)

    existing = query.first()
    return jsonify({
        'success': True,
        'data': {
            'exists': existing is not None,
            'word': existing.to_dict() if existing else None,
        },
    })


# ==================== 文档导入API ====================

ALLOWED_DOC_EXT = {'txt', 'docx', 'xlsx', 'xls', 'pdf'}
MAX_DOC_SIZE = 20 * 1024 * 1024  # 20MB


# ==================== 单词本API ====================

@app.route('/api/wordbooks', methods=['GET'])
def list_wordbooks():
    """获取所有单词本列表（含单词数）"""
    query = Wordbook.query
    user_id = get_current_user_id()
    if user_id:
        query = query.filter_by(user_id=user_id)
    books = query.order_by(Wordbook.created_at.desc()).all()
    result = []
    for b in books:
        d = b.to_dict()
        # 按用户隔离统计词本内单词数（修复：之前未过滤 user_id 导致显示全局数据）
        words_query = Word.query.filter_by(wordbook_id=b.id)
        if user_id:
            words_query = words_query.filter_by(user_id=user_id)
        words = words_query.all()
        d['word_count'] = len(words)
        d['learned_count'] = sum(1 for w in words if w.status != 'new')
        d['new_count'] = sum(1 for w in words if w.status == 'new')
        result.append(d)
    return jsonify({
        'success': True,
        'data': result
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
    book = Wordbook(name=name, description=description, color=color, user_id=get_current_user_id())
    db.session.add(book)
    db.session.commit()
    return jsonify({'success': True, 'data': book.to_dict()})


@app.route('/api/wordbooks/<int:book_id>', methods=['PUT'])
def update_wordbook(book_id):
    """更新单词本"""
    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    user_id = get_current_user_id()
    if user_id and book.user_id and book.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403
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
    user_id = get_current_user_id()
    if user_id and book.user_id and book.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403
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
    user_id = get_current_user_id()
    if user_id and book.user_id and book.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403
    # 按用户隔离查询单词（修复：之前未过滤 user_id 导致显示其他用户的单词）
    words_query = Word.query.filter_by(wordbook_id=book_id)
    if user_id:
        words_query = words_query.filter_by(user_id=user_id)
    words = words_query.order_by(Word.added_at.asc()).all()
    return jsonify({
        'success': True,
        'data': {
            'wordbook': book.to_dict(),
            'words': [w.to_dict() for w in words]
        }
    })


# ==================== 全局词本（分享/导入） ====================

@app.route('/api/global-wordbooks', methods=['GET'])
def list_global_wordbooks():
    """获取所有已分享到全局的单词本（所有用户可查看）"""
    err = require_login()
    if err:
        return err

    books = Wordbook.query.filter_by(is_shared=True).order_by(Wordbook.shared_at.desc()).all()
    result = []
    for b in books:
        d = b.to_dict(include_owner=True)
        # 全局词本：按词本所有者的 user_id 统计单词数
        owner_words = Word.query.filter_by(wordbook_id=b.id)
        if b.user_id:
            owner_words = owner_words.filter_by(user_id=b.user_id)
        words = owner_words.all()
        d['word_count'] = len(words)
        d['learned_count'] = sum(1 for w in words if w.status != 'new')
        d['new_count'] = sum(1 for w in words if w.status == 'new')
        # 标记当前用户是否是所有者
        d['is_owner'] = (b.user_id == get_current_user_id())
        result.append(d)
    return jsonify({'success': True, 'data': result})


@app.route('/api/wordbooks/<int:book_id>/share', methods=['POST'])
def share_wordbook(book_id):
    """分享单词本到全局词本（仅所有者可操作）"""
    err = require_login()
    if err:
        return err

    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404

    user_id = get_current_user_id()
    if not book.user_id or book.user_id != user_id:
        return jsonify({'success': False, 'error': '无权操作他人的单词本'}), 403

    if book.is_shared:
        return jsonify({'success': True, 'message': '该单词本已分享', 'data': book.to_dict()})

    book.is_shared = True
    book.shared_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': '单词本已分享到全局词本', 'data': book.to_dict()})


@app.route('/api/wordbooks/<int:book_id>/share', methods=['DELETE'])
def unshare_wordbook(book_id):
    """取消分享单词本（仅所有者可操作）"""
    err = require_login()
    if err:
        return err

    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404

    user_id = get_current_user_id()
    if not book.user_id or book.user_id != user_id:
        return jsonify({'success': False, 'error': '无权操作他人的单词本'}), 403

    book.is_shared = False
    book.shared_at = None
    db.session.commit()
    return jsonify({'success': True, 'message': '已取消分享'})


@app.route('/api/global-wordbooks/<int:book_id>/words', methods=['GET'])
def get_global_wordbook_words(book_id):
    """获取全局词本中的单词列表（所有登录用户可查看）"""
    err = require_login()
    if err:
        return err

    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    if not book.is_shared:
        return jsonify({'success': False, 'error': '该单词本未分享'}), 403

    words = Word.query.filter_by(wordbook_id=book_id).order_by(Word.added_at.desc()).all()
    return jsonify({
        'success': True,
        'data': {
            'wordbook': book.to_dict(include_count=True, include_owner=True),
            'words': [w.to_dict() for w in words]
        }
    })


@app.route('/api/global-wordbooks/<int:book_id>/import', methods=['POST'])
def import_global_words(book_id):
    """从全局词本导入单词到自己的词本
    请求体: {"word_ids": [1,2,3], "target_wordbook_id": 5}
    word_ids 为空时导入全部单词
    """
    err = require_login()
    if err:
        return err

    book = Wordbook.query.get(book_id)
    if not book:
        return jsonify({'success': False, 'error': '单词本不存在'}), 404
    if not book.is_shared:
        return jsonify({'success': False, 'error': '该单词本未分享'}), 403

    data = request.get_json() or {}
    word_ids = data.get('word_ids', [])
    target_wordbook_id = data.get('target_wordbook_id')

    user_id = get_current_user_id()

    # 验证目标词本归属
    if target_wordbook_id:
        target_book = Wordbook.query.get(target_wordbook_id)
        if not target_book or target_book.user_id != user_id:
            return jsonify({'success': False, 'error': '目标词本无效'}), 400

    # 获取源单词
    if word_ids:
        source_words = Word.query.filter(
            Word.id.in_(word_ids),
            Word.wordbook_id == book_id
        ).all()
    else:
        source_words = Word.query.filter_by(wordbook_id=book_id).all()

    # 导入：为当前用户创建单词副本（如已存在同名单词则跳过）
    added = 0
    skipped = 0
    for sw in source_words:
        existing = Word.query.filter_by(word=sw.word, user_id=user_id).first()
        if existing:
            skipped += 1
            continue
        new_word = Word(
            word=sw.word,
            phonetic=sw.phonetic or '',
            meaning=sw.meaning or '',
            status='new',
            split_data=sw.split_data or [],
            morph_data=sw.morph_data or [],
            examples=sw.examples or [],
            word_type=sw.word_type or '基础词',
            mnemonic=sw.mnemonic or '',
            tenses=sw.tenses,
            wordbook_id=target_wordbook_id if target_wordbook_id else None,
            user_id=user_id,
        )
        db.session.add(new_word)
        added += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'added': added,
        'skipped': skipped,
        'message': f'导入完成：新增 {added} 个单词' + (f'，跳过 {skipped} 个已存在' if skipped else '')
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
    user_id = get_current_user_id()
    wordbook_id = data.get('wordbook_id')
    if wordbook_id is not None:
        # 校验单词本存在
        book = Wordbook.query.get(wordbook_id)
        if not book:
            return jsonify({'success': False, 'error': '指定的单词本不存在'}), 400
        if user_id and book.user_id and book.user_id != user_id:
            return jsonify({'success': False, 'error': '无权访问该单词本'}), 403

    added = []
    skipped = []
    failed = []

    pending = []
    for raw_word in words_list:
        word_text = str(raw_word).strip().lower()
        if not word_text:
            continue
        if user_id:
            existing = Word.query.filter_by(word=word_text, user_id=user_id).first()
        else:
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
                user_id=user_id,
            )
            db.session.add(word)
            added.append(word_text)
        except Exception as e:
            failed.append(word_text)

    try:
        db.session.commit()
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
        words = ocr_service.recognize(image_path=filepath, user_id=user_id, role=user_role)
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
    OCR识别并直接添加到词库（并发优化版）
    上传图片 -> OCR识别 -> 词典优先+AI并发分析 -> 批量写入数据库
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

        # 2. 预处理：去重、过滤已存在的词
        added = []
        skipped = []
        failed = []
        user_id = get_current_user_id()
        wordbook_id = request.form.get('wordbook_id', type=int)

        pending = []  # [(word_text, dict_result_or_None)]
        for raw_word in words:
            word_text = raw_word.strip().lower()
            if not word_text:
                continue
            # 校验：只允许英文单词
            if not re.match(r"^[a-z][a-z\s\-']*$", word_text):
                failed.append({'word': word_text, 'error': '非有效英文单词'})
                continue
            # 去重
            if user_id:
                existing = Word.query.filter_by(word=word_text, user_id=user_id).first()
            else:
                existing = Word.query.filter_by(word=word_text).first()
            if existing:
                skipped.append(word_text)
                continue
            # 先查本地词典（毫秒级）
            dict_result = dictionary_service.lookup(word_text)
            if dict_result:
                pending.append((word_text, dict_result))
            else:
                pending.append((word_text, None))

        # 3. 对词典没有的词，用线程池并发调 AI
        ai_pending = [w for w, a in pending if a is None]
        if ai_pending:
            def _analyze(word_text):
                try:
                    return word_text, analyze_word_with_fallback(word_text)
                except Exception as e:
                    return word_text, e

            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(_analyze, ai_pending))

            ai_map = {}
            for word_text, result in results:
                ai_map[word_text] = result
        else:
            ai_map = {}

        # 4. 统一写入数据库
        for word_text, dict_result in pending:
            if dict_result is not None:
                analysis = dict_result
            elif word_text in ai_map:
                result = ai_map[word_text]
                if isinstance(result, Exception):
                    failed.append({'word': word_text, 'error': str(result)})
                    continue
                analysis = result[0] if isinstance(result, tuple) else result
            else:
                failed.append({'word': word_text, 'error': '分析失败'})
                continue

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
                    user_id=user_id,
                    wordbook_id=wordbook_id,
                )
                db.session.add(word)
                added.append(word_text)
            except Exception as e:
                failed.append({'word': word_text, 'error': str(e)})

        db.session.commit()

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


@app.route('/api/ocr/scan-preview', methods=['POST'])
def ocr_scan_preview():
    """
    极速扫描预览接口：上传图片 -> 百度OCR提取文字 -> ECDICT即时查释义
    不添加到词库，仅返回识别结果供用户确认（与AI识别接口返回格式一致）
    速度比AI视觉识别快5-10倍（OCR ~2s/张 vs AI ~20s/张）
    """
    if 'image' not in request.files:
        return jsonify({'success': False, 'error': '请上传图片文件'}), 400

    file = request.files['image']
    print(f"[OCR极速] 收到请求, filename={file.filename}")
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'}), 400

    if not allowed_file(file.filename):
        print(f"[OCR极速] 文件格式不支持: {file.filename}")
        return jsonify({'success': False, 'error': f'不支持的文件格式: {file.filename}'}), 400

    # 获取当前用户信息（用于OCR限额控制）
    current_user = get_current_user()
    user_id = current_user.id if current_user else None
    user_role = current_user.role if current_user else 'user'

    # 检查OCR服务是否可用（含限额检查）
    if not ocr_service.is_available(user_id=user_id, role=user_role):
        # 区分是未配置还是超限
        if not (ocr_service.api_key and ocr_service.secret_key):
            return jsonify({
                'success': False,
                'error': '百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY',
            }), 503
        # 超限
        global_count, user_counts = ocr_service._get_usage()
        if global_count >= ocr_service.GLOBAL_MONTHLY_LIMIT:
            msg = f'当月全局OCR识别次数已达上限（{ocr_service.GLOBAL_MONTHLY_LIMIT}次），请切换到AI精准模式'
        else:
            msg = f'您当月OCR识别次数已达上限（{ocr_service.USER_MONTHLY_LIMIT}次），请切换到AI精准模式'
        return jsonify({'success': False, 'error': msg, 'quota_exceeded': True}), 429

    # 确保上传目录存在
    upload_folder = Config.UPLOAD_FOLDER
    os.makedirs(upload_folder, exist_ok=True)

    # 安全保存文件
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    filepath = os.path.join(upload_folder, timestamp + filename)
    file.save(filepath)
    print(f"[OCR极速] 文件已保存: {filepath}")

    try:
        # 1. 百度OCR提取文字（快速，~1-3秒）
        print(f"[OCR极速] 开始OCR识别...")
        words = ocr_service.recognize(image_path=filepath)
        print(f"[OCR极速] OCR返回: {words}")

        if not words:
            return jsonify({'success': True, 'words': [], 'count': 0})

        # 2. ECDICT即时查释义（毫秒级）
        result_words = []
        seen = set()

        def _try_word(word_text):
            """查词典：有释义返回( True, meaning)，无释义返回(False, None)"""
            word_text = word_text.strip().lower()
            if not word_text or word_text in seen:
                return False, None
            if not re.match(r"^[a-z][a-z\s\-']*$", word_text):
                return False, None

            meaning = ''
            try:
                dict_result = dictionary_service.lookup(word_text)
                if dict_result and dict_result.get('meaning') and '暂无释义' not in dict_result.get('meaning', ''):
                    meaning = dict_result['meaning']
                    if '\n' in meaning:
                        meaning = meaning.split('\n')[0]
                    if len(meaning) > 80:
                        meaning = meaning[:80] + '...'
            except Exception:
                pass

            return bool(meaning), meaning

        for raw_word in words:
            word_text = raw_word.strip().lower()
            if not word_text:
                continue

            # 保持OCR原始识别结果，不拆分多词
            # 释义查到就用，查不到就空着，让用户自行处理
            if word_text in seen:
                continue
            seen.add(word_text)
            found, meaning = _try_word(word_text)
            result_words.append({'word': word_text, 'meaning': meaning if found else ''})

        print(f"[OCR极速] 识别完成: {len(result_words)} 个单词")
        return jsonify({
            'success': True,
            'words': result_words,
            'count': len(result_words),
        })
    except Exception as e:
        import traceback
        print(f"[OCR极速] 异常: {e}")
        traceback.print_exc()
        # 如果是限额超出的错误，返回429状态码
        if '上限' in str(e) or '超限' in str(e):
            return jsonify({'success': False, 'error': str(e), 'quota_exceeded': True}), 429
        return jsonify({'success': False, 'error': f'OCR识别失败: {str(e)}'}), 500
    finally:
        # 删除临时文件
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route('/api/ocr/usage', methods=['GET'])
def ocr_usage():
    """查询当月OCR识别用量（全局+当前用户个人）"""
    current_user = get_current_user()
    user_id = current_user.id if current_user else None
    user_role = current_user.role if current_user else 'user'
    usage = ocr_service.get_usage_info(user_id=user_id, role=user_role)
    return jsonify({'success': True, **usage})


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
    """获取统计数据：各状态单词数量、今日复习数、学习历史等
    可通过 ?wordbook_id= 按词书过滤（不传=全部，0=未归类，具体id=该词书）
    """
    user_id = get_current_user_id()
    wordbook_id = request.args.get('wordbook_id', '').strip()

    # 构建词书过滤条件（复用于所有查询）
    wb_filter = None
    if wordbook_id:
        if wordbook_id == '0':
            wb_filter = Word.wordbook_id.is_(None)
        else:
            try:
                wb_filter = Word.wordbook_id == int(wordbook_id)
            except ValueError:
                pass

    # 各状态单词数量（按词书过滤）
    base = Word.query
    if user_id:
        base = base.filter_by(user_id=user_id)
    if wb_filter is not None:
        base = base.filter(wb_filter)
    total = base.count()
    new_count = base.filter_by(status='new').count()
    review_count = base.filter_by(status='review').count()
    mastered_count = base.filter_by(status='mastered').count()

    # 今日待复习数量（已到期的单词，含 review 和 mastered 防遗忘回顾）
    now = datetime.utcnow()
    review_query = Word.query.filter(
        Word.next_review.isnot(None),
        Word.next_review <= now,
        Word.last_review.isnot(None),
        Word.status.in_(['review', 'mastered']),
    )
    if user_id:
        review_query = review_query.filter_by(user_id=user_id)
    if wb_filter is not None:
        review_query = review_query.filter(wb_filter)
    today_review = review_query.count()

    # 今日已学数量：实时统计今天学习的单词（last_review在今天且状态不是new）
    # 使用时区修正的 UTC 范围，确保本地午夜→UTC 的正确转换
    today_start_utc, today_end_utc = get_today_utc_range()
    learned_query = Word.query.filter(
        Word.last_review.isnot(None),
        Word.last_review >= today_start_utc,
        Word.last_review < today_end_utc,
        Word.status != 'new',
    )
    if user_id:
        learned_query = learned_query.filter_by(user_id=user_id)
    if wb_filter is not None:
        learned_query = learned_query.filter(wb_filter)
    today_learned = learned_query.count()

    # 本地日期（用于 LearnHistory 按天统计）
    today = date.today()

    # 最近7天学习历史（按用户隔离）
    seven_days_ago = today - timedelta(days=6)
    history_query = LearnHistory.query.filter(LearnHistory.date >= seven_days_ago)
    if user_id:
        history_query = history_query.filter_by(user_id=user_id)
    history = history_query.order_by(LearnHistory.date).all()

    history_data = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        count = 0
        for h in history:
            if h.date == d:
                count = h.count
                break
        history_data.append({'date': d.isoformat(), 'count': count})

    # 计算 streak_days（连续签到天数）：使用签到状态计算
    checked_in, streak_days = get_checkin_status()

    # 学习热力图数据：最近 35 天（5 周）的学习记录（按用户隔离）
    thirty_five_days_ago = today - timedelta(days=34)
    heatmap_query = LearnHistory.query.filter(LearnHistory.date >= thirty_five_days_ago)
    if user_id:
        heatmap_query = heatmap_query.filter_by(user_id=user_id)
    heatmap_history = heatmap_query.order_by(LearnHistory.date).all()
    heatmap_data = []
    for i in range(35):
        d = thirty_five_days_ago + timedelta(days=i)
        count = 0
        for h in heatmap_history:
            if h.date == d:
                count = h.count
                break
        heatmap_data.append({'date': d.isoformat(), 'count': count})

    daily_goal_val = get_setting().daily_goal or 20
    # 今日待学：每日目标减去今日已学，最低为0
    pending_today = max(0, daily_goal_val - today_learned)

    return jsonify({
        'success': True,
        'data': {
            'total': total,
            'new': new_count,
            'review': review_count,
            'mastered': mastered_count,
            'today_review': today_review,
            'today_learned': today_learned,
            'pending_today': pending_today,
            'daily_goal': daily_goal_val,
            'history': history_data,
            'streak_days': streak_days,
            'checked_in': checked_in,
            'learn_history': heatmap_data,
        }
    })


@app.route('/api/stats/enhanced', methods=['GET'])
def get_enhanced_stats():
    """增强统计：准确率趋势、平均每日学习时长、难度分布、遗忘曲线
    可选查询参数:
    - daily_times: 前端 localStorage 中的每日学习时长（JSON 数组，如 [{"date":"2024-01-01","minutes":30}]）
                   未提供时回退到 learn_sessions 表数据
    """
    user_id = get_current_user_id()
    today = date.today()
    seven_days_ago = today - timedelta(days=6)

    # ---------- 1. accuracy_trend: 最近 7 天准确率 ----------
    history_query = LearnHistory.query.filter(LearnHistory.date >= seven_days_ago)
    if user_id:
        history_query = history_query.filter_by(user_id=user_id)
    history = history_query.order_by(LearnHistory.date).all()
    accuracy_trend = []
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        correct = 0
        total_rev = 0
        learned = 0
        for h in history:
            if h.date == d:
                correct = h.correct_count or 0
                total_rev = h.total_count or 0
                learned = h.count or 0
                break
        accuracy = round(correct / total_rev * 100, 1) if total_rev else 0.0
        accuracy_trend.append({
            'date': d.isoformat(),
            'accuracy': accuracy,
            'correct': correct,
            'total': total_rev,
            'learned': learned,
        })

    # ---------- 2. avg_daily_time: 平均每日学习时长（分钟）----------
    # 优先使用前端 localStorage 传入的数据，否则回退到 learn_sessions 表
    avg_daily_time = 0.0
    daily_time_detail = []
    daily_times_param = request.args.get('daily_times', '').strip()
    frontend_times = None
    if daily_times_param:
        import json as _json
        try:
            frontend_times = _json.loads(daily_times_param)
        except (ValueError, TypeError):
            frontend_times = None

    # 构建最近 7 天的时长映射
    time_map = {}
    if frontend_times and isinstance(frontend_times, list):
        for item in frontend_times:
            if isinstance(item, dict) and item.get('date'):
                try:
                    time_map[item['date']] = float(item.get('minutes', 0) or 0)
                except (ValueError, TypeError):
                    continue
    else:
        # 回退：从 learn_sessions 表按日期汇总
        sessions = LearnSession.query.filter(
            LearnSession.date >= seven_days_ago
        )
        if user_id:
            sessions = sessions.filter_by(user_id=user_id)
        sessions = sessions.all()
        for s in sessions:
            key = s.date.isoformat() if s.date else None
            if key:
                time_map[key] = time_map.get(key, 0) + (s.duration_minutes or 0)

    total_minutes = 0.0
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        minutes = time_map.get(d.isoformat(), 0.0)
        daily_time_detail.append({'date': d.isoformat(), 'minutes': round(minutes, 1)})
        total_minutes += minutes
    avg_daily_time = round(total_minutes / 7, 1) if total_minutes else 0.0

    # ---------- 3. difficulty_distribution: 按 review_count 分档统计单词数 ----------
    # 0-2: easy, 3-5: medium, 6+: hard
    base_query = Word.query
    if user_id:
        base_query = base_query.filter_by(user_id=user_id)
    easy_count = base_query.filter(Word.review_count <= 2).count()
    medium_count = base_query.filter(
        Word.review_count >= 3, Word.review_count <= 5
    ).count()
    hard_count = base_query.filter(Word.review_count >= 6).count()
    difficulty_distribution = {
        'easy': easy_count,
        'medium': medium_count,
        'hard': hard_count,
    }

    # ---------- 4. forgetting_curve: 未来 7 天每日待复习单词数预测 ----------
    # 基于 next_review 日期统计未来 7 天每天到期需要复习的单词数
    curve = []
    for i in range(7):
        day = today + timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day)
        day_end = day_start + timedelta(days=1)
        q = Word.query.filter(
            Word.next_review.isnot(None),
            Word.next_review >= day_start,
            Word.next_review < day_end,
        )
        if user_id:
            q = q.filter_by(user_id=user_id)
        curve.append({
            'date': day.isoformat(),
            'review_count': q.count(),
        })

    return jsonify({
        'success': True,
        'data': {
            'accuracy_trend': accuracy_trend,
            'avg_daily_time': avg_daily_time,
            'daily_time_detail': daily_time_detail,
            'difficulty_distribution': difficulty_distribution,
            'forgetting_curve': curve,
        },
    })


# ==================== 复习API（艾宾浩斯遗忘曲线） ====================

@app.route('/api/review/today', methods=['GET'])
def get_today_review():
    """
    获取复习队列：返回已到期需要复习的单词（next_review <= now）
    采用艾宾浩斯遗忘曲线算法，只返回真正到期的单词，而非所有学过的词。
    
    筛选条件：
    - last_review 不为空（已学过）
    - next_review <= 当前时间（已到期）
    - status 为 review 或 mastered（mastered 词在防遗忘模式下也会到期）
    
    排序：按 next_review 升序（最该复习的、过期最久的排前面）
    
    可通过 ?wordbook_id= 按词书过滤
    可通过 ?random=1 随机排序
    可通过 ?limit= 控制数量
    可通过 ?starred=1 仅复习重点单词
    """
    setting = get_setting()
    user_id = get_current_user_id()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    random_mode = request.args.get('random', '').strip() == '1'
    now = datetime.utcnow()

    # 构建查询：已学过且到期的单词
    base_query = Word.query.filter(
        Word.last_review.isnot(None),
        Word.next_review.isnot(None),
        Word.next_review <= now,
        Word.status.in_(['review', 'mastered']),
    )
    if user_id:
        base_query = base_query.filter_by(user_id=user_id)
    if wordbook_id and wordbook_id != '0':
        try:
            base_query = base_query.filter_by(wordbook_id=int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        base_query = base_query.filter_by(wordbook_id=None)

    # starred 模式：仅返回重点单词
    starred_only = request.args.get('starred', '').strip() == '1'
    if starred_only:
        base_query = base_query.filter(Word.is_starred == True)

    # 排序：随机 or 按到期时间升序（过期最久的先复习）
    if random_mode:
        words = base_query.order_by(db.func.random()).all()
    else:
        words = base_query.order_by(Word.next_review.asc()).all()

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
    user_id = get_current_user_id()
    if user_id and word.user_id and word.user_id != user_id:
        return jsonify({'success': False, 'error': '无权访问'}), 403

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
    was_new = (word.status == 'new')

    # 记录本次复习
    word.last_review = now
    word.review_count = (word.review_count or 0) + 1
    # 错题追踪：again/hard 计为答错，累加 wrong_count；good/easy 不改变 wrong_count
    # 前端可依据 wrong_count 优先复习高频错词
    is_correct = rating in ('good', 'easy')
    if not is_correct:
        word.wrong_count = (word.wrong_count or 0) + 1

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

    # 如果单词从 new 变为 review（首次学习），更新今日学习历史
    if was_new and word.status != 'new':
        update_learn_history(1)

    db.session.commit()

    # 更新今日复习准确率统计（total_count +1，正确时 correct_count +1）
    try:
        update_review_accuracy(is_correct)
    except Exception as e:
        print(f"[统计] 更新复习准确率失败: {e}")

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
    获取学习队列：返回词书内所有单词，按添加顺序分批加载
    可通过 ?limit= 参数控制返回数量；不传则使用设置的 daily_goal
    可通过 ?wordbook_id= 按词书过滤（必须指定词书）
    可通过 ?random=1 随机取词（默认按添加顺序）
    可通过 ?exclude=1,2,3 排除指定 ID 的单词（用于"加入新词"时跳过已加载的）
    可通过 ?new_only=1 仅返回未学过（status='new'）的单词（用于"加入新词"按钮）
    """
    limit = request.args.get('limit', None, type=int)
    if limit is None:
        limit = get_setting().daily_goal

    user_id = get_current_user_id()

    # 返回词书内所有单词（不限状态：new/review/mastered 都可以学习）
    query = Word.query
    if user_id:
        query = query.filter_by(user_id=user_id)

    # 按词书过滤
    wordbook_id = request.args.get('wordbook_id', '').strip()
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter_by(wordbook_id=int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter_by(wordbook_id=None)

    # 排除指定 ID 的单词（"加入新词"时跳过已加载的）
    exclude_ids = request.args.get('exclude', '').strip()
    if exclude_ids:
        try:
            id_list = [int(x) for x in exclude_ids.split(',') if x.strip()]
            if id_list:
                query = query.filter(~Word.id.in_(id_list))
        except ValueError:
            pass

    # new_only 模式：仅返回未学过（status='new'）的单词
    new_only = request.args.get('new_only', '').strip() == '1'
    if new_only:
        query = query.filter_by(status='new')

    # starred 模式：仅返回重点单词
    starred_only = request.args.get('starred', '').strip() == '1'
    if starred_only:
        query = query.filter(Word.is_starred == True)

    # 排序：随机模式 / new_only 按 added_at / 默认按状态优先级(new>review>mastered)再 added_at
    random_mode = request.args.get('random', '').strip() == '1'
    if random_mode:
        words = query.order_by(db.func.random()).limit(limit).all()
    elif new_only:
        words = query.order_by(Word.added_at.asc()).limit(limit).all()
    else:
        status_order = case(
            {'new': 0, 'review': 1, 'mastered': 2},
            value=Word.status,
            else_=3
        )
        words = query.order_by(status_order, Word.added_at.asc()).limit(limit).all()

    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in words],
        'total': len(words),
    })


@app.route('/api/learn/today-words', methods=['GET'])
def get_today_learned_words():
    """
    获取今天学过的所有单词（今天首次学习的，即 last_review 在今天且 status != 'new'）
    可通过 ?wordbook_id= 按词书过滤
    """
    user_id = get_current_user_id()
    wordbook_id = request.args.get('wordbook_id', '').strip()
    today_start_utc, today_end_utc = get_today_utc_range()

    query = Word.query.filter(
        Word.last_review.isnot(None),
        Word.last_review >= today_start_utc,
        Word.last_review < today_end_utc,
        Word.status != 'new',
    )
    if user_id:
        query = query.filter_by(user_id=user_id)
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter_by(wordbook_id=int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter_by(wordbook_id=None)

    words = query.order_by(Word.last_review.desc()).all()

    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in words],
        'total': len(words),
    })


@app.route('/api/stats/calendar', methods=['GET'])
def get_calendar_stats():
    """获取日历统计数据：返回所有学习历史记录，用于日历视图（按用户隔离）"""
    user_id = get_current_user_id()
    history_query = LearnHistory.query
    if user_id:
        history_query = history_query.filter_by(user_id=user_id)
    all_history = history_query.order_by(LearnHistory.date).all()
    return jsonify({
        'success': True,
        'data': [{'date': h.date.isoformat(), 'count': h.count} for h in all_history],
    })


# ==================== 签到API ====================

@app.route('/api/checkin', methods=['POST'])
def checkin():
    """每日签到：用户手动点击签到，设置 checked_in=True
    连续天数基于签到记录，与学习记录无关"""
    err = require_login()
    if err:
        return err

    today = date.today()
    user_id = get_current_user_id()
    history = LearnHistory.query.filter_by(date=today, user_id=user_id).first()

    if history:
        if history.checked_in:
            # 已签到
            _, streak = get_checkin_status()
            return jsonify({
                'success': True,
                'already_checked_in': True,
                'data': {
                    'streak_days': streak,
                    'today_count': history.count,
                },
                'message': '今天已经签到过了',
            })
        else:
            # 有学习记录但未签到，设置签到标志
            history.checked_in = True
    else:
        # 今天没有任何记录，创建一条签到记录
        history = LearnHistory(date=today, count=0, checked_in=True, user_id=user_id)
        db.session.add(history)

    db.session.commit()

    _, streak = get_checkin_status()
    return jsonify({
        'success': True,
        'already_checked_in': False,
        'data': {
            'streak_days': streak,
            'today_count': history.count,
        },
        'message': f'签到成功！已连续签到{streak}天',
    })


@app.route('/api/checkin/status', methods=['GET'])
def checkin_status():
    """获取今日签到状态"""
    err = require_login()
    if err:
        return err

    checked_in, streak = get_checkin_status()
    return jsonify({
        'success': True,
        'data': {
            'checked_in': checked_in,
            'streak_days': streak,
        },
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
        user_id = get_current_user_id()
        if user_id:
            # 已登录：仅删除当前用户的单词和学习历史
            db.session.query(Word).filter_by(user_id=user_id).delete(synchronize_session=False)
            db.session.query(LearnHistory).filter_by(user_id=user_id).delete(synchronize_session=False)
        else:
            # 未登录：清空所有（向后兼容）
            db.session.query(Word).delete(synchronize_session=False)
            db.session.query(LearnHistory).delete(synchronize_session=False)
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
    starred = request.args.get('starred', '').strip()

    # 构建查询
    query = Word.query
    user_id = get_current_user_id()
    if user_id:
        query = query.filter_by(user_id=user_id)
    if wordbook_id and wordbook_id != '0':
        try:
            query = query.filter(Word.wordbook_id == int(wordbook_id))
        except ValueError:
            pass
    elif wordbook_id == '0':
        query = query.filter(Word.wordbook_id.is_(None))
    if status:
        query = query.filter(Word.status == status)
    if starred == '1':
        query = query.filter(Word.is_starred == True)
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
        ('anti_forget', 'BOOLEAN DEFAULT TRUE'),
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


def ensure_user_id_columns():
    """
    数据库迁移：为 words 和 wordbooks 表添加 user_id 列（如果不存在）
    用于用户数据隔离，旧数据库升级时自动添加
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    # words 表添加 user_id 列
    words_columns = [col['name'] for col in inspector.get_columns('words')]
    if 'user_id' not in words_columns:
        print("[迁移] 检测到 words 表缺少 user_id 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN user_id INTEGER"))
            conn.commit()
        print("[迁移] words.user_id 列添加完成")
    # wordbooks 表添加 user_id 列
    wordbooks_columns = [col['name'] for col in inspector.get_columns('wordbooks')]
    if 'user_id' not in wordbooks_columns:
        print("[迁移] 检测到 wordbooks 表缺少 user_id 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE wordbooks ADD COLUMN user_id INTEGER"))
            conn.commit()
        print("[迁移] wordbooks.user_id 列添加完成")


def fix_word_unique_constraint():
    """
    数据库迁移：将 words 表的 word 列从全局 UNIQUE 改为 (word, user_id) 联合唯一
    这样不同用户可以添加同一个单词
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    indexes = inspector.get_indexes('words')
    # 查找旧的 word 唯一索引（名称可能是 ix_words_word 或 word）
    old_unique_indexes = [
        idx for idx in indexes
        if idx.get('unique') and 'word' in idx.get('column_names', [])
    ]
    if old_unique_indexes:
        print("[迁移] 检测到 words.word 上的旧唯一索引，正在移除...")
        with db.engine.connect() as conn:
            for idx in old_unique_indexes:
                idx_name = idx['name']
                conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
            # 创建新的联合唯一索引（word + user_id）
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_words_word_user_id ON words(word, user_id)"))
            conn.commit()
        print(f"[迁移] 已移除 {len(old_unique_indexes)} 个旧索引，创建 (word, user_id) 联合唯一索引")
    else:
        # 确保联合唯一索引存在
        with db.engine.connect() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_words_word_user_id ON words(word, user_id)"))
            conn.commit()


def ensure_user_security_columns():
    """
    数据库迁移：为 users 表添加 security_question 和 security_answer 列（如果不存在）
    用于密码重置功能
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('users')]
    new_cols = [
        ('security_question', "VARCHAR(255) DEFAULT 'What is your favorite color?'"),
        ('security_answer', "VARCHAR(255) DEFAULT ''"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in columns:
            print(f"[迁移] 检测到 users 表缺少 {col_name} 列，正在添加...")
            with db.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                conn.commit()
            print(f"[迁移] users.{col_name} 列添加完成")


def ensure_user_active_column():
    """
    数据库迁移：为 users 表添加 is_active 列（如果不存在）
    用于管理员启用/禁用用户账号
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'is_active' not in columns:
        print("[迁移] 检测到 users 表缺少 is_active 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
            conn.commit()
        print("[迁移] users.is_active 列添加完成")


def ensure_word_wrong_count_column():
    """
    数据库迁移：为 words 表添加 wrong_count 列（如果不存在）
    用于错题追踪，前端可优先复习高频错词
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('words')]
    if 'wrong_count' not in columns:
        print("[迁移] 检测到 words 表缺少 wrong_count 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN wrong_count INTEGER DEFAULT 0"))
            conn.commit()
        print("[迁移] words.wrong_count 列添加完成")


def ensure_word_starred_column():
    """
    数据库迁移：为 words 表添加 is_starred 列（如果不存在）
    用于标记重点单词
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('words')]
    if 'is_starred' not in columns:
        print("[迁移] 检测到 words 表缺少 is_starred 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN is_starred BOOLEAN DEFAULT FALSE"))
            conn.commit()
        print("[迁移] words.is_starred 列添加完成")


def ensure_learn_history_accuracy_columns():
    """
    数据库迁移：为 learn_history 表添加 correct_count 和 total_count 列（如果不存在）
    用于准确率统计
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('learn_history')]
    new_cols = [
        ('correct_count', 'INTEGER DEFAULT 0'),
        ('total_count', 'INTEGER DEFAULT 0'),
    ]
    for col_name, col_def in new_cols:
        if col_name not in columns:
            print(f"[迁移] 检测到 learn_history 表缺少 {col_name} 列，正在添加...")
            with db.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE learn_history ADD COLUMN {col_name} {col_def}"))
                conn.commit()
            print(f"[迁移] learn_history.{col_name} 列添加完成")


def ensure_learn_history_checkin_column():
    """
    数据库迁移：为 learn_history 表添加 checked_in 列（如果不存在）
    用于独立的签到状态标记，与学习记录分离
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('learn_history')]
    if 'checked_in' not in columns:
        print("[迁移] 检测到 learn_history 表缺少 checked_in 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE learn_history ADD COLUMN checked_in BOOLEAN DEFAULT FALSE"))
            conn.commit()
        print("[迁移] learn_history.checked_in 列添加完成")

    # 清理：将 checked_in 为 NULL 的记录设为 FALSE（确保数据一致性）
    with db.engine.connect() as conn:
        result = conn.execute(text("UPDATE learn_history SET checked_in = FALSE WHERE checked_in IS NULL"))
        if result.rowcount > 0:
            print(f"[迁移] 已将 {result.rowcount} 条 checked_in=NULL 的记录修正为 FALSE")
        conn.commit()


def ensure_learn_history_user_id_column():
    """
    数据库迁移：为 learn_history 表添加 user_id 列（如果不存在）
    用于多用户数据隔离，每个用户有独立的学习历史记录
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('learn_history')]
    if 'user_id' not in columns:
        print("[迁移] 检测到 learn_history 表缺少 user_id 列，正在添加...")
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE learn_history ADD COLUMN user_id INTEGER"))
            conn.commit()
        print("[迁移] learn_history.user_id 列添加完成")


def fix_learn_history_unique_constraint():
    """
    数据库迁移：移除 learn_history 表 date 列上的旧唯一约束
    改为 (date, user_id) 联合唯一，允许多用户同一天各有记录
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)

    # 检查是否有 user_id 列（前置依赖）
    columns = [col['name'] for col in inspector.get_columns('learn_history')]
    if 'user_id' not in columns:
        return  # 还没添加 user_id 列，跳过

    # 查找 date 列上的唯一索引/约束
    indexes = inspector.get_indexes('learn_history')
    old_unique_indexes = [
        idx for idx in indexes
        if idx.get('unique') and 'date' in idx.get('column_names', [])
    ]

    if old_unique_indexes:
        print("[迁移] 检测到 learn_history.date 上的旧唯一索引，正在移除...")
        with db.engine.connect() as conn:
            for idx in old_unique_indexes:
                idx_name = idx['name']
                try:
                    conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                except Exception:
                    pass
            conn.commit()
        print(f"[迁移] 已移除 {len(old_unique_indexes)} 个旧唯一索引")

    # 检查表级唯一约束（SQLite 的 unique=True 在列定义上）
    # PostgreSQL: 检查唯一约束
    try:
        constraints = inspector.get_unique_constraints('learn_history')
        for uc in constraints:
            if 'date' in uc.get('column_names', []) and 'user_id' not in uc.get('column_names', []):
                # 旧的 date 唯一约束，需要删除（PostgreSQL）
                constraint_name = uc.get('name', '')
                if constraint_name:
                    print(f"[迁移] 尝试移除旧唯一约束: {constraint_name}")
                    with db.engine.connect() as conn:
                        try:
                            conn.execute(text(f"ALTER TABLE learn_history DROP CONSTRAINT IF EXISTS {constraint_name}"))
                            conn.commit()
                        except Exception:
                            pass
    except Exception:
        pass

    # 创建新的联合唯一索引
    with db.engine.connect() as conn:
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_learn_history_date_user ON learn_history(date, user_id)"))
        conn.commit()
    print("[迁移] learn_history (date, user_id) 联合唯一索引已就绪")


def ensure_wordbook_shared_columns():
    """
    数据库迁移：为 wordbooks 表添加 is_shared 和 shared_at 列（如果不存在）
    用于全局词本分享功能
    兼容 SQLite (DATETIME) 和 PostgreSQL (TIMESTAMP)
    """
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('wordbooks')]
    # PostgreSQL 用 TIMESTAMP，SQLite 用 DATETIME
    dialect_name = db.engine.dialect.name
    timestamp_type = 'TIMESTAMP' if dialect_name == 'postgresql' else 'DATETIME'
    new_cols = [
        ('is_shared', 'BOOLEAN DEFAULT FALSE'),
        ('shared_at', timestamp_type),
    ]
    for col_name, col_def in new_cols:
        if col_name not in columns:
            print(f"[迁移] 检测到 wordbooks 表缺少 {col_name} 列，正在添加...")
            with db.engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE wordbooks ADD COLUMN {col_name} {col_def}"))
                conn.commit()
            print(f"[迁移] wordbooks.{col_name} 列添加完成")


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
    # 迁移：为 words 和 wordbooks 表添加 user_id 列（用户数据隔离）
    ensure_user_id_columns()
    # 迁移：将 words.word 全局唯一改为 (word, user_id) 联合唯一
    fix_word_unique_constraint()
    # 迁移：为 users 表添加 security_question / security_answer 列（密码重置）
    ensure_user_security_columns()
    # 迁移：为 users 表添加 is_active 列（启用/禁用账号）
    ensure_user_active_column()
    # 迁移：为 words 表添加 wrong_count 列（错题追踪）
    ensure_word_wrong_count_column()
    # 迁移：为 words 表添加 is_starred 列（重点单词标记）
    ensure_word_starred_column()
    # 迁移：为 learn_history 表添加 correct_count / total_count 列（准确率统计）
    ensure_learn_history_accuracy_columns()
    # 迁移：为 learn_history 表添加 checked_in 列（独立签到状态）
    ensure_learn_history_checkin_column()
    # 迁移：为 learn_history 表添加 user_id 列（多用户数据隔离）
    ensure_learn_history_user_id_column()
    # 迁移：移除 learn_history.date 旧唯一约束，改为 (date, user_id) 联合唯一
    fix_learn_history_unique_constraint()
    # 迁移：为 wordbooks 表添加 is_shared / shared_at 列（全局词本分享）
    ensure_wordbook_shared_columns()
    # 插入演示数据
    init_demo_data()
    # 升级已有单词的拆解数据和记忆方法到新结构
    upgrade_split_data()
    # 修复 meaning 为空的旧数据单词
    fix_empty_meanings()
    # 修复异常释义（OCR artifact/纯英文）+ 补充变形词缺少的 tenses 数据
    fix_broken_meanings()
    # 强制升级所有单词的释义精简和变形数据（新的 _clean_meaning + _get_inflections 逻辑）
    force_upgrade_all_tenses()
    # 为没有例句的单词补充专升本例句
    fill_missing_examples()


# ==================== 前端静态文件服务 ====================
# 生产环境下由后端直接托管前端文件，部署后只需一个服务（同源，无需CORS）
# 本地开发也可通过 http://localhost:5000/ 直接访问前端
# Render 部署时 Root Directory=backend，只更新 backend/ 目录
# 因此优先使用 ./static/（随 backend 一起部署），回退到 ../frontend/（本地开发）
_STATIC_FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
_REPO_FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
# 优先使用 backend/static/（部署时会更新），如果不存在则用 ../frontend/（本地开发）
if os.path.exists(os.path.join(_STATIC_FRONTEND, 'index.html')):
    FRONTEND_DIR = _STATIC_FRONTEND
else:
    FRONTEND_DIR = _REPO_FRONTEND


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
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
