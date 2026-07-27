"""
数据库模型定义
包含单词模型和学习历史记录模型
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON

# 创建SQLAlchemy实例，在app.py中初始化
db = SQLAlchemy()


class Word(db.Model):
    """单词模型"""
    __tablename__ = 'words'

    # 主键ID
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 单词文本（可包含词组，如 "sports meeting"）
    word = db.Column(db.String(255), nullable=False, unique=True, index=True)
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
    """学习历史记录模型，记录每天学习的单词数量"""
    __tablename__ = 'learn_history'

    # 主键ID
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 日期（格式：YYYY-MM-DD）
    date = db.Column(db.Date, nullable=False, unique=True, index=True)
    # 当天学习的单词数量
    count = db.Column(db.Integer, default=0)

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'count': self.count,
        }

    def __repr__(self):
        return f'<LearnHistory {self.date}: {self.count}>'


class Setting(db.Model):
    """用户设置模型（单行表，存储全局设置）"""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True, default=1)
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
    # 关联单词（反向关系）
    words = db.relationship('Word', backref='wordbook', lazy='dynamic')

    def to_dict(self, include_count=False):
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'color': self.color or '#4a7fff',
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if include_count:
            data['word_count'] = self.words.count()
        return data
