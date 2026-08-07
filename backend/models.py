"""
数据库模型定义
包含用户模型、单词模型和学习历史记录模型
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON
import hashlib
import os

# 创建SQLAlchemy实例，在app.py中初始化
db = SQLAlchemy()


class User(db.Model):
    """用户模型：支持注册登录、数据隔离、管理员管理"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    # 密码盐值+哈希（sha256）
    salt = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(64), nullable=False)
    # 角色：admin / user
    role = db.Column(db.String(20), default='user')
    # 昵称（显示名）
    nickname = db.Column(db.String(80), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 安全问题及答案（用于密码重置，简单版）
    security_question = db.Column(db.String(255), default='What is your favorite color?')
    security_answer = db.Column(db.String(255), default='')
    # 账号是否启用（True=启用，False=禁用），管理员可切换
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.salt = os.urandom(16).hex()
        self.password_hash = hashlib.sha256((password + self.salt).encode()).hexdigest()

    def check_password(self, password):
        h = hashlib.sha256((password + self.salt).encode()).hexdigest()
        return h == self.password_hash

    def to_dict(self, include_stats=False):
        data = {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'nickname': self.nickname or self.username,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_active': self.is_active if self.is_active is not None else True,
            'security_question': self.security_question or 'What is your favorite color?',
        }
        if include_stats:
            data['word_count'] = Word.query.filter_by(user_id=self.id).count()
            data['mastered_count'] = Word.query.filter_by(user_id=self.id, status='mastered').count()
            data['wordbook_count'] = Wordbook.query.filter_by(user_id=self.id).count()
        return data

    def __repr__(self):
        return f'<User {self.username}>'


class Word(db.Model):
    """单词模型"""
    __tablename__ = 'words'
    __table_args__ = (
        db.UniqueConstraint('word', 'user_id', name='uq_word_user'),
    )

    # 主键ID
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 单词文本（可包含词组，如 "sports meeting"）
    word = db.Column(db.String(255), nullable=False, index=True)
    # 音标
    phonetic = db.Column(db.String(255), default='')
    # 释义
    meaning = db.Column(db.Text, default='')
    # 学习状态：new(新词) / review(复习中) / mastered(已掌握)
    status = db.Column(db.String(20), default='new', index=True)
    # 添加时间
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 上次复习时间
    last_review = db.Column(db.DateTime, nullable=True)
    # 首次学习时间（第一次从 new 变为已学状态的时间，用于精确统计"今日已学"）
    first_learned = db.Column(db.DateTime, nullable=True)
    # 复习次数
    review_count = db.Column(db.Integer, default=0)
    # 下次复习时间（用于艾宾浩斯复习算法）
    next_review = db.Column(db.DateTime, nullable=True, index=True)
    # 复合词拆解数据（JSON格式，存储AI分析的拆解结果）
    split_data = db.Column(JSON, default=list)
    # 词根词缀分析数据（JSON格式，存储词法分析结果）
    morph_data = db.Column(JSON, default=list)
    # 例句数据（JSON格式，存储例句列表）
    examples = db.Column(JSON, default=list)
    # 单词类型：复合词 / 派生词 / 基础词
    word_type = db.Column(db.String(50), default='基础词')
    # 记忆方法（AI生成的中文记忆口诀）
    mnemonic = db.Column(db.Text, default='')
    # 动词时态变形数据（JSON格式，存储动词的五种形态）
    # 结构: {base, third_singular, past, past_participle, present_participle}
    # 仅动词有此字段，非动词为 null
    tenses = db.Column(JSON, nullable=True)
    # 所属单词本 ID（外键，可空=默认单词本）
    wordbook_id = db.Column(db.Integer, db.ForeignKey('wordbooks.id'), nullable=True, index=True)
    # 所属用户 ID（外键，可空=旧数据/未登录用户）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    # 错误次数：评分 again/hard 时累加，用于前端优先复习高频错词
    wrong_count = db.Column(db.Integer, default=0)
    # 是否标记为重点单词
    is_starred = db.Column(db.Boolean, default=False)
    # 词本内排序权重（用户可手动调整单词顺序，数值小的排前面）
    sort_order = db.Column(db.Integer, default=0)

    def to_dict(self):
        """将单词对象转换为字典，用于API响应"""
        return {
            'id': self.id,
            'word': self.word,
            'phonetic': self.phonetic or '',
            'meaning': self.meaning or '',
            'status': self.status,
            'word_type': self.word_type or '基础词',
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'last_review': self.last_review.isoformat() if self.last_review else None,
            'review_count': self.review_count,
            'next_review': self.next_review.isoformat() if self.next_review else None,
            # 对 split_data 做兼容处理：旧数据缺少 original/original_meaning/transform 字段，动态补充
            'split_data': self._normalize_split_data(self.split_data or []),
            'morph_data': self.morph_data or [],
            'mnemonic': self.mnemonic or '',
            'examples': self.examples or [],
            'tenses': self.tenses or None,
            'wordbook_id': self.wordbook_id,
            'wrong_count': self.wrong_count or 0,
            'is_starred': self.is_starred if self.is_starred is not None else False,
            'sort_order': self.sort_order if self.sort_order is not None else 0,
        }

    def to_list_dict(self):
        """轻量级列表序列化：仅返回词库/首页列表展示所需字段。

        省略 split_data / morph_data / examples / tenses / mnemonic 等重型JSON字段，
        大幅降低 /api/words 列表接口的序列化开销与网络传输量（数千词时提速明显）。
        如需完整详情，前端调用 /api/words/<id> 获取 to_dict() 全量数据。
        """
        return {
            'id': self.id,
            'word': self.word,
            'phonetic': self.phonetic or '',
            'meaning': self.meaning or '',
            'status': self.status,
            'word_type': self.word_type or '基础词',
            'added_at': self.added_at.isoformat() if self.added_at else None,
            'last_review': self.last_review.isoformat() if self.last_review else None,
            'first_learned': self.first_learned.isoformat() if self.first_learned else None,
            'review_count': self.review_count,
            'next_review': self.next_review.isoformat() if self.next_review else None,
            'wordbook_id': self.wordbook_id,
            'wrong_count': self.wrong_count or 0,
            'is_starred': self.is_starred if self.is_starred is not None else False,
            'sort_order': self.sort_order if self.sort_order is not None else 0,
        }

    @staticmethod
    def _normalize_split_data(split_data):
        """
        规范化 split_data，兼容旧数据结构
        旧数据每项只有 {part, meaning, explain}，新数据增加了 {original, original_meaning, transform}
        此方法为旧数据动态补充新字段的默认值
        """
        if not isinstance(split_data, list):
            return []
        normalized = []
        for item in split_data:
            if not isinstance(item, dict):
                continue
            part = item.get('part', '')
            original = item.get('original', '') or part
            meaning = item.get('meaning', '')
            # 如果没有 transform 字段，根据原词是否等于当前部分推断
            transform = item.get('transform', '')
            if not transform:
                transform = '原形不变' if original == part else ''
            normalized.append({
                'part': part,
                'meaning': meaning,
                'original': original,
                'original_meaning': item.get('original_meaning', '') or meaning,
                'transform': transform,
                'explain': item.get('explain', ''),
            })
        return normalized

    def __repr__(self):
        return f'<Word {self.word}>'


class LearnHistory(db.Model):
    """学习历史记录模型，记录每天学习的单词数量（按用户隔离）"""
    __tablename__ = 'learn_history'
    __table_args__ = (
        db.UniqueConstraint('date', 'user_id', name='uq_learn_history_date_user'),
    )

    # 主键ID
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 日期（格式：YYYY-MM-DD）
    date = db.Column(db.Date, nullable=False, index=True)
    # 当天学习的单词数量
    count = db.Column(db.Integer, default=0)
    # 当天复习正确次数（用于准确率统计）
    correct_count = db.Column(db.Integer, default=0)
    # 当天复习总次数（用于准确率统计）
    total_count = db.Column(db.Integer, default=0)
    # 是否已签到（独立于学习记录，需用户手动点击签到）
    checked_in = db.Column(db.Boolean, default=False)
    # 所属用户 ID（外键，可空=旧数据/未登录用户）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'count': self.count,
            'correct_count': self.correct_count or 0,
            'total_count': self.total_count or 0,
            'user_id': self.user_id,
        }

    def __repr__(self):
        return f'<LearnHistory {self.date}: {self.count} (user={self.user_id})>'


class LearnSession(db.Model):
    """学习会话记录：记录每日学习时长（分钟），用于统计平均每日学习时间"""
    __tablename__ = 'learn_sessions'

    # 主键ID
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 学习日期
    date = db.Column(db.Date, nullable=False, index=True)
    # 学习时长（分钟）
    duration_minutes = db.Column(db.Integer, default=0)
    # 所属用户 ID（外键，可空=未登录用户）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'duration_minutes': self.duration_minutes or 0,
            'user_id': self.user_id,
        }

    def __repr__(self):
        return f'<LearnSession {self.date}: {self.duration_minutes}min>'


class Setting(db.Model):
    """用户设置模型

    按用户隔离：每个用户一行（user_id），未登录/旧数据沿用 id=1 的全局默认行。
    早期版本为单行全局表（所有用户共享同一套学习目标/复习策略），
    现通过 user_id 实现 per-user 隔离，避免多人互相影响。
    """
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 所属用户 ID（可空=全局默认行，id=1 向后兼容）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    # 每日新词学习目标
    daily_goal = db.Column(db.Integer, default=20)
    # 每日复习单词上限（0=不限制）
    daily_review_goal = db.Column(db.Integer, default=50)
    # 复习策略：relaxed(宽松)/standard(标准)/strict(严格)
    review_strategy = db.Column(db.String(20), default='standard')
    # 防遗忘：已掌握单词定期回顾（True/False）
    anti_forget = db.Column(db.Boolean, default=True)
    # 防遗忘回顾间隔（天），已掌握单词每隔这么多天回顾一次
    anti_forget_interval = db.Column(db.Integer, default=30)

    def to_dict(self):
        return {
            'daily_goal': self.daily_goal,
            'daily_review_goal': self.daily_review_goal,
            'review_strategy': self.review_strategy or 'standard',
            'anti_forget': self.anti_forget if self.anti_forget is not None else True,
            'anti_forget_interval': self.anti_forget_interval or 30,
        }


class Wordbook(db.Model):
    """单词本模型：用于分组管理单词（如按文档导入来源、按主题分类）"""
    __tablename__ = 'wordbooks'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 单词本名称
    name = db.Column(db.String(100), nullable=False)
    # 描述（选填）
    description = db.Column(db.String(255), default='')
    # 颜色标识（用于 UI 区分，默认靛蓝）
    color = db.Column(db.String(20), default='#4a7fff')
    # 创建时间
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 所属用户 ID（外键，可空=旧数据/未登录用户）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    # 是否分享到全局词本（True=已分享，其他用户可查看和导入单词）
    is_shared = db.Column(db.Boolean, default=False)
    # 分享时间（is_shared 设为 True 时更新）
    shared_at = db.Column(db.DateTime, nullable=True)
    # 关联单词（反向关系）
    words = db.relationship('Word', backref='wordbook', lazy='dynamic')

    def to_dict(self, include_count=False, include_owner=False):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'color': self.color or '#4a7fff',
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'is_shared': self.is_shared if self.is_shared is not None else False,
            'shared_at': self.shared_at.isoformat() if self.shared_at else None,
        }
        if include_count:
            data['word_count'] = self.words.count()
        if include_owner and self.user_id:
            owner = User.query.get(self.user_id)
            data['owner_name'] = owner.nickname or owner.username if owner else '未知'
            data['owner_id'] = self.user_id
        return data
