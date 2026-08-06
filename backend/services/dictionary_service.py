"""
本地词典服务模块
作为AI不可用时的fallback方案
包含预置的常用单词词典和基于规则的单词分析
集成 ECDICT 开源词典（77万词条），提供精准释义、音标、词性和变形分析
"""
import re
import os
import sqlite3
import threading
import requests


class DictionaryService:
    """本地词典服务，提供离线单词查询和规则分析"""

    _online_cache = {}

    # ECDICT 数据库连接（懒加载，线程安全）
    _ecdict_conn = None
    _ecdict_lock = threading.Lock()

    @property
    def _ecdict(self):
        """懒加载 ECDICT SQLite 数据库连接"""
        if self._ecdict_conn is None:
            with self._ecdict_lock:
                if self._ecdict_conn is None:
                    db_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'data', 'stardict.db'
                    )
                    if os.path.exists(db_path):
                        try:
                            self._ecdict_conn = sqlite3.connect(
                                db_path, check_same_thread=False
                            )
                            self._ecdict_conn.row_factory = sqlite3.Row
                            print(f'[ecdict] 已加载词典数据库: {db_path}')
                        except Exception as e:
                            print(f'[ecdict] 加载失败: {e}')
        return self._ecdict_conn

    # 常见英文前缀
    PREFIXES = {
        'un': '否定前缀，表示"不、非"',
        're': '重复前缀，表示"再、重新"',
        'pre': '前缀，表示"在...之前"',
        'dis': '否定前缀，表示"不、相反"',
        'mis': '错误前缀，表示"错误、不当"',
        'over': '前缀，表示"过度、超过"',
        'under': '前缀，表示"在...之下、不足"',
        'out': '前缀，表示"超过、外面"',
        'in': '前缀，表示"进入、内"',
        'im': '前缀，in的变体（用于b/m/p前）',
        'ir': '前缀，in的变体（用于r前）',
        'il': '前缀，in的变体（用于l前）',
        'en': '前缀，表示"使成为"',
        'non': '否定前缀，表示"非"',
        'anti': '前缀，表示"反对、抗"',
        'auto': '前缀，表示"自己、自动"',
        'bi': '前缀，表示"二、双"',
        'tri': '前缀，表示"三"',
        'multi': '前缀，表示"多"',
        'super': '前缀，表示"超级、超过"',
        'sub': '前缀，表示"在...下面、次"',
        'inter': '前缀，表示"在...之间"',
        'trans': '前缀，表示"横过、转变"',
    }

    # 常见英文后缀
    SUFFIXES = {
        'ing': '动名词或现在分词后缀',
        'ed': '过去式或过去分词后缀',
        'er': '名词后缀，表示"做...的人或物"',
        'or': '名词后缀，表示"做...的人"',
        'ist': '名词后缀，表示"...主义者"',
        'tion': '名词后缀，表示动作或状态',
        'sion': '名词后缀，表示动作或状态',
        'ment': '名词后缀，表示行为或结果',
        'ness': '名词后缀，表示状态或性质',
        'ity': '名词后缀，表示性质或状态',
        'able': '形容词后缀，表示"可...的"',
        'ible': '形容词后缀，表示"可...的"',
        'ful': '形容词后缀，表示"充满...的"',
        'less': '形容词后缀，表示"无...的"',
        'ous': '形容词后缀，表示"具有...的"',
        'ive': '形容词后缀，表示"有...倾向的"',
        'al': '形容词后缀，表示"...的"',
        'ly': '副词后缀，表示"...地"',
        'y': '形容词后缀，表示"有...特性的"',
        'ize': '动词后缀，表示"使...化"',
        'ise': '动词后缀，ize的英式变体',
        'ify': '动词后缀，表示"使...化"',
        'en': '动词后缀，表示"使变成"',
        'ship': '名词后缀，表示关系或状态',
        'hood': '名词后缀，表示时期或状态',
        'dom': '名词后缀，表示领域或状态',
        'ous': '形容词后缀，表示"多...的"',
        'ward': '副词后缀，表示方向',
        's': '复数或第三人称单数后缀',
        'es': '复数或第三人称单数后缀',
        'ure': '名词后缀，表示行为、状态或结果',
        'ance': '名词后缀，表示行为或状态',
        'ence': '名词后缀，表示行为或状态',
        'age': '名词后缀，表示行为或结果',
        'ish': '形容词后缀，表示"...似的"',
        'like': '形容词后缀，表示"...般的"',
        'hood': '名词后缀，表示时期或状态',
        'th': '名词后缀，表示状态或性质',
    }

    # 常见动词的时态变形表（五种形态：原形/第三人称单数/过去式/过去分词/现在分词）
    # 仅收录不规则动词和高频动词；规则动词可由 AI 动态生成
    VERB_TENSES = {
        'be':       {'base': 'be',       'third_singular': 'is',     'past': 'was/were', 'past_participle': 'been',    'present_participle': 'being'},
        'have':     {'base': 'have',     'third_singular': 'has',     'past': 'had',      'past_participle': 'had',     'present_participle': 'having'},
        'do':       {'base': 'do',       'third_singular': 'does',    'past': 'did',      'past_participle': 'done',    'present_participle': 'doing'},
        'go':       {'base': 'go',       'third_singular': 'goes',    'past': 'went',     'past_participle': 'gone',    'present_participle': 'going'},
        'make':     {'base': 'make',     'third_singular': 'makes',   'past': 'made',     'past_participle': 'made',    'present_participle': 'making'},
        'take':     {'base': 'take',     'third_singular': 'takes',   'past': 'took',     'past_participle': 'taken',   'present_participle': 'taking'},
        'come':     {'base': 'come',     'third_singular': 'comes',   'past': 'came',     'past_participle': 'come',    'present_participle': 'coming'},
        'see':      {'base': 'see',      'third_singular': 'sees',    'past': 'saw',      'past_participle': 'seen',    'present_participle': 'seeing'},
        'give':     {'base': 'give',     'third_singular': 'gives',   'past': 'gave',     'past_participle': 'given',   'present_participle': 'giving'},
        'get':      {'base': 'get',      'third_singular': 'gets',    'past': 'got',      'past_participle': 'got/gotten', 'present_participle': 'getting'},
        'know':     {'base': 'know',     'third_singular': 'knows',   'past': 'knew',     'past_participle': 'known',   'present_participle': 'knowing'},
        'think':    {'base': 'think',    'third_singular': 'thinks',  'past': 'thought',  'past_participle': 'thought', 'present_participle': 'thinking'},
        'say':      {'base': 'say',      'third_singular': 'says',    'past': 'said',     'past_participle': 'said',    'present_participle': 'saying'},
        'find':     {'base': 'find',     'third_singular': 'finds',   'past': 'found',    'past_participle': 'found',   'present_participle': 'finding'},
        'write':    {'base': 'write',    'third_singular': 'writes',  'past': 'wrote',    'past_participle': 'written', 'present_participle': 'writing'},
        'run':      {'base': 'run',      'third_singular': 'runs',    'past': 'ran',      'past_participle': 'run',     'present_participle': 'running'},
        'read':     {'base': 'read',     'third_singular': 'reads',   'past': 'read',     'past_participle': 'read',    'present_participle': 'reading'},
        'speak':    {'base': 'speak',    'third_singular': 'speaks',  'past': 'spoke',    'past_participle': 'spoken',  'present_participle': 'speaking'},
        'begin':    {'base': 'begin',    'third_singular': 'begins',  'past': 'began',    'past_participle': 'begun',   'present_participle': 'beginning'},
        'drink':    {'base': 'drink',    'third_singular': 'drinks',  'past': 'drank',    'past_participle': 'drunk',   'present_participle': 'drinking'},
        'swim':     {'base': 'swim',     'third_singular': 'swims',   'past': 'swam',     'past_participle': 'swum',    'present_participle': 'swimming'},
        'sing':     {'base': 'sing',     'third_singular': 'sings',   'past': 'sang',     'past_participle': 'sung',    'present_participle': 'singing'},
        'ring':     {'base': 'ring',     'third_singular': 'rings',   'past': 'rang',     'past_participle': 'rung',    'present_participle': 'ringing'},
        'grow':     {'base': 'grow',     'third_singular': 'grows',   'past': 'grew',     'past_participle': 'grown',   'present_participle': 'growing'},
        'fly':      {'base': 'fly',      'third_singular': 'flies',   'past': 'flew',     'past_participle': 'flown',   'present_participle': 'flying'},
        'drive':    {'base': 'drive',    'third_singular': 'drives',  'past': 'drove',    'past_participle': 'driven',  'present_participle': 'driving'},
        'ride':     {'base': 'ride',     'third_singular': 'rides',   'past': 'rode',     'past_participle': 'ridden',  'present_participle': 'riding'},
        'rise':     {'base': 'rise',     'third_singular': 'rises',   'past': 'rose',     'past_participle': 'risen',   'present_participle': 'rising'},
        'break':    {'base': 'break',    'third_singular': 'breaks',  'past': 'broke',    'past_participle': 'broken',  'present_participle': 'breaking'},
        'choose':   {'base': 'choose',   'third_singular': 'chooses', 'past': 'chose',    'past_participle': 'chosen',  'present_participle': 'choosing'},
        'forget':   {'base': 'forget',   'third_singular': 'forgets', 'past': 'forgot',   'past_participle': 'forgotten','present_participle': 'forgetting'},
        'teach':    {'base': 'teach',    'third_singular': 'teaches', 'past': 'taught',   'past_participle': 'taught',  'present_participle': 'teaching'},
        'catch':    {'base': 'catch',    'third_singular': 'catches', 'past': 'caught',   'past_participle': 'caught',  'present_participle': 'catching'},
        'buy':      {'base': 'buy',      'third_singular': 'buys',    'past': 'bought',   'past_participle': 'bought',  'present_participle': 'buying'},
        'bring':    {'base': 'bring',    'third_singular': 'brings',  'past': 'brought',  'past_participle': 'brought', 'present_participle': 'bringing'},
        'fight':    {'base': 'fight',    'third_singular': 'fights',  'past': 'fought',   'past_participle': 'fought',  'present_participle': 'fighting'},
        'think':    {'base': 'think',    'third_singular': 'thinks',  'past': 'thought',  'past_participle': 'thought', 'present_participle': 'thinking'},
        'feel':     {'base': 'feel',     'third_singular': 'feels',   'past': 'felt',     'past_participle': 'felt',    'present_participle': 'feeling'},
        'keep':     {'base': 'keep',     'third_singular': 'keeps',   'past': 'kept',     'past_participle': 'kept',    'present_participle': 'keeping'},
        'sleep':    {'base': 'sleep',    'third_singular': 'sleeps',  'past': 'slept',    'past_participle': 'slept',   'present_participle': 'sleeping'},
        'meet':     {'base': 'meet',     'third_singular': 'meets',   'past': 'met',      'past_participle': 'met',     'present_participle': 'meeting'},
        'send':     {'base': 'send',     'third_singular': 'sends',   'past': 'sent',     'past_participle': 'sent',    'present_participle': 'sending'},
        'spend':    {'base': 'spend',    'third_singular': 'spends',  'past': 'spent',    'past_participle': 'spent',   'present_participle': 'spending'},
        'build':    {'base': 'build',    'third_singular': 'builds',  'past': 'built',    'past_participle': 'built',   'present_participle': 'building'},
        'understand': {'base': 'understand', 'third_singular': 'understands', 'past': 'understood', 'past_participle': 'understood', 'present_participle': 'understanding'},
        'stand':    {'base': 'stand',    'third_singular': 'stands',  'past': 'stood',    'past_participle': 'stood',   'present_participle': 'standing'},
        'become':   {'base': 'become',   'third_singular': 'becomes', 'past': 'became',   'past_participle': 'become',  'present_participle': 'becoming'},
        'eat':      {'base': 'eat',      'third_singular': 'eats',    'past': 'ate',      'past_participle': 'eaten',   'present_participle': 'eating'},
        'fall':     {'base': 'fall',     'third_singular': 'falls',   'past': 'fell',     'past_participle': 'fallen',  'present_participle': 'falling'},
        'win':      {'base': 'win',      'third_singular': 'wins',    'past': 'won',      'past_participle': 'won',     'present_participle': 'winning'},
        'lose':     {'base': 'lose',     'third_singular': 'loses',   'past': 'lost',     'past_participle': 'lost',    'present_participle': 'losing'},
        'wear':     {'base': 'wear',     'third_singular': 'wears',   'past': 'wore',     'past_participle': 'worn',    'present_participle': 'wearing'},
        'draw':     {'base': 'draw',     'third_singular': 'draws',   'past': 'drew',     'past_participle': 'drawn',   'present_participle': 'drawing'},
        'throw':    {'base': 'throw',    'third_singular': 'throws',  'past': 'threw',    'past_participle': 'thrown',  'present_participle': 'throwing'},
        'show':     {'base': 'show',     'third_singular': 'shows',   'past': 'showed',   'past_participle': 'shown',   'present_participle': 'showing'},
        'leave':    {'base': 'leave',    'third_singular': 'leaves',  'past': 'left',     'past_participle': 'left',    'present_participle': 'leaving'},
        'hold':     {'base': 'hold',     'third_singular': 'holds',   'past': 'held',     'past_participle': 'held',    'present_participle': 'holding'},
        'cut':      {'base': 'cut',      'third_singular': 'cuts',    'past': 'cut',      'past_participle': 'cut',     'present_participle': 'cutting'},
        'hit':      {'base': 'hit',      'third_singular': 'hits',    'past': 'hit',      'past_participle': 'hit',     'present_participle': 'hitting'},
        'put':      {'base': 'put',      'third_singular': 'puts',    'past': 'put',      'past_participle': 'put',     'present_participle': 'putting'},
        'let':      {'base': 'let',      'third_singular': 'lets',    'past': 'let',      'past_participle': 'let',     'present_participle': 'letting'},
        'cost':     {'base': 'cost',     'third_singular': 'costs',   'past': 'cost',     'past_participle': 'cost',    'present_participle': 'costing'},
        # 规则动词示例
        'play':     {'base': 'play',     'third_singular': 'plays',   'past': 'played',   'past_participle': 'played',  'present_participle': 'playing'},
        'talk':     {'base': 'talk',     'third_singular': 'talks',   'past': 'talked',   'past_participle': 'talked',  'present_participle': 'talking'},
        'walk':     {'base': 'walk',     'third_singular': 'walks',   'past': 'walked',   'past_participle': 'walked',  'present_participle': 'walking'},
        'look':     {'base': 'look',     'third_singular': 'looks',   'past': 'looked',   'past_participle': 'looked',  'present_participle': 'looking'},
        'work':     {'base': 'work',     'third_singular': 'works',   'past': 'worked',   'past_participle': 'worked',  'present_participle': 'working'},
        'live':     {'base': 'live',     'third_singular': 'lives',   'past': 'lived',    'past_participle': 'lived',   'present_participle': 'living'},
        'like':     {'base': 'like',     'third_singular': 'likes',   'past': 'liked',    'past_participle': 'liked',   'present_participle': 'liking'},
        'love':     {'base': 'love',     'third_singular': 'loves',   'past': 'loved',    'past_participle': 'loved',   'present_participle': 'loving'},
        'care':     {'base': 'care',     'third_singular': 'cares',   'past': 'cared',    'past_participle': 'cared',   'present_participle': 'caring'},
        'agree':    {'base': 'agree',    'third_singular': 'agrees',  'past': 'agreed',   'past_participle': 'agreed',  'present_participle': 'agreeing'},
        'rewrite':  {'base': 'rewrite',  'third_singular': 'rewrites','past': 'rewrote',  'past_participle': 'rewritten','present_participle': 'rewriting'},
        'study':    {'base': 'study',    'third_singular': 'studies', 'past': 'studied',  'past_participle': 'studied', 'present_participle': 'studying'},
        'try':      {'base': 'try',      'third_singular': 'tries',   'past': 'tried',    'past_participle': 'tried',   'present_participle': 'trying'},
        'carry':    {'base': 'carry',    'third_singular': 'carries', 'past': 'carried',  'past_participle': 'carried', 'present_participle': 'carrying'},
    }

    # 常见基础动词的中文释义表
    # 当词在 VERB_TENSES 中但不在 DICTIONARY 中时，用此表提供基础释义
    BASIC_VERB_MEANINGS = {
        'be': 'v. 是，存在',
        'have': 'v. 有，拥有',
        'do': 'v. 做，干',
        'go': 'v. 去，走',
        'make': 'v. 制作，使',
        'take': 'v. 拿，取',
        'come': 'v. 来',
        'see': 'v. 看见',
        'give': 'v. 给',
        'get': 'v. 得到，获得',
        'know': 'v. 知道，了解',
        'think': 'v. 想，思考',
        'say': 'v. 说',
        'find': 'v. 找到，发现',
        'write': 'v. 写',
        'run': 'v. 跑，运行',
        'read': 'v. 读，阅读',
        'speak': 'v. 说话',
        'begin': 'v. 开始',
        'drink': 'v. 喝，饮',
        'swim': 'v. 游泳',
        'sing': 'v. 唱，唱歌',
        'ring': 'v. 响，打电话',
        'grow': 'v. 生长，成长',
        'fly': 'v. 飞',
        'drive': 'v. 驾驶',
        'ride': 'v. 骑，乘',
        'rise': 'v. 上升，升起',
        'break': 'v. 打破',
        'choose': 'v. 选择',
        'forget': 'v. 忘记',
        'teach': 'v. 教',
        'catch': 'v. 抓住',
        'buy': 'v. 买',
        'bring': 'v. 带来',
        'fight': 'v. 战斗，打架',
        'feel': 'v. 感觉',
        'keep': 'v. 保持',
        'sleep': 'v. 睡觉',
        'meet': 'v. 遇见',
        'send': 'v. 发送',
        'spend': 'v. 花费',
        'build': 'v. 建造',
        'understand': 'v. 理解',
        'stand': 'v. 站立',
        'become': 'v. 变成',
        'eat': 'v. 吃，进食',
        'fall': 'v. 落下',
        'win': 'v. 赢',
        'lose': 'v. 失去，输',
        'wear': 'v. 穿，戴',
        'draw': 'v. 画，绘制',
        'throw': 'v. 扔，投掷',
        'show': 'v. 展示',
        'leave': 'v. 离开',
        'hold': 'v. 拿住',
        'cut': 'v. 切',
        'hit': 'v. 打',
        'put': 'v. 放',
        'let': 'v. 让',
        'cost': 'v. 花费',
        'play': 'v. 玩，播放',
        'talk': 'v. 谈话',
        'walk': 'v. 走，散步',
        'look': 'v. 看，瞧',
        'work': 'v. 工作',
        'live': 'v. 居住，生活',
        'like': 'v. 喜欢',
        'love': 'v. 爱',
        'care': 'v. 关心',
        'agree': 'v. 同意',
        'rewrite': 'v. 重写',
        'study': 'v. 学习',
        'try': 'v. 尝试',
        'carry': 'v. 搬运',
    }

    # 常见名词的不规则复数变形
    NOUN_PLURALS = {
        'man': 'men', 'woman': 'women', 'child': 'children',
        'foot': 'feet', 'tooth': 'teeth', 'mouse': 'mice',
        'goose': 'geese', 'person': 'people', 'ox': 'oxen',
        'leaf': 'leaves', 'life': 'lives', 'wife': 'wives',
        'knife': 'knives', 'wolf': 'wolves', 'half': 'halves',
        'shelf': 'shelves', 'loaf': 'loaves', 'thief': 'thieves',
        'calf': 'calves', 'self': 'selves',
        'sheep': 'sheep', 'deer': 'deer', 'fish': 'fish',
        'species': 'species', 'series': 'series', 'aircraft': 'aircraft',
        'man': 'men', 'policeman': 'policemen', 'fireman': 'firemen',
        'Englishman': 'Englishmen', 'Frenchman': 'Frenchmen',
        'child': 'children', 'ox': 'oxen',
    }

    # 常见形容词的不规则比较级/最高级
    ADJ_DEGREES = {
        'good': {'comparative': 'better', 'superlative': 'best'},
        'well': {'comparative': 'better', 'superlative': 'best'},
        'bad': {'comparative': 'worse', 'superlative': 'worst'},
        'ill': {'comparative': 'worse', 'superlative': 'worst'},
        'many': {'comparative': 'more', 'superlative': 'most'},
        'much': {'comparative': 'more', 'superlative': 'most'},
        'little': {'comparative': 'less', 'superlative': 'least'},
        'far': {'comparative': 'farther/further', 'superlative': 'farthest/furthest'},
        'old': {'comparative': 'older/elder', 'superlative': 'oldest/eldest'},
    }

    # 反向映射：比较级/最高级 → 原级（用于查询 worse/better/best 等变形词）
    # 手动指定优先映射到更常见的原级词（如 worse→bad 而非 worse→ill）
    REVERSE_ADJ_DEGREES = {
        'better': 'good', 'best': 'good',
        'worse': 'bad', 'worst': 'bad',
        'more': 'many', 'most': 'many',
        'less': 'little', 'least': 'little',
        'farther': 'far', 'further': 'far',
        'farthest': 'far', 'furthest': 'far',
        'older': 'old', 'elder': 'old',
        'oldest': 'old', 'eldest': 'old',
    }

    # 江西专升本常见词汇例句库
    # 这些例句模拟专升本英语考试中的常见用法
    ZHUANSHENBEN_EXAMPLES = {
        'do': [
            {'en': 'What do you plan to do after graduation?', 'zh': '你毕业后打算做什么？'},
            {'en': 'He does his homework in the library every evening.', 'zh': '他每天晚上在图书馆做作业。'},
        ],
        'go': [
            {'en': 'She wants to go to college in Beijing.', 'zh': '她想去北京上大学。'},
            {'en': 'Time goes by quickly when you are busy.', 'zh': '忙碌的时候时间过得很快。'},
        ],
        'make': [
            {'en': 'You need to make a plan for your study.', 'zh': '你需要制定一个学习计划。'},
            {'en': 'Hard work can make your dream come true.', 'zh': '努力可以让你的梦想成真。'},
        ],
        'take': [
            {'en': 'It takes time to learn a foreign language.', 'zh': '学习一门外语需要时间。'},
            {'en': 'Students should take notes in class.', 'zh': '学生应该在课堂上做笔记。'},
        ],
        'get': [
            {'en': 'She got high marks in the English exam.', 'zh': '她在英语考试中得了高分。'},
            {'en': 'You can get more information on the website.', 'zh': '你可以在网站上获取更多信息。'},
        ],
        'have': [
            {'en': 'Every student has the right to receive education.', 'zh': '每个学生都有接受教育的权利。'},
            {'en': 'We have to finish the assignment before Friday.', 'zh': '我们必须在周五前完成作业。'},
        ],
        'give': [
            {'en': 'The teacher gave us a lot of homework.', 'zh': '老师给我们留了很多作业。'},
            {'en': 'Can you give me some advice on learning English?', 'zh': '你能给我一些学英语的建议吗？'},
        ],
        'learn': [
            {'en': 'We learn English to communicate with the world.', 'zh': '我们学英语是为了与世界交流。'},
            {'en': 'It is never too late to learn.', 'zh': '学习永远不会太晚。'},
        ],
        'read': [
            {'en': 'Reading English newspapers can improve your vocabulary.', 'zh': '阅读英文报纸可以扩大词汇量。'},
            {'en': 'She reads at least one book every month.', 'zh': '她每月至少读一本书。'},
        ],
        'write': [
            {'en': 'You need to write an essay about your future plan.', 'zh': '你需要写一篇关于未来计划的短文。'},
            {'en': 'He wrote a letter to his former teacher.', 'zh': '他给以前的老师写了一封信。'},
        ],
        'study': [
            {'en': 'She studies hard to pass the entrance exam.', 'zh': '她努力学习以通过入学考试。'},
            {'en': 'Many adults choose to study for a degree.', 'zh': '许多成年人选择攻读学位。'},
        ],
        'work': [
            {'en': 'He works part-time to support his studies.', 'zh': '他兼职工作来资助学业。'},
            {'en': 'Team work plays a vital role in modern society.', 'zh': '团队合作在现代社会中起着至关重要的作用。'},
        ],
        'live': [
            {'en': 'Many students live on campus during college.', 'zh': '许多学生在大学期间住在校园里。'},
            {'en': 'We should live a healthy lifestyle.', 'zh': '我们应该过健康的生活方式。'},
        ],
        'think': [
            {'en': 'I think education is the most important thing.', 'zh': '我认为教育是最重要的事情。'},
            {'en': 'Think carefully before you make a decision.', 'zh': '做决定前要仔细考虑。'},
        ],
        'know': [
            {'en': 'As we all know, practice makes perfect.', 'zh': '众所周知，熟能生巧。'},
            {'en': 'I want to know more about this program.', 'zh': '我想了解更多关于这个项目的信息。'},
        ],
        'ability': [
            {'en': 'She has the ability to speak fluent English.', 'zh': '她有能力说流利的英语。'},
            {'en': 'We should improve our communication abilities.', 'zh': '我们应该提高我们的沟通能力。'},
        ],
        'abroad': [
            {'en': 'He plans to study abroad after graduation.', 'zh': '他计划毕业后去国外留学。'},
            {'en': 'Many students choose to go abroad for further education.', 'zh': '许多学生选择出国深造。'},
        ],
        'accept': [
            {'en': 'I am glad to accept your invitation.', 'zh': '我很高兴接受你的邀请。'},
            {'en': 'The college accepted her application.', 'zh': '学院接受了她的申请。'},
        ],
        'achieve': [
            {'en': 'Hard work is the key to achieving success.', 'zh': '努力是取得成功的关键。'},
            {'en': 'She achieved her goal of passing the exam.', 'zh': '她实现了通过考试的目标。'},
        ],
        'acquire': [
            {'en': 'Students should acquire good study habits.', 'zh': '学生应该养成良好的学习习惯。'},
            {'en': 'He acquired a lot of knowledge in college.', 'zh': '他在大学里获得了很多知识。'},
        ],
        'adapt': [
            {'en': 'We must adapt to the changing environment.', 'zh': '我们必须适应不断变化的环境。'},
            {'en': 'Freshmen need time to adapt to college life.', 'zh': '新生需要时间来适应大学生活。'},
        ],
        'advantage': [
            {'en': 'Reading extensively gives you a great advantage.', 'zh': '广泛阅读会给你带来很大优势。'},
            {'en': 'What are the advantages of studying online?', 'zh': '在线学习有哪些优势？'},
        ],
        'advice': [
            {'en': 'Can you give me some advice on learning English?', 'zh': '你能给我一些学英语的建议吗？'},
            {'en': 'The teacher gave us valuable advice.', 'zh': '老师给了我们宝贵的建议。'},
        ],
        'affect': [
            {'en': 'The weather can affect our mood.', 'zh': '天气会影响我们的心情。'},
            {'en': 'Lack of sleep affects your study efficiency.', 'zh': '睡眠不足会影响你的学习效率。'},
        ],
        'afford': [
            {'en': 'Many families cannot afford college tuition.', 'zh': '许多家庭负担不起大学学费。'},
            {'en': 'I cannot afford to waste any time.', 'zh': '我浪费不起任何时间。'},
        ],
        'attempt': [
            {'en': 'He made an attempt to climb the mountain.', 'zh': '他尝试攀登那座山。'},
            {'en': 'Her attempt to pass the exam was successful.', 'zh': '她通过考试的努力成功了。'},
        ],
        'attend': [
            {'en': 'All students are required to attend the lecture.', 'zh': '所有学生都必须参加讲座。'},
            {'en': 'He decided to attend college in another city.', 'zh': '他决定去另一个城市上大学。'},
        ],
        'attract': [
            {'en': 'The campus attracts many visitors every year.', 'zh': '校园每年吸引许多参观者。'},
            {'en': 'The program attracts students from all over the country.', 'zh': '该项目吸引了来自全国各地的学生。'},
        ],
        'available': [
            {'en': 'The book is available in the library.', 'zh': '这本书在图书馆可以借到。'},
            {'en': 'Scholarships are available for top students.', 'zh': '奖学金面向优秀学生提供。'},
        ],
        'aware': [
            {'en': 'We should be aware of the importance of education.', 'zh': '我们应该意识到教育的重要性。'},
            {'en': 'Are you aware of the exam schedule?', 'zh': '你知道考试时间安排吗？'},
        ],
        'benefit': [
            {'en': 'Regular exercise benefits our health.', 'zh': '经常运动有益于我们的健康。'},
            {'en': 'Students can benefit a lot from reading.', 'zh': '学生能从阅读中受益匪浅。'},
        ],
        'capable': [
            {'en': 'She is capable of doing the job well.', 'zh': '她有能力做好这份工作。'},
            {'en': 'Every student is capable of passing the exam.', 'zh': '每个学生都有能力通过考试。'},
        ],
        'career': [
            {'en': 'Choosing the right career is very important.', 'zh': '选择正确的职业非常重要。'},
            {'en': 'He started his career as a teacher.', 'zh': '他以教师的身份开始了职业生涯。'},
        ],
        'challenge': [
            {'en': 'The exam was a real challenge for us.', 'zh': '考试对我们来说是一个真正的挑战。'},
            {'en': 'We should face challenges with courage.', 'zh': '我们应该勇敢地面对挑战。'},
        ],
        'communicate': [
            {'en': 'Good leaders communicate their ideas clearly.', 'zh': '好的领导者能清楚地表达自己的想法。'},
            {'en': 'We can communicate with people online.', 'zh': '我们可以在线与人交流。'},
        ],
        'compare': [
            {'en': 'Compare your answer with the correct one.', 'zh': '把你的答案与正确答案进行比较。'},
            {'en': 'Compared with last year, our scores have improved.', 'zh': '与去年相比，我们的成绩提高了。'},
        ],
        'compete': [
            {'en': 'Students compete for scholarships every year.', 'zh': '学生每年都为奖学金竞争。'},
            {'en': 'We must compete with others in the job market.', 'zh': '我们必须在就业市场中与他人竞争。'},
        ],
        'complete': [
            {'en': 'Please complete the form before Friday.', 'zh': '请在周五之前填写完表格。'},
            {'en': 'He has completed his master\'s degree.', 'zh': '他已经完成了硕士学位。'},
        ],
        'concern': [
            {'en': 'Education is a matter of public concern.', 'zh': '教育是公众关注的问题。'},
            {'en': 'Parents are concerned about their children\'s safety.', 'zh': '父母关心孩子们的安全。'},
        ],
        'confident': [
            {'en': 'She is confident about passing the interview.', 'zh': '她对通过面试充满信心。'},
            {'en': 'Be confident in yourself and you will succeed.', 'zh': '对自己有信心，你就会成功。'},
        ],
        'consider': [
            {'en': 'Please consider my suggestion carefully.', 'zh': '请仔细考虑我的建议。'},
            {'en': 'He is considering changing his major.', 'zh': '他正在考虑换专业。'},
        ],
        'continue': [
            {'en': 'She decided to continue her studies abroad.', 'zh': '她决定继续出国深造。'},
            {'en': 'We will continue to work hard next semester.', 'zh': '下学期我们将继续努力学习。'},
        ],
        'create': [
            {'en': 'The Internet has created many new jobs.', 'zh': '互联网创造了许多新工作。'},
            {'en': 'We should create a good learning environment.', 'zh': '我们应该创造良好的学习环境。'},
        ],
        'decide': [
            {'en': 'She decided to apply for the scholarship.', 'zh': '她决定申请奖学金。'},
            {'en': 'Have you decided on your major yet?', 'zh': '你决定好你的专业了吗？'},
        ],
        'degree': [
            {'en': 'He earned a bachelor\'s degree in English.', 'zh': '他获得了英语学士学位。'},
            {'en': 'A college degree can help you find a better job.', 'zh': '大学学位可以帮助你找到更好的工作。'},
        ],
        'depend': [
            {'en': 'Success depends on hard work.', 'zh': '成功取决于努力。'},
            {'en': 'The result depends on how much effort you put in.', 'zh': '结果取决于你投入多少努力。'},
        ],
        'develop': [
            {'en': 'Reading helps develop your imagination.', 'zh': '阅读有助于发展想象力。'},
            {'en': 'The city has developed rapidly in recent years.', 'zh': '这座城市近年来发展迅速。'},
        ],
        'difficulty': [
            {'en': 'I have difficulty understanding this passage.', 'zh': '我理解这篇文章有困难。'},
            {'en': 'She passed the exam without difficulty.', 'zh': '她毫无困难地通过了考试。'},
        ],
        'discover': [
            {'en': 'Scientists have discovered a new species.', 'zh': '科学家发现了一个新物种。'},
            {'en': 'I discovered that learning English can be fun.', 'zh': '我发现学英语可以很有趣。'},
        ],
        'economy': [
            {'en': 'The economy is growing steadily.', 'zh': '经济正在稳步增长。'},
            {'en': 'Education plays an important role in the economy.', 'zh': '教育在经济中起着重要作用。'},
        ],
        'education': [
            {'en': 'Education is the key to a better future.', 'zh': '教育是通向美好未来的关键。'},
            {'en': 'Higher education opens up more opportunities.', 'zh': '高等教育带来更多机会。'},
        ],
        'effort': [
            {'en': 'With more effort, you can achieve your goal.', 'zh': '付出更多努力，你就能实现目标。'},
            {'en': 'Her efforts were finally rewarded.', 'zh': '她的努力终于得到了回报。'},
        ],
        'employ': [
            {'en': 'The company employs over 500 people.', 'zh': '这家公司雇用了500多人。'},
            {'en': 'He is employed as a software engineer.', 'zh': '他被聘为软件工程师。'},
        ],
        'encourage': [
            {'en': 'Teachers should encourage students to think independently.', 'zh': '老师应该鼓励学生独立思考。'},
            {'en': 'My parents encouraged me to study harder.', 'zh': '我父母鼓励我更加努力学习。'},
        ],
        'environment': [
            {'en': 'We should protect the living environment.', 'zh': '我们应该保护生活环境。'},
            {'en': 'A quiet environment is good for studying.', 'zh': '安静的环境有利于学习。'},
        ],
        'essential': [
            {'en': 'Water is essential for life.', 'zh': '水是生命必不可少的。'},
            {'en': 'Good study habits are essential for success.', 'zh': '良好的学习习惯对成功至关重要。'},
        ],
        'establish': [
            {'en': 'The university was established in 1950.', 'zh': '这所大学建立于1950年。'},
            {'en': 'They established a new research center.', 'zh': '他们建立了一个新的研究中心。'},
        ],
        'examine': [
            {'en': 'The doctor examined the patient carefully.', 'zh': '医生仔细检查了病人。'},
            {'en': 'Let us examine the problem more closely.', 'zh': '让我们更仔细地研究这个问题。'},
        ],
        'experience': [
            {'en': 'Traveling gives you valuable experience.', 'zh': '旅行给你宝贵的经验。'},
            {'en': 'She has years of teaching experience.', 'zh': '她有多年的教学经验。'},
        ],
        'explain': [
            {'en': 'Can you explain this sentence to me?', 'zh': '你能给我解释这个句子吗？'},
            {'en': 'The teacher explained the grammar clearly.', 'zh': '老师清楚地解释了语法。'},
        ],
        'explore': [
            {'en': 'We should explore new ways of learning.', 'zh': '我们应该探索新的学习方式。'},
            {'en': 'Scientists are exploring the ocean depths.', 'zh': '科学家们正在探索海洋深处。'},
        ],
        'express': [
            {'en': 'Words cannot express how grateful I am.', 'zh': '言语无法表达我的感激之情。'},
            {'en': 'Learn to express yourself in English.', 'zh': '学会用英语表达自己。'},
        ],
        'improve': [
            {'en': 'You need to improve your writing skills.', 'zh': '你需要提高写作能力。'},
            {'en': 'Her English has improved a lot this year.', 'zh': '她的英语今年进步了很多。'},
        ],
        'include': [
            {'en': 'The price includes meals and accommodation.', 'zh': '价格包括餐食和住宿。'},
            {'en': 'The course includes grammar and writing.', 'zh': '课程包括语法和写作。'},
        ],
        'increase': [
            {'en': 'The number of students has increased.', 'zh': '学生人数增加了。'},
            {'en': 'We need to increase our vocabulary.', 'zh': '我们需要增加词汇量。'},
        ],
        'knowledge': [
            {'en': 'Knowledge is power.', 'zh': '知识就是力量。'},
            {'en': 'He has a wide knowledge of history.', 'zh': '他有丰富的历史知识。'},
        ],
        'opportunity': [
            {'en': 'This exam is a great opportunity for us.', 'zh': '这次考试对我们来说是个好机会。'},
            {'en': 'Education gives everyone equal opportunities.', 'zh': '教育给每个人平等的机会。'},
        ],
        'practice': [
            {'en': 'Practice makes perfect.', 'zh': '熟能生巧。'},
            {'en': 'You need more speaking practice.', 'zh': '你需要更多的口语练习。'},
        ],
        'prepare': [
            {'en': 'We must prepare well for the exam.', 'zh': '我们必须为考试做好准备。'},
            {'en': 'She is preparing for the college entrance exam.', 'zh': '她正在为升学考试做准备。'},
        ],
        'succeed': [
            {'en': 'If you work hard, you will succeed.', 'zh': '如果你努力，你就会成功。'},
            {'en': 'She succeeded in getting the scholarship.', 'zh': '她成功获得了奖学金。'},
        ],
        'suggest': [
            {'en': 'I suggest that you read more English books.', 'zh': '我建议你多读英语书。'},
            {'en': 'The doctor suggested taking more exercise.', 'zh': '医生建议多运动。'},
        ],
        'understand': [
            {'en': 'I cannot understand this difficult sentence.', 'zh': '我无法理解这个难句。'},
            {'en': 'Can you understand what the author wants to say?', 'zh': '你能理解作者想表达什么吗？'},
        ],
        'forever': [
            {'en': 'I will remember this happy moment forever.', 'zh': '我会永远记住这个快乐的时刻。'},
            {'en': 'Our friendship will last forever.', 'zh': '我们的友谊将永远持续下去。'},
        ],
        'sometimes': [
            {'en': 'Sometimes it is hard to make a decision.', 'zh': '有时候做决定很难。'},
            {'en': 'I sometimes go to the library after class.', 'zh': '我有时课后去图书馆。'},
        ],
        'conclude': [
            {'en': 'We can conclude that hard work leads to success.', 'zh': '我们可以得出结论：努力带来成功。'},
            {'en': 'The meeting concluded with a discussion.', 'zh': '会议以讨论结束。'},
        ],
        'purpose': [
            {'en': 'The purpose of learning English is to communicate.', 'zh': '学英语的目的是交流。'},
            {'en': 'He studies hard for the purpose of passing the exam.', 'zh': '他努力学习是为了通过考试。'},
        ],
        'thing': [
            {'en': 'The most important thing is to never give up.', 'zh': '最重要的事情是永远不要放弃。'},
            {'en': 'Learning English is a good thing for your future.', 'zh': '学英语对你的未来是件好事。'},
        ],
        'take care of': [
            {'en': 'Parents take care of their children with love.', 'zh': '父母用爱照顾他们的孩子。'},
            {'en': 'We should take care of our environment.', 'zh': '我们应该爱护我们的环境。'},
        ],
        'talk': [
            {'en': 'We need to talk about this problem.', 'zh': '我们需要谈谈这个问题。'},
            {'en': 'He likes to talk with his friends after class.', 'zh': '他喜欢课后和朋友聊天。'},
        ],
        'run': [
            {'en': 'She runs every morning to keep healthy.', 'zh': '她每天早上跑步保持健康。'},
            {'en': 'He decided to run for president of the student union.', 'zh': '他决定竞选学生会主席。'},
        ],
        'playfulness': [
            {'en': "The children's playfulness made the whole park lively.", 'zh': '孩子们的顽皮天性让整个公园充满了活力。'},
            {'en': 'Her playfulness brings joy to everyone around her.', 'zh': '她的活泼给周围的人带来快乐。'},
        ],
        'headphone': [
            {'en': 'She always wears her headphones while studying.', 'zh': '她学习时总是戴着耳机。'},
            {'en': 'I bought a new pair of headphones for online classes.', 'zh': '我买了一副新耳机用于上网课。'},
        ],
        'smartphone': [
            {'en': 'I rely on my smartphone for navigation and communication.', 'zh': '我依赖智能手机进行导航和通讯。'},
            {'en': 'The smartphone has become an essential tool for learning.', 'zh': '智能手机已成为学习的重要工具。'},
        ],
        'breakthrough': [
            {'en': 'The team achieved a significant breakthrough in AI research.', 'zh': '该团队在人工智能研究中取得了重大突破。'},
            {'en': 'This discovery represents a major breakthrough in medicine.', 'zh': '这一发现代表了医学上的重大突破。'},
        ],
        'traffic regulations': [
            {'en': 'Drivers must strictly follow all traffic regulations.', 'zh': '驾驶员必须严格遵守所有交通规则。'},
            {'en': 'Everyone should be aware of traffic regulations.', 'zh': '每个人都应该了解交通规则。'},
        ],
        'quickly': [
            {'en': 'He finished his homework quickly and went to play.', 'zh': '他很快完成了作业然后去玩了。'},
            {'en': 'The students quickly adapted to the new environment.', 'zh': '学生们很快适应了新环境。'},
        ],
        'careful': [
            {'en': 'Be careful when crossing the road.', 'zh': '过马路时要小心。'},
            {'en': 'He is a careful student who never makes mistakes.', 'zh': '他是一个细心的人，从不犯错。'},
        ],
        'careless': [
            {'en': 'It was careless of him to lose the key.', 'zh': '他弄丢了钥匙，太粗心了。'},
            {'en': 'A careless mistake cost him the exam.', 'zh': '一个粗心的错误让他考试失利。'},
        ],
        'friendship': [
            {'en': 'Their friendship lasted for many years.', 'zh': '他们的友谊持续了很多年。'},
            {'en': 'True friendship is more valuable than gold.', 'zh': '真正的友谊比黄金更珍贵。'},
        ],
        'agreement': [
            {'en': 'We reached an agreement after a long discussion.', 'zh': '经过长时间讨论，我们达成了协议。'},
            {'en': 'They signed the agreement with a handshake.', 'zh': '他们握手签署了协议。'},
        ],
        'kindness': [
            {'en': 'Thank you for your kindness and support.', 'zh': '感谢你的善意和支持。'},
            {'en': 'She is known for her kindness to everyone.', 'zh': '她以对每个人的善良而闻名。'},
        ],
        'homework': [
            {'en': 'I have a lot of homework to do today.', 'zh': '我今天有很多作业要做。'},
            {'en': 'Have you finished your homework yet?', 'zh': '你完成作业了吗？'},
        ],
        'football': [
            {'en': 'He likes playing football after school.', 'zh': '他喜欢放学后踢足球。'},
            {'en': 'The football match was very exciting.', 'zh': '这场足球比赛非常精彩。'},
        ],
        'basketball': [
            {'en': 'Basketball is my favorite sport.', 'zh': '篮球是我最喜欢的运动。'},
            {'en': 'They played basketball for two hours.', 'zh': '他们打了两个小时篮球。'},
        ],
        'playground': [
            {'en': 'Children are playing on the playground.', 'zh': '孩子们正在操场上玩。'},
            {'en': 'The school has a large playground for sports.', 'zh': '学校有一个大操场供运动使用。'},
        ],
        'sunglasses': [
            {'en': 'She wears sunglasses in summer.', 'zh': '她夏天戴太阳镜。'},
            {'en': 'I bought a new pair of sunglasses for the trip.', 'zh': '我为旅行买了一副新太阳镜。'},
        ],
        'apple': [
            {'en': 'I eat an apple every day to stay healthy.', 'zh': '我每天吃一个苹果保持健康。'},
            {'en': 'An apple a day keeps the doctor away.', 'zh': '一天一苹果，医生远离我。'},
        ],
        'important': [
            {'en': 'Family is more important than anything else.', 'zh': '家庭比其他任何事情都重要。'},
            {'en': 'What is the most important thing in learning English?', 'zh': '学英语中最重要的事情是什么？'},
        ],
        'education': [
            {'en': 'Education is the key to success in life.', 'zh': '教育是人生成功的关键。'},
            {'en': 'Everyone has the right to receive education.', 'zh': '每个人都有接受教育的权利。'},
        ],
        'success': [
            {'en': 'Hard work is the foundation of success.', 'zh': '努力是成功的基础。'},
            {'en': 'She achieved great success in her career.', 'zh': '她在事业上取得了巨大成功。'},
        ],
        'opportunity': [
            {'en': 'This exam is a great opportunity for you.', 'zh': '这次考试对你来说是一个很好的机会。'},
            {'en': 'Don\'t miss the opportunity to study abroad.', 'zh': '不要错过出国留学的机会。'},
        ],
        'challenge': [
            {'en': 'Learning English is a challenge, but also an opportunity.', 'zh': '学英语是一个挑战，也是一个机会。'},
            {'en': 'We should face challenges with courage.', 'zh': '我们应该勇敢地面对挑战。'},
        ],
        'develop': [
            {'en': 'Reading helps develop your thinking skills.', 'zh': '阅读有助于发展你的思维能力。'},
            {'en': 'The city is developing rapidly in recent years.', 'zh': '这座城市近年来发展迅速。'},
        ],
        'improve': [
            {'en': 'We should improve our English step by step.', 'zh': '我们应该逐步提高英语水平。'},
            {'en': 'Practice is the best way to improve your skills.', 'zh': '练习是提高技能的最好方法。'},
        ],
        'environment': [
            {'en': 'We should protect our living environment.', 'zh': '我们应该保护我们的生活环境。'},
            {'en': 'A good learning environment is very important.', 'zh': '良好的学习环境非常重要。'},
        ],
        'society': [
            {'en': 'Everyone should contribute to society.', 'zh': '每个人都应该为社会做贡献。'},
            {'en': 'In modern society, English is widely used.', 'zh': '在现代社会中，英语被广泛使用。'},
        ],
        # 常见核心词精选例句
        'nerve': [
            {'en': 'The doctor examined the patient\'s nerve carefully.', 'zh': '医生仔细检查了病人的神经。'},
            {'en': 'It takes a lot of nerve to speak in front of many people.', 'zh': '在很多人面前讲话需要很大的勇气。'},
        ],
        'pressure': [
            {'en': 'Students are under great pressure before exams.', 'zh': '学生在考试前承受着巨大的压力。'},
            {'en': 'The pressure of the water caused the pipe to burst.', 'zh': '水的压力导致管道破裂。'},
        ],
        'culture': [
            {'en': 'Chinese culture has a long history of over 5000 years.', 'zh': '中国文化有五千多年的悠久历史。'},
            {'en': 'We should respect different cultures around the world.', 'zh': '我们应该尊重世界上不同的文化。'},
        ],
        'nature': [
            {'en': 'It is human nature to seek happiness.', 'zh': '追求幸福是人的本性。'},
            {'en': 'We should live in harmony with nature.', 'zh': '我们应该与自然和谐相处。'},
        ],
        'development': [
            {'en': 'The city has seen rapid development in recent years.', 'zh': '这座城市近年来发展迅速。'},
            {'en': 'Education plays a key role in personal development.', 'zh': '教育在个人发展中起着关键作用。'},
        ],
        'stress': [
            {'en': 'Too much stress can affect your health.', 'zh': '过多的压力会影响你的健康。'},
            {'en': 'The teacher stressed the importance of reading.', 'zh': '老师强调了阅读的重要性。'},
        ],
        'nervous': [
            {'en': 'She felt nervous before the interview.', 'zh': '她在面试前感到紧张。'},
            {'en': 'Public speaking makes many people nervous.', 'zh': '公众演讲让很多人感到紧张。'},
        ],
        'tense': [
            {'en': 'The atmosphere in the room was very tense.', 'zh': '房间里的气氛非常紧张。'},
            {'en': 'He used the wrong tense in his essay.', 'zh': '他在作文中用错了时态。'},
        ],
        'good': [
            {'en': 'She is a good student who always helps others.', 'zh': '她是一个总是帮助别人的好学生。'},
            {'en': 'This book is good for improving your vocabulary.', 'zh': '这本书对提高词汇量很有帮助。'},
        ],
        'worse': [
            {'en': 'The weather became worse in the afternoon.', 'zh': '下午天气变得更糟了。'},
            {'en': 'His condition is getting worse day by day.', 'zh': '他的状况一天天恶化。'},
        ],
        'press': [
            {'en': 'Press the button to start the machine.', 'zh': '按下按钮启动机器。'},
            {'en': 'The press reported the event in detail.', 'zh': '新闻界详细报道了这一事件。'},
        ],
        'chef': [
            {'en': 'The chef prepared a delicious meal for us.', 'zh': '厨师为我们准备了一顿美味的饭菜。'},
            {'en': 'She dreams of becoming a famous chef.', 'zh': '她梦想成为一名著名的厨师。'},
        ],
        'cooker': [
            {'en': 'I bought a new rice cooker yesterday.', 'zh': '我昨天买了一个新电饭煲。'},
            {'en': 'A pressure cooker can save a lot of cooking time.', 'zh': '高压锅可以节省很多烹饪时间。'},
        ],
        'stressful': [
            {'en': 'Moving to a new city can be very stressful.', 'zh': '搬到新城市可能会非常有压力。'},
            {'en': 'She finds her new job quite stressful.', 'zh': '她觉得新工作压力很大。'},
        ],
        'failure': [
            {'en': 'Failure is the mother of success.', 'zh': '失败是成功之母。'},
            {'en': 'The power failure caused the machine to stop.', 'zh': '电力故障导致机器停止运转。'},
        ],
        'pleasure': [
            {'en': 'It\'s a pleasure to meet you.', 'zh': '很高兴认识你。'},
            {'en': 'Reading brings me great pleasure.', 'zh': '阅读给我带来很大的快乐。'},
        ],
        # ===== 数据库中需要修复的单词例句 =====
        'understand': [
            {'en': 'I couldn\'t understand the passage until I read it twice.', 'zh': '直到读了两遍我才理解这篇文章。'},
            {'en': 'Can you understand what the author wants to say?', 'zh': '你能理解作者想表达什么吗？'},
        ],
        'rewrite': [
            {'en': 'The teacher asked him to rewrite the composition.', 'zh': '老师让他重写作文。'},
            {'en': 'She had to rewrite the report because of the errors.', 'zh': '因为有些错误，她不得不重写报告。'},
        ],
        'teacher': [
            {'en': 'Our English teacher encourages us to speak more in class.', 'zh': '我们的英语老师鼓励我们在课堂上多发言。'},
            {'en': 'She has been a teacher for over twenty years.', 'zh': '她当老师已经二十多年了。'},
        ],
        'reading': [
            {'en': 'Extensive reading can broaden your horizons.', 'zh': '广泛阅读可以开阔你的视野。'},
            {'en': 'The reading comprehension test was quite difficult.', 'zh': '阅读理解测试相当难。'},
        ],
        'homework': [
            {'en': 'Remember to finish your homework before the deadline.', 'zh': '记得在截止日期前完成作业。'},
            {'en': 'The teacher assigned too much homework this weekend.', 'zh': '老师这个周末布置了太多作业。'},
        ],
        'careful': [
            {'en': 'You should be careful with your spelling in the exam.', 'zh': '考试时你应该注意拼写。'},
            {'en': 'A careful reader can find the details in the text.', 'zh': '细心的读者能发现文章中的细节。'},
        ],
        'kindness': [
            {'en': 'She showed great kindness to the new students.', 'zh': '她对新生表现出了极大的善意。'},
            {'en': 'An act of kindness can brighten someone\'s day.', 'zh': '一个善举可以照亮某人的一天。'},
        ],
        'look forward to': [
            {'en': 'I look forward to hearing from you soon.', 'zh': '我期待早日收到你的回复。'},
            {'en': 'We are looking forward to the summer holiday.', 'zh': '我们正期待着暑假的到来。'},
        ],
        'look up to': [
            {'en': 'Many students look up to their teachers as role models.', 'zh': '许多学生把老师当作榜样来敬仰。'},
            {'en': 'She has always looked up to her older sister.', 'zh': '她一直敬仰她的姐姐。'},
        ],
        'tension': [
            {'en': 'There was a lot of tension in the room during the exam.', 'zh': '考试期间教室里气氛很紧张。'},
            {'en': 'The tension between the two countries has increased.', 'zh': '两国之间的紧张关系加剧了。'},
        ],
        'the best': [
            {'en': 'She is one of the best students in our class.', 'zh': '她是我们班最优秀的学生之一。'},
            {'en': 'Who do you think is the best candidate for this position?', 'zh': '你认为谁是这个职位的最佳人选？'},
        ],
        'test': [
            {'en': 'The final test will cover all the chapters we learned.', 'zh': '期末考试将涵盖我们学过的所有章节。'},
            {'en': 'You need to test the hypothesis before drawing a conclusion.', 'zh': '在得出结论之前，你需要检验这个假设。'},
        ],
        'be under too much pressure': [
            {'en': 'Many students are under too much pressure nowadays.', 'zh': '如今许多学生承受着太大的压力。'},
            {'en': 'Being under too much pressure can lead to health problems.', 'zh': '承受过大压力可能导致健康问题。'},
        ],
        'water': [
            {'en': 'Drinking enough water every day is good for your health.', 'zh': '每天喝足够的水对健康有益。'},
            {'en': 'Please water the flowers before you leave.', 'zh': '离开前请给花浇水。'},
        ],
        'thing': [
            {'en': 'The most important thing is to believe in yourself.', 'zh': '最重要的事情是相信自己。'},
            {'en': 'There are many things we can do to improve our English.', 'zh': '我们可以做很多事情来提高英语水平。'},
        ],
        'information': [
            {'en': 'You can find more information on the school website.', 'zh': '你可以在学校网站上找到更多信息。'},
            {'en': 'The book provides useful information about career planning.', 'zh': '这本书提供了关于职业规划的有用信息。'},
        ],
        'apple': [
            {'en': 'An apple a day keeps the doctor away.', 'zh': '一天一个苹果，医生远离我。'},
            {'en': 'She bought some fresh apples at the market.', 'zh': '她在市场上买了一些新鲜的苹果。'},
        ],
        'headphone': [
            {'en': 'He listens to English podcasts with his headphones.', 'zh': '他用耳机听英语播客。'},
            {'en': 'Please put on your headphones for the listening test.', 'zh': '请戴上耳机准备听力考试。'},
        ],
        'breakthrough': [
            {'en': 'Scientists have made a major breakthrough in cancer research.', 'zh': '科学家在癌症研究方面取得了重大突破。'},
            {'en': 'The new technology represents a breakthrough in communication.', 'zh': '这项新技术代表了通讯领域的突破。'},
        ],
        'playfulness': [
            {'en': 'The children\'s playfulness filled the room with laughter.', 'zh': '孩子们的活泼让房间里充满了笑声。'},
            {'en': 'Her playfulness made the learning process more enjoyable.', 'zh': '她的活泼让学习过程更加愉快。'},
        ],
        'beautiful': [
            {'en': 'The campus looks especially beautiful in spring.', 'zh': '春天校园显得格外美丽。'},
            {'en': 'What a beautiful poem she wrote for the competition!', 'zh': '她为比赛写了一首多美的诗啊！'},
        ],
        'quickly': [
            {'en': 'The economy of this city has grown quickly in recent years.', 'zh': '近年来这座城市的经济发展很快。'},
            {'en': 'Please answer the question as quickly as possible.', 'zh': '请尽快回答这个问题。'},
        ],
        'running': [
            {'en': 'Running every morning helps him stay energetic.', 'zh': '每天早上跑步帮助他保持精力充沛。'},
            {'en': 'The running water in the river sounds like music.', 'zh': '河里流淌的水声如同音乐。'},
        ],
        'football': [
            {'en': 'Football is the most popular sport in the world.', 'zh': '足球是世界上最受欢迎的运动。'},
            {'en': 'He was injured during the football match last week.', 'zh': '他在上周的足球比赛中受伤了。'},
        ],
        'basketball': [
            {'en': 'Yao Ming is one of the greatest basketball players in China.', 'zh': '姚明是中国最伟大的篮球运动员之一。'},
            {'en': 'They practice basketball every afternoon after school.', 'zh': '他们每天放学后练习篮球。'},
        ],
        'sunglasses': [
            {'en': 'She wore a pair of sunglasses to protect her eyes from the sun.', 'zh': '她戴了一副太阳镜来保护眼睛免受阳光照射。'},
            {'en': 'He forgot his sunglasses when he went to the beach.', 'zh': '他去海滩时忘了带太阳镜。'},
        ],
        'playground': [
            {'en': 'The children were playing happily on the playground.', 'zh': '孩子们在操场上快乐地玩耍。'},
            {'en': 'Our school is planning to build a new playground.', 'zh': '我们学校计划建一个新操场。'},
        ],
        'careless': [
            {'en': 'He made several careless mistakes in the math exam.', 'zh': '他在数学考试中犯了几处粗心的错误。'},
            {'en': 'A careless driver may cause serious accidents.', 'zh': '粗心的驾驶员可能引发严重事故。'},
        ],
        'friendship': [
            {'en': 'True friendship is more valuable than money.', 'zh': '真正的友谊比金钱更有价值。'},
            {'en': 'Their friendship began when they were in primary school.', 'zh': '他们的友谊始于小学时期。'},
        ],
        'agreement': [
            {'en': 'After a long discussion, they finally reached an agreement.', 'zh': '经过长时间的讨论，他们终于达成了协议。'},
            {'en': 'Please read the agreement carefully before signing it.', 'zh': '签署前请仔细阅读协议。'},
        ],
        'smartphone': [
            {'en': 'Smartphones have become an essential part of our daily life.', 'zh': '智能手机已成为我们日常生活中不可或缺的一部分。'},
            {'en': 'Many students use smartphones to look up new words.', 'zh': '许多学生用智能手机查生词。'},
        ],
        'happiness': [
            {'en': 'True happiness comes from within, not from money.', 'zh': '真正的幸福来自内心，而非金钱。'},
            {'en': 'The birth of her baby brought her great happiness.', 'zh': '孩子的出生给她带来了巨大的幸福。'},
        ],
        'classroom': [
            {'en': 'Every classroom in our school is equipped with a computer.', 'zh': '我们学校每间教室都配有电脑。'},
            {'en': 'Please keep the classroom clean and tidy.', 'zh': '请保持教室干净整洁。'},
        ],
        'talk': [
            {'en': 'The professor will give a talk on career development.', 'zh': '教授将做一场关于职业发展的讲座。'},
            {'en': 'We need to have a serious talk about your future.', 'zh': '我们需要认真谈谈你的未来。'},
        ],
        'run': [
            {'en': 'She runs five kilometers every morning to keep fit.', 'zh': '她每天早上跑五公里来保持健康。'},
            {'en': 'The river runs through the center of the city.', 'zh': '这条河穿过市中心。'},
        ],
        'write': [
            {'en': 'Students are required to write a 300-word essay.', 'zh': '学生需要写一篇300字的短文。'},
            {'en': 'She writes down new words in her notebook every day.', 'zh': '她每天把生词记在笔记本上。'},
        ],
        'study': [
            {'en': 'She studies hard to pass the entrance exam.', 'zh': '她努力学习以通过入学考试。'},
            {'en': 'Many adults choose to study for a degree.', 'zh': '许多成年人选择攻读学位。'},
        ],
        'take care of': [
            {'en': 'She takes care of her elderly mother.', 'zh': '她照顾年迈的母亲。'},
            {'en': 'Please take care of your belongings.', 'zh': '请照看好您的随身物品。'},
        ],
        'sports meeting': [
            {'en': 'Our school will hold a sports meeting next month.', 'zh': '我们学校将在下个月举办运动会。'},
            {'en': 'Many students signed up for the sports meeting.', 'zh': '许多学生报名参加了运动会。'},
        ],
        'traffic regulations': [
            {'en': 'Drivers must strictly follow all traffic regulations.', 'zh': '驾驶员必须严格遵守所有交通法规。'},
            {'en': 'The city has updated its traffic regulations to reduce congestion.', 'zh': '该市已更新交通法规以减少拥堵。'},
        ],
    }

    # 专升本核心词释义覆盖表
    # 当 ECDICT 的释义排序不符合专升本考试频率时，用此表覆盖
    # key=单词, value=优选释义（最多2条，用换行分隔）
    MEANING_OVERRIDES = {
        'pressure': 'n. 压力，压强\nvt. 迫使',
        'nerve': 'n. 神经；勇气',
        'culture': 'n. 文化，修养',
        'nature': 'n. 自然，本性',
        'development': 'n. 发展，开发',
        'failure': 'n. 失败，故障',
        'pleasure': 'n. 快乐，愉快',
        'picture': 'n. 图片，照片\nvt. 描绘',
        'measure': 'n. 措施，测量\nvt. 测量',
        'treasure': 'n. 财宝，珍品\nvt. 珍爱',
        'mixture': 'n. 混合，混合物',
        'furniture': 'n. 家具',
        'agriculture': 'n. 农业',
        'architecture': 'n. 建筑学，建筑风格',
        'literature': 'n. 文学，文献',
        'manufacture': 'n. 制造，制造业\nvt. 制造',
        'signature': 'n. 签名',
        'exposure': 'n. 暴露，揭露',
        'leisure': 'n. 闲暇，空闲',
        'capture': 'n. 捕获\nvt. 俘获',
        'feature': 'n. 特征，特色\nvt. 以...为特色',
        'venture': 'n. 冒险\nv. 冒险',
        'creature': 'n. 生物，动物',
        'fracture': 'n. 骨折，断裂',
        'sculpture': 'n. 雕塑',
        'texture': 'n. 质地，纹理',
        'lecture': 'n. 演讲，讲座\nv. 讲课',
        # ECDICT 释义排序错误修正
        'worse': 'adj. 更坏的，更差的\nadv. 更坏地',
        'affordable': 'adj. 买得起的，负担得起的',
        'stressful': 'adj. 有压力的，紧张的',
        'press': 'n. 压力，印刷机，新闻界\nv. 压，按',
        'good': 'adj. 好的，优良的',
        'nervous': 'adj. 紧张的，神经的',
        'tense': 'adj. 紧张的，拉紧的\nn. 时态',
        'stress': 'n. 压力，强调\nvt. 强调',
        'chef': 'n. 厨师',
        'cooker': 'n. 炊具，炉灶',
        # ECDICT 释义质量修正（释义不准确、重复或包含生僻义）
        'test': 'n. 测试，考试\nv. 测试，检验',
        'water': 'n. 水\nv. 浇水',
        'thing': 'n. 事情，东西',
        'information': 'n. 信息，资料',
        'apple': 'n. 苹果',
        'headphone': 'n. 耳机',
        'breakthrough': 'n. 突破，突破性进展',
        'playfulness': 'n. 活泼，顽皮',
        'tension': 'n. 紧张，张力',
        'understand': 'v. 理解，明白',
        'rewrite': 'v. 重写，改写',
        'teacher': 'n. 教师，老师',
        'reading': 'n. 阅读\nv. read的现在分词',
        'homework': 'n. 家庭作业',
        'careful': 'adj. 小心的，仔细的',
        'kindness': 'n. 仁慈，善良',
        'happiness': 'n. 幸福，快乐',
        'beautiful': 'adj. 美丽的，漂亮的',
        'quickly': 'adv. 快速地，迅速地',
        'running': 'n. 跑步\nv. run的现在分词',
        'football': 'n. 足球',
        'basketball': 'n. 篮球',
        'sunglasses': 'n. 太阳镜',
        'playground': 'n. 操场，游乐场',
        'careless': 'adj. 粗心的，不小心的',
        'friendship': 'n. 友谊，友情',
        'agreement': 'n. 同意，协议',
        'smartphone': 'n. 智能手机',
        'talk': 'v. 谈话，交谈\nn. 谈话',
        'run': 'v. 跑，运行',
        'thing': 'n. 事情，东西',
        'write': 'v. 写，书写',
        # 用户反馈的翻译质量问题：修正为专升本常考释义
        'conclude': 'v. 得出结论，断定；结束，终止',
        'purpose': 'n. 目的，意图',
        'children': 'n. 孩子，儿童（child的复数）',
        'sometimes': 'adv. 有时，偶尔',
        'everybody': 'pron. 每个人，人人',
        'forever': 'adv. 永远，永久',
        'alike': 'adj. 相似的，相同的\nadv. 同样地',
        'twice': 'adv. 两次；两倍',
        'error': 'n. 错误，差错',
        'conduct': 'n. 行为，举止\nv. 进行，指挥',
        'carry out': 'v. 执行，实施',
        'tide': 'n. 潮汐，潮流',
        'strike': 'v. 打，击；罢工\nn. 罢工，打击',
        'pain': 'n. 疼痛，痛苦',
        'gain': 'v. 获得，赢得\nn. 收获，利益',
        'sight': 'n. 视力，看见；景象',
        'industry': 'n. 工业，产业；勤奋',
        'industrious': 'adj. 勤劳的，勤奋的',
        'parent': 'n. 父母，家长',
        'mind': 'n. 头脑，思想\nv. 介意，在意',
        'like': 'v. 喜欢\nprep. 像，如同\nadj. 相似的',
        'dislike': 'n. 不喜欢\nv. 不喜欢，厌恶',
        'unlike': 'prep. 不像，和...不同',
        'judge': 'n. 法官，裁判\nv. 判断，评判',
        'cover': 'n. 封面，遮盖物\nv. 覆盖，报道',
        'loud': 'adj. 大声的，响亮的',
        'action': 'n. 行动，行为',
        'bird': 'n. 鸟，禽类',
        'feather': 'n. 羽毛',
        'flock': 'n. 一群(鸟/羊)\nv. 群集',
        'trouble': 'n. 麻烦，困难\nv. 使烦恼',
        'road': 'n. 道路，公路',
        'medicine': 'n. 药，药物；医学',
        'bitter': 'adj. 苦的，痛苦的',
        'will': 'n. 意志，意愿\naux. 将，会',
        'willpower': 'n. 意志力',
        'begin': 'v. 开始',
        'half': 'n. 一半\nadj. 一半的',
        'smoke': 'n. 烟，烟雾\nv. 冒烟；吸烟',
        'lab': 'n. 实验室',
        'experiment': 'n. 实验，试验\nv. 做实验',
        'lecture': 'n. 讲座，演讲\nv. 讲课',
        'dine': 'v. 进餐，用餐',
        'dinner': 'n. 晚餐，正餐',
        'breakfast': 'n. 早餐',
        'lunch': 'n. 午餐',
        'canteen': 'n. 食堂，餐厅',
        'cafeteria': 'n. 自助餐厅',
        'restaurant': 'n. 餐馆，饭店',
        'playground': 'n. 操场，游乐场',
        'library': 'n. 图书馆',
        'psychology': 'n. 心理学',
        'physics': 'n. 物理学',
        'geography': 'n. 地理学',
        'biology': 'n. 生物学',
        'chemistry': 'n. 化学',
        'curriculum': 'n. 课程，(全部)课程',
        'compulsory': 'adj. 必修的，义务的',
        'select': 'v. 挑选，选择',
        'grade': 'n. 年级；成绩\nv. 评分',
        'score': 'n. 分数，成绩\nv. 得分',
        'major': 'n. 专业\nadj. 主要的\nv. 主修',
        'assignment': 'n. 作业，任务',
        'homework': 'n. 家庭作业',
        'housework': 'n. 家务',
        'quiz': 'n. 测验，小考',
        'survey': 'n. 调查，民意调查\nv. 调查',
        'enquiry': 'n. 询问，打听',
        'inquiry': 'n. 询问，调查',
        'exam': 'n. 考试',
        'examination': 'n. 考试；检查',
        'finger': 'n. 手指',
        'figure': 'n. 数字；人物；身材\nv. 认为',
        'character': 'n. 性格，品质；人物；角色',
        'characteristic': 'n. 特征，特点\nadj. 典型的',
        'typical': 'adj. 典型的，有代表性的',
        'represent': 'v. 代表；表现',
        'representative': 'n. 代表\nadj. 有代表性的',
        'approval': 'n. 赞成，同意；批准',
        'approve': 'v. 赞成，同意；批准',
        'disapprove': 'v. 不赞成，反对',
        'favorable': 'adj. 有利的，赞成的',
        'favorite': 'adj. 最喜爱的\nn. 最喜欢的人/物',
        'supportive': 'adj. 支持的，支援的',
        'support': 'n. 支持；支柱\nv. 支持，支撑',
        'neutral': 'adj. 中立的，中性的',
        'indifferent': 'adj. 冷漠的，不关心的',
        'negative': 'adj. 消极的，否定的\nn. 否定',
        'objection': 'n. 反对，异议',
        'opposition': 'n. 反对，敌对',
        'critical': 'adj. 批评的；关键的；危急的',
        'suspicious': 'adj. 可疑的，多疑的',
        'suspect': 'v. 怀疑，猜想\nn. 嫌疑犯',
        'subjective': 'adj. 主观的',
        'subject': 'n. 主题；科目\nadj. 服从的\nv. 使遭受',
        'objective': 'adj. 客观的\nn. 目标',
        'tolerant': 'adj. 宽容的，容忍的',
        'tolerate': 'v. 容忍，忍受',
        'pessimistic': 'adj. 悲观的',
        'optimistic': 'adj. 乐观的',
        'compare': 'v. 比较，对比',
        'comparison': 'n. 比较，对比',
        'contrast': 'n. 对比，对照\nv. 对比',
        'cause': 'n. 原因；事业\nv. 引起，导致',
        'effective': 'adj. 有效的',
        'efficient': 'adj. 高效的，效率高的',
        'struggle': 'n. 奋斗，挣扎\nv. 奋斗',
        'effort': 'n. 努力，力气',
        'stamina': 'n. 耐力，持久力',
        'patience': 'n. 耐心，忍耐',
        'patient': 'n. 病人\nadj. 有耐心的',
        'impatient': 'adj. 不耐烦的，没有耐心的',
        'possible': 'adj. 可能的',
        'impossible': 'adj. 不可能的',
        'courage': 'n. 勇气，胆量',
        'courageous': 'adj. 勇敢的，有胆量的',
        'brave': 'adj. 勇敢的',
        'bravery': 'n. 勇敢，勇气',
        'dare': 'v. 敢，敢于',
        'coward': 'n. 懦夫，胆小鬼',
        'timid': 'adj. 胆小的，羞怯的',
        'crowd': 'n. 人群\nv. 拥挤',
        'perseverance': 'n. 坚持不懈，毅力',
        'dilemma': 'n. 困境，进退两难',
        'setback': 'n. 挫折，倒退',
        'hardship': 'n. 艰难，困苦',
        'obstacle': 'n. 障碍，阻碍',
        'barrier': 'n. 障碍，屏障',
        'adversity': 'n. 逆境，不幸',
        'advertise': 'v. 做广告，宣传',
        'advertisement': 'n. 广告',
        'progress': 'n. 进步，进展\nv. 前进',
        'improve': 'v. 改善，提高',
        'develop': 'v. 发展，开发；培养',
        'population': 'n. 人口',
        'popularize': 'v. 推广，普及',
        'pollution': 'n. 污染',
        'pollute': 'v. 污染',
        'contaminate': 'v. 污染，弄脏',
        'polluted': 'adj. 受污染的',
        'pollutant': 'n. 污染物',
        'achievement': 'n. 成就，成绩',
        'fulfillment': 'n. 完成，实现',
        'accomplish': 'v. 完成，实现',
        'accomplishment': 'n. 成就，才艺',
        'accommodate': 'v. 容纳；为...提供住宿',
        'accompany': 'v. 陪伴，陪同；伴奏',
        'company': 'n. 公司；陪伴',
        'companion': 'n. 同伴，伙伴',
        'ambition': 'n. 雄心，抱负',
        'ambitious': 'adj. 有雄心的，有抱负的',
        'pursue': 'v. 追求，从事',
        'pursuit': 'n. 追求，追赶',
        'expectation': 'n. 期望，期待',
        'unexpected': 'adj. 意想不到的，意外的',
        'anticipation': 'n. 预期，期待',
        'exception': 'n. 例外',
        'launch': 'v. 发射；发起，开展',
        'campaign': 'n. 运动，活动；战役',
        'attack': 'n. 攻击，袭击\nv. 攻击',
        'defend': 'v. 保卫，防御；辩护',
        'defence': 'n. 防御，保卫',
        'defense': 'n. 防御，保卫',
        'defendant': 'n. 被告',
        'accuse': 'v. 指控，指责',
        'charge': 'n. 费用；电荷\nv. 收费；充电；指控',
        'conflict': 'n. 冲突，矛盾\nv. 冲突',
        'negotiate': 'v. 谈判，协商',
        'surrender': 'v. 投降，屈服',
        'loser': 'n. 失败者',
        'winner': 'n. 获胜者',
        'enemy': 'n. 敌人，仇敌',
        'ally': 'n. 同盟国，盟友\nv. 结盟',
        'alliance': 'n. 联盟，同盟',
        'kill': 'v. 杀死，消灭',
        'slay': 'v. 杀死，残杀',
        'weapon': 'n. 武器，兵器',
        'gun': 'n. 枪，炮',
        'tank': 'n. 坦克；水箱',
        'sword': 'n. 剑，刀',
        'missile': 'n. 导弹',
        'bomb': 'n. 炸弹\nv. 轰炸',
        'bullet': 'n. 子弹',
        'shield': 'n. 盾牌；保护\nv. 保护',
        'helmet': 'n. 头盔，安全帽',
        'bulletproof': 'adj. 防弹的',
        'waterproof': 'adj. 防水的',
        'parachute': 'n. 降落伞',
        'civilization': 'n. 文明，文化',
        'civil': 'adj. 公民的；国内的；文明的',
        'ancient': 'adj. 古代的，古老的',
        'dynasty': 'n. 王朝，朝代',
        'emperor': 'n. 皇帝',
        'royal': 'adj. 王室的，皇家的',
        'empire': 'n. 帝国',
        'king': 'n. 国王',
        'kingdom': 'n. 王国',
        'imperial': 'adj. 帝国的，皇帝的',
        'prince': 'n. 王子',
        'princess': 'n. 公主',
        'colonize': 'v. 开拓殖民地',
        'industrialization': 'n. 工业化',
        'globalization': 'n. 全球化',
        'museum': 'n. 博物馆',
        'gallery': 'n. 画廊，美术馆',
        'exhibition': 'n. 展览，展览会',
        'exhibit': 'n. 展品\nv. 展览，展出',
        'display': 'n. 陈列，展示\nv. 展示，显示',
        'collection': 'n. 收藏品，收集',
        'treasure': 'n. 财宝，珍品\nv. 珍视',
        'global': 'adj. 全球的',
        'emit': 'v. 发出，排放',
        'renewable': 'adj. 可再生的',
        'eco-friendly': 'adj. 环保的',
        'conservation': 'n. 保护，保存',
        'restore': 'v. 恢复，修复',
        'store': 'n. 商店；储存\nv. 储存',
        'story': 'n. 故事；楼层',
        'storey': 'n. 楼层',
        'floor': 'n. 地板；楼层',
        'archaeologist': 'n. 考古学家',
        'archaeology': 'n. 考古学',
        'unearth': 'v. 发掘，出土',
        'excavate': 'v. 挖掘，发掘',
        'ruin': 'n. 废墟；毁灭\nv. 毁坏',
        'remains': 'n. 遗迹，残余',
        'coverage': 'n. 覆盖；新闻报道',
        'edit': 'v. 编辑，剪辑',
        'editor': 'n. 编辑',
        'edition': 'n. 版本，版次',
        'issue': 'n. 问题；发行\nv. 发行，发布',
        'magazine': 'n. 杂志',
        'press': 'n. 新闻界；印刷机\nv. 按压',
        'pressure': 'n. 压力，压强\nv. 迫使',
        'cooker': 'n. 炊具，炉灶',
        'chef': 'n. 厨师，主厨',
        'stress': 'n. 压力；强调\nv. 强调',
        'stressful': 'adj. 有压力的',
        'tense': 'adj. 紧张的\nn. 时态',
        'tension': 'n. 紧张，张力',
        'nervous': 'adj. 紧张的，神经的',
        'nerve': 'n. 神经；勇气',
        'newspaper': 'n. 报纸',
        'reporter': 'n. 记者',
        'report': 'n. 报告；报道\nv. 报告，报道',
        'journalist': 'n. 新闻记者',
        'correspondent': 'n. 记者，通讯员',
        'columnist': 'n. 专栏作家',
        'respond': 'v. 回应，反应',
        'response': 'n. 回应，反应',
        'reply': 'n. 回答，答复\nv. 回答',
        'column': 'n. 专栏；圆柱；列',
        'volume': 'n. 卷；音量；体积',
        'section': 'n. 部分；章节；部门',
        'charity': 'n. 慈善，慈善机构',
        'hide': 'v. 隐藏，躲藏',
        'wire': 'n. 电线；金属丝',
        'thief': 'n. 小偷，贼',
        'kettle': 'n. 水壶',
        'boil': 'v. 煮沸，沸腾',
        'pour': 'v. 倾倒；倾泻；倒(水)',
        'escape': 'n. 逃跑；逃脱\nv. 逃跑，逃脱',
        'glove': 'n. 手套',
        'host': 'n. 主人；主持人\nv. 主办',
        'hostess': 'n. 女主人；女主持人',
        'deliver': 'v. 递送，交付；发表',
        'full-time': 'adj. 全职的',
        'part-time': 'adj. 兼职的',
        'headline': 'n. 标题，头条',
        'body': 'n. 身体；主体',
        'conclusion': 'n. 结论，结束',
        'conclude': 'v. 得出结论，断定；结束',
        'summary': 'n. 摘要，总结',
        'abstract': 'n. 摘要\nadj. 抽象的',
        'paper': 'n. 纸；论文；试卷',
        'journey': 'n. 旅行，旅程',
        'tour': 'n. 旅行，观光\nv. 旅游',
        'travel': 'n. 旅行\nv. 旅行',
        'voyage': 'n. 航行，航海',
        'tourist': 'n. 游客，旅行者',
        'tourism': 'n. 旅游业',
        'hotel': 'n. 旅馆，酒店',
        'motel': 'n. 汽车旅馆',
        'backpack': 'n. 背包\nv. 背包旅行',
        'accommodation': 'n. 住宿，膳宿',
        'tent': 'n. 帐篷',
        'means': 'n. 方法，手段',
        'vehicle': 'n. 车辆，交通工具',
        'bike': 'n. 自行车',
        'bicycle': 'n. 自行车',
        'tram': 'n. 有轨电车',
        'metro': 'n. 地铁',
        'underground': 'n. 地铁\nadj. 地下的',
        'ship': 'n. 船，舰\nv. 运送',
        'boat': 'n. 小船，船',
        'ferry': 'n. 渡船，摆渡',
        'ticket': 'n. 票，入场券',
        'website': 'n. 网站',
        'certificate': 'n. 证书，证明',
        'passport': 'n. 护照',
        'pass': 'v. 通过，经过\nn. 通行证',
        'port': 'n. 港口，口岸',
        'import': 'n. 进口\nv. 进口',
        'export': 'n. 出口\nv. 出口',
        'exit': 'n. 出口\nv. 退出',
        'visa': 'n. 签证',
        'trip': 'n. 旅行，旅程',
        'luggage': 'n. 行李',
        'baggage': 'n. 行李',
        'depart': 'v. 离开，出发',
        'departure': 'n. 出发，离开',
        'gate': 'n. 大门，出入口',
        'terminal': 'n. 终点站；终端\nadj. 末端的',
        'declare': 'v. 宣布，声明；申报',
        'tax': 'n. 税，税款\nv. 征税',
        'taxpayer': 'n. 纳税人',
        'quarantine': 'n. 隔离，检疫',
        'duty': 'n. 责任，义务；关税',
        'free': 'adj. 自由的；免费的\nadv. 免费地',
        'freedom': 'n. 自由',
        'booklet': 'n. 小册子',
        'leaflet': 'n. 传单，小册子',
        'guidebook': 'n. 旅游指南',
        'guide': 'n. 向导，指南\nv. 引导',
        'brochure': 'n. 小册子，宣传册',
        'map': 'n. 地图',
        'mountain': 'n. 山，山脉',
        'hill': 'n. 小山，丘陵',
        'peak': 'n. 山顶，顶峰\nv. 达到高峰',
        'slope': 'n. 斜坡，山坡',
        'steep': 'adj. 陡峭的',
        'cliff': 'n. 悬崖，峭壁',
        'valley': 'n. 山谷，溪谷',
        'ocean': 'n. 海洋',
        'sea': 'n. 海，海洋',
        'overseas': 'adj. 海外的\nadv. 在海外',
        'wave': 'n. 波浪；挥手\nv. 挥手',
        'island': 'n. 岛，岛屿',
        'rock': 'n. 岩石；摇滚乐',
        'stone': 'n. 石头，石块',
        'beach': 'n. 海滩，沙滩',
        'coastal': 'adj. 沿海的，海岸的',
        'fisherman': 'n. 渔民',
        'fishery': 'n. 渔业；渔场',
        'sand': 'n. 沙，沙子',
        'lake': 'n. 湖，湖泊',
        'river': 'n. 河流',
        'riverside': 'n. 河岸，河边',
        'riverbank': 'n. 河岸',
        'short': 'adj. 短的；矮的',
        'shorten': 'v. 缩短，变短',
        'shortage': 'n. 短缺，不足',
        'scenery': 'n. 风景，景色',
        'scenic': 'adj. 风景优美的',
        'resort': 'n. 度假胜地；凭借',
        'destination': 'n. 目的地，终点',
        'landscape': 'n. 风景，景观',
        'landmark': 'n. 地标，里程碑',
        'monument': 'n. 纪念碑，历史遗迹',
        'adventure': 'n. 冒险，奇遇',
        'fountain': 'n. 喷泉，喷水池',
        # 短语释义覆盖
        'look up to': 'v. 尊敬，敬仰',
        'the best': '最好的（人或物）',
        'be under too much pressure': '承受太大压力',
        # 短语中常见单词的释义覆盖（ECDICT可能返回生僻释义，这里确保用常用释义）
        'be': 'v. 是，存在',
        'take': 'v. 拿，取',
        'care': 'n. 关心，照顾',
        'of': 'prep. 关于',
        'look': 'v. 看',
        'forward': 'adv. 向前',
        'up': 'adv. 向上',
        'to': 'prep. 朝向',
        'the': 'art. 定冠词，表示特指',
        'best': 'adj. 最好的',
        'much': 'adj./adv. 多，大量',
        'under': 'prep. 在...之下',
        'too': 'adv. 太，过于',
        'pressure': 'n. 压力',
        'cooker': 'n. 炊具，炉灶',
        'traffic': 'n. 交通',
        'regulations': 'n. 规则，法规',
        'regulation': 'n. 规则，法规',
        'meeting': 'n. 聚会，集会',
        'sports': 'n. 运动',
        'sport': 'n. 运动',
    }

    # 专升本例句模板（兜底方案）
    # 优先级：ZHUANSHENBEN_EXAMPLES精选例句 > AI例句 > 本模板兜底，保证每个词都至少有例句。
    # 模板针对不同词性做了语法安全设计（动词用不定式/祈使式，副词用"地"结尾的修饰位置），
    # 并用 {word} 英文原词 + {zh} 中文释义 组合，避免纯英文释义泄露。
    EXAMPLE_TEMPLATES = {
        'verb': [
            # 动词：统一用不定式，语法对任何动词的动词原形都正确
            {'en': 'We should learn to {word} step by step.', 'zh': '我们应该学会循序渐进地做到这一点：{zh}。'},
            {'en': 'It is important to {word} in our daily life.', 'zh': '在我们的日常生活中，能做到{zh}是很重要的。'},
            {'en': 'I want to {word} it carefully this time.', 'zh': '这次我想认真地把它做到位。'},
        ],
        'noun_plural': [
            # 复数名词：用 These/are，避免 "This children is"
            {'en': 'These {word} are common in our daily life.', 'zh': '这些{zh}在我们的日常生活中很常见。'},
            {'en': 'We should pay more attention to {word}.', 'zh': '我们应该给予{zh}更多的关注。'},
            {'en': 'I learned a lot about {word} this term.', 'zh': '这学期我学到了很多关于{zh}的知识。'},
        ],
        'noun': [
            # 单数名词：放入自然语境，避免 "This children is"
            {'en': 'The {word} plays an important role in our daily life.', 'zh': '{zh}在我们的日常生活中发挥着重要作用。'},
            {'en': 'We should pay more attention to {word}.', 'zh': '我们应该给予{zh}更多的关注。'},
            {'en': 'I am learning about {word} this term.', 'zh': '这学期我正在学习关于{zh}的知识。'},
        ],
        'adj': [
            {'en': 'She is a very {word} student in our class.', 'zh': '她是我们班一个非常{zh}的学生。'},
            {'en': 'It is {word} to make a good plan.', 'zh': '制定一个好计划是非常{zh}的。'},
            {'en': 'This book is really {word} for us.', 'zh': '这本书对我们来说确实很{zh}。'},
        ],
        'adv': [
            # 普通副词（非频率副词）：放在动词后作方式状语
            {'en': 'He answered the question {word} in class.', 'zh': '他在课堂上{zh}地回答了问题。'},
            {'en': 'She studies {word} to pass the exam.', 'zh': '她{zh}地学习以便通过考试。'},
        ],
        'pron': [
            {'en': 'Everyone should help each other in class.', 'zh': '课堂上每个人都应该互相帮助。'},
            {'en': 'We must be kind to everyone around us.', 'zh': '我们必须善待身边的每一个人。'},
        ],
        'other': [
            {'en': 'We should use this word in the right way.', 'zh': '我们应该正确地使用这个词。'},
            {'en': 'This word is useful in our daily English.', 'zh': '这个词在我们的日常英语中很有用。'},
        ],
    }

    # 预置词典：20个常见单词的完整解析
    # split 每项包含：part(当前部分), meaning(这部分的意思), original(原词),
    #                original_meaning(原词的意思), transform(变形规则), explain(作用说明)
    DICTIONARY = {
        'sports meeting': {
            'phonetic': '/spɔːts ˈmiːtɪŋ/',
            'meaning': 'n. 运动会',
            'type': '复合词',
            'split': [
                {
                    'part': 'sports', 'meaning': 'n. 运动',
                    'original': 'sport', 'original_meaning': 'n. 运动',
                    'transform': '加 -s 变复数',
                    'explain': '复数形式作定语，修饰 meeting',
                },
                {
                    'part': 'meeting', 'meaning': 'n. 聚会，集会',
                    'original': 'meet', 'original_meaning': 'v. 遇见，会面',
                    'transform': '去掉词尾不发音的 e，加 -ing',
                    'explain': 'meet 加 -ing 变成名词，表示"聚在一起的活动"',
                },
            ],
            'morph': [],
            'mnemonic': '运动会就是"运动(sports)"的"聚会(meeting)"，字面意思"运动的聚会"。',
            'examples': [
                {'en': 'We will hold a sports meeting next week.', 'zh': '我们下周将举行运动会。'},
                {'en': 'She won three gold medals at the sports meeting.', 'zh': '她在运动会上赢得了三枚金牌。'},
            ],
        },
        'classroom': {
            'phonetic': '/ˈklɑːsruːm/',
            'meaning': 'n. 教室',
            'type': '复合词',
            'split': [
                {
                    'part': 'class', 'meaning': 'n. 班级，课程',
                    'original': 'class', 'original_meaning': 'n. 班级，课程',
                    'transform': '原形不变',
                    'explain': '表示学习群体',
                },
                {
                    'part': 'room', 'meaning': 'n. 房间',
                    'original': 'room', 'original_meaning': 'n. 房间',
                    'transform': '原形不变',
                    'explain': '表示空间场所',
                },
            ],
            'morph': [],
            'mnemonic': '教室就是"班级(class)"上课的"房间(room)"，班级的房间=教室。',
            'examples': [
                {'en': 'The students are reading in the classroom.', 'zh': '学生们正在教室里读书。'},
                {'en': 'Our classroom is on the second floor.', 'zh': '我们的教室在二楼。'},
            ],
        },
        'understand': {
            'phonetic': '/ˌʌndəˈstænd/',
            'meaning': 'v. 理解，明白',
            'type': '派生词',
            'split': [
                {
                    'part': 'under', 'meaning': 'prep./adv. 在...下面',
                    'original': 'under', 'original_meaning': 'prep./adv. 在...下面',
                    'transform': '原形不变',
                    'explain': '前缀，表示"在...之下"',
                },
                {
                    'part': 'stand', 'meaning': 'v. 站立',
                    'original': 'stand', 'original_meaning': 'v. 站立',
                    'transform': '原形不变',
                    'explain': '词根，"站在某物之下"引申为"看清、理解"',
                },
            ],
            'morph': [
                {'type': 'prefix', 'word': 'under-', 'meaning': '前缀，表示"在...之下"'},
                {'type': 'root', 'word': 'stand', 'meaning': 'v. 站立'},
            ],
            'mnemonic': '理解就是"站在(stand)"事物"下面(under)"看清楚，站得近才看得明白。',
            'examples': [
                {'en': 'I can\'t understand what you mean.', 'zh': '我不明白你的意思。'},
                {'en': 'Do you understand this question?', 'zh': '你理解这个问题吗？'},
            ],
        },
        'beautiful': {
            'phonetic': '/ˈbjuːtɪfl/',
            'meaning': 'adj. 美丽的，漂亮的',
            'type': '派生词',
            'split': [
                {
                    'part': 'beauty', 'meaning': 'n. 美丽',
                    'original': 'beauty', 'original_meaning': 'n. 美丽',
                    'transform': '把 y 改成 i（再加后缀）',
                    'explain': '词根，表示"美"',
                },
                {
                    'part': '-ful', 'meaning': '形容词后缀，表示"充满...的"',
                    'original': 'full', 'original_meaning': 'adj. 满的',
                    'transform': '缩略为后缀 -ful',
                    'explain': '源自 full（满的），把名词变成形容词，表示"充满美的"',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'beauty', 'meaning': 'n. 美丽'},
                {'type': 'suffix', 'word': '-ful', 'meaning': '形容词后缀，源自 full，表示"充满...的"'},
            ],
            'mnemonic': '美丽的就是"充满美(beauty)"的样子，beauty 去 y 加 i 变成 beauti，再加 -ful（源自 full 满的）= beautiful。',
            'examples': [
                {'en': 'What a beautiful flower!', 'zh': '多美的花啊！'},
                {'en': 'She has a beautiful voice.', 'zh': '她有一副美丽的嗓音。'},
            ],
        },
        'happiness': {
            'phonetic': '/ˈhæpinəs/',
            'meaning': 'n. 幸福，快乐',
            'type': '派生词',
            'split': [
                {
                    'part': 'happy', 'meaning': 'adj. 快乐的',
                    'original': 'happy', 'original_meaning': 'adj. 快乐的',
                    'transform': '把 y 改成 i',
                    'explain': '词根，表示"快乐"',
                },
                {
                    'part': '-ness', 'meaning': '名词后缀，表示状态',
                    'original': '-ness', 'original_meaning': '名词后缀，表示状态',
                    'transform': '本身是后缀，无变形',
                    'explain': '把形容词变成名词，表示"快乐的状态"',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'happy', 'meaning': 'adj. 快乐的'},
                {'type': 'suffix', 'word': '-ness', 'meaning': '名词后缀，将形容词转为名词，表示状态'},
            ],
            'mnemonic': '幸福就是"快乐(happy)"的"状态(-ness)"，happy 把 y 改 i 加 ness = happiness。',
            'examples': [
                {'en': 'Money can\'t buy happiness.', 'zh': '金钱买不到幸福。'},
                {'en': 'Her eyes were full of happiness.', 'zh': '她的眼中充满了快乐。'},
            ],
        },
        'rewrite': {
            'phonetic': '/ˌriːˈraɪt/',
            'meaning': 'v. 重写，改写',
            'type': '派生词',
            'split': [
                {
                    'part': 're', 'meaning': '前缀，表示"再、重新"',
                    'original': 're', 'original_meaning': '前缀，表示"再、重新"',
                    'transform': '本身是前缀，无变形',
                    'explain': '前缀，表示重复',
                },
                {
                    'part': 'write', 'meaning': 'v. 写',
                    'original': 'write', 'original_meaning': 'v. 写',
                    'transform': '原形不变',
                    'explain': '词根',
                },
            ],
            'morph': [
                {'type': 'prefix', 'word': 're-', 'meaning': '前缀，表示"再、重新"'},
                {'type': 'root', 'word': 'write', 'meaning': 'v. 写'},
            ],
            'mnemonic': '重写就是"重新(re)"+"写(write)"，re+write=rewrite。',
            'examples': [
                {'en': 'I need to rewrite this essay.', 'zh': '我需要重写这篇文章。'},
                {'en': 'She rewrote the letter three times.', 'zh': '她把信重写了三遍。'},
            ],
        },
        'teacher': {
            'phonetic': '/ˈtiːtʃə/',
            'meaning': 'n. 教师，老师',
            'type': '派生词',
            'split': [
                {
                    'part': 'teach', 'meaning': 'v. 教，教书',
                    'original': 'teach', 'original_meaning': 'v. 教，教书',
                    'transform': '原形不变',
                    'explain': '词根',
                },
                {
                    'part': '-er', 'meaning': '名词后缀，表示"做...的人"',
                    'original': '-er', 'original_meaning': '名词后缀，表示"做...的人"',
                    'transform': '本身是后缀，无变形',
                    'explain': '把动词变成名词，表示"教书的人"即老师',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'teach', 'meaning': 'v. 教，教书'},
                {'type': 'suffix', 'word': '-er', 'meaning': '名词后缀，表示"做...的人"'},
            ],
            'mnemonic': '老师就是"教书(teach)"的"人(-er)"，teach+er=teacher。',
            'examples': [
                {'en': 'My teacher is very kind.', 'zh': '我的老师非常和蔼。'},
                {'en': 'She is a teacher of English.', 'zh': '她是一位英语老师。'},
            ],
        },
        'quickly': {
            'phonetic': '/ˈkwɪkli/',
            'meaning': 'adv. 快速地，迅速地',
            'type': '派生词',
            'split': [
                {
                    'part': 'quick', 'meaning': 'adj. 快的',
                    'original': 'quick', 'original_meaning': 'adj. 快的',
                    'transform': '原形不变',
                    'explain': '词根',
                },
                {
                    'part': '-ly', 'meaning': '副词后缀，将形容词转为副词',
                    'original': 'like', 'original_meaning': 'adj. 相似的',
                    'transform': '缩略为后缀 -ly',
                    'explain': '源自 like（相似的），把形容词变成副词，表示"快地"',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'quick', 'meaning': 'adj. 快的'},
                {'type': 'suffix', 'word': '-ly', 'meaning': '副词后缀，源自 like，将形容词转为副词'},
            ],
            'mnemonic': '快速地就是"快(quick)"的副词形式，quick 直接加 -ly（源自 like 相似的，即"以...的方式"）= quickly。',
            'examples': [
                {'en': 'He ran quickly to catch the bus.', 'zh': '他快速跑去赶公交车。'},
                {'en': 'Time passes quickly when you\'re having fun.', 'zh': '快乐时光飞逝。'},
            ],
        },
        'running': {
            'phonetic': '/ˈrʌnɪŋ/',
            'meaning': 'n. 跑步；v. run的现在分词',
            'type': '派生词',
            'split': [
                {
                    'part': 'run', 'meaning': 'v. 跑',
                    'original': 'run', 'original_meaning': 'v. 跑',
                    'transform': '双写词尾辅音字母 n，再加 -ing（短元音+辅音结尾的规则）',
                    'explain': '词根',
                },
                {
                    'part': '-ing', 'meaning': '现在分词/动名词后缀，表示进行时或动作本身',
                    'original': '-ing', 'original_meaning': '现在分词/动名词后缀',
                    'transform': '加 -ing 构成现在分词',
                    'explain': '把动词变成进行时态或名词，表示"跑"这件事/正在跑',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'run', 'meaning': 'v. 跑'},
                {'type': 'suffix', 'word': '-ing', 'meaning': '动名词或现在分词后缀'},
            ],
            'mnemonic': '跑步就是"跑(run)"这件事，run 双写 n 加 ing = running（短元音+辅音结尾要双写）。',
            'examples': [
                {'en': 'Running is good for your health.', 'zh': '跑步有益健康。'},
                {'en': 'The water is running from the tap.', 'zh': '水正从水龙头里流出来。'},
            ],
        },
        'reading': {
            'phonetic': '/ˈriːdɪŋ/',
            'meaning': 'n. 阅读；v. read的现在分词',
            'type': '派生词',
            'split': [
                {
                    'part': 'read', 'meaning': 'v. 阅读，读',
                    'original': 'read', 'original_meaning': 'v. 阅读，读',
                    'transform': '原形不变',
                    'explain': '词根',
                },
                {
                    'part': '-ing', 'meaning': '现在分词/动名词后缀，表示进行时或动作本身',
                    'original': '-ing', 'original_meaning': '现在分词/动名词后缀',
                    'transform': '加 -ing 构成现在分词',
                    'explain': '把动词变成进行时态或名词，表示"读"这件事/正在读',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'read', 'meaning': 'v. 阅读，读'},
                {'type': 'suffix', 'word': '-ing', 'meaning': '动名词或现在分词后缀'},
            ],
            'mnemonic': '阅读就是"读(read)"这件事，read 直接加 ing = reading。',
            'examples': [
                {'en': 'Reading is a good habit.', 'zh': '阅读是一个好习惯。'},
                {'en': 'She is reading a novel in the garden.', 'zh': '她正在花园里读小说。'},
            ],
        },
        'football': {
            'phonetic': '/ˈfʊtbɔːl/',
            'meaning': 'n. 足球',
            'type': '复合词',
            'split': [
                {
                    'part': 'foot', 'meaning': 'n. 脚',
                    'original': 'foot', 'original_meaning': 'n. 脚',
                    'transform': '原形不变',
                    'explain': '表示用脚踢',
                },
                {
                    'part': 'ball', 'meaning': 'n. 球',
                    'original': 'ball', 'original_meaning': 'n. 球',
                    'transform': '原形不变',
                    'explain': '表示球类',
                },
            ],
            'morph': [],
            'mnemonic': '足球就是用"脚(foot)"踢的"球(ball)"，foot+ball=football。',
            'examples': [
                {'en': 'He likes playing football after school.', 'zh': '他喜欢放学后踢足球。'},
                {'en': 'The football match was exciting.', 'zh': '那场足球比赛很精彩。'},
            ],
        },
        'basketball': {
            'phonetic': '/ˈbɑːskɪtbɔːl/',
            'meaning': 'n. 篮球',
            'type': '复合词',
            'split': [
                {
                    'part': 'basket', 'meaning': 'n. 篮子',
                    'original': 'basket', 'original_meaning': 'n. 篮子',
                    'transform': '原形不变',
                    'explain': '指投球的目标篮筐',
                },
                {
                    'part': 'ball', 'meaning': 'n. 球',
                    'original': 'ball', 'original_meaning': 'n. 球',
                    'transform': '原形不变',
                    'explain': '表示球类',
                },
            ],
            'morph': [],
            'mnemonic': '篮球就是往"篮子(basket)"里投的"球(ball)"，basket+ball=basketball。',
            'examples': [
                {'en': 'Basketball is my favorite sport.', 'zh': '篮球是我最喜欢的运动。'},
                {'en': 'They played basketball for two hours.', 'zh': '他们打了两个小时篮球。'},
            ],
        },
        'homework': {
            'phonetic': '/ˈhəʊmwɜːk/',
            'meaning': 'n. 家庭作业',
            'type': '复合词',
            'split': [
                {
                    'part': 'home', 'meaning': 'n. 家',
                    'original': 'home', 'original_meaning': 'n. 家',
                    'transform': '原形不变',
                    'explain': '表示在家中完成',
                },
                {
                    'part': 'work', 'meaning': 'n. 工作，任务',
                    'original': 'work', 'original_meaning': 'n. 工作，任务',
                    'transform': '原形不变',
                    'explain': '表示学习任务',
                },
            ],
            'morph': [],
            'mnemonic': '家庭作业就是在"家(home)"做的"工作(work)"，home+work=homework。',
            'examples': [
                {'en': 'I have a lot of homework today.', 'zh': '我今天有很多作业。'},
                {'en': 'Have you finished your homework?', 'zh': '你完成作业了吗？'},
            ],
        },
        'sunglasses': {
            'phonetic': '/ˈsʌnɡlɑːsɪz/',
            'meaning': 'n. 太阳镜',
            'type': '复合词',
            'split': [
                {
                    'part': 'sun', 'meaning': 'n. 太阳',
                    'original': 'sun', 'original_meaning': 'n. 太阳',
                    'transform': '原形不变',
                    'explain': '表示遮挡阳光',
                },
                {
                    'part': 'glasses', 'meaning': 'n. 眼镜',
                    'original': 'glass', 'original_meaning': 'n. 玻璃；玻璃杯',
                    'transform': '加 -es 变复数（以 s 结尾的词加 -es）',
                    'explain': 'glass 的复数形式，这里指"眼镜"（眼镜由两片玻璃组成，所以用复数）',
                },
            ],
            'morph': [],
            'mnemonic': '太阳镜就是挡"太阳(sun)"的"眼镜(glasses)"，sun+glasses=sunglasses。',
            'examples': [
                {'en': 'She wears sunglasses in summer.', 'zh': '她夏天戴太阳镜。'},
                {'en': 'I bought a new pair of sunglasses.', 'zh': '我买了一副新太阳镜。'},
            ],
        },
        'playground': {
            'phonetic': '/ˈpleɪɡraʊnd/',
            'meaning': 'n. 操场，游乐场',
            'type': '复合词',
            'split': [
                {
                    'part': 'play', 'meaning': 'v. 玩耍',
                    'original': 'play', 'original_meaning': 'v. 玩耍',
                    'transform': '原形不变',
                    'explain': '表示活动的性质',
                },
                {
                    'part': 'ground', 'meaning': 'n. 场地',
                    'original': 'ground', 'original_meaning': 'n. 场地，地面',
                    'transform': '原形不变',
                    'explain': '表示活动场所',
                },
            ],
            'morph': [],
            'mnemonic': '操场就是"玩(play)"的"场地(ground)"，play+ground=playground。',
            'examples': [
                {'en': 'Children are playing on the playground.', 'zh': '孩子们正在操场上玩。'},
                {'en': 'The school has a large playground.', 'zh': '这所学校有一个大操场。'},
            ],
        },
        'careful': {
            'phonetic': '/ˈkeəfl/',
            'meaning': 'adj. 小心的，仔细的',
            'type': '派生词',
            'split': [
                {
                    'part': 'care', 'meaning': 'n. 小心，关怀',
                    'original': 'care', 'original_meaning': 'n. 小心，关怀',
                    'transform': '原形不变，直接加后缀',
                    'explain': '词根',
                },
                {
                    'part': '-ful', 'meaning': '形容词后缀，表示"充满...的"',
                    'original': 'full', 'original_meaning': 'adj. 满的',
                    'transform': '缩略为后缀 -ful',
                    'explain': '源自 full（满的），把名词变成形容词，表示"充满小心的"',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'care', 'meaning': 'n. 小心，关怀'},
                {'type': 'suffix', 'word': '-ful', 'meaning': '形容词后缀，源自 full，表示"充满...的"'},
            ],
            'mnemonic': '小心的就是"充满小心(care)"的状态，care 直接加 -ful（源自 full 满的）= careful。',
            'examples': [
                {'en': 'Be careful when crossing the road.', 'zh': '过马路时要小心。'},
                {'en': 'He is a careful driver.', 'zh': '他是一个细心的司机。'},
            ],
        },
        'careless': {
            'phonetic': '/ˈkeələs/',
            'meaning': 'adj. 粗心的，不小心的',
            'type': '派生词',
            'split': [
                {
                    'part': 'care', 'meaning': 'n. 小心，关怀',
                    'original': 'care', 'original_meaning': 'n. 小心，关怀',
                    'transform': '原形不变，直接加后缀',
                    'explain': '词根',
                },
                {
                    'part': '-less', 'meaning': '形容词后缀，表示"无、没有...的"',
                    'original': 'less', 'original_meaning': 'adj. 较少的',
                    'transform': '缩略为后缀 -less，表示"无、没有"',
                    'explain': '形似 less（较少的），助记：少到没有，把名词变成形容词，表示"没有小心的"即粗心',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'care', 'meaning': 'n. 小心，关怀'},
                {'type': 'suffix', 'word': '-less', 'meaning': '形容词后缀，形似 less，表示"无...的"'},
            ],
            'mnemonic': '粗心的就是"没有小心(care)"，care 直接加 -less（形似 less 较少的，助记：少到没有）= careless。对比记忆：careful(小心) vs careless(粗心)。',
            'examples': [
                {'en': 'It was careless of him to lose the key.', 'zh': '他弄丢了钥匙，太粗心了。'},
                {'en': 'A careless mistake cost him the game.', 'zh': '一个粗心的失误让他输掉了比赛。'},
            ],
        },
        'friendship': {
            'phonetic': '/ˈfrendʃɪp/',
            'meaning': 'n. 友谊，友情',
            'type': '派生词',
            'split': [
                {
                    'part': 'friend', 'meaning': 'n. 朋友',
                    'original': 'friend', 'original_meaning': 'n. 朋友',
                    'transform': '原形不变',
                    'explain': '词根',
                },
                {
                    'part': '-ship', 'meaning': '名词后缀，表示关系或状态',
                    'original': 'shape', 'original_meaning': 'n. 形态，样子',
                    'transform': '演变为后缀 -ship',
                    'explain': '源自 shape（形态），把名词变成抽象名词，表示"朋友的形态/关系"即友谊',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'friend', 'meaning': 'n. 朋友'},
                {'type': 'suffix', 'word': '-ship', 'meaning': '名词后缀，源自 shape，表示关系或状态'},
            ],
            'mnemonic': '友谊就是"朋友(friend)"之间的"关系(-ship)"，friend 直接加 -ship（源自 shape 形态，即关系的形态）= friendship。',
            'examples': [
                {'en': 'Their friendship lasted for many years.', 'zh': '他们的友谊持续了很多年。'},
                {'en': 'True friendship is priceless.', 'zh': '真正的友谊是无价的。'},
            ],
        },
        'agreement': {
            'phonetic': '/əˈɡriːmənt/',
            'meaning': 'n. 同意，协议',
            'type': '派生词',
            'split': [
                {
                    'part': 'agree', 'meaning': 'v. 同意',
                    'original': 'agree', 'original_meaning': 'v. 同意',
                    'transform': '原形不变，直接加后缀',
                    'explain': '词根',
                },
                {
                    'part': '-ment', 'meaning': '名词后缀，表示行为或结果',
                    'original': '-ment', 'original_meaning': '名词后缀，表示行为或结果',
                    'transform': '本身是后缀，无变形',
                    'explain': '把动词变成名词，表示"同意的结果"即协议',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'agree', 'meaning': 'v. 同意'},
                {'type': 'suffix', 'word': '-ment', 'meaning': '名词后缀，表示行为或结果'},
            ],
            'mnemonic': '协议就是"同意(agree)"的"结果(-ment)"，agree 直接加 ment = agreement。',
            'examples': [
                {'en': 'We reached an agreement yesterday.', 'zh': '我们昨天达成了协议。'},
                {'en': 'They signed the agreement with a smile.', 'zh': '他们微笑着签署了协议。'},
            ],
        },
        'kindness': {
            'phonetic': '/ˈkaɪndnəs/',
            'meaning': 'n. 仁慈，善良',
            'type': '派生词',
            'split': [
                {
                    'part': 'kind', 'meaning': 'adj. 善良的',
                    'original': 'kind', 'original_meaning': 'adj. 善良的',
                    'transform': '原形不变',
                    'explain': '词根',
                },
                {
                    'part': '-ness', 'meaning': '名词后缀，表示状态或性质',
                    'original': '-ness', 'original_meaning': '名词后缀，表示状态或性质',
                    'transform': '本身是后缀，无变形',
                    'explain': '把形容词变成名词，表示"善良的状态"',
                },
            ],
            'morph': [
                {'type': 'root', 'word': 'kind', 'meaning': 'adj. 善良的'},
                {'type': 'suffix', 'word': '-ness', 'meaning': '名词后缀，表示状态或性质'},
            ],
            'mnemonic': '善良就是"善良(kind)"的"状态(-ness)"，kind+ness=kindness。',
            'examples': [
                {'en': 'Thank you for your kindness.', 'zh': '感谢你的善意。'},
                {'en': 'She is known for her kindness to animals.', 'zh': '她以善待动物而闻名。'},
            ],
        },
        # ===== 常见基础词（AI可能给非常用释义，本地词典保证准确） =====
        'key': {
            'phonetic': '/kiː/',
            'meaning': 'n. 钥匙；关键；键；答案',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'key联想"ki(开)-y"，用来"开"门的东西就是钥匙，引申为"关键"。',
            'examples': [
                {'en': 'The key to success is hard work.', 'zh': '成功的关键是努力。'},
                {'en': 'He lost his car keys.', 'zh': '他丢了车钥匙。'},
            ],
        },
        'value': {
            'phonetic': '/ˈvæljuː/',
            'meaning': 'n. 价值；价值观 v. 重视，估价',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'value音译"瓦流"，有"价值"的东西才会留下来。',
            'examples': [
                {'en': 'This book is of great value to students.', 'zh': '这本书对学生很有价值。'},
                {'en': 'We should value our friendship.', 'zh': '我们应该重视我们的友谊。'},
            ],
        },
        'change': {
            'phonetic': '/tʃeɪndʒ/',
            'meaning': 'n. 变化；零钱 v. 改变，交换',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'change联想"常改"，事物经常"改变"。',
            'examples': [
                {'en': 'Climate change affects everyone.', 'zh': '气候变化影响每个人。'},
                {'en': 'I need to change my password.', 'zh': '我需要修改密码。'},
            ],
        },
        'point': {
            'phonetic': '/pɔɪnt/',
            'meaning': 'n. 点；观点；分数；要点 v. 指向',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'point本意是"尖端"，引申为"指向"和"观点"。',
            'examples': [
                {'en': 'What is your point?', 'zh': '你的观点是什么？'},
                {'en': 'She pointed at the map.', 'zh': '她指向地图。'},
            ],
        },
        'state': {
            'phonetic': '/steɪt/',
            'meaning': 'n. 状态；州；国家 v. 陈述',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'state联想"stay(停留)+t"，停留的状态就是"状态"。',
            'examples': [
                {'en': 'The state of the economy is worrying.', 'zh': '经济状况令人担忧。'},
                {'en': 'He stated his opinion clearly.', 'zh': '他清楚地陈述了自己的观点。'},
            ],
        },
        'field': {
            'phonetic': '/fiːld/',
            'meaning': 'n. 田野；领域；场地',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'field联想"filled(填满)"，田地里填满了庄稼。',
            'examples': [
                {'en': 'She works in the field of medicine.', 'zh': '她在医学领域工作。'},
                {'en': 'The children are playing in the field.', 'zh': '孩子们在田野里玩耍。'},
            ],
        },
        'match': {
            'phonetic': '/mætʃ/',
            'meaning': 'n. 比赛；匹配；火柴 v. 匹配，相配',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'match联想"马齿"，马的牙齿要"匹配"才能吃草。',
            'examples': [
                {'en': 'We watched a football match yesterday.', 'zh': '我们昨天看了一场足球比赛。'},
                {'en': 'The colors match perfectly.', 'zh': '颜色搭配得很完美。'},
            ],
        },
        'sound': {
            'phonetic': '/saʊnd/',
            'meaning': 'n. 声音 v. 听起来 adj. 健全的；合理的',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'sound本身就是"声音"的意思，也有"听起来"和"健全的"含义。',
            'examples': [
                {'en': 'The sound of music filled the room.', 'zh': '音乐声充满了房间。'},
                {'en': 'That sounds like a good idea.', 'zh': '那听起来是个好主意。'},
            ],
        },
        # ===== 拆解修正词条（基于权威词源字典 etymonline.com） =====
        'breakthrough': {
            'phonetic': '/ˈbreɪkθruː/',
            'meaning': 'n. 突破，突破性进展',
            'type': '复合词',
            'split': [
                {'part': 'break', 'meaning': 'v. 打破，突破', 'original': 'break', 'original_meaning': 'v. 打破，突破', 'transform': '原形不变', 'explain': '表示"打破"障碍'},
                {'part': 'through', 'meaning': 'prep./adv. 穿过，通过', 'original': 'through', 'original_meaning': 'prep./adv. 穿过，通过', 'transform': '原形不变', 'explain': '表示"穿过"障碍'},
            ],
            'morph': [],
            'mnemonic': '突破就是"打破(break)"障碍并"穿过(through)"去，break + through = breakthrough。',
            'examples': [
                {'en': 'Scientists have made a major breakthrough in cancer research.', 'zh': '科学家在癌症研究方面取得了重大突破。'},
                {'en': 'The new technology represents a breakthrough in communication.', 'zh': '这项新技术代表了通讯领域的突破。'},
            ],
        },
        'smartphone': {
            'phonetic': '/ˈsmɑːrtfoʊn/',
            'meaning': 'n. 智能手机',
            'type': '复合词',
            'split': [
                {'part': 'smart', 'meaning': 'adj. 智能的，聪明的', 'original': 'smart', 'original_meaning': 'adj. 智能的，聪明的', 'transform': '原形不变', 'explain': '表示"智能的"'},
                {'part': 'phone', 'meaning': 'n. 电话，手机', 'original': 'phone', 'original_meaning': 'n. 电话（源自希腊语 phone"声音"）', 'transform': '原形不变', 'explain': '表示通讯设备'},
            ],
            'morph': [],
            'mnemonic': '智能手机就是"智能(smart)"的"电话(phone)"，smart + phone = smartphone。',
            'examples': [
                {'en': 'Smartphones have become an essential part of our daily life.', 'zh': '智能手机已成为我们日常生活中不可或缺的一部分。'},
                {'en': 'Many students use smartphones to look up new words.', 'zh': '许多学生用智能手机查生词。'},
            ],
        },
        'headphone': {
            'phonetic': '/ˈhedfoʊn/',
            'meaning': 'n. 耳机',
            'type': '复合词',
            'split': [
                {'part': 'head', 'meaning': 'n. 头', 'original': 'head', 'original_meaning': 'n. 头', 'transform': '原形不变', 'explain': '表示戴在头上的设备'},
                {'part': 'phone', 'meaning': 'n. 声音（源自希腊语 phone）', 'original': 'phone', 'original_meaning': 'n. 电话（源自希腊语 phone"声音"）', 'transform': '原形不变', 'explain': 'phone 原意为"声音"，戴在头上传声的设备就是耳机'},
            ],
            'morph': [],
            'mnemonic': '耳机就是戴在"头(head)"上发出"声音(phone)"的设备，head + phone = headphone。',
            'examples': [
                {'en': 'He listens to English podcasts with his headphones.', 'zh': '他用耳机听英语播客。'},
                {'en': 'Please put on your headphones for the listening test.', 'zh': '请戴上耳机准备听力考试。'},
            ],
        },
        'important': {
            'phonetic': '/ɪmˈpɔːrtnt/',
            'meaning': 'adj. 重要的',
            'type': '派生词',
            'split': [
                {'part': 'im-', 'meaning': '前缀，表示"进入"（in- 在 p/b/m 前的变体）', 'original': 'in-', 'original_meaning': '前缀，表示"进入"', 'transform': 'in- 变为 im-（在 p 前同化）', 'explain': '前缀，表示"带入"'},
                {'part': 'port', 'meaning': 'v. 搬运，携带', 'original': 'port', 'original_meaning': 'v. 搬运，携带（拉丁语 portare）', 'transform': '原形不变', 'explain': '词根，表示"搬运"，"带入分量"引申为"重要的"'},
                {'part': '-ant', 'meaning': '形容词后缀，表示"具有...性质的"', 'original': '-ant', 'original_meaning': '形容词后缀，表示"具有...性质的"', 'transform': '本身是后缀，无变形', 'explain': '把动词变成形容词'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'im-', 'meaning': '前缀，表示"进入"（in-的变体）'},
                {'type': 'root', 'word': 'port', 'meaning': 'v. 搬运，携带'},
                {'type': 'suffix', 'word': '-ant', 'meaning': '形容词后缀'},
            ],
            'mnemonic': 'im（进入）+ port（搬运）→ "带入分量"的东西 → 有分量的 → 重要的。联想同根词：import(进口)、transport(运输)。',
            'examples': [
                {'en': 'Family is more important than anything else.', 'zh': '家庭比其他任何事情都重要。'},
                {'en': 'What is the most important thing in learning English?', 'zh': '学英语中最重要的事情是什么？'},
            ],
        },
        'tension': {
            'phonetic': '/ˈtenʃn/',
            'meaning': 'n. 紧张，张力',
            'type': '派生词',
            'split': [
                {'part': 'tense', 'meaning': 'adj. 紧张的，拉紧的', 'original': 'tense', 'original_meaning': 'adj. 紧张的，拉紧的（拉丁语 tendere"拉伸"）', 'transform': '去掉词尾 e', 'explain': '词根，表示"拉紧"'},
                {'part': '-ion', 'meaning': '名词后缀，表示动作或状态', 'original': '-ion', 'original_meaning': '名词后缀，表示动作或状态', 'transform': '本身是后缀，无变形', 'explain': '把形容词变成名词，表示"拉紧的状态"即紧张、张力'},
            ],
            'morph': [
                {'type': 'root', 'word': 'tense', 'meaning': 'adj. 紧张的，拉紧的'},
                {'type': 'suffix', 'word': '-ion', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'tense（拉紧）+ ion（名词后缀）→ 拉紧的状态 → 紧张、张力。联想同根词：extend(延伸)、contain(包含)。',
            'examples': [
                {'en': 'There was a lot of tension in the room during the exam.', 'zh': '考试期间教室里气氛很紧张。'},
                {'en': 'The tension between the two countries has increased.', 'zh': '两国之间的紧张关系加剧了。'},
            ],
        },
        'nervous': {
            'phonetic': '/ˈnɜːrvəs/',
            'meaning': 'adj. 紧张的，神经的',
            'type': '派生词',
            'split': [
                {'part': 'nerve', 'meaning': 'n. 神经', 'original': 'nerve', 'original_meaning': 'n. 神经', 'transform': '去掉词尾 e', 'explain': '词根，表示"神经"'},
                {'part': '-ous', 'meaning': '形容词后缀，表示"充满...的、具有...特性的"', 'original': '-ous', 'original_meaning': '形容词后缀，表示"充满...的"', 'transform': '本身是后缀，无变形', 'explain': '把名词变成形容词，表示"神经紧绷的"即紧张的'},
            ],
            'morph': [
                {'type': 'root', 'word': 'nerve', 'meaning': 'n. 神经'},
                {'type': 'suffix', 'word': '-ous', 'meaning': '形容词后缀'},
            ],
            'mnemonic': 'nerve（神经）+ ous（充满...的）→ 神经紧绷的 → 紧张的。联想：考试前"神经"绷紧就是"紧张的"。',
            'examples': [
                {'en': 'She felt nervous before the interview.', 'zh': '她在面试前感到紧张。'},
                {'en': 'Public speaking makes many people nervous.', 'zh': '公众演讲让很多人感到紧张。'},
            ],
        },
        'information': {
            'phonetic': '/ˌɪnfərˈmeɪʃn/',
            'meaning': 'n. 信息，资料',
            'type': '派生词',
            'split': [
                {'part': 'in-', 'meaning': '前缀，表示"进入"', 'original': 'in-', 'original_meaning': '前缀，表示"进入"', 'transform': '本身是前缀，无变形', 'explain': '前缀，表示"注入"'},
                {'part': 'form', 'meaning': 'n. 形式，形状', 'original': 'form', 'original_meaning': 'n. 形式，形状（拉丁语 forma）', 'transform': '原形不变', 'explain': '词根，表示"形成"，"注入形式"引申为"告知"'},
                {'part': '-ation', 'meaning': '名词后缀，表示动作或状态', 'original': '-ation', 'original_meaning': '名词后缀，表示动作或状态', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"告知的内容"即信息'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'in-', 'meaning': '前缀，表示"进入"'},
                {'type': 'root', 'word': 'form', 'meaning': 'n. 形式，形状'},
                {'type': 'suffix', 'word': '-ation', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'in（进入）+ form（形式）+ ation（名词后缀）→ 将知识"注入形式"的过程 → 告知 → 信息。联想：form(形式)、reform(改革)。',
            'examples': [
                {'en': 'You can find more information on the school website.', 'zh': '你可以在学校网站上找到更多信息。'},
                {'en': 'The book provides useful information about career planning.', 'zh': '这本书提供了关于职业规划的有用信息。'},
            ],
        },
        'cooker': {
            'phonetic': '/ˈkʊkər/',
            'meaning': 'n. 炊具，炉灶',
            'type': '派生词',
            'split': [
                {'part': 'cook', 'meaning': 'v. 烹调，做饭', 'original': 'cook', 'original_meaning': 'v. 烹调，做饭', 'transform': '原形不变', 'explain': '词根，表示"烹饪"'},
                {'part': '-er', 'meaning': '名词后缀，表示"做...的器具"', 'original': '-er', 'original_meaning': '名词后缀，表示"做...的人或物"', 'transform': '本身是后缀，无变形', 'explain': '此处表"器具"而非"人"，用来烹饪的器具即炊具'},
            ],
            'morph': [
                {'type': 'root', 'word': 'cook', 'meaning': 'v. 烹调'},
                {'type': 'suffix', 'word': '-er', 'meaning': '名词后缀，表器具'},
            ],
            'mnemonic': 'cook（烹饪）+ er（做...的器具）→ 用来烹饪的器具 → 炊具。注意：cook 本身可指厨师，cooker 指炊具。',
            'examples': [
                {'en': 'I bought a new rice cooker yesterday.', 'zh': '我昨天买了一个新电饭煲。'},
                {'en': 'A pressure cooker can save a lot of cooking time.', 'zh': '高压锅可以节省很多烹饪时间。'},
            ],
        },
        'playfulness': {
            'phonetic': '/ˈpleɪflnəs/',
            'meaning': 'n. 活泼，顽皮',
            'type': '派生词',
            'split': [
                {'part': 'play', 'meaning': 'v. 玩，游戏', 'original': 'play', 'original_meaning': 'v. 玩，游戏', 'transform': '原形不变', 'explain': '词根，表示"玩"'},
                {'part': '-ful', 'meaning': '形容词后缀，表示"充满...的"', 'original': 'full', 'original_meaning': 'adj. 满的', 'transform': '缩略为后缀 -ful', 'explain': '源自 full（满的），把动词变成形容词，表示"充满玩的"'},
                {'part': '-ness', 'meaning': '名词后缀，表示状态或性质', 'original': '-ness', 'original_meaning': '名词后缀，表示状态或性质', 'transform': '本身是后缀，无变形', 'explain': '把形容词变成名词，表示"爱玩的状态"即顽皮'},
            ],
            'morph': [
                {'type': 'root', 'word': 'play', 'meaning': 'v. 玩'},
                {'type': 'suffix', 'word': '-ful', 'meaning': '形容词后缀'},
                {'type': 'suffix', 'word': '-ness', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'play（玩）+ ful（充满）→ playful（爱玩的）+ ness（状态）→ 爱玩的状态 → 顽皮、活泼。',
            'examples': [
                {'en': "The children's playfulness filled the room with laughter.", 'zh': '孩子们的活泼让房间里充满了笑声。'},
                {'en': 'Her playfulness made the learning process more enjoyable.', 'zh': '她的活泼让学习过程更加愉快。'},
            ],
        },
        'pressure': {
            'phonetic': '/ˈpreʃər/',
            'meaning': 'n. 压力，压强\nvt. 迫使',
            'type': '派生词',
            'split': [
                {'part': 'press', 'meaning': 'v. 压，按', 'original': 'press', 'original_meaning': 'v. 压，按', 'transform': '原形不变', 'explain': '词根，表示"按压"'},
                {'part': '-ure', 'meaning': '名词后缀，表示行为、状态或结果', 'original': '-ure', 'original_meaning': '名词后缀，表示行为、状态或结果', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"按压的状态"即压力'},
            ],
            'morph': [
                {'type': 'root', 'word': 'press', 'meaning': 'v. 压，按'},
                {'type': 'suffix', 'word': '-ure', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'press（压）+ ure（名词后缀）→ 按压的状态 → 压力。联想：press 是词根，pressure 是它的名词形式。',
            'examples': [
                {'en': 'Students are under great pressure before exams.', 'zh': '学生在考试前承受着巨大的压力。'},
                {'en': 'The pressure of the water caused the pipe to burst.', 'zh': '水的压力导致管道破裂。'},
            ],
        },
        'stressful': {
            'phonetic': '/ˈstresfl/',
            'meaning': 'adj. 有压力的，紧张的',
            'type': '派生词',
            'split': [
                {'part': 'stress', 'meaning': 'n. 压力', 'original': 'stress', 'original_meaning': 'n. 压力', 'transform': '原形不变', 'explain': '词根，表示"压力"'},
                {'part': '-ful', 'meaning': '形容词后缀，表示"充满...的"', 'original': 'full', 'original_meaning': 'adj. 满的', 'transform': '缩略为后缀 -ful', 'explain': '源自 full（满的），把名词变成形容词，表示"充满压力的"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'stress', 'meaning': 'n. 压力'},
                {'type': 'suffix', 'word': '-ful', 'meaning': '形容词后缀'},
            ],
            'mnemonic': 'stress（压力）+ ful（充满...的）→ 充满压力的 → 有压力的、紧张的。',
            'examples': [
                {'en': 'Moving to a new city can be very stressful.', 'zh': '搬到新城市可能会非常有压力。'},
                {'en': 'She finds her new job quite stressful.', 'zh': '她觉得新工作压力很大。'},
            ],
        },
        # ===== 基础词（不应拆解，但需要记忆方法） =====
        'press': {
            'phonetic': '/pres/',
            'meaning': 'n. 压力，印刷机，新闻界\nv. 压，按',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'press 是词根，意思是"按压"。记住它就能推出 pressure(压力)、compress(压缩)、express(表达=向外压出)。',
            'examples': [
                {'en': 'Press the button to start the machine.', 'zh': '按下按钮启动机器。'},
                {'en': 'The press reported the event in detail.', 'zh': '新闻界详细报道了这一事件。'},
            ],
        },
        'stress': {
            'phonetic': '/stres/',
            'meaning': 'n. 压力，强调\nvt. 强调',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'stress 是 distress（痛苦）的缩略形式，表示"压力、强调"。联想 s(死) + tress(丝) = 像被丝线勒住一样的"压力"。',
            'examples': [
                {'en': 'Too much stress can affect your health.', 'zh': '过多的压力会影响你的健康。'},
                {'en': 'The teacher stressed the importance of reading.', 'zh': '老师强调了阅读的重要性。'},
            ],
        },
        'thing': {
            'phonetic': '/θɪŋ/',
            'meaning': 'n. 事情，东西',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'think（思考）去掉 k 就是 thing，表示"被思考的东西"即"事情、东西"。',
            'examples': [
                {'en': 'The most important thing is to believe in yourself.', 'zh': '最重要的事情是相信自己。'},
                {'en': 'There are many things we can do to improve our English.', 'zh': '我们可以做很多事情来提高英语水平。'},
            ],
        },
        'water': {
            'phonetic': '/ˈwɔːtər/',
            'meaning': 'n. 水\nv. 浇水',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'water 是最古老的基础词之一，联想 w(波) + a(一) + ter(特) = "一个特别的波浪"就是水。',
            'examples': [
                {'en': 'Drinking enough water every day is good for your health.', 'zh': '每天喝足够的水对健康有益。'},
                {'en': 'Please water the flowers before you leave.', 'zh': '离开前请给花浇水。'},
            ],
        },
        'tense': {
            'phonetic': '/tens/',
            'meaning': 'adj. 紧张的，拉紧的\nn. 时态',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'tense 来自拉丁语 tendere（拉伸），拉紧的弦 → "紧张的"。同时也有"时态"的意思。',
            'examples': [
                {'en': 'The atmosphere in the room was very tense.', 'zh': '房间里的气氛非常紧张。'},
                {'en': 'He used the wrong tense in his essay.', 'zh': '他在作文中用错了时态。'},
            ],
        },
        'nerve': {
            'phonetic': '/nɜːrv/',
            'meaning': 'n. 神经；勇气',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'nerve 来自拉丁语 nervus（神经/肌腱）。联想"那芙"——神话中的精灵，浑身充满"勇气"和"神经"的力量。',
            'examples': [
                {'en': 'The doctor examined the patient\'s nerve carefully.', 'zh': '医生仔细检查了病人的神经。'},
                {'en': 'It takes a lot of nerve to speak in front of many people.', 'zh': '在很多人面前讲话需要很大的勇气。'},
            ],
        },
        'chef': {
            'phonetic': '/ʃef/',
            'meaning': 'n. 厨师',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'chef 来自法语，意思是"主厨、厨师"。联想"谢夫"——感谢厨师为你做饭。',
            'examples': [
                {'en': 'The chef prepared a delicious meal for us.', 'zh': '厨师为我们准备了一顿美味的饭菜。'},
                {'en': 'She dreams of becoming a famous chef.', 'zh': '她梦想成为一名著名的厨师。'},
            ],
        },
        'good': {
            'phonetic': '/ɡʊd/',
            'meaning': 'adj. 好的，优良的',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'good 是最基础的正向形容词。联想"顾的"——顾及到别人的就是"好的"。',
            'examples': [
                {'en': 'She is a good student who always helps others.', 'zh': '她是一个总是帮助别人的好学生。'},
                {'en': 'This book is good for improving your vocabulary.', 'zh': '这本书对提高词汇量很有帮助。'},
            ],
        },
        'goods': {
            'phonetic': '/ɡʊdz/',
            'meaning': 'n. 商品，货物',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'goods 是 good 的复数形式，但词义不同，指"商品、货物"。',
            'examples': [
                {'en': 'The shop sells all kinds of goods.', 'zh': '这家商店出售各种各样的商品。'},
                {'en': 'These goods are made in China.', 'zh': '这些货物是中国制造的。'},
            ],
        },
        'talk': {
            'phonetic': '/tɔːk/',
            'meaning': 'v. 谈话，交谈\nn. 谈话',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'talk 联想"套口"——把心里的话从套口里倒出来，就是交谈聊天。',
            'examples': [
                {'en': 'The professor will give a talk on career development.', 'zh': '教授将做一场关于职业发展的讲座。'},
                {'en': 'We need to have a serious talk about your future.', 'zh': '我们需要认真谈谈你的未来。'},
            ],
        },
        'run': {
            'phonetic': '/rʌn/',
            'meaning': 'v. 跑，运行',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'run 是最基础的动作词。联想"润"——跑起来像水一样流动，就是"跑、运行"。',
            'examples': [
                {'en': 'She runs five kilometers every morning to keep fit.', 'zh': '她每天早上跑五公里来保持健康。'},
                {'en': 'The river runs through the center of the city.', 'zh': '这条河穿过市中心。'},
            ],
        },
        'go': {
            'phonetic': '/ɡoʊ/',
            'meaning': 'v. 去，走',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'go 是最基础的动词，表示"去、走"。联想"狗"——狗喜欢到处"跑、去"。',
            'examples': [
                {'en': 'She wants to go to college in Beijing.', 'zh': '她想去北京上大学。'},
                {'en': 'Time goes by quickly when you are busy.', 'zh': '忙碌的时候时间过得很快。'},
            ],
        },
        'do': {
            'phonetic': '/duː/',
            'meaning': 'v. 做，干',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'do 是英语中最基础的动词，想象你正在动手做事（do something），就像说"做吧！"一样简单直接。',
            'examples': [
                {'en': 'What do you plan to do after graduation?', 'zh': '你毕业后打算做什么？'},
                {'en': 'He does his homework in the library every evening.', 'zh': '他每天晚上在图书馆做作业。'},
            ],
        },
        'write': {
            'phonetic': '/raɪt/',
            'meaning': 'v. 写，书写',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'write 联想"赖特"——赖特兄弟在飞机上写字记录飞行数据，帮助记忆"写"这个动作。',
            'examples': [
                {'en': 'Students are required to write a 300-word essay.', 'zh': '学生需要写一篇300字的短文。'},
                {'en': 'She writes down new words in her notebook every day.', 'zh': '她每天把生词记在笔记本上。'},
            ],
        },
        'study': {
            'phonetic': '/ˈstʌdi/',
            'meaning': 'v. 学习',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'study 联想"死呆地"——死死呆在书桌前，就是在"学习"。',
            'examples': [
                {'en': 'She studies hard to pass the entrance exam.', 'zh': '她努力学习以通过入学考试。'},
                {'en': 'Many adults choose to study for a degree.', 'zh': '许多成年人选择攻读学位。'},
            ],
        },
        'test': {
            'phonetic': '/test/',
            'meaning': 'n. 测试，考试\nv. 测试，检验',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'test 联想"太死他"——考试太难了，太死他了（太要命了），就是"测试、考试"。',
            'examples': [
                {'en': 'The final test will cover all the chapters we learned.', 'zh': '期末考试将涵盖我们学过的所有章节。'},
                {'en': 'You need to test the hypothesis before drawing a conclusion.', 'zh': '在得出结论之前，你需要检验这个假设。'},
            ],
        },
        'apple': {
            'phonetic': '/ˈæpl/',
            'meaning': 'n. 苹果',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'apple 联想"阿婆"——阿婆手里拿着一个红苹果。',
            'examples': [
                {'en': 'An apple a day keeps the doctor away.', 'zh': '一天一个苹果，医生远离我。'},
                {'en': 'She bought some fresh apples at the market.', 'zh': '她在市场上买了一些新鲜的苹果。'},
            ],
        },
        'worse': {
            'phonetic': '/wɜːrs/',
            'meaning': 'adj. 更坏的，更差的\nadv. 更坏地',
            'type': '变形词',
            'split': [
                {'part': 'worse', 'meaning': 'adj. 更坏的，更差的', 'original': 'bad', 'original_meaning': 'adj. 坏的', 'transform': '不规则比较级（bad → worse → worst）', 'explain': '是 bad/ill 的不规则比较级形式'},
            ],
            'morph': [],
            'mnemonic': 'worse 是 bad 的不规则比较级，与 worst（最高级）、better（反义比较级）成组记忆。联想"沃死"——更坏了，快要死掉了。',
            'examples': [
                {'en': 'The weather became worse in the afternoon.', 'zh': '下午天气变得更糟了。'},
                {'en': 'His condition is getting worse day by day.', 'zh': '他的状况一天天恶化。'},
            ],
        },
        # ===== 专升本高频词：基于权威词源字典（etymonline.com）的拆解 =====
        'development': {
            'phonetic': '/dɪˈveləpmənt/',
            'meaning': 'n. 发展，开发；发育',
            'type': '派生词',
            'split': [
                {'part': 'develop', 'meaning': 'v. 发展，开发', 'original': 'develop', 'original_meaning': 'v. 发展，开发（源自法语 développer）', 'transform': '原形不变', 'explain': '词根，表示"发展"'},
                {'part': '-ment', 'meaning': '名词后缀，表示行为或结果', 'original': '-ment', 'original_meaning': '名词后缀，表示行为或结果', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"发展的过程或结果"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'develop', 'meaning': 'v. 发展，开发'},
                {'type': 'suffix', 'word': '-ment', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'develop（发展）+ ment（名词后缀）→ 发展的过程或结果 → 发展。联想同根词：develop(发展)、developer(开发者)。',
            'examples': [
                {'en': 'The development of technology has changed our lives.', 'zh': '科技的发展改变了我们的生活。'},
                {'en': 'She is studying the development of children.', 'zh': '她正在研究儿童的发展。'},
            ],
        },
        'develop': {
            'phonetic': '/dɪˈveləp/',
            'meaning': 'v. 发展，开发；冲洗（照片）',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'develop 来自法语 développer（展开），de-（解除）+ voloper（包裹）→ 解开包裹 → 展开 → 发展。虽然看似有 de- 前缀，但它是作为整体借入英语的基础词。',
            'examples': [
                {'en': 'We need to develop a good study habit.', 'zh': '我们需要养成良好的学习习惯。'},
                {'en': 'The city has developed rapidly in recent years.', 'zh': '这座城市近年来发展迅速。'},
            ],
        },
        'education': {
            'phonetic': '/ˌedʒuˈkeɪʃn/',
            'meaning': 'n. 教育',
            'type': '派生词',
            'split': [
                {'part': 'educate', 'meaning': 'v. 教育', 'original': 'educate', 'original_meaning': 'v. 教育（拉丁语 educare "引导出来"）', 'transform': '去掉词尾 e', 'explain': '词根，e-(出)+duc(引导)+-ate(动词后缀)→"引导出来"即教育'},
                {'part': '-ion', 'meaning': '名词后缀，表示行为或状态', 'original': '-ion', 'original_meaning': '名词后缀，表示行为或状态', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"教育的行为或过程"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'educate', 'meaning': 'v. 教育'},
                {'type': 'suffix', 'word': '-ion', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'educate（教育）+ ion（名词后缀）→ 教育。educate 源自拉丁语 e-(出)+ducare(引导)，即"把人引导出来"→教育。联想同根词：educator(教育者)。',
            'examples': [
                {'en': 'Education is the key to a better future.', 'zh': '教育是通向美好未来的关键。'},
                {'en': 'She received a good education in college.', 'zh': '她在大学接受了良好的教育。'},
            ],
        },
        'communicate': {
            'phonetic': '/kəˈmjuːnɪkeɪt/',
            'meaning': 'v. 交流，沟通；传达',
            'type': '派生词',
            'split': [
                {'part': 'com-', 'meaning': '前缀，表示"共同、一起"', 'original': 'com-', 'original_meaning': '前缀，表示"共同、一起"', 'transform': '本身是前缀，无变形', 'explain': '前缀，con- 在 m 前的变体，表示"共同的"'},
                {'part': 'munic', 'meaning': '词根，表示"服务、公共"', 'original': 'munic', 'original_meaning': '词根，源自拉丁语 communis（共同的、公共的）', 'transform': '原形不变', 'explain': '词根，表示"公共、共享"'},
                {'part': '-ate', 'meaning': '动词后缀', 'original': '-ate', 'original_meaning': '动词后缀', 'transform': '本身是后缀，无变形', 'explain': '把词根变成动词，表示"使共享"即交流'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'com-', 'meaning': '前缀，表示"共同"'},
                {'type': 'root', 'word': 'munic', 'meaning': '词根，表示"公共、共享"'},
                {'type': 'suffix', 'word': '-ate', 'meaning': '动词后缀'},
            ],
            'mnemonic': 'com（共同）+ munic（共享）+ ate（动词后缀）→ 使共同分享 → 交流、沟通。联想同根词：community(社区)、communication(交流)。',
            'examples': [
                {'en': 'It is important to communicate with your parents.', 'zh': '和父母沟通很重要。'},
                {'en': 'Teachers should communicate clearly with students.', 'zh': '老师应该与学生清楚地沟通。'},
            ],
        },
        'communication': {
            'phonetic': '/kəˌmjuːnɪˈkeɪʃn/',
            'meaning': 'n. 交流，通讯，沟通',
            'type': '派生词',
            'split': [
                {'part': 'communicate', 'meaning': 'v. 交流，沟通', 'original': 'communicate', 'original_meaning': 'v. 交流，沟通', 'transform': '去掉词尾 e', 'explain': '词根，表示"交流"'},
                {'part': '-ion', 'meaning': '名词后缀，表示行为或状态', 'original': '-ion', 'original_meaning': '名词后缀，表示行为或状态', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"交流的行为"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'communicate', 'meaning': 'v. 交流'},
                {'type': 'suffix', 'word': '-ion', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'communicate（交流）+ ion（名词后缀）→ 交流的行为 → 交流、通讯。',
            'examples': [
                {'en': 'Good communication is essential in any relationship.', 'zh': '良好的沟通在任何关系中都是必不可少的。'},
                {'en': 'Mobile phones have changed the way of communication.', 'zh': '手机改变了交流方式。'},
            ],
        },
        'success': {
            'phonetic': '/səkˈses/',
            'meaning': 'n. 成功；成功的人或事物',
            'type': '派生词',
            'split': [
                {'part': 'suc-', 'meaning': '前缀，表示"在...之后"（sub- 的变体）', 'original': 'sub-', 'original_meaning': '前缀，表示"在...之下、之后"', 'transform': 'sub- 在 c 前同化为 suc-', 'explain': '前缀，表示"紧随其后"'},
                {'part': 'cess', 'meaning': '词根，表示"走、行"', 'original': 'cess', 'original_meaning': '词根，源自拉丁语 cedere（走、行）', 'transform': '原形不变', 'explain': '词根，"紧跟其后走"引申为"成功"'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'suc-', 'meaning': '前缀，sub-的变体'},
                {'type': 'root', 'word': 'cess', 'meaning': '词根，表示"走"'},
            ],
            'mnemonic': 'suc（在...之后）+ cess（走）→ 紧跟其后走到终点 → 成功。联想同根词：succeed(成功)、process(过程)、access(进入)。',
            'examples': [
                {'en': 'Hard work is the key to success.', 'zh': '努力是成功的关键。'},
                {'en': 'The meeting was a great success.', 'zh': '这次会议非常成功。'},
            ],
        },
        'successful': {
            'phonetic': '/səkˈsesfl/',
            'meaning': 'adj. 成功的；有成就的',
            'type': '派生词',
            'split': [
                {'part': 'success', 'meaning': 'n. 成功', 'original': 'success', 'original_meaning': 'n. 成功', 'transform': '原形不变', 'explain': '词根，表示"成功"'},
                {'part': '-ful', 'meaning': '形容词后缀，表示"充满...的"', 'original': 'full', 'original_meaning': 'adj. 满的', 'transform': '缩略为后缀 -ful', 'explain': '源自 full（满的），把名词变成形容词，表示"充满成功的"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'success', 'meaning': 'n. 成功'},
                {'type': 'suffix', 'word': '-ful', 'meaning': '形容词后缀'},
            ],
            'mnemonic': 'success（成功）+ ful（充满...的）→ 充满成功的 → 成功的。',
            'examples': [
                {'en': 'She is a successful businesswoman.', 'zh': '她是一位成功的女商人。'},
                {'en': 'The project was highly successful.', 'zh': '这个项目非常成功。'},
            ],
        },
        'suggest': {
            'phonetic': '/səˈdʒest/',
            'meaning': 'v. 建议，提议；暗示',
            'type': '派生词',
            'split': [
                {'part': 'sug-', 'meaning': '前缀，表示"在...下面"（sub- 的变体）', 'original': 'sub-', 'original_meaning': '前缀，表示"在...之下"', 'transform': 'sub- 在 g 前同化为 sug-', 'explain': '前缀，表示"从下面托起"'},
                {'part': 'gest', 'meaning': '词根，表示"带来、携带"', 'original': 'gest', 'original_meaning': '词根，源自拉丁语 gerere（带来、做）', 'transform': '原形不变', 'explain': '词根，"从下面带来"引申为"提出建议"'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'sug-', 'meaning': '前缀，sub-的变体'},
                {'type': 'root', 'word': 'gest', 'meaning': '词根，表示"带来"'},
            ],
            'mnemonic': 'sug（在...下面）+ gest（带来）→ 从下面带来 → 提出来 → 建议。联想同根词：gesture(手势)、digest(消化)。',
            'examples': [
                {'en': 'I suggest that you read more English books.', 'zh': '我建议你多读英语书。'},
                {'en': 'The doctor suggested taking more exercise.', 'zh': '医生建议多做运动。'},
            ],
        },
        'consider': {
            'phonetic': '/kənˈsɪdər/',
            'meaning': 'v. 考虑，细想；认为',
            'type': '派生词',
            'split': [
                {'part': 'con-', 'meaning': '前缀，表示"共同、彻底"', 'original': 'con-', 'original_meaning': '前缀，表示"共同、彻底"', 'transform': '本身是前缀，无变形', 'explain': '前缀，表示"仔细地"'},
                {'part': 'sider', 'meaning': '词根，源自拉丁语 sidus（星辰）', 'original': 'sider', 'original_meaning': '词根，源自拉丁语 sidus/sideris（星辰）', 'transform': '原形不变', 'explain': '词根，原意为"观察星辰"（古代航海靠星辰导航），引申为"仔细观察、考虑"'},
            ],
            'morph': [
                {'type': 'prefix', 'word': 'con-', 'meaning': '前缀，表示"彻底"'},
                {'type': 'root', 'word': 'sider', 'meaning': '词根，源自"星辰"'},
            ],
            'mnemonic': 'con（彻底）+ sider（星辰）→ 仔细观察星辰（古代航海靠看星）→ 仔细考虑。联想：consider 的本意是"看星象做决定"。',
            'examples': [
                {'en': 'You should consider all the options carefully.', 'zh': '你应该仔细考虑所有选项。'},
                {'en': 'She is considered one of the best teachers.', 'zh': '她被认为是最优秀的老师之一。'},
            ],
        },
        'imagination': {
            'phonetic': '/ɪˌmædʒɪˈneɪʃn/',
            'meaning': 'n. 想象力；想象',
            'type': '派生词',
            'split': [
                {'part': 'imagine', 'meaning': 'v. 想象', 'original': 'imagine', 'original_meaning': 'v. 想象（源自拉丁语 imaginari）', 'transform': '去掉词尾 e', 'explain': '词根，表示"想象"'},
                {'part': '-ation', 'meaning': '名词后缀，表示行为或能力', 'original': '-ation', 'original_meaning': '名词后缀，表示行为或能力', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"想象的能力"'},
            ],
            'morph': [
                {'type': 'root', 'word': 'imagine', 'meaning': 'v. 想象'},
                {'type': 'suffix', 'word': '-ation', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'imagine（想象）+ ation（名词后缀）→ 想象的能力 → 想象力。联想同根词：image(图像)、imagine(想象)。',
            'examples': [
                {'en': 'Children have rich imagination.', 'zh': '孩子们有丰富的想象力。'},
                {'en': 'Use your imagination to solve the problem.', 'zh': '用你的想象力来解决问题。'},
            ],
        },
        'imagine': {
            'phonetic': '/ɪˈmædʒɪn/',
            'meaning': 'v. 想象，设想；认为',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'imagine 源自拉丁语 imago（图像），形成心理图像就是"想象"。联想：image(图像) → imagine(在脑中形成图像) → 想象。',
            'examples': [
                {'en': 'I can\'t imagine life without the Internet.', 'zh': '我无法想象没有互联网的生活。'},
                {'en': 'Imagine that you are traveling around the world.', 'zh': '想象你正在环游世界。'},
            ],
        },
        'regulation': {
            'phonetic': '/ˌreɡjuˈleɪʃn/',
            'meaning': 'n. 规则，法规；管理',
            'type': '派生词',
            'split': [
                {'part': 'regulate', 'meaning': 'v. 管理，控制', 'original': 'regulate', 'original_meaning': 'v. 管理，控制（源自拉丁语 regula "规则"）', 'transform': '去掉词尾 e', 'explain': '词根，表示"管理"'},
                {'part': '-ion', 'meaning': '名词后缀，表示行为或结果', 'original': '-ion', 'original_meaning': '名词后缀，表示行为或结果', 'transform': '本身是后缀，无变形', 'explain': '把动词变成名词，表示"管理的规定"即规则'},
            ],
            'morph': [
                {'type': 'root', 'word': 'regulate', 'meaning': 'v. 管理'},
                {'type': 'suffix', 'word': '-ion', 'meaning': '名词后缀'},
            ],
            'mnemonic': 'regulate（管理）+ ion（名词后缀）→ 管理的规定 → 规则、法规。联想同根词：regular(规律的)、regulate(管理)。',
            'examples': [
                {'en': 'Students must follow the school regulations.', 'zh': '学生必须遵守学校的规定。'},
                {'en': 'New regulations were introduced last year.', 'zh': '去年出台了新规定。'},
            ],
        },
        'forward': {
            'phonetic': '/ˈfɔːrwərd/',
            'meaning': 'adv. 向前；前方的',
            'type': '复合词',
            'split': [
                {'part': 'fore', 'meaning': 'prep./adv. 在前部，前面', 'original': 'fore', 'original_meaning': 'prep./adv. 在前部（古英语 fore "前面"）', 'transform': 'fore 变为 for', 'explain': '表示"前面"的方向'},
                {'part': 'ward', 'meaning': '后缀，表示"朝向...方向"', 'original': 'ward', 'original_meaning': '后缀，表示"朝向...方向"（古英语 -weard）', 'transform': '原形不变', 'explain': '表示"朝向"某方向'},
            ],
            'morph': [],
            'mnemonic': 'fore（前面）+ ward（朝向）→ 朝向前面的方向 → 向前。联想同根词：forehead(额头)、backward(向后)。',
            'examples': [
                {'en': 'She is looking forward to the summer holiday.', 'zh': '她正期待着暑假的到来。'},
                {'en': 'Please move forward to make room for others.', 'zh': '请往前走，给别人腾出空间。'},
            ],
        },
        'culture': {
            'phonetic': '/ˈkʌltʃər/',
            'meaning': 'n. 文化',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'culture 源自拉丁语 colere（耕种、培养），引申为"培养出来的东西"即文化。联想：agriculture(农业) 中也含有 cult（耕种）。',
            'examples': [
                {'en': 'Chinese culture has a long history.', 'zh': '中国文化历史悠久。'},
                {'en': 'Learning about different cultures is fascinating.', 'zh': '了解不同的文化很有趣。'},
            ],
        },
        'traffic': {
            'phonetic': '/ˈtræfɪk/',
            'meaning': 'n. 交通；来往车辆',
            'type': '基础词',
            'split': [],
            'morph': [],
            'mnemonic': 'traffic 源自古意大利语 trafficare（在沿海贸易），作为整体借入英语。联想"穿梭"——车流穿梭就是"交通"。',
            'examples': [
                {'en': 'There was heavy traffic on the road this morning.', 'zh': '今天早上路上交通很拥堵。'},
                {'en': 'Traffic regulations should be strictly followed.', 'zh': '应该严格遵守交通规则。'},
            ],
        },
    }

    # ===== 补充词典（用户笔记句式/谚语/搭配，释义精简常用）=====
    # 覆盖专升本笔记中 ECDICT 未收录的句式模板、谚语、固定搭配
    # 释义采用笔记中手工整理的常见用法，精简、贴合考试（不显示过多义项）
    SUPPLEMENT_DICTIONARY = {
        "as bad as": '和...一样差',
        "have a good knowledge of": '熟练掌握',
        "on the morning": '在早上',
        "from day to night": '从早到晚',
        "hardly...when...": '刚...就',
        "scarcely...when...": '一...就',
        "no sooner...than...": '一...就',
        "how fast": '多快',
        "speed driving": '超速行驶',
        "follow one's advice": '听从某人的建议',
        "follow one's example": '照某人做，以某人为榜样',
        "parenting style": '教养方式',
        "baby-proofing": '防婴儿',
        "you are welcome.": '不客气',
        "it is my pleasure.": '我的荣幸',
        "narrow the gap between the rich and the poor": '缩小贫富差距',
        "receive education": '受教育 接受教育',
        "call upon sb": '拜访某人，号召',
        "call at sp": '拜访某地',
        "pre-school education": '学前教育',
        "be worse than": '比...更糟',
        "be better than": '比...更好',
        "succeed in doing sth": '成功做成某事',
        "practice makes perfect.": '熟能生巧',
        "there is no doubt that.": '毫无疑问',
        "traditional virtue": '传统美德',
        "be accustomed to doing sth.": '习惯于做某事',
        "get accustomed to doing sth.": '习惯于做某事',
        "be used to doing sth.": '习惯于做某事',
        "get used to doing sth.": '习惯于做某事',
        "use sth. to do sth.": '用某物做某事',
        "be used to do sth.": '被用来做某事',
        "used to do sth.": '过去常常做某事',
        "live a adj. life": '过着一种……样的生活',
        "live an adj. life": '过着一种……样的生活',
        "lead a adj. life": '过着一种……样的生活',
        "lead an adj. life": '过着一种……样的生活',
        "be likely to do sth.": '可能做某事',
        "career prospect": '职业前景',
        "seek a job": '找工作',
        "learn by oneself": '自学',
        "learn to do sth.": '学着做某事',
        "too...to do sth.": '太……而不能……',
        "can't too...": '不为过 要……',
        "you can't be too careful.": '你再小心也不为过。 你要多加小心',
        "a woman can't have too many shoes.": '女性有再多的鞋子也不为过',
        "it is never too old to learn.": '活到老学到老',
        "keep away from sth.": '远离某物',
        "an apple a day keeps a doctor away.": '每天一苹果，医生远离我',
        "a friend in need is a friend indeed.": '患难见真情',
        "action speaks louder than words.": '事实胜于雄辩',
        "take action to do sth": '采取措施做某事',
        "a good medicine tastes bitter.": '良药苦口',
        "all roads lead to rome.": '条条大路通罗马',
        "birds of feather flock together.": '人以类聚，物以群分',
        "don’t trouble trouble until trouble troubles you.": '不要自找麻烦除非麻烦找上门',
        "do as you would be done by.": '己所不欲，勿施于人',
        "do as the romans do.": '入乡随俗',
        "don’t judge a book by its cover.": '不要以貌取人',
        "every dog has its day.": '风水轮流转',
        "failure is the mother of success.": '失败是成功之母',
        "god helps those who help themselves.": '天助自助者',
        "great minds think alike.": '英雄所见略同',
        "would you mind doing sth": '你介意做某事吗',
        "honesty is the best policy.": '诚信至上',
        "industry is the parent of success.": '勤奋是成功之母',
        "live and learn.": '活到老学到老',
        "rain cats and dogs.": '倾盆大雨',
        "to see is to believe.": '眼见为实',
        "strike while the iron is hot.": '趁热打铁',
        "to err is human.": '人非圣贤，孰能无过？',
        "think twice before you act.": '三思而后行',
        "time and tide wait for no man.": '时间不等人',
        "well begun is half done.": '好的开始是成功的一半',
        "attitude to sth": '对待某事的态度',
        "attitude towards sth": '对待某事的态度',
        "object to doing sth": '反对做某事',
        "oppose doing sth.": '反对做某事',
        "problem-solving order": '解决问题',
        "take effective measures to do sth": '采取有效措施做某事',
        "giving examples": '举例',
        "strive to do sth": '努力做某事',
        "spare no efforts to do sth": '不遗余力做某事',
        "the developing countries": '发展中国家',
        "the developed countries": '发达国家',
        "poverty-stricken area": '贫困地区',
        "densely-populated area": '人口密集区',
        "expect to do sth": '期望做某事',
        "be expected to do sth": '被期望做某事，应该做某事',
        "charge sb with sth": '因某事控告某人',
        "be under too much pressure": '压力过大',
        "backpacker hostel": '背包客旅店',
        "the means of transport": '交通方式',
        "at the foot of the mountain": '山脚',
        "go trekking": '徒步',
        "stay fit": '保持健康',
        "treat a as b": '把a当作b',
        "treat sb to sth": '用某物招待某人',
        "dr.": '博士',
        "pay attention to doing sth": '留意做某事',
        "apply a to b": '将a应用到b',
        "oppose doing sth": '反对做某事',
        "it is a waste of time doing sth": '做某事是浪费时间',
        "it is a waste of money doing sth": '做某事是浪费金钱',
        "it is a waste of energy doing sth": '做某事是浪费精力',
        "be absorbed in doing sth": '专心致志做某事',
        "present sth to sb": '将某物赠送给某人',
        "it occurred to sb that...": '某人突然想起',
        "take sth for granted": '认为…理所当然',
        "it takes sb time to do sth": '做某事花费某人时间',
        "it took sb time to do sth": '做某事花费某人时间',
        "it costs sb money to do sth": '做某事花费某人钱财',
        "it cost sb money to do sth": '做某事花费某人钱财',
        "sb spend money on sth": '某人花费时间 金钱在某物上',
        "sb spend time on sth": '某人花费时间 金钱在某物上',
        "sb pay money for sth": '某人支付钱财为某物 某人为某物买单',
        "sb1 charge sb2 money for sth": '某人1就某物向某人2要多少钱',
        "be made to do sth": '被迫做某事',
        "live in harmony with": '与……和谐共处',
        "prevent sb from doing sth": '阻止某人做某事',
        "stop to do sth": '停下来去做某事',
        "stop doing sth": '停止正在做某事',
        "much to one's relief": '让某人感到如释重负的是',
        "accessible adj.": '可得到的',
        "sth be available to sb": '某人可获得某物',
        "stable and secure": '安稳',
        "in order to do sth": '为了做某事',
        "so as to do sth": '为了做某事',
        "return sth to sb": '将某物归还给某人',
        "return to sp": '返回某地',
        "it's a deal.": '一言为定',
        "by credit card": '用信用卡',
        "invite sb to do sth": '邀请某人做某事',
        "i have no idea.": '我不知道',
        "marry sb": '嫁给某人，娶某人',
        "draw one's attention": '吸引某人的注意力',
        "a sense of humour": '幽默感',
        "feel like doing sth": '想要做某事',
        "would like to do sth": '想要做某事',
        "prefer to do sth": '更喜欢做某事',
        "prefer doing sth1 to doing sth2": '相比于做2更喜欢做1',
        "prefer a with b": '更喜欢有b的a',
        "would rather do sth": '宁愿做某事',
        "would rather do sth1 than do sth2": '宁愿做1而不愿做2',
        "would do sth1 rather than do sth2": '宁愿做1而不愿做2',
        "may as well do sth": '不妨做某事',
        "look forward to doing sth": '期盼做某事',
        "leave sb a deep impression": '给某人留下深刻的印象',
        "sb be impressed by sth": '某物给某人留下深刻印象',
        "sb be to blame": '某人应该受到责备',
        "regret to do": '对未做的事情表示遗憾',
        "at no way": '决不',
        "way to do sth": '做某事的方法',
        "way of doing sth": '做某事的方法',
        "in a adj. way": '以一种…的方式',
        "in an adj. way": '以一种…的方式',
        "only in this way": '只有通过这种方法',
        "mean doing sth": '意味着做某事',
        # 常见基础口语词（ECDICT 无中文释义或会被在线英文兜底污染，这里直接内置）
        "hello": 'int. 你好，喂',
        "hi": 'int. 你好',
        "hey": 'int. 嗨，喂',
        # ===== 补充：文档中其余无释义词（句式/谚语/口语，释义精简常用）=====
        "how time flies!": '时间过得真快！',
        "i am fine, thank you": '我很好，谢谢',
        "you deserve it!": '你应得的；真是活该',
        "what is this in english?": '这个用英语怎么说？',
        "not…until…": '直到……才……',
        "have a lot of trouble (in) doing sth": '做某事很困难',
        "have difficulty (in) doing sth": '做某事有困难',
        "have a hard time (in) doing sth": '做某事很艰难',
        "no pains, no gains": '不劳无获',
        "where there is smoke, there is fire": '无风不起浪',
        "where there is love, there is hope": '有爱就有希望',
        "sb spend money (in) doing sth": '某人花钱做某事',
        "sb spend time (in) doing sth": '某人花时间做某事',
        "rather than do sth2, would do sth1": '宁愿做某事1，也不愿做某事2',
        "be short for …": '是……的缩写',
    }

    # ===== 专升本常见短语词典 =====
    # ECDICT 对短语的翻译覆盖率有限，这里收录专升本考试常见短语
    # 每个条目格式与 DICTIONARY 相同，至少包含 meaning 和 examples
    PHRASE_DICTIONARY = {
        'overhead bridge': {
            'phonetic': '',
            'meaning': 'n. 立交桥；天桥，高架桥',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'overhead（在头顶的）+ bridge（桥）→ 架在头顶上的桥，即"立交桥/天桥"',
            'examples': [
                {'en': 'There is an overhead bridge near the school.', 'zh': '学校附近有一座人行天桥。'},
                {'en': 'We should walk across the overhead bridge.', 'zh': '我们应该从天桥上走过去。'},
            ],
        },
        'last name': {
            'phonetic': '',
            'meaning': 'n. 姓，姓氏',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'last（最后的）+ name（名字）→ 西方名字中排在最后的"姓"',
            'examples': [
                {'en': 'My last name is Wang.', 'zh': '我姓王。'},
                {'en': 'Please write down your first name and last name.', 'zh': '请写下你的名和姓。'},
            ],
        },
        'as bad as': {
            'phonetic': '',
            'meaning': '和……一样糟糕',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'as + 形容词 + as 表示"和……一样"，as bad as 即"和……一样坏/糟糕"',
            'examples': [
                {'en': 'The weather today is as bad as yesterday.', 'zh': '今天天气和昨天一样糟糕。'},
                {'en': 'His handwriting is as bad as mine.', 'zh': '他的字写得和我一样差。'},
            ],
        },
        'as good as': {
            'phonetic': '',
            'meaning': '和……一样好；几乎等于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'as + 形容词 + as 表示"和……一样"，as good as 即"和……一样好"',
            'examples': [
                {'en': 'His English is as good as hers.', 'zh': '他的英语和她一样好。'},
                {'en': 'The plan is as good as finished.', 'zh': '计划几乎等于完成了。'},
            ],
        },
        'the best': {
            'phonetic': '',
            'meaning': '最好的（人或物）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'the + 最高级，表示"最……的"',
            'examples': [
                {'en': 'She is one of the best students in our class.', 'zh': '她是我们班最优秀的学生之一。'},
                {'en': 'Who do you think is the best candidate for this position?', 'zh': '你认为谁是这个职位的最佳人选？'},
            ],
        },
        'have a good knowledge of': {
            'phonetic': '',
            'meaning': '精通；掌握；对……很了解',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'have a knowledge of 表示"了解"，加 good 表示"很了解/精通"',
            'examples': [
                {'en': 'She has a good knowledge of English grammar.', 'zh': '她精通英语语法。'},
                {'en': 'You need to have a good knowledge of computers for this job.', 'zh': '做这份工作需要精通计算机。'},
            ],
        },
        'take care of': {
            'phonetic': '',
            'meaning': '照顾；照料',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'take care 表示"小心/注意"，加 of 表示"照顾某人/某物"',
            'examples': [
                {'en': 'She takes care of her elderly mother.', 'zh': '她照顾年迈的母亲。'},
                {'en': 'Please take care of your belongings.', 'zh': '请照看好您的随身物品。'},
            ],
        },
        'look forward to': {
            'phonetic': '',
            'meaning': '期待；盼望',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look forward 表示"向前看"，加 to 表示"期待某事"',
            'examples': [
                {'en': 'I look forward to hearing from you soon.', 'zh': '我期待早日收到你的回复。'},
                {'en': 'We are looking forward to the summer holiday.', 'zh': '我们正期待着暑假的到来。'},
            ],
        },
        'be good at': {
            'phonetic': '',
            'meaning': '擅长；善于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be good at = 擅长做某事',
            'examples': [
                {'en': 'He is good at math and physics.', 'zh': '他擅长数学和物理。'},
                {'en': 'Are you good at playing basketball?', 'zh': '你擅长打篮球吗？'},
            ],
        },
        'be bad at': {
            'phonetic': '',
            'meaning': '不擅长；不善于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be bad at = 不擅长做某事，与 be good at 相反',
            'examples': [
                {'en': 'I am bad at singing but good at dancing.', 'zh': '我不擅长唱歌但擅长跳舞。'},
            ],
        },
        'be interested in': {
            'phonetic': '',
            'meaning': '对……感兴趣',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be interested in = 对……有兴趣',
            'examples': [
                {'en': 'She is interested in Chinese culture.', 'zh': '她对中国文化感兴趣。'},
                {'en': 'I am not interested in this topic.', 'zh': '我对这个话题不感兴趣。'},
            ],
        },
        'be fond of': {
            'phonetic': '',
            'meaning': '喜欢；喜爱',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be fond of = 喜爱某人/某物',
            'examples': [
                {'en': 'He is fond of classical music.', 'zh': '他喜欢古典音乐。'},
            ],
        },
        'be proud of': {
            'phonetic': '',
            'meaning': '为……感到骄傲',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be proud of = 以……为荣',
            'examples': [
                {'en': 'We are proud of our achievements.', 'zh': '我们为自己的成就感到骄傲。'},
            ],
        },
        'be afraid of': {
            'phonetic': '',
            'meaning': '害怕；担心',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be afraid of = 害怕某人/某物',
            'examples': [
                {'en': 'She is afraid of dogs.', 'zh': '她害怕狗。'},
            ],
        },
        'be tired of': {
            'phonetic': '',
            'meaning': '厌倦；厌烦',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be tired of = 对……感到厌倦',
            'examples': [
                {'en': 'I am tired of doing the same thing every day.', 'zh': '我厌倦了每天做同样的事。'},
            ],
        },
        'be full of': {
            'phonetic': '',
            'meaning': '充满',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be full of = 充满某物',
            'examples': [
                {'en': 'The room is full of people.', 'zh': '房间里挤满了人。'},
            ],
        },
        'be short of': {
            'phonetic': '',
            'meaning': '缺少；短缺',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be short of = 缺乏某物',
            'examples': [
                {'en': 'We are short of money this month.', 'zh': '这个月我们缺钱。'},
            ],
        },
        'be worth doing': {
            'phonetic': '',
            'meaning': '值得做某事',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be worth + doing = 值得做……',
            'examples': [
                {'en': 'This book is worth reading.', 'zh': '这本书值得读。'},
            ],
        },
        'be used to': {
            'phonetic': '',
            'meaning': '习惯于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be used to + 名词/doing = 习惯于……',
            'examples': [
                {'en': 'I am used to getting up early.', 'zh': '我习惯早起。'},
            ],
        },
        'used to': {
            'phonetic': '',
            'meaning': '过去常常',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'used to + 动词原形 = 过去常常做某事',
            'examples': [
                {'en': 'I used to play basketball a lot.', 'zh': '我过去常打篮球。'},
            ],
        },
        'get used to': {
            'phonetic': '',
            'meaning': '逐渐习惯于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'get used to = 逐渐变得习惯于',
            'examples': [
                {'en': 'You will get used to the weather here.', 'zh': '你会习惯这里的天气的。'},
            ],
        },
        'be familiar with': {
            'phonetic': '',
            'meaning': '熟悉；了解',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be familiar with = 对……熟悉',
            'examples': [
                {'en': 'Are you familiar with this software?', 'zh': '你熟悉这个软件吗？'},
            ],
        },
        'be famous for': {
            'phonetic': '',
            'meaning': '因……而闻名',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be famous for = 因为……而出名',
            'examples': [
                {'en': 'Hangzhou is famous for its West Lake.', 'zh': '杭州因西湖而闻名。'},
            ],
        },
        'be angry with': {
            'phonetic': '',
            'meaning': '生……的气',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be angry with sb. = 生某人的气',
            'examples': [
                {'en': 'Don\'t be angry with me.', 'zh': '别生我的气。'},
            ],
        },
        'be strict with': {
            'phonetic': '',
            'meaning': '对……严格要求',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be strict with sb. = 对某人严格',
            'examples': [
                {'en': 'Our teacher is strict with us.', 'zh': '我们的老师对我们很严格。'},
            ],
        },
        'be satisfied with': {
            'phonetic': '',
            'meaning': '对……满意',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be satisfied with = 对……感到满意',
            'examples': [
                {'en': 'I am satisfied with the result.', 'zh': '我对结果感到满意。'},
            ],
        },
        'be popular with': {
            'phonetic': '',
            'meaning': '受……欢迎',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be popular with = 在……中受欢迎',
            'examples': [
                {'en': 'The song is popular with young people.', 'zh': '这首歌受年轻人欢迎。'},
            ],
        },
        'be different from': {
            'phonetic': '',
            'meaning': '与……不同',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be different from = 和……不一样',
            'examples': [
                {'en': 'This book is different from that one.', 'zh': '这本书和那本不同。'},
            ],
        },
        'be similar to': {
            'phonetic': '',
            'meaning': '与……相似',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be similar to = 和……类似',
            'examples': [
                {'en': 'Your idea is similar to mine.', 'zh': '你的想法和我的相似。'},
            ],
        },
        'be made of': {
            'phonetic': '',
            'meaning': '由……制成（看得出原材料）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be made of = 用……做的（能看出原料）',
            'examples': [
                {'en': 'The desk is made of wood.', 'zh': '这张桌子是木头做的。'},
            ],
        },
        'be made from': {
            'phonetic': '',
            'meaning': '由……制成（看不出原材料）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be made from = 用……做的（看不出原料）',
            'examples': [
                {'en': 'Paper is made from wood.', 'zh': '纸是用木头造的。'},
            ],
        },
        'be made up of': {
            'phonetic': '',
            'meaning': '由……组成',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be made up of = 由……构成',
            'examples': [
                {'en': 'The team is made up of five members.', 'zh': '这个团队由五名成员组成。'},
            ],
        },
        'put on': {
            'phonetic': '',
            'meaning': '穿上；戴上',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'put on = 穿上衣服/戴上帽子等',
            'examples': [
                {'en': 'Put on your coat, it\'s cold outside.', 'zh': '穿上外套，外面很冷。'},
            ],
        },
        'take off': {
            'phonetic': '',
            'meaning': '脱下；起飞',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'take off = 脱衣服 / 飞机起飞',
            'examples': [
                {'en': 'The plane will take off in ten minutes.', 'zh': '飞机十分钟后起飞。'},
            ],
        },
        'turn on': {
            'phonetic': '',
            'meaning': '打开（电器等）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'turn on = 打开开关',
            'examples': [
                {'en': 'Please turn on the lights.', 'zh': '请把灯打开。'},
            ],
        },
        'turn off': {
            'phonetic': '',
            'meaning': '关掉（电器等）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'turn off = 关掉开关',
            'examples': [
                {'en': 'Turn off the TV before you go to bed.', 'zh': '睡觉前关掉电视。'},
            ],
        },
        'give up': {
            'phonetic': '',
            'meaning': '放弃',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'give up = 放弃做某事',
            'examples': [
                {'en': 'Never give up on your dreams.', 'zh': '永远不要放弃你的梦想。'},
            ],
        },
        'pick up': {
            'phonetic': '',
            'meaning': '捡起；接（人）；学会',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'pick up = 捡起来 / 开车接人 / 自然学会',
            'examples': [
                {'en': 'I will pick you up at the station.', 'zh': '我会在车站接你。'},
            ],
        },
        'look up': {
            'phonetic': '',
            'meaning': '查阅；向上看',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look up = 在字典/资料中查找',
            'examples': [
                {'en': 'Look up the word in the dictionary.', 'zh': '在字典里查这个词。'},
            ],
        },
        'find out': {
            'phonetic': '',
            'meaning': '发现；查明',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'find out = 经过调查发现/查明',
            'examples': [
                {'en': 'I will find out the truth.', 'zh': '我会查明真相。'},
            ],
        },
        'hand in': {
            'phonetic': '',
            'meaning': '上交；提交',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'hand in = 把东西交上去',
            'examples': [
                {'en': 'Please hand in your homework on time.', 'zh': '请按时交作业。'},
            ],
        },
        'hand out': {
            'phonetic': '',
            'meaning': '分发；散发',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'hand out = 把东西分发出去',
            'examples': [
                {'en': 'The teacher handed out the test papers.', 'zh': '老师分发了试卷。'},
            ],
        },
        'look after': {
            'phonetic': '',
            'meaning': '照顾；照料',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look after = 照顾某人',
            'examples': [
                {'en': 'Can you look after my cat?', 'zh': '你能照看我的猫吗？'},
            ],
        },
        'look for': {
            'phonetic': '',
            'meaning': '寻找',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look for = 寻找某物/某人',
            'examples': [
                {'en': 'What are you looking for?', 'zh': '你在找什么？'},
            ],
        },
        'look at': {
            'phonetic': '',
            'meaning': '看；注视',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look at = 看着某物',
            'examples': [
                {'en': 'Look at the blackboard, please.', 'zh': '请看黑板。'},
            ],
        },
        'look like': {
            'phonetic': '',
            'meaning': '看起来像',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look like = 看上去像……',
            'examples': [
                {'en': 'She looks like her mother.', 'zh': '她看起来像她妈妈。'},
            ],
        },
        'listen to': {
            'phonetic': '',
            'meaning': '听；倾听',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'listen to = 听某人说话/听某物',
            'examples': [
                {'en': 'I like to listen to music.', 'zh': '我喜欢听音乐。'},
            ],
        },
        'belong to': {
            'phonetic': '',
            'meaning': '属于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'belong to = 属于某人',
            'examples': [
                {'en': 'This book belongs to the library.', 'zh': '这本书是图书馆的。'},
            ],
        },
        'depend on': {
            'phonetic': '',
            'meaning': '依赖；取决于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'depend on = 依靠 / 由……决定',
            'examples': [
                {'en': 'It depends on the weather.', 'zh': '这取决于天气。'},
            ],
        },
        'focus on': {
            'phonetic': '',
            'meaning': '专注于；集中注意力于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'focus on = 把注意力集中在……',
            'examples': [
                {'en': 'Focus on your studies.', 'zh': '专注于你的学业。'},
            ],
        },
        'concentrate on': {
            'phonetic': '',
            'meaning': '集中精力于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'concentrate on = 全神贯注于……',
            'examples': [
                {'en': 'I can\'t concentrate on my work.', 'zh': '我无法集中精力工作。'},
            ],
        },
        'apply for': {
            'phonetic': '',
            'meaning': '申请',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'apply for = 申请职位/学校等',
            'examples': [
                {'en': 'He applied for a scholarship.', 'zh': '他申请了奖学金。'},
            ],
        },
        'wait for': {
            'phonetic': '',
            'meaning': '等待',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'wait for = 等待某人/某事',
            'examples': [
                {'en': 'I am waiting for the bus.', 'zh': '我在等公交车。'},
            ],
        },
        'search for': {
            'phonetic': '',
            'meaning': '搜索；寻找',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'search for = 搜寻某人/某物',
            'examples': [
                {'en': 'They are searching for the missing dog.', 'zh': '他们在寻找走失的狗。'},
            ],
        },
        'pay for': {
            'phonetic': '',
            'meaning': '为……付款',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'pay for = 为……付钱',
            'examples': [
                {'en': 'I will pay for the dinner.', 'zh': '我来付晚饭的钱。'},
            ],
        },
        'ask for': {
            'phonetic': '',
            'meaning': '请求；索要',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'ask for = 要求得到/请求',
            'examples': [
                {'en': 'He asked for help.', 'zh': '他请求帮助。'},
            ],
        },
        'prepare for': {
            'phonetic': '',
            'meaning': '为……做准备',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'prepare for = 为某事做准备',
            'examples': [
                {'en': 'We are preparing for the exam.', 'zh': '我们正在为考试做准备。'},
            ],
        },
        'thanks to': {
            'phonetic': '',
            'meaning': '多亏；由于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'thanks to = 因为/多亏了某人某事',
            'examples': [
                {'en': 'Thanks to your help, I passed the exam.', 'zh': '多亏你的帮助，我通过了考试。'},
            ],
        },
        'due to': {
            'phonetic': '',
            'meaning': '由于；因为',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'due to = 因为某事',
            'examples': [
                {'en': 'The flight was delayed due to bad weather.', 'zh': '航班因恶劣天气延误。'},
            ],
        },
        'owing to': {
            'phonetic': '',
            'meaning': '由于；因为',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'owing to = 因为（同 due to）',
            'examples': [
                {'en': 'The game was canceled owing to rain.', 'zh': '比赛因雨取消了。'},
            ],
        },
        'in order to': {
            'phonetic': '',
            'meaning': '为了；以便',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'in order to + 动词 = 为了做某事',
            'examples': [
                {'en': 'I got up early in order to catch the train.', 'zh': '我早起为了赶火车。'},
            ],
        },
        'so as to': {
            'phonetic': '',
            'meaning': '以便；为了',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'so as to + 动词 = 以便做某事',
            'examples': [
                {'en': 'Speak louder so as to let everyone hear you.', 'zh': '说大声点以便大家都能听到。'},
            ],
        },
        'in spite of': {
            'phonetic': '',
            'meaning': '尽管；不管',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'in spite of = 尽管（同 despite）',
            'examples': [
                {'en': 'He went out in spite of the rain.', 'zh': '尽管下雨他还是出去了。'},
            ],
        },
        'instead of': {
            'phonetic': '',
            'meaning': '代替；而不是',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'instead of = 而不是 / 代替',
            'examples': [
                {'en': 'I will have tea instead of coffee.', 'zh': '我要茶而不是咖啡。'},
            ],
        },
        'because of': {
            'phonetic': '',
            'meaning': '因为；由于',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'because of + 名词 = 因为某事',
            'examples': [
                {'en': 'The match was canceled because of rain.', 'zh': '比赛因雨取消了。'},
            ],
        },
        'ahead of': {
            'phonetic': '',
            'meaning': '在……前面；领先',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'ahead of = 在……之前/领先于',
            'examples': [
                {'en': 'She is ahead of her classmates in math.', 'zh': '她的数学领先于同学。'},
            ],
        },
        'on behalf of': {
            'phonetic': '',
            'meaning': '代表',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'on behalf of = 代表某人',
            'examples': [
                {'en': 'I thank you on behalf of our team.', 'zh': '我代表团队感谢你。'},
            ],
        },
        'be under too much pressure': {
            'phonetic': '',
            'meaning': '承受太大压力',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'under pressure = 承受压力，too much = 太大',
            'examples': [
                {'en': 'Students are under too much pressure nowadays.', 'zh': '如今学生承受的压力太大了。'},
            ],
        },
        'pressure cooker': {
            'phonetic': '',
            'meaning': '高压锅',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'pressure（压力）+ cooker（炊具）= 高压锅',
            'examples': [
                {'en': 'My mother bought a new pressure cooker.', 'zh': '我妈妈买了一个新的高压锅。'},
            ],
        },
        'look up to': {
            'phonetic': '',
            'meaning': 'v. 尊敬，敬仰',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look up（向上看）+ to → 仰望某人 → 尊敬、敬仰',
            'examples': [
                {'en': 'Many students look up to their teachers as role models.', 'zh': '许多学生把老师当作榜样来敬仰。'},
                {'en': 'She has always looked up to her older sister.', 'zh': '她一直敬仰她的姐姐。'},
            ],
        },
        'see through': {
            'phonetic': '',
            'meaning': 'v. 看穿，识破；(help sb) 帮某人度过(难关)',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'see(看) + through(穿透) → 看穿、识破',
            'examples': [
                {'en': 'His friends helped him see through the hard times.', 'zh': '他的朋友们帮他熬过了艰难时期。'},
                {'en': 'We can see through his lie.', 'zh': '我们能看穿他的谎言。'},
            ],
        },
        'see off': {
            'phonetic': '',
            'meaning': 'v. 为……送行，送别',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'see(送) + off(离开) → 送某人离开 → 送行',
            'examples': [
                {'en': 'We went to the airport to see him off.', 'zh': '我们去机场为他送行。'},
                {'en': 'She saw her parents off at the station.', 'zh': '她在车站送别了父母。'},
            ],
        },
        'be able to': {
            'phonetic': '',
            'meaning': 'v. 能够，会（can 的多种时态形式）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be(是) + able(能够的) + to do → 能够做某事',
            'examples': [
                {'en': 'She will be able to finish the task on time.', 'zh': '她将能够按时完成任务。'},
                {'en': 'Are you able to come to my birthday party?', 'zh': '你能来参加我的生日聚会吗？'},
            ],
        },
        'regard as': {
            'phonetic': '',
            'meaning': 'v. 把……看作，认为',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'regard(看待) + as(作为) → 把……看作',
            'examples': [
                {'en': 'We regard him as our best friend.', 'zh': '我们把他看作最好的朋友。'},
                {'en': 'It is regarded as one of the greatest books.', 'zh': '它被认为是伟大的著作之一。'},
            ],
        },
        'be accustomed to doing sth': {
            'phonetic': '',
            'meaning': 'v. 习惯于做某事',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be accustomed(习惯的) + to → 习惯于',
            'examples': [
                {'en': 'She is accustomed to getting up early.', 'zh': '她习惯于早起。'},
            ],
        },
        'get accustomed to doing sth': {
            'phonetic': '',
            'meaning': 'v. 变得习惯于做某事',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'get(变得) accustomed(习惯) to → 逐渐习惯',
            'examples': [
                {'en': 'You will get accustomed to the new school soon.', 'zh': '你很快就会习惯新学校。'},
            ],
        },
        'be used to doing sth': {
            'phonetic': '',
            'meaning': 'v. 习惯于做某事',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'be used(习惯于的) to doing → 习惯了做某事',
            'examples': [
                {'en': 'He is used to living in the countryside.', 'zh': '他习惯了住在乡下。'},
            ],
        },
        'used to do sth': {
            'phonetic': '',
            'meaning': 'v. 过去常常做某事（现在不做了）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'used to + do 表示"过去常常做"',
            'examples': [
                {'en': 'I used to play basketball after school.', 'zh': '我以前放学后常常打篮球。'},
            ],
        },
        'take advantage of': {
            'phonetic': '',
            'meaning': 'v. 利用；占……的便宜',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'take(取) advantage(优势) of → 利用',
            'examples': [
                {'en': 'We should take advantage of the sunny weather.', 'zh': '我们应该利用这晴朗的天气。'},
            ],
        },
        'make use of': {
            'phonetic': '',
            'meaning': 'v. 利用，使用',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'make(使) use(使用) of → 利用',
            'examples': [
                {'en': 'You should make full use of your time.', 'zh': '你应该充分利用你的时间。'},
            ],
        },
        'pay attention to': {
            'phonetic': '',
            'meaning': 'v. 注意，关注',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'pay(给予) attention(注意力) to → 注意到，关注',
            'examples': [
                {'en': 'Please pay attention to the teacher in class.', 'zh': '上课时请认真听老师讲课。'},
            ],
        },
        'take part in': {
            'phonetic': '',
            'meaning': 'v. 参加，参与',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'take part(部分) in → 参加',
            'examples': [
                {'en': 'Many students take part in the school activities.', 'zh': '许多学生参加了学校的活动。'},
            ],
        },
        'look forward to': {
            'phonetic': '',
            'meaning': 'v. 盼望，期待',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'look(看) forward(向前) to → 向前看 → 期待',
            'examples': [
                {'en': 'I look forward to hearing from you.', 'zh': '我期待收到你的来信。'},
            ],
        },
        'get along with': {
            'phonetic': '',
            'meaning': 'v. 与……相处融洽；进展',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'get along(相处) with sb → 与某人相处',
            'examples': [
                {'en': 'She gets along well with her classmates.', 'zh': '她和同学们相处得很好。'},
            ],
        },
        'come up with': {
            'phonetic': '',
            'meaning': 'v. 想出，提出（主意、计划）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'come up(出现) with → 想出好主意',
            'examples': [
                {'en': 'He came up with a good idea for the project.', 'zh': '他为这个项目想出了一个好主意。'},
            ],
        },
        'carry out': {
            'phonetic': '',
            'meaning': 'v. 执行，实施（计划、任务）',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'carry(执行) out(出来) → 实施、执行',
            'examples': [
                {'en': 'We must carry out the plan carefully.', 'zh': '我们必须认真执行这项计划。'},
            ],
        },
        'put off': {
            'phonetic': '',
            'meaning': 'v. 推迟，拖延',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'put(放) off(离开) → 放到一边 → 推迟',
            'examples': [
                {'en': 'Never put off what you can do today.', 'zh': '今日事今日毕，不要拖延。'},
            ],
        },
        'give up': {
            'phonetic': '',
            'meaning': 'v. 放弃',
            'type': '短语',
            'split': [],
            'morph': [],
            'mnemonic': 'give(给) up(向上) → 交出 → 放弃',
            'examples': [
                {'en': 'Never give up on your dreams.', 'zh': '永远不要放弃你的梦想。'},
            ],
        },
        # ===== 补充：常见短语（避免依赖在线翻译，释义准确、例句贴合）=====
        'be adept at': {
            'phonetic': '', 'meaning': 'v. 擅长于，善于', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'adept(熟练的) + at → 在某方面熟练 → 擅长于',
            'examples': [
                {'en': 'She is adept at solving math problems.', 'zh': '她擅长解数学题。'},
                {'en': 'He is adept at playing the piano.', 'zh': '他擅长弹钢琴。'},
            ],
        },
        'summer camp': {
            'phonetic': '', 'meaning': 'n. 夏令营', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'summer(夏天) + camp(营地) → 夏令营',
            'examples': [
                {'en': 'I went to a summer camp last July.', 'zh': '去年七月我参加了一个夏令营。'},
                {'en': 'The summer camp is full of fun activities.', 'zh': '夏令营里充满了有趣的活动。'},
            ],
        },
        'as soon as': {
            'phonetic': '', 'meaning': 'conj. 一……就……', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'as soon as 表示"一……就……"，引导时间状语从句',
            'examples': [
                {'en': 'I will call you as soon as I arrive.', 'zh': '我一到就给你打电话。'},
                {'en': 'As soon as the bell rang, the students left.', 'zh': '铃声一响，学生们就离开了。'},
            ],
        },
        'the instant': {
            'phonetic': '', 'meaning': 'conj. 一……就……（=as soon as）', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'the instant 可作连词，相当于 as soon as，表示"一……就"',
            'examples': [
                {'en': 'The instant I saw him, I knew the truth.', 'zh': '我一见到他就知道了真相。'},
                {'en': 'She smiled the instant she heard the news.', 'zh': '她一听到这个消息就笑了。'},
            ],
        },
        'swimming pool': {
            'phonetic': '', 'meaning': 'n. 游泳池', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'swimming(游泳) + pool(池) → 游泳池',
            'examples': [
                {'en': 'There is a big swimming pool near our school.', 'zh': '我们学校附近有一个大游泳池。'},
                {'en': 'We often swim in the swimming pool in summer.', 'zh': '夏天我们经常在游泳池里游泳。'},
            ],
        },
        'the authorities': {
            'phonetic': '', 'meaning': 'n. 当局，官方；权威人士', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'authority(权威) 的复数形式，指"当局/官方"',
            'examples': [
                {'en': 'The authorities are taking measures to protect the environment.', 'zh': '当局正在采取措施保护环境。'},
                {'en': 'The local authorities should solve this problem.', 'zh': '当地政府应该解决这个问题。'},
            ],
        },
        'thank you': {
            'phonetic': '', 'meaning': '谢谢你', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'thank(感谢) + you(你) → 谢谢你',
            'examples': [
                {'en': 'Thank you for your help.', 'zh': '谢谢你的帮助。'},
                {'en': 'Thank you very much for your invitation.', 'zh': '非常感谢你的邀请。'},
            ],
        },
        'as a result': {
            'phonetic': '', 'meaning': '因此，结果；作为结果', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'as a result 表示"因此/结果"，常与 of 连用',
            'examples': [
                {'en': 'He studied hard, and as a result he passed the exam.', 'zh': '他学习很努力，结果通过了考试。'},
                {'en': 'As a result of the rain, the match was put off.', 'zh': '由于下雨，比赛被推迟了。'},
            ],
        },
        'in english': {
            'phonetic': '', 'meaning': '用英语', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in + 语言 表示"用……语言"',
            'examples': [
                {'en': 'Please answer the question in English.', 'zh': '请用英语回答这个问题。'},
                {'en': 'Can you say this word in English?', 'zh': '你能用英语说出这个词吗？'},
            ],
        },
        'in chinese': {
            'phonetic': '', 'meaning': '用中文，用汉语', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in + 语言 表示"用……语言"',
            'examples': [
                {'en': 'Please explain the sentence in Chinese.', 'zh': '请用中文解释这个句子。'},
                {'en': 'He can translate the article into Chinese.', 'zh': '他能把这篇文章译成中文。'},
            ],
        },
        'originate from': {
            'phonetic': '', 'meaning': 'v. 起源于，源自', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'originate(起源) + from(从) → 起源于',
            'examples': [
                {'en': 'Tea culture originated from China.', 'zh': '茶文化起源于中国。'},
                {'en': 'These customs originate from ancient times.', 'zh': '这些习俗起源于古代。'},
            ],
        },
        'generation gap': {
            'phonetic': '', 'meaning': 'n. 代沟', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'generation(一代人) + gap(差距) → 代沟',
            'examples': [
                {'en': 'There is a generation gap between parents and children.', 'zh': '父母和孩子之间存在着代沟。'},
                {'en': 'We should bridge the generation gap through communication.', 'zh': '我们应该通过沟通来弥合代沟。'},
            ],
        },
        'education background': {
            'phonetic': '', 'meaning': 'n. 教育背景，学历', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'education(教育) + background(背景) → 教育背景',
            'examples': [
                {'en': 'She has a good education background.', 'zh': '她有良好的教育背景。'},
                {'en': 'Please fill in your education background on the form.', 'zh': '请在表格上填写你的教育背景。'},
            ],
        },
        'first name': {
            'phonetic': '', 'meaning': 'n. 名字（名，如 John）', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': '西方人名中 first name 排在前面，指"名"',
            'examples': [
                {'en': 'My first name is Tom.', 'zh': '我的名字叫汤姆。'},
                {'en': 'Please write your first name here.', 'zh': '请在这里写上你的名字。'},
            ],
        },
        'family name': {
            'phonetic': '', 'meaning': 'n. 姓，姓氏', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'family(家庭) + name(名字) → 家族的姓 → 姓氏',
            'examples': [
                {'en': 'Wang is my family name.', 'zh': '王是我的姓。'},
                {'en': 'In China, the family name comes first.', 'zh': '在中国，姓排在前面。'},
            ],
        },
        'answer the phone': {
            'phonetic': '', 'meaning': '接电话', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'answer(回应) + the phone(电话) → 接电话',
            'examples': [
                {'en': 'Please answer the phone, it is ringing.', 'zh': '请接一下电话，它在响。'},
                {'en': 'She was busy answering the phone.', 'zh': '她正忙着接电话。'},
            ],
        },
        "in one's +": {
            'phonetic': '', 'meaning': '在某人的……（中），如 in one\u2019s opinion 依某人看来', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': "in + 物主代词 + 名词，如 in my opinion 依我看来",
            'examples': [
                {'en': 'In my opinion, reading is very important.', 'zh': '在我看来，阅读非常重要。'},
                {'en': 'In his free time, he likes playing basketball.', 'zh': '在他空闲时，他喜欢打篮球。'},
            ],
        },
        'senior high': {
            'phonetic': '', 'meaning': 'n. 高中', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'senior(较高年级的) + high(高中) → 高中',
            'examples': [
                {'en': 'He studies in a senior high school.', 'zh': '他在一所高中上学。'},
                {'en': 'Senior high life is busy but meaningful.', 'zh': '高中生活忙碌而有意义。'},
            ],
        },
        'middle aged': {
            'phonetic': '', 'meaning': 'adj. 中年的', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'middle(中间) + aged(年纪的) → 中年的',
            'examples': [
                {'en': 'He is a middle-aged man.', 'zh': '他是个中年人。'},
                {'en': 'Middle-aged people should have regular check-ups.', 'zh': '中年人应该定期体检。'},
            ],
        },
        'junior high school': {
            'phonetic': '', 'meaning': 'n. 初中', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'junior(较低年级的) + high school(中学) → 初中',
            'examples': [
                {'en': 'I studied in a junior high school for three years.', 'zh': '我在一所初中学习了三年。'},
                {'en': 'She teaches English at a junior high school.', 'zh': '她在一所初中教英语。'},
            ],
        },
        'junior high': {
            'phonetic': '', 'meaning': 'n. 初中', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'junior high 是 junior high school 的简称，指"初中"',
            'examples': [
                {'en': 'He is a student in junior high.', 'zh': '他是一名初中生。'},
                {'en': 'Junior high is an important stage for learning.', 'zh': '初中是学习的重要阶段。'},
            ],
        },
        'senior high school': {
            'phonetic': '', 'meaning': 'n. 高中', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'senior(较高年级的) + high school(中学) → 高中',
            'examples': [
                {'en': 'She is studying in a senior high school.', 'zh': '她正在一所高中读书。'},
                {'en': 'Senior high school students work hard for the exam.', 'zh': '高中生为考试而努力。'},
            ],
        },
        'be senior to': {
            'phonetic': '', 'meaning': '比……年长；比……资历深', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'be senior to sb 表示"比某人年长/资历深"，to 后接比较对象',
            'examples': [
                {'en': 'He is senior to me in this company.', 'zh': '他在公司里资历比我深。'},
                {'en': 'She is three years senior to her brother.', 'zh': '她比她弟弟大三岁。'},
            ],
        },
        'graduate from': {
            'phonetic': '', 'meaning': 'v. 从……毕业', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'graduate(毕业) + from(从) → 从……毕业',
            'examples': [
                {'en': 'He graduated from a famous university.', 'zh': '他毕业于一所著名大学。'},
                {'en': 'She will graduate from college next year.', 'zh': '她明年将从大学毕业。'},
            ],
        },
        'run out of': {
            'phonetic': '', 'meaning': 'v. 用完，耗尽', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'run out(耗尽) + of → 用完某物',
            'examples': [
                {'en': 'We have run out of paper.', 'zh': '我们的纸用完了。'},
                {'en': 'The car ran out of gas on the way.', 'zh': '汽车在半路上没油了。'},
            ],
        },
        'in fact': {
            'phonetic': '', 'meaning': '事实上，实际上', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in fact 表示"事实上/实际上"，用于说明真实情况',
            'examples': [
                {'en': 'In fact, English is not so difficult.', 'zh': '事实上，英语并没有那么难。'},
                {'en': 'He looks young, but in fact he is forty.', 'zh': '他看起来年轻，但实际上他四十岁了。'},
            ],
        },
        'as a matter of fact': {
            'phonetic': '', 'meaning': '事实上，实际上', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'as a matter of fact 与 in fact 同义，表示"事实上"',
            'examples': [
                {'en': 'As a matter of fact, I knew the answer.', 'zh': '事实上，我早就知道答案了。'},
                {'en': 'As a matter of fact, he is not from Beijing.', 'zh': '事实上，他不是北京人。'},
            ],
        },
        'in theory': {
            'phonetic': '', 'meaning': '理论上，从理论上讲', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in theory 表示"理论上"，与 in practice(实际上)相对',
            'examples': [
                {'en': 'In theory, this plan should work.', 'zh': '理论上，这个计划应该可行。'},
                {'en': 'In theory, everyone is equal.', 'zh': '从理论上讲，人人平等。'},
            ],
        },
        'in advance': {
            'phonetic': '', 'meaning': '提前，预先', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in advance 表示"提前/预先"，如 book in advance(提前预订)',
            'examples': [
                {'en': 'Please book the tickets in advance.', 'zh': '请提前订票。'},
                {'en': 'You should prepare for the exam in advance.', 'zh': '你应该提前为考试做准备。'},
            ],
        },
        'in case': {
            'phonetic': '', 'meaning': '以防万一，万一；假如', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in case 表示"以防万一"，in case of 表示"如果发生"',
            'examples': [
                {'en': 'Take an umbrella in case it rains.', 'zh': '带把伞以防下雨。'},
                {'en': 'In case of fire, call 119.', 'zh': '如果发生火灾，拨打119。'},
            ],
        },
        'in detail': {
            'phonetic': '', 'meaning': '详细地', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in detail 表示"详细地"，相当于 in a detailed way',
            'examples': [
                {'en': 'Please explain the rules in detail.', 'zh': '请详细说明一下规则。'},
                {'en': 'He described the accident in detail.', 'zh': '他详细描述了这次事故。'},
            ],
        },
        'face to face': {
            'phonetic': '', 'meaning': '面对面地', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'face(脸) + to + face(脸) → 面对面',
            'examples': [
                {'en': 'They talked face to face.', 'zh': '他们面对面地交谈。'},
                {'en': 'We should communicate face to face sometimes.', 'zh': '我们有时应该面对面交流。'},
            ],
        },
        'in addition': {
            'phonetic': '', 'meaning': '此外，另外', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in addition 表示"此外"，in addition to 表示"除……之外"',
            'examples': [
                {'en': 'In addition, he is good at sports.', 'zh': '此外，他擅长运动。'},
                {'en': 'In addition to English, she learns French.', 'zh': '除了英语，她还学法语。'},
            ],
        },
        'in general': {
            'phonetic': '', 'meaning': '总的来说，一般来说', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in general 表示"总的来说/一般来说"',
            'examples': [
                {'en': 'In general, students like the new teacher.', 'zh': '总的来说，学生们喜欢这位新老师。'},
                {'en': 'In general, exercise is good for health.', 'zh': '一般来说，运动有益健康。'},
            ],
        },
        'in front of': {
            'phonetic': '', 'meaning': '在……前面', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in front of 表示"在……（外部）前面"，in the front of 表示"在……（内部）前部"',
            'examples': [
                {'en': 'There is a tree in front of the house.', 'zh': '房子前面有一棵树。'},
                {'en': 'He sits in front of the classroom.', 'zh': '他坐在教室的前面。'},
            ],
        },
        'in no time': {
            'phonetic': '', 'meaning': '立刻，马上，很快', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in no time 字面"没有时间"→ 表示"很快/立刻"',
            'examples': [
                {'en': 'The bus will come in no time.', 'zh': '公交车很快就到。'},
                {'en': 'He finished the work in no time.', 'zh': '他很快就把工作做完了。'},
            ],
        },
        'in particular': {
            'phonetic': '', 'meaning': '尤其，特别', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in particular 表示"尤其/特别"，相当于 especially',
            'examples': [
                {'en': 'I like sports, basketball in particular.', 'zh': '我喜欢运动，尤其是篮球。'},
                {'en': 'He cares about the environment in particular.', 'zh': '他尤其关注环境问题。'},
            ],
        },
        'at last': {
            'phonetic': '', 'meaning': '最后，终于', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'at last 表示"最后/终于"，用于长期等待后',
            'examples': [
                {'en': 'At last, we arrived at the station.', 'zh': '最后，我们终于到达了车站。'},
                {'en': 'He passed the exam at last.', 'zh': '他终于通过了考试。'},
            ],
        },
        'without any doubt': {
            'phonetic': '', 'meaning': '毫无疑问', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'without(没有) + doubt(怀疑) → 毫无疑问',
            'examples': [
                {'en': 'Without any doubt, she is the best student.', 'zh': '毫无疑问，她是最好的学生。'},
                {'en': 'He will win without any doubt.', 'zh': '他会毫无疑问地获胜。'},
            ],
        },
        'thrift store': {
            'phonetic': '', 'meaning': 'n. 旧货店，二手商店', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'thrift(节俭) + store(商店) → 卖旧货的店 → 旧货店',
            'examples': [
                {'en': 'She bought a book at the thrift store.', 'zh': '她在旧货店买了一本书。'},
                {'en': 'The thrift store sells cheap second-hand things.', 'zh': '这家旧货店出售便宜的二手物品。'},
            ],
        },
        'live in': {
            'phonetic': '', 'meaning': 'v. 居住在，住在', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'live(居住) + in(在……里) → 居住在',
            'examples': [
                {'en': 'I live in a small town.', 'zh': '我住在一个小镇上。'},
                {'en': 'They live in the countryside.', 'zh': '他们住在乡下。'},
            ],
        },
        'make friends': {
            'phonetic': '', 'meaning': 'v. 交朋友', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'make(交) + friends(朋友) → 交朋友，make friends with sb 与某人交朋友',
            'examples': [
                {'en': 'He is good at making friends.', 'zh': '他擅长交朋友。'},
                {'en': 'I want to make friends with new classmates.', 'zh': '我想和新同学交朋友。'},
            ],
        },
        'leave for': {
            'phonetic': '', 'meaning': 'v. 动身前往，出发去', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'leave(离开) + for(前往) → 动身前往某地',
            'examples': [
                {'en': 'We will leave for Shanghai tomorrow.', 'zh': '我们明天动身去上海。'},
                {'en': 'He left for Beijing early this morning.', 'zh': '他今天一早就出发去北京了。'},
            ],
        },
        'job hunting': {
            'phonetic': '', 'meaning': 'n. 找工作，求职', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'job(工作) + hunting(寻找) → 找工作',
            'examples': [
                {'en': 'He is busy with job hunting now.', 'zh': '他现在正忙着找工作。'},
                {'en': 'Job hunting is not easy for graduates.', 'zh': '对毕业生来说，找工作并不容易。'},
            ],
        },
        'learn from': {
            'phonetic': '', 'meaning': 'v. 向……学习；从……中学习', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'learn(学习) + from(从/向) → 向……学习',
            'examples': [
                {'en': 'We should learn from each other.', 'zh': '我们应该互相学习。'},
                {'en': 'Learn from your mistakes.', 'zh': '从你的错误中学习。'},
            ],
        },
        'keep away': {
            'phonetic': '', 'meaning': 'v. 远离，不靠近', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'keep(保持) + away(离开) → 保持距离 → 远离',
            'examples': [
                {'en': 'Please keep away from the fire.', 'zh': '请远离火源。'},
                {'en': 'Keep away from danger.', 'zh': '远离危险。'},
            ],
        },
        'bird flu': {
            'phonetic': '', 'meaning': 'n. 禽流感', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'bird(鸟) + flu(流感) → 禽流感',
            'examples': [
                {'en': 'Bird flu can spread among birds.', 'zh': '禽流感会在禽类中传播。'},
                {'en': 'We should eat well-cooked food to avoid bird flu.', 'zh': '我们应该吃煮熟的食品以防禽流感。'},
            ],
        },
        'where there is a will, there is a way': {
            'phonetic': '', 'meaning': '有志者事竟成', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'where(哪里) + there is(有) + a will(意志) → 有志者事竟成',
            'examples': [
                {'en': 'Where there is a will, there is a way.', 'zh': '有志者事竟成。'},
                {'en': 'Keep trying, for where there is a will, there is a way.', 'zh': '继续努力，因为有志者事竟成。'},
            ],
        },
        'compulsory course': {
            'phonetic': '', 'meaning': 'n. 必修课', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'compulsory(强制的) + course(课程) → 必修课',
            'examples': [
                {'en': 'English is a compulsory course in college.', 'zh': '英语是大学的一门必修课。'},
                {'en': 'Every student must take the compulsory courses.', 'zh': '每个学生都必须修读必修课。'},
            ],
        },
        'selective course': {
            'phonetic': '', 'meaning': 'n. 选修课', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'selective(选择的) + course(课程) → 选修课',
            'examples': [
                {'en': 'She chose a selective course on music.', 'zh': '她选了一门音乐选修课。'},
                {'en': 'Students can choose selective courses freely.', 'zh': '学生可以自由选择选修课。'},
            ],
        },
        'report card': {
            'phonetic': '', 'meaning': 'n. 成绩单', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'report(报告) + card(卡片) → 成绩单',
            'examples': [
                {'en': 'He got good grades on his report card.', 'zh': '他的成绩单上取得了好成绩。'},
                {'en': 'Parents look at the report card carefully.', 'zh': '家长会仔细看成绩单。'},
            ],
        },
        'skip classes': {
            'phonetic': '', 'meaning': 'v. 逃课，旷课', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'skip(跳过) + classes(课) → 逃课',
            'examples': [
                {'en': 'He should not skip classes.', 'zh': '他不应该逃课。'},
                {'en': 'Students who skip classes will be punished.', 'zh': '逃课的学生会受到处罚。'},
            ],
        },
        'in public': {
            'phonetic': '', 'meaning': '公开地，当众', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in public 表示"公开地/当众"，与 in private(私下)相对',
            'examples': [
                {'en': 'Don\u2019t speak loudly in public.', 'zh': '不要在公共场合大声说话。'},
                {'en': 'He praised her in public.', 'zh': '他当众表扬了她。'},
            ],
        },
        'compared with': {
            'phonetic': '', 'meaning': '与……相比', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'compared(比较) + with(和) → 与……相比',
            'examples': [
                {'en': 'Compared with last year, the price is higher.', 'zh': '与去年相比，价格更高了。'},
                {'en': 'Compared with him, I still have a lot to learn.', 'zh': '与他相比，我还有很多东西要学。'},
            ],
        },
        'for example': {
            'phonetic': '', 'meaning': '例如，比如', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'for example 表示"例如"，常缩写为 e.g.',
            'examples': [
                {'en': 'Many fruits are healthy, for example, apples.', 'zh': '很多水果很健康，例如苹果。'},
                {'en': 'For example, you can take a bus to school.', 'zh': '例如，你可以坐公交车去学校。'},
            ],
        },
        'civil war': {
            'phonetic': '', 'meaning': 'n. 内战', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'civil(国内的) + war(战争) → 内战',
            'examples': [
                {'en': 'The country suffered a long civil war.', 'zh': '这个国家经历了长期的内战。'},
                {'en': 'The civil war broke out in 1861.', 'zh': '内战于1861年爆发。'},
            ],
        },
        'cultural relics': {
            'phonetic': '', 'meaning': 'n. 文物，文化遗产', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'cultural(文化的) + relics(遗物) → 文物',
            'examples': [
                {'en': 'We should protect the cultural relics.', 'zh': '我们应该保护文物。'},
                {'en': 'These cultural relics are very precious.', 'zh': '这些文物非常珍贵。'},
            ],
        },
        'morning edition': {
            'phonetic': '', 'meaning': 'n. 晨报，早间版', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'morning(早晨) + edition(版本) → 晨报',
            'examples': [
                {'en': 'He reads the morning edition of the newspaper.', 'zh': '他读报纸的晨报版。'},
                {'en': 'The morning edition comes out at six.', 'zh': '晨报六点出版。'},
            ],
        },
        'evening edition': {
            'phonetic': '', 'meaning': 'n. 晚报，晚间版', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'evening(晚上) + edition(版本) → 晚报',
            'examples': [
                {'en': 'The evening edition has the latest news.', 'zh': '晚报刊登了最新消息。'},
                {'en': 'He bought the evening edition on his way home.', 'zh': '他在回家路上买了晚报。'},
            ],
        },
        'sleeping bag': {
            'phonetic': '', 'meaning': 'n. 睡袋', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'sleeping(睡觉) + bag(袋子) → 睡袋',
            'examples': [
                {'en': 'He brought a sleeping bag for the camp.', 'zh': '他为露营带了一个睡袋。'},
                {'en': 'You need a warm sleeping bag at night.', 'zh': '晚上你需要一个暖和的睡袋。'},
            ],
        },
        'by means of': {
            'phonetic': '', 'meaning': '通过……的方法，借助……', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'by means of 表示"通过/借助……的方式"',
            'examples': [
                {'en': 'We can learn English by means of listening.', 'zh': '我们可以通过听来学英语。'},
                {'en': 'He solved the problem by means of a computer.', 'zh': '他借助电脑解决了问题。'},
            ],
        },
        'departure gate': {
            'phonetic': '', 'meaning': 'n. 登机口，出发闸口', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'departure(出发) + gate(门) → 登机口',
            'examples': [
                {'en': 'Please go to Gate 8, the departure gate.', 'zh': '请前往8号登机口。'},
                {'en': 'The departure gate is near the shop.', 'zh': '登机口在商店附近。'},
            ],
        },
        'customs office': {
            'phonetic': '', 'meaning': 'n. 海关', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'customs(海关) + office(办公处) → 海关部门',
            'examples': [
                {'en': 'He had to go through the customs office.', 'zh': '他必须通过海关。'},
                {'en': 'The customs office checks the luggage.', 'zh': '海关检查行李。'},
            ],
        },
        'duty free': {
            'phonetic': '', 'meaning': 'adj. 免税的', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'duty(税) + free(免除) → 免税的',
            'examples': [
                {'en': 'She bought some duty-free goods at the airport.', 'zh': '她在机场买了一些免税商品。'},
                {'en': 'Duty-free shops are popular with travelers.', 'zh': '免税店很受旅客欢迎。'},
            ],
        },
        'free of charge': {
            'phonetic': '', 'meaning': '免费', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'free(免费的) + of charge(费用) → 免费',
            'examples': [
                {'en': 'The museum is free of charge on Sundays.', 'zh': '博物馆周日免费开放。'},
                {'en': 'The service is free of charge.', 'zh': '这项服务是免费的。'},
            ],
        },
        'go camping': {
            'phonetic': '', 'meaning': 'v. 去露营', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'go + camping(露营) → 去露营',
            'examples': [
                {'en': 'We went camping near the lake last weekend.', 'zh': '上周末我们去湖边露营了。'},
                {'en': 'They often go camping in summer.', 'zh': '他们夏天经常去露营。'},
            ],
        },
        'go hiking': {
            'phonetic': '', 'meaning': 'v. 去徒步，去远足', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'go + hiking(徒步) → 去远足',
            'examples': [
                {'en': 'We will go hiking in the mountains.', 'zh': '我们将去山里远足。'},
                {'en': 'Going hiking is good for health.', 'zh': '远足对健康有益。'},
            ],
        },
        'hot spring': {
            'phonetic': '', 'meaning': 'n. 温泉', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'hot(热的) + spring(泉水) → 温泉',
            'examples': [
                {'en': 'They relaxed in the hot spring.', 'zh': '他们在温泉里放松。'},
                {'en': 'The hot spring is good for the body.', 'zh': '温泉对身体有益。'},
            ],
        },
        'bungee jumping': {
            'phonetic': '', 'meaning': 'n. 蹦极', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'bungee(蹦极绳) + jumping(跳) → 蹦极',
            'examples': [
                {'en': 'Bungee jumping is an exciting sport.', 'zh': '蹦极是一项刺激的运动。'},
                {'en': 'He tried bungee jumping for the first time.', 'zh': '他第一次尝试了蹦极。'},
            ],
        },
        'be fit for': {
            'phonetic': '', 'meaning': 'v. 适合，适宜于', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'be fit for 表示"适合"，相当于 be suitable for',
            'examples': [
                {'en': 'He is fit for the job.', 'zh': '他适合这份工作。'},
                {'en': 'This water is not fit for drinking.', 'zh': '这水不适合饮用。'},
            ],
        },
        'cooperate with': {
            'phonetic': '', 'meaning': 'v. 与……合作', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'cooperate(合作) + with(和) → 与……合作',
            'examples': [
                {'en': 'We should cooperate with each other.', 'zh': '我们应该互相合作。'},
                {'en': 'The two companies cooperate with each other.', 'zh': '这两家公司互相合作。'},
            ],
        },
        'nursery school': {
            'phonetic': '', 'meaning': 'n. 幼儿园', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'nursery(托儿所) + school(学校) → 幼儿园',
            'examples': [
                {'en': 'The child goes to a nursery school.', 'zh': '这个孩子上幼儿园。'},
                {'en': 'Nursery school is important for children.', 'zh': '幼儿园对孩子们很重要。'},
            ],
        },
        'lung cancer': {
            'phonetic': '', 'meaning': 'n. 肺癌', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'lung(肺) + cancer(癌症) → 肺癌',
            'examples': [
                {'en': 'Smoking can cause lung cancer.', 'zh': '吸烟会导致肺癌。'},
                {'en': 'He gave up smoking to avoid lung cancer.', 'zh': '他戒烟以避免肺癌。'},
            ],
        },
        'be confronted with': {
            'phonetic': '', 'meaning': 'v. 面临，面对', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'confront(面对) 的被动式 → 面临',
            'examples': [
                {'en': 'We are confronted with many difficulties.', 'zh': '我们面临许多困难。'},
                {'en': 'He was confronted with a hard choice.', 'zh': '他面临一个艰难的选择。'},
            ],
        },
        'hand over': {
            'phonetic': '', 'meaning': 'v. 移交，交出', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'hand(递交) + over(过去) → 移交',
            'examples': [
                {'en': 'He handed over the keys to me.', 'zh': '他把钥匙交给了我。'},
                {'en': 'Please hand over the report to the manager.', 'zh': '请把报告交给经理。'},
            ],
        },
        'hot pot': {
            'phonetic': '', 'meaning': 'n. 火锅', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'hot(热的) + pot(锅) → 火锅',
            'examples': [
                {'en': 'We had hot pot together last night.', 'zh': '我们昨晚一起吃了火锅。'},
                {'en': 'Hot pot is popular in Chongqing.', 'zh': '火锅在重庆很受欢迎。'},
            ],
        },
        'french fries': {
            'phonetic': '', 'meaning': 'n. 炸薯条', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'French(法国的) + fries(油炸食品) → 炸薯条',
            'examples': [
                {'en': 'He likes eating French fries with ketchup.', 'zh': '他喜欢蘸番茄酱吃炸薯条。'},
                {'en': 'French fries are a popular fast food.', 'zh': '炸薯条是一种受欢迎的快餐。'},
            ],
        },
        'raw food': {
            'phonetic': '', 'meaning': 'n. 生食，生鲜食物', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'raw(生的) + food(食物) → 生食',
            'examples': [
                {'en': 'Some people prefer raw food.', 'zh': '有些人更喜欢吃生食。'},
                {'en': 'Raw food may carry bacteria.', 'zh': '生食可能携带细菌。'},
            ],
        },
        'tai chi': {
            'phonetic': '', 'meaning': 'n. 太极拳', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'tai chi 是"太极"的音译，指太极拳',
            'examples': [
                {'en': 'My grandfather practices tai chi every morning.', 'zh': '我爷爷每天早上打太极拳。'},
                {'en': 'Tai chi is good for the elderly.', 'zh': '太极拳对老年人有好处。'},
            ],
        },
        'world cup': {
            'phonetic': '', 'meaning': 'n. 世界杯', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'world(世界) + cup(杯) → 世界杯',
            'examples': [
                {'en': 'The World Cup is held every four years.', 'zh': '世界杯每四年举办一次。'},
                {'en': 'Many people watch the World Cup on TV.', 'zh': '许多人在电视上看世界杯。'},
            ],
        },
        'be filled with': {
            'phonetic': '', 'meaning': 'v. 充满，装满', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'be filled with 表示"充满"，相当于 be full of',
            'examples': [
                {'en': 'The room is filled with books.', 'zh': '房间里堆满了书。'},
                {'en': 'Her heart is filled with hope.', 'zh': '她的心中充满了希望。'},
            ],
        },
        'for the time being': {
            'phonetic': '', 'meaning': '暂时，眼下', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'for the time being 表示"暂时/眼下"',
            'examples': [
                {'en': 'For the time being, we can stay here.', 'zh': '暂时我们可以待在这里。'},
                {'en': 'This is enough for the time being.', 'zh': '眼下这些就够了。'},
            ],
        },
        'be absent from': {
            'phonetic': '', 'meaning': 'v. 缺席，不在', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'be absent from 表示"缺席"，absent(缺席的) + from',
            'examples': [
                {'en': 'He was absent from class yesterday.', 'zh': '他昨天上课缺席了。'},
                {'en': 'She is absent from school because of illness.', 'zh': '她因病没有上学。'},
            ],
        },
        'solar energy': {
            'phonetic': '', 'meaning': 'n. 太阳能', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'solar(太阳的) + energy(能量) → 太阳能',
            'examples': [
                {'en': 'Solar energy is clean and renewable.', 'zh': '太阳能是清洁且可再生的。'},
                {'en': 'People use solar energy to generate power.', 'zh': '人们利用太阳能发电。'},
            ],
        },
        'take away': {
            'phonetic': '', 'meaning': 'v. 带走；拿走；外卖', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'take(拿) + away(离开) → 带走，take-away 作名词指外卖',
            'examples': [
                {'en': 'Please take away the rubbish.', 'zh': '请把垃圾带走。'},
                {'en': 'We can order take-away food.', 'zh': '我们可以点外卖。'},
            ],
        },
        'take place': {
            'phonetic': '', 'meaning': 'v. 发生，举行', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'take place 表示"发生/举行"，不用于被动语态',
            'examples': [
                {'en': 'The meeting will take place tomorrow.', 'zh': '会议将在明天举行。'},
                {'en': 'Great changes have taken place in my hometown.', 'zh': '我的家乡发生了巨大的变化。'},
            ],
        },
        'take the place of': {
            'phonetic': '', 'meaning': 'v. 代替，取代', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'take(占) + the place(位置) + of → 取代……的位置',
            'examples': [
                {'en': 'Computers have taken the place of typewriters.', 'zh': '电脑已经取代了打字机。'},
                {'en': 'Who will take the place of the manager?', 'zh': '谁将接替经理？'},
            ],
        },
        'take pride in': {
            'phonetic': '', 'meaning': 'v. 以……为自豪，为……感到骄傲', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'take pride(自豪) in → 以……为豪，相当于 be proud of',
            'examples': [
                {'en': 'She takes pride in her work.', 'zh': '她为自己的工作感到自豪。'},
                {'en': 'We take pride in our school.', 'zh': '我们为学校感到骄傲。'},
            ],
        },
        'hydropower station': {
            'phonetic': '', 'meaning': 'n. 水电站', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'hydropower(水力发电) + station(站) → 水电站',
            'examples': [
                {'en': 'A new hydropower station was built on the river.', 'zh': '河上新建了一座水电站。'},
                {'en': 'The hydropower station supplies electricity to the town.', 'zh': '这座水电站为小镇供电。'},
            ],
        },
        'power failure': {
            'phonetic': '', 'meaning': 'n. 停电，断电', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'power(电力) + failure(故障) → 停电',
            'examples': [
                {'en': 'There was a power failure in our area.', 'zh': '我们这一带停电了。'},
                {'en': 'The power failure lasted two hours.', 'zh': '停电持续了两个小时。'},
            ],
        },
        'electric fan': {
            'phonetic': '', 'meaning': 'n. 电风扇', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'electric(电的) + fan(扇子) → 电风扇',
            'examples': [
                {'en': 'It is hot, please turn on the electric fan.', 'zh': '天很热，请打开电风扇。'},
                {'en': 'The electric fan is on the table.', 'zh': '电风扇在桌子上。'},
            ],
        },
        'online shopping': {
            'phonetic': '', 'meaning': 'n. 网上购物', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'online(在线的) + shopping(购物) → 网上购物',
            'examples': [
                {'en': 'Online shopping is becoming more and more popular.', 'zh': '网上购物越来越受欢迎。'},
                {'en': 'She does online shopping once a week.', 'zh': '她每周网购一次。'},
            ],
        },
        'log in': {
            'phonetic': '', 'meaning': 'v. 登录，登入', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'log in 表示"登录"，log(记录) + in，反义词 log out(退出)',
            'examples': [
                {'en': 'Please log in with your account.', 'zh': '请用你的账号登录。'},
                {'en': 'He logged in to check his email.', 'zh': '他登录查看邮件。'},
            ],
        },
        'return ticket': {
            'phonetic': '', 'meaning': 'n. 往返票', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'return(返回) + ticket(票) → 往返票',
            'examples': [
                {'en': 'He bought a return ticket to Beijing.', 'zh': '他买了一张去北京的往返票。'},
                {'en': 'A return ticket is cheaper than two single tickets.', 'zh': '往返票比两张单程票便宜。'},
            ],
        },
        'single ticket': {
            'phonetic': '', 'meaning': 'n. 单程票', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'single(单程的) + ticket(票) → 单程票',
            'examples': [
                {'en': 'I only need a single ticket.', 'zh': '我只需要一张单程票。'},
                {'en': 'A single ticket costs ten yuan.', 'zh': '单程票价十元。'},
            ],
        },
        'shop assistant': {
            'phonetic': '', 'meaning': 'n. 售货员，店员', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'shop(商店) + assistant(助手) → 店员',
            'examples': [
                {'en': 'The shop assistant is very friendly.', 'zh': '那位售货员很友好。'},
                {'en': 'Ask the shop assistant for help.', 'zh': '请店员帮忙。'},
            ],
        },
        'in cash': {
            'phonetic': '', 'meaning': '用现金，付现款', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in cash 表示"用现金"，与 by card(刷卡)相对',
            'examples': [
                {'en': 'Can I pay in cash?', 'zh': '我能用现金付款吗？'},
                {'en': 'He paid for the goods in cash.', 'zh': '他用现金付了货款。'},
            ],
        },
        'reception desk': {
            'phonetic': '', 'meaning': 'n. 前台，接待处', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'reception(接待) + desk(柜台) → 前台',
            'examples': [
                {'en': 'Please go to the reception desk for a key.', 'zh': '请到前台取钥匙。'},
                {'en': 'The reception desk is on the first floor.', 'zh': '前台在一楼。'},
            ],
        },
        'all of a sudden': {
            'phonetic': '', 'meaning': '突然，猛地', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'all of a sudden 表示"突然"，相当于 suddenly',
            'examples': [
                {'en': 'All of a sudden, it began to rain.', 'zh': '突然下起雨来。'},
                {'en': 'He stood up all of a sudden.', 'zh': '他突然站了起来。'},
            ],
        },
        'crime rate': {
            'phonetic': '', 'meaning': 'n. 犯罪率', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'crime(犯罪) + rate(比率) → 犯罪率',
            'examples': [
                {'en': 'The crime rate in this city is falling.', 'zh': '这座城市的犯罪率正在下降。'},
                {'en': 'Better education can lower the crime rate.', 'zh': '更好的教育能降低犯罪率。'},
            ],
        },
        'fall in love with': {
            'phonetic': '', 'meaning': 'v. 爱上，与……相爱', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'fall(坠入) + in love(爱) + with → 爱上',
            'examples': [
                {'en': 'He fell in love with the city at first sight.', 'zh': '他对这座城市一见钟情。'},
                {'en': 'They fell in love with each other.', 'zh': '他们彼此相爱了。'},
            ],
        },
        'come across': {
            'phonetic': '', 'meaning': 'v. 偶遇，碰到；无意中发现', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'come(来) + across(横过) → 偶然遇到',
            'examples': [
                {'en': 'I came across an old friend in the street.', 'zh': '我在街上偶遇一位老朋友。'},
                {'en': 'He came across a useful book in the library.', 'zh': '他在图书馆无意中发现了一本有用的书。'},
            ],
        },
        'by accident': {
            'phonetic': '', 'meaning': '偶然地，意外地', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'by accident 表示"偶然/意外"，相当于 by chance',
            'examples': [
                {'en': 'I found the key by accident.', 'zh': '我偶然找到了钥匙。'},
                {'en': 'He broke the window by accident.', 'zh': '他意外打碎了窗户。'},
            ],
        },
        'be composed of': {
            'phonetic': '', 'meaning': 'v. 由……组成', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'compose(组成) 的被动式 → 由……组成，相当于 consist of',
            'examples': [
                {'en': 'Water is composed of hydrogen and oxygen.', 'zh': '水由氢和氧组成。'},
                {'en': 'The team is composed of ten students.', 'zh': '这个团队由十名学生组成。'},
            ],
        },
        'consist of': {
            'phonetic': '', 'meaning': 'v. 由……组成，包括', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'consist(组成) + of → 由……组成，不用于被动语态',
            'examples': [
                {'en': 'The class consists of thirty students.', 'zh': '这个班由三十名学生组成。'},
                {'en': 'A healthy diet consists of fresh food.', 'zh': '健康的饮食由新鲜食物组成。'},
            ],
        },
        'soap opera': {
            'phonetic': '', 'meaning': 'n. 肥皂剧', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'soap(肥皂) + opera(剧) → 肥皂剧（因早期由肥皂商赞助）',
            'examples': [
                {'en': 'She likes watching soap operas.', 'zh': '她喜欢看肥皂剧。'},
                {'en': 'The soap opera is on at eight.', 'zh': '这部肥皂剧八点播出。'},
            ],
        },
        'see to it that': {
            'phonetic': '', 'meaning': '务必使……，确保', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'see to it that 表示"务必/确保"，相当于 make sure that',
            'examples': [
                {'en': 'See to it that you finish your homework on time.', 'zh': '务必按时完成作业。'},
                {'en': 'See to it that the door is locked.', 'zh': '确保门已锁好。'},
            ],
        },
        "take one's temperature": {
            'phonetic': '', 'meaning': 'v. 量体温', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': "take(测) + one's + temperature(体温) → 量体温",
            'examples': [
                {'en': 'The nurse took his temperature.', 'zh': '护士给他量了体温。'},
                {'en': 'Please take your temperature first.', 'zh': '请先量一下体温。'},
            ],
        },
        'make preparations for': {
            'phonetic': '', 'meaning': 'v. 为……做准备', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'make preparations(准备) for → 为……做准备',
            'examples': [
                {'en': 'We are making preparations for the exam.', 'zh': '我们正在为考试做准备。'},
                {'en': 'They made preparations for the trip.', 'zh': '他们为旅行做了准备。'},
            ],
        },
        'name list': {
            'phonetic': '', 'meaning': 'n. 名单', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'name(名字) + list(名单) → 名单',
            'examples': [
                {'en': 'Please check your name on the name list.', 'zh': '请在名单上核对你的名字。'},
                {'en': 'The name list is on the wall.', 'zh': '名单挂在墙上。'},
            ],
        },
        'in no way': {
            'phonetic': '', 'meaning': '决不，绝不', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'in no way 表示"决不"，相当于 not at all',
            'examples': [
                {'en': 'In no way will I give up.', 'zh': '我决不会放弃。'},
                {'en': 'He is in no way to blame.', 'zh': '决不该怪他。'},
            ],
        },
        'from time to time': {
            'phonetic': '', 'meaning': '不时，偶尔', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'from time to time 表示"不时/偶尔"，相当于 sometimes',
            'examples': [
                {'en': 'He visits his grandparents from time to time.', 'zh': '他偶尔去看望祖父母。'},
                {'en': 'From time to time, she writes to her friends.', 'zh': '她不时给朋友写信。'},
            ],
        },
        'some time': {
            'phonetic': '', 'meaning': '一段时间', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'some(一些) + time(时间) → 一段时间；注意与 sometime(某个时候)区分',
            'examples': [
                {'en': 'I need some time to think it over.', 'zh': '我需要一些时间来考虑。'},
                {'en': 'He stayed there for some time.', 'zh': '他在那里待了一段时间。'},
            ],
        },
        'by no means': {
            'phonetic': '', 'meaning': '决不，绝不', 'type': '短语',
            'split': [], 'morph': [],
            'mnemonic': 'by no means 表示"决不"，与 in no way 同义',
            'examples': [
                {'en': 'This is by no means an easy task.', 'zh': '这绝不是一项容易的任务。'},
                {'en': 'He is by no means a lazy student.', 'zh': '他绝不是个懒惰的学生。'},
            ],
        },
    }

    def __init__(self):
        """初始化本地词典服务"""
        pass

    def _get_inflections(self, word_lower, meaning=''):
        """
        获取单词的变形数据，统一存入 tenses 字段
        - 动词：时态变形（base/third_singular/past/past_participle/present_participle）
        - 名词：复数变形（singular/plural）
        - 形容词：级变化（positive/comparative/superlative）
        有什么变形返回什么，没有返回 None
        """
        import re as _re

        # 1. 动词时态
        if word_lower in self.VERB_TENSES:
            t = self.VERB_TENSES[word_lower].copy()
            t['inflection_type'] = 'tense'
            return t

        # 2. 名词复数（不规则）
        if word_lower in self.NOUN_PLURALS:
            return {
                'singular': word_lower,
                'plural': self.NOUN_PLURALS[word_lower],
                'inflection_type': 'plural',
            }

        # 3. 形容词比较级/最高级（不规则）
        if word_lower in self.ADJ_DEGREES:
            d = self.ADJ_DEGREES[word_lower]
            return {
                'positive': word_lower,
                'comparative': d['comparative'],
                'superlative': d['superlative'],
                'inflection_type': 'degree',
            }

        # 检测词性：兼容 ECDICT 的 a.(形容词)、r.(副词) 前缀
        meaning_stripped = (meaning or '').strip()
        is_noun = meaning_stripped.lower().startswith('n.')
        is_adj = meaning_stripped.lower().startswith('adj.') or meaning_stripped.lower().startswith('a.')
        is_verb = _re.match(r'^(v|vi|vt|aux)\.', meaning_stripped.lower()) is not None

        # 4. 规则名词复数（以辅音字母+y结尾，变y为i加es；以s/x/ch/sh结尾加es；其他加s）
        if is_noun:
            if word_lower.endswith('y') and len(word_lower) > 1 and word_lower[-2] not in 'aeiou':
                plural = word_lower[:-1] + 'ies'
                return {'singular': word_lower, 'plural': plural, 'inflection_type': 'plural'}
            elif word_lower.endswith(('s', 'x', 'ch', 'sh')):
                plural = word_lower + 'es'
                return {'singular': word_lower, 'plural': plural, 'inflection_type': 'plural'}
            elif not word_lower.endswith('s'):
                plural = word_lower + 's'
                return {'singular': word_lower, 'plural': plural, 'inflection_type': 'plural'}

        # 5. 规则形容词比较级/最高级（单音节词）
        if is_adj:
            # 以 e 结尾：加 r/st
            if len(word_lower) <= 5 and word_lower.endswith('e'):
                return {
                    'positive': word_lower,
                    'comparative': word_lower + 'r',
                    'superlative': word_lower + 'st',
                    'inflection_type': 'degree',
                }
            # 辅音+短元音+辅音结尾的双写（如 big → bigger → biggest）
            elif len(word_lower) == 3 and word_lower[0] not in 'aeiou' and word_lower[1] in 'aeiou' and word_lower[2] not in 'aeiou':
                return {
                    'positive': word_lower,
                    'comparative': word_lower + word_lower[-1] + 'er',
                    'superlative': word_lower + word_lower[-1] + 'est',
                    'inflection_type': 'degree',
                }
            # 其他短词：加 er/est
            elif len(word_lower) <= 5 and not word_lower.endswith('e'):
                return {
                    'positive': word_lower,
                    'comparative': word_lower + 'er',
                    'superlative': word_lower + 'est',
                    'inflection_type': 'degree',
                }

        # 6. 规则动词时态（以常见动词后缀判断）
        if is_verb and word_lower not in self.VERB_TENSES:
            # 以 e 结尾：加 d
            if word_lower.endswith('e'):
                return {
                    'base': word_lower,
                    'third_singular': word_lower + 's',
                    'past': word_lower + 'd',
                    'past_participle': word_lower + 'd',
                    'present_participle': word_lower[:-1] + 'ing',
                    'inflection_type': 'tense',
                }
            # 辅音+短元音+辅音结尾的双写（如 run → running）
            elif len(word_lower) >= 3 and word_lower[-1] not in 'aeiou' and word_lower[-2] in 'aeiou' and word_lower[-3] not in 'aeiou' and word_lower[-1] not in 'wxy':
                return {
                    'base': word_lower,
                    'third_singular': word_lower + 's',
                    'past': word_lower + word_lower[-1] + 'ed',
                    'past_participle': word_lower + word_lower[-1] + 'ed',
                    'present_participle': word_lower + word_lower[-1] + 'ing',
                    'inflection_type': 'tense',
                }
            # 以辅音+y结尾：变y为i加ed
            elif word_lower.endswith('y') and len(word_lower) > 1 and word_lower[-2] not in 'aeiou':
                return {
                    'base': word_lower,
                    'third_singular': word_lower[:-1] + 'ies',
                    'past': word_lower[:-1] + 'ied',
                    'past_participle': word_lower[:-1] + 'ied',
                    'present_participle': word_lower + 'ing',
                    'inflection_type': 'tense',
                }
            # 一般情况：加 ed/ing
            else:
                return {
                    'base': word_lower,
                    'third_singular': word_lower + 's',
                    'past': word_lower + 'ed',
                    'past_participle': word_lower + 'ed',
                    'present_participle': word_lower + 'ing',
                    'inflection_type': 'tense',
                }

        # 5b. 多音节形容词比较级/最高级（more/most），保证形容词都有变形按钮
        if is_adj and len(word_lower) > 5:
            return {
                'positive': word_lower,
                'comparative': f'more {word_lower}',
                'superlative': f'the most {word_lower}',
                'inflection_type': 'degree',
            }

        return None

    # 频率副词（用于例句语法安全：放在句首/动词前，避免错误位置）
    FREQ_ADVERBS = {
        'sometimes', 'usually', 'often', 'always', 'never', 'sometimes', 'seldom',
        'rarely', 'frequently', 'occasionally', 'forever', 'always', 'generally',
        'normally', 'typically', 'hardly', 'ever', 'twice', 'once',
    }
    # 复数名词（例句需用复数be动词/there be，避免 "This children is"）
    PLURAL_NOUNS = {
        'children', 'people', 'men', 'women', 'feet', 'teeth', 'mice', 'geese',
        'oxen', 'elves', 'leaves', 'knives', 'lives', 'goods', 'clothes',
        'trousers', 'scissors', 'glasses', 'sunglasses', 'data', 'media',
    }

    def _get_zhuanshenben_examples(self, word, meaning=''):
        """
        获取专升本例句：优先从专门例句库中查找，没有则根据词性用语法安全的模板生成。

        模板做了语法安全设计：
          - 名词：复数名词用 "These ... are"，单数用 "This ... is"；并避免 "This children is"。
          - 副词：频率副词（sometimes/forever 等）放在句首或动词前，避免错误位置。
          - 动词：用不定式/祈使式，避免第三人称单数变化错误。
          - 代词（somebody/everybody 等）用专门模板，避免 "This somebody is"。

        返回:
            list: 例句列表 [{en, zh}, ...]，可能为空
        """
        word_lower = word.lower().strip()

        # 1. 先查专门的专升本例句库
        if word_lower in self.ZHUANSHENBEN_EXAMPLES:
            return self.ZHUANSHENBEN_EXAMPLES[word_lower]

        # 2. 尝试去掉复数/时态后缀再查
        if word_lower.endswith('s') and word_lower[:-1] in self.ZHUANSHENBEN_EXAMPLES:
            return self.ZHUANSHENBEN_EXAMPLES[word_lower[:-1]]
        if word_lower.endswith('ing') and word_lower[:-3] in self.ZHUANSHENBEN_EXAMPLES:
            return self.ZHUANSHENBEN_EXAMPLES[word_lower[:-3]]
        if word_lower.endswith('ed') and word_lower[:-2] in self.ZHUANSHENBEN_EXAMPLES:
            return self.ZHUANSHENBEN_EXAMPLES[word_lower[:-2]]

        # 3. 没有专门例句，根据词性用模板生成
        import re
        meaning_str = (meaning or '').strip()
        meaning_lower = meaning_str.lower()
        pos = None
        # 检测词性前缀（兼容 ECDICT 的 vi./vt./a./pl. 等格式）
        if re.match(r'^(v|vi|vt|aux|link)\.', meaning_lower) or re.match(r'^(v|vi|vt|aux)\s', meaning_lower):
            pos = 'verb'
        elif re.match(r'^(n|pl)\.', meaning_lower) or re.match(r'^(n|pl)\s', meaning_lower):
            pos = 'noun'
        elif re.match(r'^(adj|a)\.', meaning_lower) or re.match(r'^adj\s', meaning_lower):
            pos = 'adj'
        elif re.match(r'^(adv|ad)\.', meaning_lower) or re.match(r'^adv\s', meaning_lower):
            pos = 'adv'
        elif re.match(r'^(pron|pron)\.', meaning_lower) or re.match(r'^pron\s', meaning_lower):
            pos = 'pron'
        elif re.match(r'^(prep|conj)\.', meaning_lower):
            pos = 'other'

        # 4. 如果释义没有标准词性前缀，尝试从单词后缀推断
        if not pos:
            # 复数名词（children/people/常见+s）优先判为名词，避免被"en"等动词后缀误导
            if word_lower in self.PLURAL_NOUNS or word_lower.endswith('s') and not word_lower.endswith(('ss', 'us', 'is', 'ous')):
                pos = 'noun'
            elif word_lower.endswith(('ful', 'ous', 'ive', 'able', 'ible', 'al', 'less', 'ish', 'ic', 'ant', 'ent', 'ary', 'ory')):
                pos = 'adj'
            elif word_lower.endswith(('tion', 'sion', 'ment', 'ness', 'ity', 'ship', 'hood', 'ance', 'ence', 'dom', 'ism', 'ist', 'age')):
                pos = 'noun'
            elif word_lower.endswith(('ly', 'ward', 'wise')):
                pos = 'adv'
            elif word_lower.endswith(('ize', 'ise', 'ify', 'ate')):
                pos = 'verb'
            else:
                # 默认按名词处理（最常见的词性）
                pos = 'noun'

        # 代词（somebody/everybody/anything 等）使用专门模板
        if word_lower in ('somebody', 'everybody', 'anybody', 'nobody', 'someone',
                          'everyone', 'anyone', 'something', 'everything', 'anything', 'nothing'):
            return [
                {'en': f'Everyone should help {word_lower} in need.', 'zh': '每个人都应该帮助需要帮助的人。'},
                {'en': f'{word_lower.capitalize()} can make a difference in our daily life.',
                 'zh': '每个人都能在日常生活的某方面产生影响。'},
            ]

        # 频率副词使用专门模板（避免 "sometimes in class" 的错误位置）
        if pos == 'adv' and word_lower in self.FREQ_ADVERBS:
            return [
                {'en': f'{word_lower.capitalize()}, I read English books in the morning.',
                 'zh': '有时，我早上会读英语书。'},
                {'en': f'We should study hard {word_lower} to pass the exam.',
                 'zh': '我们应该经常努力学习以通过考试。'},
            ]

        # 复数名词使用复数模板（避免 "This children is"）
        if pos == 'noun' and (word_lower in self.PLURAL_NOUNS or
                              (word_lower.endswith('s') and not word_lower.endswith(('ss', 'us', 'is', 'ous')))):
            pos = 'noun_plural'

        if pos and pos in self.EXAMPLE_TEMPLATES:
            # 提取中文释义（去掉词性前缀、括号注释，只取第一条释义）
            zh_meaning = meaning_str
            # 只取第一行（ECDICT 多词性释义用换行分隔）
            zh_meaning = zh_meaning.split('\n')[0].strip()
            # 去掉所有词性前缀（包括缩写和完整形式：adj./adjective./vi./vt. 等）
            zh_meaning = re.sub(r'^(adjective|adverb|noun|verb|vi|vt|aux|pl|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\.\s*', '', zh_meaning, flags=re.IGNORECASE)
            zh_meaning = re.sub(r'^(adjective|adverb|noun|verb|vi|vt|aux|pl|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\s+', '', zh_meaning, flags=re.IGNORECASE)
            # 去掉方括号注释如 [体] [法] [医]
            zh_meaning = re.sub(r'\[.*?\]', '', zh_meaning)
            # 去掉圆括号注释如 (书名)
            zh_meaning = re.sub(r'（.*?）', '', zh_meaning)
            zh_meaning = re.sub(r'\(.*?\)', '', zh_meaning)
            # 只取第一条释义（分号或逗号分隔）
            zh_meaning = re.split(r'[;；,，]', zh_meaning)[0].strip()
            # 如果释义是纯英文（没有中文字符），说明是英文定义泄露，用单词本身代替
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in zh_meaning)
            if not has_chinese:
                zh_meaning = word_lower
            # 形容词去掉尾部的"的"，避免模板中出现"好的的人"
            if pos == 'adj' and zh_meaning.endswith('的'):
                zh_meaning = zh_meaning[:-1]
            # 副词去掉尾部的"地"，避免模板中出现"安静地地发言"
            if pos == 'adv' and zh_meaning.endswith('地'):
                zh_meaning = zh_meaning[:-1]
            # 去掉首尾多余空格和标点
            zh_meaning = zh_meaning.strip('，,。 ') or word_lower

            templates = self.EXAMPLE_TEMPLATES[pos]
            examples = []
            for tpl in templates:
                examples.append({
                    'en': tpl['en'].replace('{word}', word_lower),
                    'zh': tpl['zh'].replace('{word}', word_lower).replace('{zh}', zh_meaning),
                })
            return examples

        return []

    # 模板例句特征字符串，用于检测低质量模板生成的例句
    TEMPLATE_PATTERNS = [
        'I usually {word} in the morning',
        'It is important to {word} every day',
        'She wants to {word} her English skills',
        'This {word} is very important to us',
        'I learned a lot from this {word}',
        'The {word} has changed our lives',
        'She is a very {word} person',
        'This book is very {word}',
        'The weather today is quite {word}',
        'He spoke {word} at the meeting',
        'She always listens {word} in class',
    ]

    def is_template_examples(self, examples):
        """检测例句是否是模板生成的低质量例句"""
        if not examples:
            return True
        try:
            if isinstance(examples, str):
                import json as _json
                ex_list = _json.loads(examples)
            else:
                ex_list = examples
            if not ex_list or not isinstance(ex_list, list):
                return True
            for ex in ex_list:
                en = ex.get('en', '') if isinstance(ex, dict) else ''
                # 检查是否包含模板特征
                for pattern in self.TEMPLATE_PATTERNS:
                    # 去掉 {word} 占位符，用通配匹配
                    check = pattern.replace('{word}', '')
                    parts = check.split('{word}') if '{word}' in pattern else [check]
                    if all(p in en for p in parts if p.strip()):
                        return True
                # 检查所有例句是否结构完全相同（只是单词不同）
            return False
        except Exception:
            return True

    def _fetch_online_examples(self, word):
        """
        从在线词典API获取真实例句
        使用 free dictionary API (dictionaryapi.dev)
        """
        word_lower = word.lower().strip()
        try:
            resp = requests.get(
                f'https://api.dictionaryapi.dev/api/v2/entries/en/{word_lower}',
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    examples = []
                    for entry in data:
                        for meaning in entry.get('meanings', []):
                            for defn in meaning.get('definitions', []):
                                example = defn.get('example', '')
                                if example and len(example) > 10:
                                    # 英文例句，需要翻译中文
                                    examples.append({
                                        'en': example,
                                        'zh': '',  # 在线API不提供中文翻译
                                    })
                                if len(examples) >= 3:
                                    break
                            if len(examples) >= 3:
                                break
                        if len(examples) >= 3:
                            break
                    # 只返回有中文翻译的例句（在线API没有中文翻译，所以通常返回空）
                    # 但如果例句足够简单，我们可以用简单翻译
                    return []  # 暂时不使用在线例句（没有中文翻译）
        except Exception as e:
            print(f'[dict] online examples fail({word}): {e}')
        return []


    def _query_ecdict(self, word):
        """查询 ECDICT 词典数据库，返回完整词条数据"""
        conn = self._ecdict
        if not conn:
            return None
        try:
            cur = conn.execute(
                'SELECT word, phonetic, definition, translation, pos, exchange, tag, collins, oxford FROM stardict WHERE word = ? COLLATE NOCASE',
                (word,)
            )
            row = cur.fetchone()
            if row:
                return dict(row)
        except Exception as e:
            print(f'[ecdict] query error({word}): {e}')
        return None

    def get_similar_words(self, word, limit=5):
        """
        从 ECDICT 词典中获取与目标词拼写相近的单词（用于选择题干扰项）
        策略：优先取与目标词共享前缀的词（前2-4个字母相同则大概率形近），
        其次是长度相近的词。返回 [{word, meaning}, ...]，每条释义来自 ECDICT。
        若 ECDICT 不可用或命中不足，返回可用的部分（调用方负责兜底）。
        """
        conn = self._ecdict
        if not conn:
            return []
        target = (word or '').lower().strip()
        if not target or len(target) < 3:
            return []

        # 取目标词的前2-4个字符作为前缀，优先匹配形近词
        prefixes = []
        for n in (4, 3, 2):
            if len(target) >= n:
                prefixes.append(target[:n])
        # 也尝试后缀匹配（如 -tion 结尾的词）
        suffixes = []
        for n in (3, 4):
            if len(target) >= n:
                suffixes.append(target[-n:])

        results = []
        seen = set()
        import re as _re
        try:
            for pref in prefixes:
                # 共享前缀：word LIKE 'pref%'，长度在目标词 ±2 范围内
                cur = conn.execute(
                    'SELECT word, translation FROM stardict '
                    'WHERE word LIKE ? COLLATE NOCASE '
                    'AND translation IS NOT NULL AND translation != "" '
                    'AND length(word) BETWEEN ? AND ? '
                    'ORDER BY length(word) LIMIT 60',
                    (pref + '%', max(3, len(target) - 2), len(target) + 2)
                )
                for row in cur.fetchall():
                    w = (row['word'] or '').strip().lower()
                    if not w or w == target or w in seen:
                        continue
                    # 过滤非真实词（缩写/代号/含数字或符号）
                    if not _re.match(r'^[a-z][a-z\-]*$', w):
                        continue
                    if len(w) < 3:
                        continue
                    meaning = self._clean_meaning(row['translation'] or '', '')
                    if not meaning:
                        continue
                    seen.add(w)
                    results.append({'word': w, 'meaning': meaning})
                    if len(results) >= limit:
                        return results
            # 前缀不足时，尝试后缀匹配
            for suf in suffixes:
                cur = conn.execute(
                    'SELECT word, translation FROM stardict '
                    'WHERE word LIKE ? COLLATE NOCASE '
                    'AND translation IS NOT NULL AND translation != "" '
                    'AND length(word) BETWEEN ? AND ? '
                    'ORDER BY length(word) LIMIT 60',
                    ('%' + suf, max(3, len(target) - 2), len(target) + 2)
                )
                for row in cur.fetchall():
                    w = (row['word'] or '').strip().lower()
                    if not w or w == target or w in seen:
                        continue
                    if not _re.match(r'^[a-z][a-z\-]*$', w):
                        continue
                    if len(w) < 3:
                        continue
                    meaning = self._clean_meaning(row['translation'] or '', '')
                    if not meaning:
                        continue
                    seen.add(w)
                    results.append({'word': w, 'meaning': meaning})
                    if len(results) >= limit:
                        return results
        except Exception as e:
            print(f'[ecdict] 获取形近词失败({word}): {e}')
        return results

    def _is_real_word(self, word, ecdict_data):
        """
        判断 ECDICT 中的词条是否是真正的英语单词（而非缩写/代号）
        用于过滤如 "ss"（[计]子系统）这类不应作为词根的条目
        """
        if not ecdict_data or not ecdict_data.get('translation'):
            return False
        word_lower = word.lower().strip()
        # 1. 太短的词（少于3个字母）大概率不是独立单词，除非是常见短词
        common_short = {'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it',
                        'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we', 'am',
                        'ox', 'ax', 'ex', 'ad', 'ed', 'oh', 'ok', 'ah', 'hi', 'lo', 'pi'}
        if len(word_lower) < 3 and word_lower not in common_short:
            return False
        # 2. 翻译以方括号开头（如 [计] [医] [化]），说明是专业缩写
        translation = ecdict_data.get('translation', '')
        if translation.strip().startswith('['):
            # 但如果方括号后面有正常中文释义，可能是真实词条
            import re
            bracket_removed = re.sub(r'^\[.*?\]', '', translation).strip()
            if not bracket_removed or not any('\u4e00' <= c <= '\u9fff' for c in bracket_removed[:10]):
                return False
        # 3. 没有音标且词长<=4，可能是缩写（真实单词通常有音标）
        phonetic = ecdict_data.get('phonetic', '') or ''
        if not phonetic and len(word_lower) <= 4:
            return False
        # 4. pos 字段为空且翻译以方括号开头，是缩写
        pos = ecdict_data.get('pos', '') or ''
        if not pos and translation.strip().startswith('['):
            return False
        return True

    def _convert_phonetic(self, phonetic):
        """将 ECDICT 音标编码转换为标准 IPA 格式"""
        if not phonetic:
            return ''
        result = phonetic
        result = result.replace(':', '\u02d0')  # long vowel mark ː
        result = result.replace("'", '\u02c8')   # primary stress ˈ
        result = result.replace(',', '\u02cc')   # secondary stress ˌ
        return '/' + result + '/'

    def _clean_meaning(self, translation, pos_field=''):
        """
        精简 ECDICT 释义：只保留专升本最常考的1-2条释义，常用词性优先
        ECDICT translation 格式：用换行分隔不同词性的释义
        ECDICT pos 字段格式如 "v:5/n:95" 表示动词5%名词95%，用于确定主词性
        过滤纯英文行、专业术语
        """
        if not translation:
            return ''
        import re as _re
        # 按换行分割
        lines = translation.strip().split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 去除行内方括号注释如 [体] [法] [网]
            line = _re.sub(r'\[.*?\]', '', line).strip()
            if not line:
                continue
            # 跳过纯英文行（没有中文字符的行是英文定义）
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in line)
            if not has_chinese:
                continue
            clean_lines.append(line)

        if not clean_lines:
            return ''

        # 解析 ECDICT pos 字段，获取词性频率（如 "v:5/n:95" → {n:95, v:5}）
        pos_freq = {}
        if pos_field:
            for item in pos_field.split('/'):
                if ':' in item:
                    code, freq = item.split(':', 1)
                    try:
                        pos_freq[code.strip()] = int(freq.strip())
                    except ValueError:
                        pass

        # 词性优先级：如果有 pos 频率数据，按频率排序；否则默认 名词 > 动词 > 形容词 > 副词
        # 对于专升本考试，大多数核心词是名词（如 pressure, nerve, culture, development）
        def _pos_code(line):
            low = line.lower().strip()
            if low.startswith('adj.') or low.startswith('a.'):
                return 'j'
            if low.startswith('vi.') or low.startswith('vt.') or low.startswith('v.') or low.startswith('aux.'):
                return 'v'
            if low.startswith('n.'):
                return 'n'
            if low.startswith('adv.') or low.startswith('ad.') or low.startswith('r.'):
                return 'r'
            return 'o'

        def _pos_priority(line):
            code = _pos_code(line)
            if pos_freq:
                # 有频率数据：按频率降序排（频率高的词性排前面）
                return -pos_freq.get(code, 0)
            # 无频率数据：名词优先（专升本核心词多为名词），然后动词、形容词、副词
            order = {'n': 0, 'v': 1, 'j': 2, 'r': 3, 'o': 4}
            return order.get(code, 4)

        clean_lines.sort(key=_pos_priority)

        # 精简释义：按词性分组，合并同词性重复行，输出考试向精简释义。
        # 目标：合并 "adv. 有时\nadv. 时常" → "adv. 有时，时常"，
        #       合并 "vt. 结束\nvt. 作结论" → "vt. 作结论，结束"（按频率排序）。
        # 最多保留 2 个词性组，每组最多 3 个释义，避免重复和碎片化。
        pos_groups = {}  # pos_code -> {'prefix': std_prefix, 'meanings': [...]}
        for line in clean_lines:
            pos_match = _re.match(r'^([a-z]+\.)\s*', line.lower())
            pos_prefix = pos_match.group(1) if pos_match else ''
            code = _pos_code(line)
            # 词性前缀标准化：ECDICT 用 a./r. 等缩写，统一转为 adj./adv. 等标准形式
            pos_std = pos_prefix
            if pos_prefix == 'a.':
                pos_std = 'adj.'
            elif pos_prefix in ('r.', 'ad.'):
                pos_std = 'adv.'
            content = _re.sub(r'^[a-z]+\.\s*', '', line)
            parts = _re.split(r'[;；,，]', content)
            candidates = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # 过滤过长的释义（超过15个字的专业术语）
                if len(part) > 15:
                    continue
                skip = False
                for marker in ['人名', '地名', '药名', '网络用语']:
                    if part == marker or part.startswith(marker):
                        skip = True
                        break
                # 单字标记（化/生/医/网/药）只在释义恰好等于该字时过滤
                if part in ('化', '生', '医', '网', '药', '体', '法', '计'):
                    skip = True
                if skip:
                    continue
                candidates.append(part)
            # 优先选择2字及以上的释义；如果全部都是单字，则取第一个
            multi_char = [c for c in candidates if len(c) >= 2]
            chosen = multi_char if multi_char else (candidates[:1] if candidates else [])
            for part in chosen:
                g = pos_groups.setdefault(code, {'prefix': pos_std, 'meanings': []})
                if part not in g['meanings']:
                    g['meanings'].append(part)

        if not pos_groups:
            return clean_lines[0][:40]

        # 词性组排序：有 pos 频率数据按频率降序，否则 名词>动词>形容词>副词>其他
        def _group_priority(code):
            if pos_freq:
                return -pos_freq.get(code, 0)
            order = {'n': 0, 'v': 1, 'j': 2, 'r': 3, 'o': 4}
            return order.get(code, 4)

        ordered_codes = sorted(pos_groups.keys(), key=_group_priority)
        meanings = []
        for code in ordered_codes[:2]:
            g = pos_groups[code]
            # 同一词性内，优先多字释义（更贴近考试释义），再按出现顺序
            parts = g['meanings'][:3]
            joined = '，'.join(parts)
            if g['prefix']:
                meanings.append(f"{g['prefix']} {joined}")
            else:
                meanings.append(joined)

        return '\n'.join(meanings) if meanings else clean_lines[0][:40]

    def _parse_exchange(self, exchange_str):
        """
        解析 ECDICT exchange 字段为结构化变形数据
        格式: 0:lemma/1:form_type/p:past_form/d:pp_form/i:ing_form/3:3rd_form/s:plural/r:comparative/t:superlative
        0: 表示原形（lemma），1: 表示当前词的变形类型
        p/d/i/3/s/r/t: 表示该原形的各种变形形式
        """
        if not exchange_str:
            return {}
        result = {}
        for part in exchange_str.split('/'):
            if ':' in part:
                key, value = part.split(':', 1)
                result[key] = value
        return result

    def _build_tenses_from_exchange(self, word, exchange):
        """从 ECDICT exchange 字段构建时态/变形数据"""
        if not exchange:
            return None
        # 动词时态：检查是否有 p(过去式)/d(过去分词)/i(现在分词)/3(三单) 字段
        has_verb_forms = any(k in exchange for k in ('p', 'd', 'i', '3'))
        if has_verb_forms:
            return {
                'base': word,
                'third_singular': exchange.get('3', ''),
                'past': exchange.get('p', ''),
                'past_participle': exchange.get('d', ''),
                'present_participle': exchange.get('i', ''),
                'inflection_type': 'tense',
            }
        # 名词复数
        if 's' in exchange:
            return {
                'singular': word,
                'plural': exchange.get('s', ''),
                'inflection_type': 'plural',
            }
        # 形容词比较级/最高级
        if 'r' in exchange or 't' in exchange:
            return {
                'positive': word,
                'comparative': exchange.get('r', ''),
                'superlative': exchange.get('t', ''),
                'inflection_type': 'degree',
            }
        return None

    def _is_common_ecdict_word(self, word, conn, allow_inflection=True):
        """
        判断一个词是否足够常用（用于复合词拆解质量控制，避免把生僻词拆解得支离破碎）。
        常用定义：ECDICT 有中文释义，且 BNC 词频排名 <= 5000（BNC 越小越常用），
        且释义中不含网络/专业/人名地名/外来语等生僻标记。
        若本身不是常用词，则尝试识别其常用原词的复数/时态变形（如 times→time, studies→study）。
        返回 (is_common, base_word)；base_word 为识别出的常用原形。
        """
        rare_markers = ['[网络]', '[机]', '[法]', '[医]', '[化]', '[生]', '[药]', '[俗]',
                        '[人名]', '[地名]', '[数]', '[物]', '[经]', '[无]', '[军]', '[林]']
        try:
            r = conn.execute(
                'SELECT bnc, translation FROM stardict WHERE word = ? COLLATE NOCASE AND translation IS NOT NULL AND translation != ""',
                (word,)
            ).fetchone()
        except Exception:
            r = None
        if r:
            t = r['translation'] or ''
            if any(m in t for m in rare_markers):
                return False, word
            if not any('\u4e00' <= c <= '\u9fff' for c in t):
                return False, word
            bnc = r['bnc']
            if bnc is not None and bnc <= 5000:
                return True, word
        # 尝试识别变形：复数/第三人称/过去式/现在分词 → 常用原词
        if allow_inflection and len(word) > 3:
            candidates = []
            if word.endswith('ies') and len(word) > 4:
                candidates.append(word[:-3] + 'y')
            elif word.endswith('es') and len(word) > 4:
                candidates.append(word[:-2])
            elif word.endswith('s') and not word.endswith('ss'):
                candidates.append(word[:-1])
            if word.endswith('ed') and len(word) > 4:
                candidates.append(word[:-2])
            if word.endswith('ing') and len(word) > 5:
                candidates.append(word[:-3])
                candidates.append(word[:-3] + 'e')
            for cand in candidates:
                ok, base = self._is_common_ecdict_word(cand, conn, allow_inflection=False)
                if ok:
                    return True, cand
        return False, word

    def _try_compound_split(self, word):
        """
        第一层拆解：尝试将单词拆分为两个已知高频独立单词（复合词检测）
        例如: basketball -> basket + ball, sometimes -> some + times(time的复数)
        质量控制：两部分至少3字符，且都必须是常用词（BNC 词频靠前、含中文释义、
        非网络/专业/生僻词），否则视为无意义拆分并放弃复合词拆解，交给词缀分析。
        """
        conn = self._ecdict
        if not conn:
            return None
        best = None
        best_score = -1
        for i in range(3, len(word) - 2):
            part1 = word[:i]
            part2 = word[i:]
            if len(part1) < 3 or len(part2) < 3:
                continue
            # 任一部分是已知前缀/后缀，不是复合词
            if part1 in self.PREFIXES or part2 in self.SUFFIXES or part1 in self.SUFFIXES or part2 in self.PREFIXES:
                continue
            ok1, base1 = self._is_common_ecdict_word(part1, conn)
            ok2, base2 = self._is_common_ecdict_word(part2, conn)
            if not (ok1 and ok2):
                continue
            # 评分：两部分都是原形（非变形）的复合词更标准，其次总长度越长越好
            score = len(part1) + len(part2)
            if base1 == part1 and base2 == part2:
                score += 100
            if score > best_score:
                best_score = score
                best = (part1, part2, base1, base2)
        if best is None:
            return None
        part1, part2, base1, base2 = best

        def _part_entry(part, base):
            bd = self._query_ecdict(base)
            bm = self._clean_meaning(bd.get('translation', ''), bd.get('pos', '')) if bd else ''
            bm = bm.split('\n')[0][:60] if bm else base
            if base != part:
                return {
                    'part': part,
                    'meaning': bm,
                    'original': base,
                    'original_meaning': bm,
                    'transform': f'是"{base}"的变形',
                    'explain': f'"{base}"的变形形式',
                }
            return {
                'part': part,
                'meaning': bm,
                'original': part,
                'original_meaning': bm,
                'transform': '原形不变',
                'explain': '独立单词',
            }

        return [_part_entry(part1, base1), _part_entry(part2, base2)]

    # 复合词精确拆解覆盖表（用户更看重"按单词拆解"）
    # ECDICT 把某些常见复合词标为某词的变形（如 sometimes 是 sometime 的复数），
    # 但按单词拆解对背单词更有帮助，故在此覆盖：
    # value 为拆解列表，每项 {part, base, meaning, transform, explain}
    COMPOUND_SPLITS = {
        'sometimes': [
            {'part': 'some', 'base': 'some', 'meaning': 'adj/adv. 一些，大约', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'times', 'base': 'time', 'meaning': 'n. 时间', 'transform': '是"time"的复数', 'explain': '"time"的复数形式（多次）'},
        ],
        'everyday': [
            {'part': 'every', 'base': 'every', 'meaning': 'adj. 每个的', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'day', 'base': 'day', 'meaning': 'n. 天，日子', 'transform': '原形不变', 'explain': '独立单词'},
        ],
        'everybody': [
            {'part': 'every', 'base': 'every', 'meaning': 'adj. 每个的', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'body', 'base': 'body', 'meaning': 'n. 身体', 'transform': '原形不变', 'explain': '独立单词（every+body=每个人）'},
        ],
        'anything': [
            {'part': 'any', 'base': 'any', 'meaning': 'pron. 任何', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'thing', 'base': 'thing', 'meaning': 'n. 东西，事物', 'transform': '原形不变', 'explain': '独立单词（any+thing=任何东西）'},
        ],
        'nothing': [
            {'part': 'no', 'base': 'no', 'meaning': 'adj. 没有', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'thing', 'base': 'thing', 'meaning': 'n. 东西，事物', 'transform': '原形不变', 'explain': '独立单词（no+thing=没有东西）'},
        ],
        'everything': [
            {'part': 'every', 'base': 'every', 'meaning': 'adj. 每个的', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'thing', 'base': 'thing', 'meaning': 'n. 东西，事物', 'transform': '原形不变', 'explain': '独立单词'},
        ],
        'someone': [
            {'part': 'some', 'base': 'some', 'meaning': 'adj/adv. 一些', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'one', 'base': 'one', 'meaning': 'num. 一个', 'transform': '原形不变', 'explain': '独立单词（some+one=某人）'},
        ],
        'somebody': [
            {'part': 'some', 'base': 'some', 'meaning': 'adj/adv. 一些', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'body', 'base': 'body', 'meaning': 'n. 身体', 'transform': '原形不变', 'explain': '独立单词（some+body=某人）'},
        ],
        'nobody': [
            {'part': 'no', 'base': 'no', 'meaning': 'adj. 没有', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'body', 'base': 'body', 'meaning': 'n. 身体', 'transform': '原形不变', 'explain': '独立单词（no+body=没有人）'},
        ],
        'anybody': [
            {'part': 'any', 'base': 'any', 'meaning': 'pron. 任何', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'body', 'base': 'body', 'meaning': 'n. 身体', 'transform': '原形不变', 'explain': '独立单词（any+body=任何人）'},
        ],
        'without': [
            {'part': 'with', 'base': 'with', 'meaning': 'prep. 和，随着', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'out', 'base': 'out', 'meaning': 'adv. 在外', 'transform': '原形不变', 'explain': '独立单词（with+out=没有）'},
        ],
        'throughout': [
            {'part': 'through', 'base': 'through', 'meaning': 'prep. 穿过，通过', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'out', 'base': 'out', 'meaning': 'adv. 在外', 'transform': '原形不变', 'explain': '独立单词（through+out=遍及，贯穿）'},
        ],
        'understand': [
            {'part': 'under', 'base': 'under', 'meaning': 'prep. 在……之下', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'stand', 'base': 'stand', 'meaning': 'v. 站立', 'transform': '原形不变', 'explain': '独立单词（under+stand=理解）'},
        ],
        'forever': [
            {'part': 'for', 'base': 'for', 'meaning': 'prep. 为了', 'transform': '原形不变', 'explain': '独立单词'},
            {'part': 'ever', 'base': 'ever', 'meaning': 'adv. 曾经', 'transform': '原形不变', 'explain': '独立单词（for+ever=永远）'},
        ],
        'friendship': [
            {'part': 'friend', 'base': 'friend', 'meaning': 'n. 朋友', 'transform': '原形不变', 'explain': '词根'},
            {'part': '-ship', 'base': 'ship', 'meaning': 'n. 关系，状态（ship后缀）', 'transform': '本身是后缀', 'explain': '名词后缀，表示关系'},
        ],
    }

    # 自动复合词表：词义透明、确属两个单词合成的复合词。
    # 与 COMPOUND_SPLITS 不同，这里不手工写每部分的释义，而是运行时从 ECDICT 自动取。
    # 值 = (part1, part2)，如 weekday → (week, day)。
    # 只收录"词义确实由两部分合成"的复合词，避免 "knowledge→know+ledge" 这类误导性拆分。
    AUTO_COMPOUNDS = {
        'weekday': ('week', 'day'),
        'weekend': ('week', 'end'),
        'afternoon': ('after', 'noon'),
        'nightmare': ('night', 'mare'),
        'forefather': ('fore', 'father'),
        'policymaker': ('policy', 'maker'),
        'daydream': ('day', 'dream'),
        'newspaper': ('news', 'paper'),
        'riverside': ('river', 'side'),
        'riverbank': ('river', 'bank'),
        'landscape': ('land', 'scape'),
        'hardware': ('hard', 'ware'),
        'software': ('soft', 'ware'),
        'microwave': ('micro', 'wave'),
        'volleyball': ('volley', 'ball'),
        'honeymoon': ('honey', 'moon'),
        'bridegroom': ('bride', 'groom'),
        'hydropower': ('hydro', 'power'),
        'fisherman': ('fisher', 'man'),
        'headache': ('head', 'ache'),
        'toothache': ('tooth', 'ache'),
        'stomachache': ('stomach', 'ache'),
        'hairstyle': ('hair', 'style'),
        'forehead': ('fore', 'head'),
        'bulletproof': ('bullet', 'proof'),
        'parachute': ('para', 'chute'),
        'e-commerce': ('e', 'commerce'),
        'high-tech': ('high', 'tech'),
        'fat-free': ('fat', 'free'),
        'well-educated': ('well', 'educated'),
        'second-hand': ('second', 'hand'),
        'full-time': ('full', 'time'),
        'part-time': ('part', 'time'),
        'semi-final': ('semi', 'final'),
        'baby-proofing': ('baby', 'proofing'),
        'bad-tempered': ('bad', 'tempered'),
        'quick-tempered': ('quick', 'tempered'),
        'grown-up': ('grown', 'up'),
        'sunrise': ('sun', 'rise'),
        'sunset': ('sun', 'set'),
        'moonlight': ('moon', 'light'),
        'sunlight': ('sun', 'light'),
        'hometown': ('home', 'town'),
        'homeland': ('home', 'land'),
        'homework': ('home', 'work'),
        'housework': ('house', 'work'),
        'classroom': ('class', 'room'),
        'bedroom': ('bed', 'room'),
        'bathroom': ('bath', 'room'),
        'toothpaste': ('tooth', 'paste'),
        'toothbrush': ('tooth', 'brush'),
        'sunglasses': ('sun', 'glasses'),
        'basketball': ('basket', 'ball'),
        'football': ('foot', 'ball'),
        'baseball': ('base', 'ball'),
        'headmaster': ('head', 'master'),
        'girlfriend': ('girl', 'friend'),
        'boyfriend': ('boy', 'friend'),
        'earthquake': ('earth', 'quake'),
        'rainfall': ('rain', 'fall'),
        'waterfall': ('water', 'fall'),
        'dragonfly': ('dragon', 'fly'),
        'butterfly': ('butter', 'fly'),
        'firework': ('fire', 'work'),
        'playground': ('play', 'ground'),
        'snowman': ('snow', 'man'),
        'snowball': ('snow', 'ball'),
        'eyesight': ('eye', 'sight'),
        'chairman': ('chair', 'man'),
        'spokesman': ('spokes', 'man'),
        'businessman': ('business', 'man'),
    }

    def _build_auto_compound(self, word_lower):
        """按 AUTO_COMPOUNDS 自动构建复合词拆解（释义从 ECDICT 自动取）"""
        p1, p2 = self.AUTO_COMPOUNDS[word_lower]
        out = []
        for part in (p1, p2):
            bd = self._query_ecdict(part)
            bm = self._clean_meaning(bd.get('translation', ''), bd.get('pos', '')) if bd else ''
            bm = bm.split('\n')[0][:40] if bm else part
            out.append({
                'part': part,
                'meaning': bm,
                'original': part,
                'original_meaning': bm,
                'transform': '原形不变',
                'explain': '独立单词',
            })
        return out

    def _build_curated_compound(self, word_lower):
        """按 COMPOUND_SPLITS 覆盖表构建复合词拆解结果"""
        parts = self.COMPOUND_SPLITS[word_lower]
        split = []
        for p in parts:
            meaning = p.get('meaning') or p['base']
            split.append({
                'part': p['part'],
                'meaning': meaning,
                'original': p['base'],
                'original_meaning': meaning,
                'transform': p.get('transform', '原形不变'),
                'explain': p.get('explain', '独立单词'),
            })
        return split

    def _fallback_compound_meaning(self, word_lower):
        """复合词兜底释义：当 ECDICT 无释义时，用简单释义保证有词义"""
        fallback = {
            'sometimes': 'adv. 有时，偶尔',
            'everyday': 'adj. 每天的，日常的',
            'everybody': 'pron. 每个人，人人',
            'anything': 'pron. 任何东西，任何事情',
            'nothing': 'pron. 没有什么，没有东西',
            'everything': 'pron. 一切，所有事物',
            'someone': 'pron. 某人，有人',
            'somebody': 'pron. 某人，有人',
            'nobody': 'pron. 没有人，无人',
            'anybody': 'pron. 任何人',
            'without': 'prep. 没有，缺乏',
            'throughout': 'prep. 遍及，贯穿',
            'understand': 'v. 理解，明白，懂得',
            'forever': 'adv. 永远，永久',
            'friendship': 'n. 友谊，友情',
        }
        return fallback.get(word_lower, f'{word_lower}（复合词）')

    def _pos_label(self, pos_raw):
        """把 ECDICT 词性代码（如 'n:100'）转为中文词性标签"""
        if not pos_raw:
            return ''
        pos_code = str(pos_raw).split(':')[0]
        pos_map = {
            'n': '名词', 'v': '动词', 'j': '形容词', 'r': '副词',
            'p': '介词', 'c': '连词', 'u': '代词', 'i': '感叹词',
            'a': '形容词', 'x': '助动词',
        }
        return pos_map.get(pos_code, '')

    def _decompose_with_ecdict(self, word, ecdict_data):
        """
        三层拆解逻辑（核心方法）：
        第一层：复合词拆解（如 basketball → basket + ball）
        第二层：变形词拆解（如 running → run + 现在分词变形）
        第三层：派生词拆解（如 unhappiness → un + happy + ness）
        如果都不能拆解，返回基础词信息
        """
        word_lower = word.lower().strip()
        # 0. 复合词精确覆盖表优先：按单词拆解（如 sometimes → some + times）
        if word_lower in self.COMPOUND_SPLITS:
            meaning = self.MEANING_OVERRIDES.get(word_lower) or \
                self._clean_meaning(ecdict_data.get('translation', ''), ecdict_data.get('pos', ''))
            return {
                'phonetic': self._convert_phonetic(ecdict_data.get('phonetic', '')),
                'meaning': meaning,
                'type': '复合词',
                'split': self._build_curated_compound(word_lower),
                'morph': [],
                'mnemonic': f'"{word_lower}" 由两部分组成，按单词拆解更易记忆。',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': None,
                'pos_label': self._pos_label(ecdict_data.get('pos', '')),
            }
        # 0b. 自动复合词表：词义透明的复合词按单词拆解（如 weekday → week + day）
        if word_lower in self.AUTO_COMPOUNDS:
            meaning = self.MEANING_OVERRIDES.get(word_lower) or \
                self._clean_meaning(ecdict_data.get('translation', ''), ecdict_data.get('pos', ''))
            return {
                'phonetic': self._convert_phonetic(ecdict_data.get('phonetic', '')),
                'meaning': meaning,
                'type': '复合词',
                'split': self._build_auto_compound(word_lower),
                'morph': [],
                'mnemonic': f'"{word_lower}" 由两个单词组成，按单词拆解更易记忆。',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': self._get_inflections(word_lower, meaning),
                'pos_label': self._pos_label(ecdict_data.get('pos', '')),
            }
        exchange = self._parse_exchange(ecdict_data.get('exchange', ''))
        pos_raw = ecdict_data.get('pos', '') or ''
        # 优先使用专升本释义覆盖表
        if word_lower in self.MEANING_OVERRIDES:
            translation = self.MEANING_OVERRIDES[word_lower]
        else:
            translation = self._clean_meaning(ecdict_data.get('translation', ''), pos_raw)
        phonetic = self._convert_phonetic(ecdict_data.get('phonetic', ''))

        # 解析词性标签（如 "n:100" → "名词"）
        pos_label = ''
        if pos_raw:
            pos_code = pos_raw.split(':')[0]
            pos_map = {
                'n': '名词', 'v': '动词', 'j': '形容词', 'r': '副词',
                'p': '介词', 'c': '连词', 'u': '代词', 'i': '感叹词',
                'a': '形容词', 'x': '助动词',
            }
            pos_label = pos_map.get(pos_code, '')

        # ===== 第二层：变形词拆解 =====
        # exchange 中有 0:lemma/1:type 表示当前词是某个原词的变形
        if '0' in exchange and '1' in exchange:
            lemma = exchange['0']
            form_type = exchange['1']
            form_desc = {
                'p': '过去式', 'd': '过去分词', 'i': '现在分词/动名词',
                '3': '第三人称单数', 's': '复数形式',
                'r': '比较级', 't': '最高级',
            }
            transform = form_desc.get(form_type, '变形')

            # 查询原词的释义
            lemma_data = self._query_ecdict(lemma)
            lemma_translation = self._clean_meaning(lemma_data.get('translation', ''), lemma_data.get('pos', '')) if lemma_data else ''
            lemma_phonetic = self._convert_phonetic(lemma_data.get('phonetic', '')) if lemma_data else ''

            # 查询原词的完整变形信息：优先用内置不规则变形表
            tenses = None
            if lemma_data:
                tenses = self._get_inflections(lemma, lemma_translation)
                if not tenses:
                    lemma_exchange = self._parse_exchange(lemma_data.get('exchange', ''))
                    tenses = self._build_tenses_from_exchange(lemma, lemma_exchange)
            # 若原词无变形（如意外形容词），尝试对当前词本身生成变形（如比较级/复数）
            if not tenses:
                tenses = self._get_inflections(word_lower, translation)

            meaning = translation or f'{lemma}的{transform}'

            split = [{
                'part': word_lower,
                'meaning': meaning,
                'original': lemma,
                'original_meaning': lemma_translation or meaning,
                'transform': transform,
                'explain': f'是"{lemma}"的{transform}',
            }]

            # 如果原词也有释义，添加原词信息
            if lemma_translation and lemma != word_lower:
                split.append({
                    'part': lemma,
                    'meaning': lemma_translation,
                    'original': lemma,
                    'original_meaning': lemma_translation,
                    'transform': '原形',
                    'explain': '原词',
                })

            return {
                'phonetic': phonetic,
                'meaning': meaning,
                'type': '变形词',
                'split': split,
                'morph': [],
                'mnemonic': f'"{word_lower}"是"{lemma}"的{transform}',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': tenses,
                'pos_label': pos_label,
            }

        # ===== 前置检查：如果词有明显前缀且词根是已知词，优先走派生词拆解 =====
        skip_compound = False
        for prefix in sorted(self.PREFIXES.keys(), key=len, reverse=True):
            if word_lower.startswith(prefix) and len(word_lower) > len(prefix) + 2:
                candidate_root = word_lower[len(prefix):]
                root_check = self._query_ecdict(candidate_root)
                if self._is_real_word(candidate_root, root_check):
                    skip_compound = True
                    break
                # 也检查去后缀后的词根（如 unhappiness → un + happi + ness → happy）
                for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
                    if candidate_root.endswith(suffix) and len(candidate_root) > len(suffix) + 1:
                        inner_root = candidate_root[:-len(suffix)]
                        if inner_root != word_lower:
                            inner_check = self._query_ecdict(inner_root)
                            if self._is_real_word(inner_root, inner_check):
                                skip_compound = True
                                break
                        # y/i 变体检查 (happy → happi)
                        if inner_root and inner_root + 'y' != word_lower:
                            y_check = self._query_ecdict(inner_root + 'y')
                            if self._is_real_word(inner_root + 'y', y_check):
                                skip_compound = True
                                break
                if skip_compound:
                    break

        # ===== 前置检查B：如果词有明显后缀且去掉后缀后是已知词，也跳过复合词拆解 =====
        # 如 development → develop + ment，应走派生词拆解而非复合词拆解
        if not skip_compound:
            for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
                if word_lower.endswith(suffix) and len(word_lower) > len(suffix) + 2:
                    candidate_root = word_lower[:-len(suffix)]
                    root_check = self._query_ecdict(candidate_root)
                    if self._is_real_word(candidate_root, root_check):
                        skip_compound = True
                        break
                    # y/i 变体检查 (happi → happy)
                    if candidate_root and len(candidate_root) >= 2 and candidate_root[-1] == 'i':
                        y_check = self._query_ecdict(candidate_root[:-1] + 'y')
                        if self._is_real_word(candidate_root[:-1] + 'y', y_check):
                            skip_compound = True
                            break
                    # e 结尾检查 (mak → make)
                    if candidate_root and not candidate_root.endswith('e'):
                        e_check = self._query_ecdict(candidate_root + 'e')
                        if self._is_real_word(candidate_root + 'e', e_check):
                            skip_compound = True
                            break

        # ===== 第一层：复合词拆解（仅当没有明显前缀/后缀词根时）=====
        compound = None
        if not skip_compound:
            compound = self._try_compound_split(word_lower)
        if compound:
            # 复合词也可能有变形，优先用内置不规则变形表
            tenses = self._get_inflections(word_lower, translation)
            if not tenses:
                tenses = self._build_tenses_from_exchange(word_lower, exchange)
            return {
                'phonetic': phonetic,
                'meaning': translation,
                'type': '复合词',
                'split': compound,
                'morph': [],
                'mnemonic': '',
                'examples': self._get_zhuanshenben_examples(word_lower, translation),
                'tenses': tenses,
                'pos_label': pos_label,
            }

        # ===== 第三层：派生词拆解（前缀/后缀分析）=====
        detected_prefix = None
        detected_root = word_lower
        detected_suffix = None
        final_root = word_lower

        # 检测前缀
        for prefix in sorted(self.PREFIXES.keys(), key=len, reverse=True):
            if word_lower.startswith(prefix) and len(word_lower) > len(prefix) + 2:
                candidate = word_lower[len(prefix):]
                # 检查去掉前缀后的词是否是已知单词（如 rediscover → discover）
                candidate_data = self._query_ecdict(candidate)
                if self._is_real_word(candidate, candidate_data):
                    detected_prefix = prefix
                    detected_root = candidate
                    final_root = candidate
                    break
                # 如果去掉前缀后的词不是已知单词，尝试进一步去后缀
                for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
                    if candidate.endswith(suffix) and len(candidate) > len(suffix) + 1:
                        inner = candidate[:-len(suffix)]
                        # 检查 inner 是否是已知单词
                        inner_data = self._query_ecdict(inner)
                        if self._is_real_word(inner, inner_data):
                            detected_prefix = prefix
                            detected_root = candidate
                            detected_suffix = suffix
                            final_root = inner
                            break
                        # y/i 变体检查: happi → happy
                        if inner and len(inner) >= 2 and inner[-1] == 'i':
                            y_candidate = inner[:-1] + 'y'
                            y_data = self._query_ecdict(y_candidate)
                            if self._is_real_word(y_candidate, y_data):
                                detected_prefix = prefix
                                detected_root = candidate
                                detected_suffix = suffix
                                final_root = y_candidate
                                break
                        # e 结尾检查: mak → make
                        if inner and not inner.endswith('e'):
                            e_candidate = inner + 'e'
                            e_data = self._query_ecdict(e_candidate)
                            if self._is_real_word(e_candidate, e_data):
                                detected_prefix = prefix
                                detected_root = candidate
                                detected_suffix = suffix
                                final_root = e_candidate
                                break
                if detected_prefix:
                    break

        # 如果没有检测到前缀，仅检测后缀
        if not detected_prefix:
            for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
                if word_lower.endswith(suffix) and len(word_lower) > len(suffix) + 1:
                    candidate = word_lower[:-len(suffix)]
                    # 检查去掉后缀后的词是否是已知单词
                    candidate_data = self._query_ecdict(candidate)
                    if candidate_data and candidate_data.get('translation'):
                        detected_suffix = suffix
                        detected_root = candidate
                        final_root = candidate
                        break
                    # y/i 变体检查: happi → happy
                    if candidate and len(candidate) >= 2 and candidate[-1] == 'i':
                        y_candidate = candidate[:-1] + 'y'
                        y_data = self._query_ecdict(y_candidate)
                        if y_data and y_data.get('translation'):
                            detected_suffix = suffix
                            final_root = y_candidate
                            break
                    # 双写辅音检查: runn → run
                    if candidate and len(candidate) >= 2 and candidate[-1] == candidate[-2]:
                        short_candidate = candidate[:-1]
                        short_data = self._query_ecdict(short_candidate)
                        if short_data and short_data.get('translation'):
                            detected_suffix = suffix
                            final_root = short_candidate
                            break
                    # e 结尾检查: mak → make
                    if candidate and not candidate.endswith('e'):
                        e_candidate = candidate + 'e'
                        e_data = self._query_ecdict(e_candidate)
                        if e_data and e_data.get('translation'):
                            detected_suffix = suffix
                            final_root = e_candidate
                            break

        word_type = '基础词'
        morph = []
        split = []

        if (detected_prefix or detected_suffix) and final_root and final_root != word_lower:
            word_type = '派生词'

            # 查询词根的释义
            root_data = self._query_ecdict(final_root)
            root_meaning = self._clean_meaning(root_data.get('translation', ''), root_data.get('pos', '')) if root_data else ''

            # 确定变形描述
            transform_desc = '原形不变'
            if final_root != detected_root:
                # 词根经过变形（如 y→i, 双写, 去 e）
                if final_root.endswith('y') and detected_root.endswith('i'):
                    transform_desc = '把 y 改成 i'
                elif len(final_root) > 0 and len(detected_root) > 0 and final_root + detected_root[-1] == detected_root:
                    transform_desc = '双写词尾辅音字母'
                elif final_root.endswith('e') and not detected_root.endswith('e'):
                    transform_desc = '去掉词尾 e'

            if root_meaning:
                split.append({
                    'part': final_root,
                    'meaning': root_meaning,
                    'original': final_root,
                    'original_meaning': root_meaning,
                    'transform': transform_desc,
                    'explain': '词根',
                })
                morph.insert(0, {
                    'type': 'root',
                    'word': final_root,
                    'meaning': root_meaning.split('\n')[0][:30],
                })
            else:
                split.append({
                    'part': final_root,
                    'meaning': '词根',
                    'original': final_root,
                    'original_meaning': '词根',
                    'transform': transform_desc,
                    'explain': '词根',
                })
                morph.insert(0, {
                    'type': 'root',
                    'word': final_root,
                    'meaning': '词根',
                })

            if detected_prefix:
                prefix_meaning = self.PREFIXES[detected_prefix]
                split.insert(0, {
                    'part': detected_prefix,
                    'meaning': prefix_meaning,
                    'original': detected_prefix,
                    'original_meaning': prefix_meaning,
                    'transform': '本身是前缀',
                    'explain': '前缀',
                })
                morph.append({
                    'type': 'prefix',
                    'word': f'{detected_prefix}-',
                    'meaning': prefix_meaning,
                })

            if detected_suffix:
                suffix_meaning = self.SUFFIXES[detected_suffix]
                split.append({
                    'part': detected_suffix,
                    'meaning': suffix_meaning,
                    'original': detected_suffix,
                    'original_meaning': suffix_meaning,
                    'transform': '本身是后缀',
                    'explain': '后缀',
                })
                morph.append({
                    'type': 'suffix',
                    'word': f'-{detected_suffix}',
                    'meaning': suffix_meaning,
                })

        # 如果没有检测到前后缀，或词根就是原词本身，判断为基础词
        if not split:
            word_type = '基础词'
            # 基础词兜底拆解：即使无法拆成复合词/词缀，也给出一个"基础单词"条目，
            # 保证每个单词的拆解区域都不为空，用户至少能看到该词的自有释义。
            if translation:
                split.append({
                    'part': word_lower,
                    'meaning': translation.split('\n')[0][:60],
                    'original': word_lower,
                    'original_meaning': translation.split('\n')[0][:60],
                    'transform': '原形不变',
                    'explain': '基础单词',
                })
                morph.append({
                    'type': 'root',
                    'word': word_lower,
                    'meaning': translation.split('\n')[0][:30],
                })

        # 构建变形数据：优先用内置不规则变形表（ADJ_DEGREES/VERB_TENSES/NOUN_PLURALS），
        # 再用 ECDICT exchange 字段（规则变形）
        tenses = self._get_inflections(word_lower, translation)
        if not tenses:
            tenses = self._build_tenses_from_exchange(word_lower, exchange)

        return {
            'phonetic': phonetic,
            'meaning': translation,
            'type': word_type,
            'split': split,
            'morph': morph,
            'mnemonic': '',
            'examples': self._get_zhuanshenben_examples(word_lower, translation),
            'tenses': tenses,
            'pos_label': pos_label,
        }

    def _get_phrase_examples(self, phrase, meaning=''):
        """
        为短语/词组生成例句
        将整个短语自然地融入完整英文句子中，而不是机械替换

        参数:
            phrase: 短语（如 "be good at"）
            meaning: 短语释义

        返回:
            list: 例句列表 [{en, zh}, ...]
        """
        import re

        # 常见短语的专门例句库
        PHRASE_EXAMPLES = {
            'be good at': [
                {'en': 'You are good at English words.', 'zh': '你擅长英语单词。'},
                {'en': 'She is good at playing the piano.', 'zh': '她擅长弹钢琴。'},
                {'en': 'He is good at math and science.', 'zh': '他擅长数学和科学。'},
            ],
            'be interested in': [
                {'en': 'I am interested in learning English.', 'zh': '我对学习英语感兴趣。'},
                {'en': 'She is interested in Chinese culture.', 'zh': '她对中国文化感兴趣。'},
            ],
            'be proud of': [
                {'en': 'I am proud of my country.', 'zh': '我为我的国家感到自豪。'},
                {'en': 'She is proud of her achievements.', 'zh': '她为自己的成就感到自豪。'},
            ],
            'be afraid of': [
                {'en': 'He is afraid of dogs.', 'zh': '他害怕狗。'},
                {'en': 'Don\'t be afraid of making mistakes.', 'zh': '不要害怕犯错。'},
            ],
            'look forward to': [
                {'en': 'I look forward to hearing from you.', 'zh': '我期待你的回复。'},
                {'en': 'We look forward to the weekend.', 'zh': '我们期待周末的到来。'},
            ],
            'give up': [
                {'en': 'Don\'t give up! You can do it.', 'zh': '不要放弃！你能做到。'},
                {'en': 'She decided to give up smoking.', 'zh': '她决定戒烟。'},
            ],
            'take care of': [
                {'en': 'Please take care of your health.', 'zh': '请照顾好你的健康。'},
                {'en': 'She takes care of her little brother.', 'zh': '她照顾她的弟弟。'},
            ],
            'be used to': [
                {'en': 'I am used to getting up early.', 'zh': '我习惯早起。'},
                {'en': 'She is used to the busy life here.', 'zh': '她习惯了这里忙碌的生活。'},
            ],
            'be full of': [
                {'en': 'The room is full of people.', 'zh': '房间里挤满了人。'},
                {'en': 'Her eyes were full of tears.', 'zh': '她眼中充满了泪水。'},
            ],
            'be famous for': [
                {'en': 'Hangzhou is famous for its tea.', 'zh': '杭州以茶叶闻名。'},
                {'en': 'The city is famous for its food.', 'zh': '这座城市因其美食而闻名。'},
            ],
            'be strict with': [
                {'en': 'Our teacher is strict with us.', 'zh': '我们的老师对我们很严格。'},
                {'en': 'She is strict with her children.', 'zh': '她对自己的孩子很严格。'},
            ],
            'be angry with': [
                {'en': 'He was angry with me.', 'zh': '他生我的气了。'},
                {'en': 'Don\'t be angry with him.', 'zh': '别生他的气。'},
            ],
            'be different from': [
                {'en': 'This book is different from that one.', 'zh': '这本书和那本不同。'},
                {'en': 'Chinese is very different from English.', 'zh': '中文和英文有很大不同。'},
            ],
            'be similar to': [
                {'en': 'My opinion is similar to yours.', 'zh': '我的意见和你的相似。'},
                {'en': 'This dress is similar to hers.', 'zh': '这件裙子和她的很像。'},
            ],
            'be tired of': [
                {'en': 'I am tired of doing the same thing.', 'zh': '我厌倦了做同样的事情。'},
                {'en': 'She is tired of his excuses.', 'zh': '她厌倦了他的借口。'},
            ],
            'be ready for': [
                {'en': 'Are you ready for the exam?', 'zh': '你准备好考试了吗？'},
                {'en': 'We are ready for the trip.', 'zh': '我们为旅行做好了准备。'},
            ],
            'be good for': [
                {'en': 'Milk is good for your health.', 'zh': '牛奶对你的健康有益。'},
                {'en': 'Exercise is good for you.', 'zh': '锻炼对你有好处。'},
            ],
            'be under too much pressure': [
                {'en': 'She is under too much pressure at work.', 'zh': '她在工作中承受了太大的压力。'},
                {'en': 'Students are under too much pressure before exams.', 'zh': '学生在考试前承受了太大的压力。'},
                {'en': 'Don\'t put yourself under too much pressure.', 'zh': '不要给自己太大的压力。'},
            ],
            'be under pressure': [
                {'en': 'He is under pressure to finish the project.', 'zh': '他承受着完成项目的压力。'},
                {'en': 'The team is under pressure to meet the deadline.', 'zh': '团队承受着赶上截止日期的压力。'},
            ],
            'be good with': [
                {'en': 'She is good with children.', 'zh': '她很擅长和孩子打交道。'},
                {'en': 'He is good with his hands.', 'zh': '他动手能力很强。'},
            ],
        }

        # 优先查专门例句库
        if phrase in PHRASE_EXAMPLES:
            return PHRASE_EXAMPLES[phrase]

        # 提取中文释义（去掉词性前缀、括号注释，只取第一条释义）
        zh_meaning = meaning or ''
        zh_meaning = zh_meaning.split('\n')[0].strip()
        meaning_lower = zh_meaning.lower()
        # 检测词性（兼容 ECDICT 的 vi./vt./a. 等格式）
        is_noun = bool(re.match(r'^n\.', meaning_lower) or re.match(r'^n\s', meaning_lower))
        is_verb = bool(re.match(r'^(v|vi|vt|aux)\.', meaning_lower) or re.match(r'^(v|vi|vt|aux)\s', meaning_lower))
        is_adj = bool(re.match(r'^(adj|a)\.', meaning_lower) or re.match(r'^adj\s', meaning_lower))

        # 去掉所有词性前缀（包括 ECDICT 的 a./vi./vt./aux. 等格式）
        zh_meaning = re.sub(r'^(vi|vt|aux|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\.\s*', '', zh_meaning)
        zh_meaning = re.sub(r'^(vi|vt|aux|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\s+', '', zh_meaning)
        zh_meaning = re.sub(r'\[.*?\]', '', zh_meaning)
        zh_meaning = re.sub(r'（.*?）', '', zh_meaning)
        zh_meaning = re.sub(r'\(.*?\)', '', zh_meaning)
        zh_meaning = re.split(r'[;；,，]', zh_meaning)[0].strip()
        zh_meaning = zh_meaning.strip('，,。 ') or phrase

        phrase_words = phrase.split()
        phrase_rest = ' '.join(phrase_words[1:])  # 去掉 be 后的部分

        # 根据短语结构生成例句
        # 1. be 短语：将 be 变位为 am/is/are，根据短语含义生成完整句子
        if phrase_words[0] == 'be':
            # 判断 be 短语后面跟的是介词还是形容词
            # 如 "be good at" → 后接名词作宾语
            # 如 "be under pressure" → 后接介词短语作表语
            if phrase_rest.startswith(('at', 'in', 'of', 'for', 'with', 'to', 'about')):
                # be + adj/prep + 介词 → 后面接名词宾语
                be_examples = [
                    {'en': f'She is {phrase_rest} English.', 'zh': f'她{zh_meaning}英语。'},
                    {'en': f'He is {phrase_rest} math.', 'zh': f'他{zh_meaning}数学。'},
                    {'en': f'They are {phrase_rest} sports.', 'zh': f'他们{zh_meaning}运动。'},
                ]
            else:
                # be + 名词/形容词短语 → 直接作表语，不需要额外宾语
                be_examples = [
                    {'en': f'She is {phrase_rest}.', 'zh': f'她{zh_meaning}。'},
                    {'en': f'The students are {phrase_rest}.', 'zh': f'学生们{zh_meaning}。'},
                    {'en': f'I don\'t want to be {phrase_rest}.', 'zh': f'我不想{zh_meaning}。'},
                ]
            return be_examples

        # 2. 动词短语：直接用短语作谓语或放在 to 后面
        if is_verb or (phrase_words[0] not in ('the', 'a', 'an')):
            # 判断短语是否以动词开头（简单启发式）
            verb_examples = [
                {'en': f'Many students want to {phrase} every day.', 'zh': f'很多学生每天想要{zh_meaning}。'},
                {'en': f'It is important to {phrase} in our daily life.', 'zh': f'在日常生活中{zh_meaning}是很重要的。'},
                {'en': f'She decided to {phrase} yesterday.', 'zh': f'她昨天决定{zh_meaning}。'},
            ]
            return verb_examples

        # 3. 名词短语：作为主语或宾语
        if is_noun:
            noun_examples = [
                {'en': f'The {phrase} is very popular among students.', 'zh': f'{zh_meaning}在学生中很受欢迎。'},
                {'en': f'I learned a lot from this {phrase}.', 'zh': f'我从这个{zh_meaning}中学到了很多。'},
            ]
            return noun_examples

        # 4. 默认：通用模板
        return [
            {'en': f'Can you explain what "{phrase}" means?', 'zh': f'你能解释一下"{zh_meaning}"是什么意思吗？'},
            {'en': f'The phrase "{phrase}" is commonly used in English.', 'zh': f'短语"{zh_meaning}"在英语中很常用。'},
        ]

    def _handle_phrase(self, phrase):
        """
        处理短语/词组（包含空格的输入，如 "be good at"、"sports meeting"）
        优先级：内置短语词典 → ECDICT 整体释义 → Agnes AI 整体释义 → 逐词拆解

        参数:
            phrase: 短语字符串（已转为小写）

        返回:
            dict: 分析结果，包含整体释义和每个单词的拆解
        """
        parts = phrase.split()
        if len(parts) < 2:
            return None

        # 0. 优先查内置短语词典（专升本常见短语，释义准确）
        if phrase in self.PHRASE_DICTIONARY:
            entry = self.PHRASE_DICTIONARY[phrase]
            result = entry.copy()
            # 补充拆解信息（逐词拆分用于学习参考）
            split = []
            for part in parts:
                # 优先使用 MEANING_OVERRIDES 中的常用释义
                if part in self.MEANING_OVERRIDES:
                    part_meaning = self.MEANING_OVERRIDES[part]
                    split.append({
                        'part': part,
                        'meaning': part_meaning,
                        'original': part,
                        'original_meaning': part_meaning,
                        'transform': '原形不变',
                        'explain': '独立单词',
                    })
                    continue
                part_data = self._query_ecdict(part)
                if part_data and part_data.get('translation'):
                    part_meaning = self._clean_meaning(part_data['translation'], part_data.get('pos', ''))
                    part_meaning = part_meaning.split('\n')[0][:60] if part_meaning else ''
                    split.append({
                        'part': part,
                        'meaning': part_meaning or f'{part}',
                        'original': part,
                        'original_meaning': part_meaning,
                        'transform': '原形不变',
                        'explain': '独立单词',
                    })
                else:
                    split.append({
                        'part': part,
                        'meaning': '',
                        'original': part,
                        'original_meaning': '',
                        'transform': '原形不变',
                        'explain': '独立单词',
                    })
            result['split'] = split
            result['tenses'] = None  # 短语不显示时态按钮
            return result

        # 1. 尝试从 ECDICT 查询整个短语的释义
        phrase_data = self._query_ecdict(phrase)
        phrase_translation = ''
        phrase_phonetic = ''
        if phrase_data and phrase_data.get('translation'):
            phrase_translation = self._clean_meaning(phrase_data['translation'], phrase_data.get('pos', ''))
            phrase_phonetic = self._convert_phonetic(phrase_data.get('phonetic', ''))

        # 1.5 释义质量检查：ECDICT 对短语的翻译可能不准确（如逐字翻译、碎片化释义）
        # 如果释义质量差，清空让它走 AI 翻译
        if phrase_translation:
            import re as _re
            # 去掉词性前缀后检查实际内容
            content = _re.sub(r'^[a-z]+\.\s*', '', phrase_translation).strip()
            # 检查中文字符数量
            chars_only = [c for c in content if '\u4e00' <= c <= '\u9fff']
            if len(chars_only) <= 3:
                # 中文内容太短，可能是碎片化释义（如 "冠", "姣姣者"）
                phrase_translation = ''
            elif content.count(',') >= 2 and all(len(p.strip()) <= 2 for p in content.split(',')):
                # 多个超短释义用逗号分隔，可能是逐字翻译
                phrase_translation = ''
            elif '\n' in content:
                # 多行释义：检查每行是否都是超短碎片
                lines_content = [l.strip() for l in content.split('\n') if l.strip()]
                if all(len(l) <= 3 for l in lines_content):
                    phrase_translation = ''

        # 2. 如果 ECDICT 没有整体释义，尝试在线查词
        if not phrase_translation:
            online_result = self._online_lookup(phrase)
            if online_result and online_result.get('meaning'):
                phrase_translation = online_result['meaning']

        # 2.5 释义必须含中文：若在线词典只返回英文定义（如 see through -> verb. To ...
        # see ...），这种释义对背单词没有任何帮助，必须清空交由 AI 翻译成中文。
        if phrase_translation and not any('\u4e00' <= c <= '\u9fff' for c in phrase_translation):
            phrase_translation = ''

        # 3. 如果仍无释义，标记需要 AI 翻译（由 app.py 层处理）
        #    返回 None 让 lookup() 返回 None，从而触发 AI 分析
        if not phrase_translation:
            return None

        # 4. 有整体释义了，拆分每个单词用于学习参考
        split = []
        for part in parts:
            # 优先使用 MEANING_OVERRIDES 中的常用释义（避免 ECDICT 返回生僻释义）
            if part in self.MEANING_OVERRIDES:
                override_meaning = self.MEANING_OVERRIDES[part]
                split.append({
                    'part': part,
                    'meaning': override_meaning,
                    'original': part,
                    'original_meaning': override_meaning,
                    'transform': '原形不变',
                    'explain': '独立单词',
                })
                continue
            part_data = self._query_ecdict(part)
            if part_data and part_data.get('translation'):
                part_meaning = self._clean_meaning(part_data['translation'], part_data.get('pos', ''))
                part_meaning = part_meaning.split('\n')[0][:60] if part_meaning else ''

                # 检查该单词是否是某个原词的变形（如 sports -> sport 的复数）
                part_exchange = self._parse_exchange(part_data.get('exchange', ''))
                original = part
                original_meaning = part_meaning
                transform = '原形不变'

                if '0' in part_exchange and '1' in part_exchange:
                    lemma = part_exchange['0']
                    form_type = part_exchange['1']
                    form_desc = {
                        'p': '过去式', 'd': '过去分词', 'i': '现在分词/动名词',
                        '3': '第三人称单数', 's': '复数形式',
                        'r': '比较级', 't': '最高级',
                        's1': '复数形式', 's2': '复数形式', 's3': '复数形式（作定语）',
                        'p1': '过去式', 'p2': '过去式',
                        'd1': '过去分词', 'd2': '过去分词',
                        'i1': '现在分词/动名词', 'i2': '现在分词/动名词',
                    }
                    transform = form_desc.get(form_type, '')
                    if not transform:
                        for code, desc in form_desc.items():
                            if form_type.startswith(code):
                                transform = desc
                                break
                    if not transform:
                        transform = '变形'
                    lemma_data = self._query_ecdict(lemma)
                    if lemma_data and lemma_data.get('translation'):
                        original = lemma
                        lemma_meaning = self._clean_meaning(lemma_data['translation'], lemma_data.get('pos', ''))
                        original_meaning = lemma_meaning.split('\n')[0][:60] if lemma_meaning else ''

                split.append({
                    'part': part,
                    'meaning': part_meaning or f'{part}（暂无释义）',
                    'original': original,
                    'original_meaning': original_meaning,
                    'transform': transform,
                    'explain': '独立单词',
                })
            elif part in self.DICTIONARY:
                part_meaning = self.DICTIONARY[part].get('meaning', '')
                split.append({
                    'part': part,
                    'meaning': part_meaning,
                    'original': part,
                    'original_meaning': part_meaning,
                    'transform': '原形不变',
                    'explain': '独立单词',
                })
            else:
                split.append({
                    'part': part,
                    'meaning': f'{part}（暂无释义）',
                    'original': part,
                    'original_meaning': '',
                    'transform': '原形不变',
                    'explain': '独立单词',
                })

        # 3. 如果短语整体没有释义，从各部分拼接一个基础释义
        if not phrase_translation:
            phrase_translation = '；'.join(
                f"{s['part']}: {s['meaning']}" for s in split
                if s.get('meaning') and '暂无' not in s.get('meaning', '')
            ) or f'{phrase}（暂无释义）'

        # 4. 短语/词组不提供时态变形（时态仅对单个动词有意义）
        tenses = None

        # 5. 记忆方法
        parts_str = ' + '.join(parts)
        mnemonic = f'"{phrase}"由{" ".join(parts)}组成，即{parts_str}的组合。'

        # 6. 为短语生成合适的例句（不用单词模板，避免语法错误）
        examples = self._get_phrase_examples(phrase, phrase_translation)

        return {
            'phonetic': phrase_phonetic,
            'meaning': phrase_translation,
            'type': '复合词',
            'split': split,
            'morph': [],
            'mnemonic': mnemonic,
            'examples': examples,
            'tenses': tenses,
        }

    # 补充词典归一化键映射（懒加载，用于处理文档提取词与词典键末尾标点不一致）
    _supp_norm_map = None

    @classmethod
    def _normalize_key(cls, w):
        """
        归一化词典查询键：统一小写、去掉首尾空白、去掉末尾标点
        （句号/感叹号/问号/省略号/全角括号等），使
        "get used to doing sth." 与文档提取的 "get used to doing sth" 能够匹配。
        """
        return re.sub(r"[.?!…。！？\s（）()·、]+$", "", (w or '').strip().lower())

    def _get_supp_norm_map(self):
        """构建补充词典的归一化键映射 {norm_key: meaning}，处理末尾标点不一致"""
        if self.__class__._supp_norm_map is None:
            mapping = {}
            for raw, val in self.SUPPLEMENT_DICTIONARY.items():
                nk = self._normalize_key(raw)
                if nk and nk not in mapping:
                    mapping[nk] = val
            self.__class__._supp_norm_map = mapping
        return self.__class__._supp_norm_map

    def lookup(self, word):
        """
        查询本地词典

        参数:
            word: 要查询的单词或词组

        返回:
            dict: 查询结果（与AI返回格式相同），如果未找到返回None
        """
        # 统一转为小写进行查询
        word_lower = word.lower().strip()
        # 清理文档提取残留的尾部括号（如 "hurt （" → "hurt"，"damage （" → "damage"）
        word_lower = re.sub(r"[（(]+$", "", word_lower).strip()

        # ===== 补充词典（用户笔记句式/谚语/搭配，释义精简常用）=====
        # 优先级最高：这些是专升本笔记中手工整理的常用释义，比 ECDICT 更贴合考试
        # 先精确匹配，再用归一化键匹配（处理末尾标点不一致，如 "doing sth." vs "doing sth"）
        supp_meaning = self.SUPPLEMENT_DICTIONARY.get(word_lower)
        if supp_meaning is None:
            supp_meaning = self._get_supp_norm_map().get(self._normalize_key(word_lower))
        if supp_meaning:
            meaning = supp_meaning
            # 生成拆解：词组逐词拆解，单次给出基础词条目，保证拆解区域不为空
            supp_split = []
            if ' ' in word_lower:
                for part in word_lower.split():
                    part_data = self._query_ecdict(part)
                    pm = self._clean_meaning(part_data.get('translation', ''), part_data.get('pos', '')) if part_data else ''
                    pm = pm.split('\n')[0][:60] if pm else ''
                    supp_split.append({
                        'part': part,
                        'meaning': pm or part,
                        'original': part,
                        'original_meaning': pm,
                        'transform': '原形不变',
                        'explain': '独立单词',
                    })
            else:
                m0 = meaning.split('\n')[0][:60]
                supp_split.append({
                    'part': word_lower,
                    'meaning': m0,
                    'original': word_lower,
                    'original_meaning': m0,
                    'transform': '原形不变',
                    'explain': '基础单词',
                })
            return {
                'phonetic': '',
                'meaning': meaning,
                'type': '复合词' if ' ' in word_lower else '基础词',
                'split': supp_split,
                'morph': [],
                'mnemonic': '',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': None if ' ' in word_lower else self._get_inflections(word_lower, meaning),
            }

        # ===== 复合词精确拆解优先级（单词语素拆解优先）=====
        # 用户核心需求：优先按单词/复合词拆解（understand → under + stand 两个单词），
        # 而不是把 under 当作前缀。COMPOUND_SPLITS 覆盖表里明确收录的复合词，
        # 直接走"按单词拆解"逻辑，避免被 DICTIONARY 的"派生词/前缀"拆解覆盖。
        if ' ' not in word_lower and word_lower in self.COMPOUND_SPLITS:
            ecdict_data = self._query_ecdict(word_lower)
            meaning = self.MEANING_OVERRIDES.get(word_lower) or \
                (self._clean_meaning(ecdict_data.get('translation', ''), ecdict_data.get('pos', '')) if ecdict_data else '')
            if not meaning:
                # 兜底：为个别复合词提供精释义
                meaning = self._fallback_compound_meaning(word_lower)
            return {
                'phonetic': self._convert_phonetic(ecdict_data.get('phonetic', '')) if ecdict_data else '',
                'meaning': meaning,
                'type': '复合词',
                'split': self._build_curated_compound(word_lower),
                'morph': [],
                'mnemonic': f'"{word_lower}" 由两个单词组成，按单词拆解更易记忆。',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': self._get_inflections(word_lower, meaning),
                'pos_label': self._pos_label(ecdict_data.get('pos', '')) if ecdict_data else '',
            }

        # ===== 短语/词组处理（包含空格的输入，如 "be good at"）=====
        # 优先检查 DICTIONARY（包含手工编辑的精确拆解数据，如 "sports meeting"）
        if ' ' in word_lower and word_lower in self.DICTIONARY:
            result = self.DICTIONARY[word_lower].copy()
            result['tenses'] = None  # 短语不显示时态按钮
            # 补充例句（如果词典自带例句为空）
            if not result.get('examples'):
                zs_examples = self._get_zhuanshenben_examples(word_lower, result.get('meaning', ''))
                if zs_examples:
                    result['examples'] = zs_examples
            return result

        if ' ' in word_lower:
            phrase_result = self._handle_phrase(word_lower)
            if phrase_result:
                return phrase_result
            # 短语翻译质量不佳或无释义：直接返回 None 触发 AI 分析
            # 不再 fall through 到逐词 ECDICT 查询，避免返回碎片化释义
            return None

        # 先精确匹配
        if word_lower in self.DICTIONARY:
            result = self.DICTIONARY[word_lower].copy()
            # 合并变形数据（时态/复数/比较级等，有什么附加什么）
            if 'tenses' not in result or not result.get('tenses'):
                infl = self._get_inflections(word_lower, result.get('meaning', ''))
                if infl:
                    result['tenses'] = infl
            elif word_lower in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[word_lower]
                result['tenses']['inflection_type'] = 'tense'
            # 补充专升本例句（如果词典自带例句为空或不足）
            if not result.get('examples'):
                zs_examples = self._get_zhuanshenben_examples(word_lower, result.get('meaning', ''))
                if zs_examples:
                    result['examples'] = zs_examples
            # 基础词兜底拆解：单个单词即使无法拆解，也保证拆解区域不为空
            if not result.get('split'):
                m = (result.get('meaning') or '').split('\n')[0][:60]
                result['split'] = [{
                    'part': word_lower,
                    'meaning': m,
                    'original': word_lower,
                    'original_meaning': m,
                    'transform': '原形不变',
                    'explain': '基础单词',
                }]
            return result

        # 尝试匹配复数形式（去掉末尾的s）
        if word_lower.endswith('s') and word_lower[:-1] in self.DICTIONARY:
            result = self.DICTIONARY[word_lower[:-1]].copy()
            base = word_lower[:-1]
            if base in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[base]
                result['tenses']['inflection_type'] = 'tense'
            elif 'tenses' not in result or not result.get('tenses'):
                infl = self._get_inflections(base, result.get('meaning', ''))
                if infl:
                    result['tenses'] = infl
            # 补充专升本例句
            if not result.get('examples'):
                zs_examples = self._get_zhuanshenben_examples(base, result.get('meaning', ''))
                if zs_examples:
                    result['examples'] = zs_examples
            # 基础词兜底拆解：保证拆解区域不为空
            if not result.get('split'):
                m = (result.get('meaning') or '').split('\n')[0][:60]
                result['split'] = [{
                    'part': word_lower,
                    'meaning': m,
                    'original': base,
                    'original_meaning': m,
                    'transform': f'是"{base}"的复数形式',
                    'explain': f'"{base}"的复数形式',
                }]
            return result

        # 尝试匹配ing形式（去掉末尾的ing）
        if word_lower.endswith('ing') and word_lower[:-3] in self.DICTIONARY:
            result = self.DICTIONARY[word_lower[:-3]].copy()
            base = word_lower[:-3]
            if base in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[base]
                result['tenses']['inflection_type'] = 'tense'
            elif 'tenses' not in result or not result.get('tenses'):
                infl = self._get_inflections(base, result.get('meaning', ''))
                if infl:
                    result['tenses'] = infl
            # 补充专升本例句
            if not result.get('examples'):
                zs_examples = self._get_zhuanshenben_examples(base, result.get('meaning', ''))
                if zs_examples:
                    result['examples'] = zs_examples
            return result

        # 已知动词但不在词典中：返回基础释义 + 时态
        if word_lower in self.VERB_TENSES:
            meaning = self.BASIC_VERB_MEANINGS.get(word_lower, f'v. {word_lower}')
            m0 = meaning.split('\n')[0][:60]
            result = {
                'phonetic': '',
                'meaning': meaning,
                'type': '动词',
                'split': [{
                    'part': word_lower,
                    'meaning': m0,
                    'original': word_lower,
                    'original_meaning': m0,
                    'transform': '原形不变',
                    'explain': '基础单词',
                }],
                'morph': [],
                'mnemonic': '',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': self.VERB_TENSES[word_lower],
            }
            result['tenses']['inflection_type'] = 'tense'
            return result

        # 检查是否是不规则形容词的比较级/最高级（如 worse→bad, better→good）
        if word_lower in self.REVERSE_ADJ_DEGREES:
            base_word = self.REVERSE_ADJ_DEGREES[word_lower]
            degrees = self.ADJ_DEGREES[base_word]
            # 确定当前词是比较级还是最高级
            comp_forms = degrees['comparative'].split('/')
            sup_forms = degrees['superlative'].split('/')
            if word_lower in comp_forms:
                form_type = '比较级'
            elif word_lower in sup_forms:
                form_type = '最高级'
            else:
                form_type = '变形'

            # 查询原级的释义
            base_data = self._query_ecdict(base_word)
            base_translation = self._clean_meaning(base_data.get('translation', ''), base_data.get('pos', '')) if base_data else ''
            base_phonetic = self._convert_phonetic(base_data.get('phonetic', '')) if base_data else ''

            # 当前词的释义：优先用 MEANING_OVERRIDES，其次 ECDICT 自身释义，否则用原级释义+变形说明
            cur_ecdict = self._query_ecdict(word_lower)
            if word_lower in self.MEANING_OVERRIDES:
                meaning = self.MEANING_OVERRIDES[word_lower]
            else:
                cur_translation = self._clean_meaning(cur_ecdict.get('translation', ''), cur_ecdict.get('pos', '')) if cur_ecdict else ''
                meaning = cur_translation or f'{base_word}的{form_type}' if base_translation else (cur_translation or f'{form_type}')

            # 构建变形数据（包含原级、比较级、最高级完整信息）
            tenses = {
                'positive': base_word,
                'comparative': degrees['comparative'],
                'superlative': degrees['superlative'],
                'inflection_type': 'degree',
            }

            split = [{
                'part': word_lower,
                'meaning': meaning,
                'original': base_word,
                'original_meaning': base_translation or meaning,
                'transform': form_type,
                'explain': f'是"{base_word}"的{form_type}',
            }]
            if base_translation and base_word != word_lower:
                split.append({
                    'part': base_word,
                    'meaning': base_translation,
                    'original': base_word,
                    'original_meaning': base_translation,
                    'transform': '原形',
                    'explain': '原词',
                })

            return {
                'phonetic': self._convert_phonetic(cur_ecdict.get('phonetic', '')) if cur_ecdict else base_phonetic,
                'meaning': meaning,
                'type': '变形词',
                'split': split,
                'morph': [],
                'mnemonic': f'"{word_lower}"是"{base_word}"的{form_type}',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': tenses,
            }

        # 内置词典未找到，尝试 ECDICT 词典
        ecdict_data = self._query_ecdict(word_lower)
        if ecdict_data and ecdict_data.get('translation'):
            result = self._decompose_with_ecdict(word_lower, ecdict_data)
            if result:
                return result

        # ECDICT 未找到，尝试在线查词
        online_result = self._online_lookup(word_lower)
        if online_result:
            return online_result

        # 未找到返回None
        return None

    def _online_lookup(self, word):
        """在线查词：调用有道词典获取中文释义和音标"""
        if word in self._online_cache:
            return self._online_cache[word]
        result = None
        try:
            resp = requests.get(
                'https://fanyi.youdao.com/translate',
                params={'doctype': 'json', 'type': 'EN2ZH_CN', 'i': word},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                tr = data.get('translateResult', [])
                if tr and tr[0]:
                    tgt = tr[0][0].get('tgt', '')
                    if tgt and tgt.lower() != word.lower():
                        meaning = tgt
                        web = data.get('web', [])
                        if web:
                            for item in web:
                                if item.get('key', '').lower() == word.lower():
                                    vals = item.get('value', [])
                                    if vals:
                                        meaning = '; '.join(vals[:3])
                                        break
                        result = {
                            'phonetic': '',
                            'meaning': meaning,
                            'type': '基础词',
                            'split': [],
                            'morph': [],
                            'mnemonic': '',
                            'examples': self._get_zhuanshenben_examples(word, meaning),
                            'tenses': None,
                        }
        except Exception as e:
            print(f'[dict] youdao fail({word}): {e}')
        if not result:
            try:
                resp = requests.get(
                    f'https://api.dictionaryapi.dev/api/v2/entries/en/{word}',
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=5
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        entry = data[0]
                        phonetic = ''
                        for p in entry.get('phonetics', []):
                            if p.get('text'):
                                phonetic = p['text']
                                break
                        # 英文兜底释义：只取最常用词性（第一个 meaning 组）的第一条定义。
                        # dictionaryapi 把词性按常用程度排序，生僻/古语词义（如 knowledge 的
                        # 古动词义 "To confess"）通常在最后，只取第一组即可自然排除，
                        # 避免把不常用的英文定义存进词库误导考生。
                        mtexts = []
                        meanings = entry.get('meanings', []) or []
                        if meanings:
                            first = meanings[0]
                            pos = first.get('partOfSpeech', '')
                            defs = first.get('definitions', []) or []
                            if defs and defs[0].get('definition'):
                                dt = defs[0]['definition'].strip()
                                if dt:
                                    mtexts.append(f'{pos}. {dt}')
                        if mtexts:
                            meaning = '; '.join(mtexts[:2])
                            result = {
                                'phonetic': phonetic,
                                'meaning': meaning,
                                'type': '基础词',
                                'split': [],
                                'morph': [],
                                'mnemonic': '',
                                'examples': self._get_zhuanshenben_examples(word, meaning),
                                'tenses': None,
                            }
            except Exception as e:
                print(f'[dict] freeapi fail({word}): {e}')
        # 释义必须含中文：在线词典若只返回英文定义（对背单词无帮助），丢弃交由 AI 翻译
        if result and not any('\u4e00' <= c <= '\u9fff' for c in (result.get('meaning') or '')):
            result = None
        self._online_cache[word] = result
        return result

    def analyze_with_rules(self, word):
        """
        用规则分析单词（检测前后缀），返回基础解析
        当词典中也没有该单词时，使用此方法进行简单分析

        参数:
            word: 要分析的单词

        返回:
            dict: 分析结果（与AI返回格式相同）
        """
        word_lower = word.lower().strip()
        morph = []
        split = []
        word_type = '基础词'

        # 检测前缀
        detected_prefix = None
        detected_root = word_lower
        for prefix in sorted(self.PREFIXES.keys(), key=len, reverse=True):
            if word_lower.startswith(prefix) and len(word_lower) > len(prefix) + 2:
                detected_prefix = prefix
                detected_root = word_lower[len(prefix):]
                word_type = '派生词'
                morph.append({
                    'type': 'prefix',
                    'word': f'{prefix}-',
                    'meaning': self.PREFIXES[prefix],
                })
                break

        # 检测后缀
        detected_suffix = None
        final_root = detected_root
        for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
            if detected_root.endswith(suffix) and len(detected_root) > len(suffix) + 1:
                detected_suffix = suffix
                final_root = detected_root[:-len(suffix)]
                word_type = '派生词'
                morph.append({
                    'type': 'suffix',
                    'word': f'-{suffix}',
                    'meaning': self.SUFFIXES[suffix],
                })
                break

        # 如果有词根且与原词不同，添加词根
        if final_root and final_root != word_lower:
            morph.insert(0, {
                'type': 'root',
                'word': final_root,
                'meaning': '词根',
            })

        # 检测复合词：如果单词中间有可识别的独立词
        # 简单处理：尝试将单词分成两部分
        for i in range(3, len(word_lower) - 2):
            part1 = word_lower[:i]
            part2 = word_lower[i:]
            if part1 in self.DICTIONARY and part2 in self.DICTIONARY:
                word_type = '复合词'
                # 复合词拆解，补充原词与变形规则字段（规则分析阶段默认原形不变）
                split = [
                    {
                        'part': part1,
                        'meaning': self.DICTIONARY[part1]['meaning'],
                        'original': part1,
                        'original_meaning': self.DICTIONARY[part1]['meaning'],
                        'transform': '原形不变',
                        'explain': '独立单词',
                    },
                    {
                        'part': part2,
                        'meaning': self.DICTIONARY[part2]['meaning'],
                        'original': part2,
                        'original_meaning': self.DICTIONARY[part2]['meaning'],
                        'transform': '原形不变',
                        'explain': '独立单词',
                    },
                ]
                morph = []
                break

        # 构建返回结果
        # 优先从 ECDICT 获取释义
        meaning = ''
        ecdict_data = self._query_ecdict(word_lower)
        if ecdict_data and ecdict_data.get('translation'):
            meaning = self._clean_meaning(ecdict_data['translation'], ecdict_data.get('pos', ''))
        if not meaning:
            meaning = self._infer_meaning(word_lower, detected_prefix, detected_suffix, final_root)

        # 检查动词时态：原词或词根是已知动词时，补充 tenses
        tenses = self._lookup_tenses(word_lower, detected_suffix, final_root)

        # 派生词也补充 split（词根 + 词缀），让前端能显示拆解
        if not split and (detected_prefix or detected_suffix) and final_root:
            split = self._build_derivative_split(
                word_lower, detected_prefix, detected_suffix, final_root
            )

        # 记忆方法兜底
        affix_parts = []
        if detected_prefix:
            affix_parts.append(f'前缀 {detected_prefix}（{self.PREFIXES.get(detected_prefix, "")}）')
        if detected_suffix:
            affix_parts.append(f'后缀 -{detected_suffix}（{self.SUFFIXES.get(detected_suffix, "")}）')
        if affix_parts:
            mnemonic = f'"{word_lower}" 含有{"、".join(affix_parts)}，可根据词根"{final_root}"推断含义。'
        elif final_root and final_root != word_lower:
            mnemonic = f'"{word_lower}" 可拆分为词根"{final_root}"，据此推断含义。'
        else:
            mnemonic = f'"{word_lower}" 暂无记忆方法，建议手动补充。'

        # 如果 _lookup_tenses 没找到变形，尝试用 _get_inflections
        if not tenses:
            tenses = self._get_inflections(word_lower, meaning)
        elif tenses and 'inflection_type' not in tenses:
            tenses['inflection_type'] = 'tense'

        # 补充专升本例句
        examples = self._get_zhuanshenben_examples(word_lower, meaning)

        # 基础词/词组兜底拆解：保证拆解区域不为空
        if not split:
            if ' ' in word_lower:
                for part in word_lower.split():
                    pd = self._query_ecdict(part)
                    pm = self._clean_meaning(pd.get('translation', ''), pd.get('pos', '')) if pd else ''
                    pm = pm.split('\n')[0][:60] if pm else ''
                    split.append({
                        'part': part,
                        'meaning': pm or part,
                        'original': part,
                        'original_meaning': pm,
                        'transform': '原形不变',
                        'explain': '独立单词',
                    })
            else:
                m0 = (meaning or '').split('\n')[0][:60]
                split.append({
                    'part': word_lower,
                    'meaning': m0,
                    'original': word_lower,
                    'original_meaning': m0,
                    'transform': '原形不变',
                    'explain': '基础单词',
                })

        return {
            'phonetic': '',
            'meaning': meaning,
            'type': word_type,
            'split': split,
            'morph': morph,
            'mnemonic': mnemonic,
            'examples': examples,
            'tenses': tenses,
        }

    def _infer_meaning(self, word, prefix, suffix, root):
        """
        根据前后缀推断单词的基础释义
        当词典和AI都无法给出释义时，用规则推断一个基础含义
        """
        # 后缀推断词性和含义
        suffix_meaning_map = {
            'ing': f'v. {root}的现在分词/动名词' if root else 'v. 动名词/现在分词',
            'ed': f'v. {root}的过去式/过去分词' if root else 'v. 过去式/过去分词',
            'er': f'n. 做{root}的人或物' if root else 'n. 做...的人或物',
            'or': f'n. 做{root}的人' if root else 'n. 做...的人',
            'ist': f'n. ...主义者（与{root}相关）' if root else 'n. ...主义者',
            'tion': f'n. {root}的动作或状态' if root else 'n. 动作或状态',
            'sion': f'n. {root}的动作或状态' if root else 'n. 动作或状态',
            'ment': f'n. {root}的行为或结果' if root else 'n. 行为或结果',
            'ness': f'n. {root}的状态或性质' if root else 'n. 状态或性质',
            'ity': f'n. {root}的性质或状态' if root else 'n. 性质或状态',
            'able': f'adj. 可{root}的' if root else 'adj. 可...的',
            'ible': f'adj. 可{root}的' if root else 'adj. 可...的',
            'ful': f'adj. 充满{root}的' if root else 'adj. 充满...的',
            'less': f'adj. 没有{root}的' if root else 'adj. 无...的',
            'ous': f'adj. 具有{root}的' if root else 'adj. 具有...的',
            'ive': f'adj. 有{root}倾向的' if root else 'adj. 有...倾向的',
            'al': f'adj. 与{root}相关的' if root else 'adj. ...的',
            'ly': f'adv. {root}地' if root else 'adv. ...地',
            'y': f'adj. 有{root}特性的' if root else 'adj. 有...特性的',
            'ize': f'v. 使{root}化' if root else 'v. 使...化',
            'ise': f'v. 使{root}化' if root else 'v. 使...化',
            'ify': f'v. 使{root}化' if root else 'v. 使...化',
            'en': f'v. 使变成{root}' if root else 'v. 使变成',
            'ship': f'n. {root}的关系或状态' if root else 'n. 关系或状态',
            'hood': f'n. {root}的时期或状态' if root else 'n. 时期或状态',
            'dom': f'n. {root}的领域或状态' if root else 'n. 领域或状态',
        }
        # 前缀推断含义
        prefix_meaning_map = {
            'un': '否定/相反',
            're': '重新/再次',
            'pre': '在...之前',
            'dis': '否定/相反',
            'mis': '错误',
            'over': '过度',
            'under': '不足/在下',
            'out': '超过/外面',
            'in': '进入/内',
            'im': '进入/内',
            'ir': '进入/内',
            'il': '进入/内',
            'en': '使成为',
            'non': '非',
            'anti': '反对',
            'auto': '自动',
            'bi': '双',
            'tri': '三',
            'multi': '多',
            'super': '超级',
            'sub': '在下面/次',
            'inter': '在...之间',
            'trans': '横过/转变',
        }

        parts = []
        if prefix and prefix in prefix_meaning_map and root:
            parts.append(prefix_meaning_map[prefix])
        if suffix and suffix in suffix_meaning_map:
            parts.append(suffix_meaning_map[suffix])

        if parts:
            return '，'.join(parts) + f'（词根: {root}，建议手动确认完整释义）' if root else '，'.join(parts)
        # 完全无法推断时，尝试 ECDICT 词典
        ecdict_data = self._query_ecdict(word)
        if ecdict_data and ecdict_data.get('translation'):
            return self._clean_meaning(ecdict_data['translation'], ecdict_data.get('pos', ''))
        # ECDICT 也没有，尝试在线查词
        online = self._online_lookup(word)
        if online and online.get('meaning'):
            return online['meaning']
        return f'{word}（暂无释义，建议点击编辑手动补充）'

    def _build_derivative_split(self, word, prefix, suffix, root):
        """
        为派生词构建 split 拆解数据（词根 + 前缀/后缀）
        """
        split = []
        if prefix:
            split.append({
                'part': prefix,
                'meaning': self.PREFIXES.get(prefix, '前缀'),
                'original': prefix,
                'original_meaning': self.PREFIXES.get(prefix, '前缀'),
                'transform': '本身是前缀，无变形',
                'explain': '前缀',
            })
        if root:
            split.append({
                'part': root,
                'meaning': '词根',
                'original': root,
                'original_meaning': '词根',
                'transform': '原形不变',
                'explain': '词根',
            })
        if suffix:
            split.append({
                'part': '-' + suffix,
                'meaning': self.SUFFIXES.get(suffix, '后缀'),
                'original': '-' + suffix,
                'original_meaning': self.SUFFIXES.get(suffix, '后缀'),
                'transform': '本身是后缀，无变形',
                'explain': '后缀',
            })
        return split

    def _lookup_tenses(self, word, suffix, root):
        """
        查找动词时态数据，处理多种变形情况
        包括双写辅音变形（running→run, swimming→swim, getting→get）
        """
        # 1. 原词直接命中
        if word in self.VERB_TENSES:
            return self.VERB_TENSES[word]
        # 2. 词根直接命中
        if root and root in self.VERB_TENSES:
            return self.VERB_TENSES[root]
        # 3. 处理 -ing/-ed 后缀的双写辅音变形
        #    running→runn→run, swimming→swimm→swim, getting→gett→get
        if suffix in ('ing', 'ed') and len(word) > 4:
            strip_len = len(suffix)
            candidate = word[:-strip_len]
            # 双写辅音结尾：去掉重复的最后一个字母
            if len(candidate) >= 2 and candidate[-1] == candidate[-2]:
                shorter = candidate[:-1]
                if shorter in self.VERB_TENSES:
                    return self.VERB_TENSES[shorter]
            # 以 e 结尾的动词加 ing 时去掉 e（making→mak→make）
            if candidate and candidate + 'e' in self.VERB_TENSES:
                return self.VERB_TENSES[candidate + 'e']
            # 以 ie 结尾的动词加 ing 变成 ying（lying→ly→lie）
            if word.endswith('ying') and len(word) > 4:
                base = word[:-4] + 'ie'
                if base in self.VERB_TENSES:
                    return self.VERB_TENSES[base]
        # 4. 处理 -ed 后缀的 e 结尾动词（liked→lik→like）
        if suffix == 'ed' and len(word) > 3:
            candidate = word[:-2]
            if candidate + 'e' in self.VERB_TENSES:
                return self.VERB_TENSES[candidate + 'e']
        return None

    def get_demo_words(self):
        """
        获取演示单词列表，用于数据库初始化
        返回词典中所有的单词及其解析

        返回:
            list[dict]: 演示单词列表
        """
        demo_words = []
        for word, analysis in self.DICTIONARY.items():
            demo_words.append({
                'word': word,
                'phonetic': analysis['phonetic'],
                'meaning': analysis['meaning'],
                'word_type': analysis['type'],
                'split_data': analysis['split'],
                'morph_data': analysis['morph'],
                'mnemonic': analysis.get('mnemonic', ''),
                'examples': analysis['examples'],
            })
        return demo_words
