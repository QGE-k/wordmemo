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
        'sing': 'v. 唱',
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
        'eat': 'v. 吃',
        'fall': 'v. 落下',
        'win': 'v. 赢',
        'lose': 'v. 失去，输',
        'wear': 'v. 穿',
        'draw': 'v. 画',
        'throw': 'v. 扔',
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
        'look': 'v. 看',
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

    # 江西专升本常见词汇例句库
    # 这些例句模拟专升本英语考试中的常见用法
    ZHUANSHENBEN_EXAMPLES = {
        'do': [
            {'en': 'What do you plan to do after graduation?', 'zh': '你毕业后打算做什么？'},
            {'en': 'We should do our best to pass the exam.', 'zh': '我们应该尽最大努力通过考试。'},
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
            {'en': 'Team work is very important in modern society.', 'zh': '团队合作在现代社会中非常重要。'},
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
            {'en': 'She has the ability to learn English well.', 'zh': '她有能力学好英语。'},
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
            {'en': 'It is important to communicate with others effectively.', 'zh': '与他人有效沟通很重要。'},
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
            {'en': 'It is important to understand the main idea.', 'zh': '理解主旨很重要。'},
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
            {'en': 'It is important to learn English well for your future.', 'zh': '为你的未来学好英语很重要。'},
            {'en': 'Education plays an important role in our life.', 'zh': '教育在我们生活中起着重要作用。'},
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
    }

    # 专升本例句模板（当单词没有专门例句时，根据词性生成通用例句）
    # {word}=英文单词，{zh}=中文释义（从meaning字段提取）
    EXAMPLE_TEMPLATES = {
        'verb': [
            {'en': 'I usually {word} in the morning.', 'zh': '我通常在早上{zh}。'},
            {'en': 'It is important to {word} every day.', 'zh': '每天{zh}是很重要的。'},
            {'en': 'She wants to {word} her English skills.', 'zh': '她想{zh}她的英语能力。'},
        ],
        'noun': [
            {'en': 'This {word} is very important to us.', 'zh': '这个{zh}对我们来说非常重要。'},
            {'en': 'I learned a lot from this {word}.', 'zh': '我从这个{zh}中学到了很多。'},
            {'en': 'The {word} has changed our lives.', 'zh': '{zh}改变了我们的生活。'},
        ],
        'adj': [
            {'en': 'She is a very {word} person.', 'zh': '她是一个非常{zh}的人。'},
            {'en': 'This book is very {word}.', 'zh': '这本书非常{zh}。'},
            {'en': 'The weather today is quite {word}.', 'zh': '今天的天气相当{zh}。'},
        ],
        'adv': [
            {'en': 'He spoke {word} at the meeting.', 'zh': '他在会议上{zh}地发言。'},
            {'en': 'She always listens {word} in class.', 'zh': '她上课时总是{zh}地听讲。'},
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

        # 4. 规则名词复数（以辅音字母+y结尾，变y为i加es；以s/x/ch/sh结尾加es；其他加s）
        # 仅当释义以 n. 开头时才判断为名词
        if meaning and meaning.strip().startswith('n.'):
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
        # 仅当释义以 adj. 开头时才判断
        if meaning and meaning.strip().startswith('adj.'):
            if len(word_lower) <= 5 and word_lower.endswith('e'):
                return {
                    'positive': word_lower,
                    'comparative': word_lower + 'r',
                    'superlative': word_lower + 'st',
                    'inflection_type': 'degree',
                }
            elif len(word_lower) <= 4 and word_lower.endswith(('a', 'e', 'i', 'o', 'u')) is False:
                # 辅音+短元音+辅音结尾的双写
                if len(word_lower) == 3 and word_lower[0] not in 'aeiou' and word_lower[1] in 'aeiou' and word_lower[2] not in 'aeiou':
                    return {
                        'positive': word_lower,
                        'comparative': word_lower + word_lower[-1] + 'er',
                        'superlative': word_lower + word_lower[-1] + 'est',
                        'inflection_type': 'degree',
                    }
                elif len(word_lower) <= 5:
                    return {
                        'positive': word_lower,
                        'comparative': word_lower + 'er',
                        'superlative': word_lower + 'est',
                        'inflection_type': 'degree',
                    }

        return None

    def _get_zhuanshenben_examples(self, word, meaning=''):
        """
        获取专升本例句：优先从专门例句库中查找，没有则根据词性用模板生成

        参数:
            word: 单词
            meaning: 单词释义（用于推断词性）

        返回:
            list: 例句列表 [{en, zh}, ...]，可能为空
        """
        word_lower = word.lower().strip()

        # 1. 先查专门的专升本例句库
        if word_lower in self.ZHUANSHENBEN_EXAMPLES:
            return self.ZHUANSHENBEN_EXAMPLES[word_lower]

        # 2. 尝试去掉复数/时态后缀再查
        base = word_lower
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
        # 检测词性前缀（兼容 ECDICT 的 vi./vt./a. 等格式）
        if re.match(r'^(v|vi|vt|aux)\.', meaning_lower) or re.match(r'^(v|vi|vt|aux)\s', meaning_lower):
            pos = 'verb'
        elif re.match(r'^n\.', meaning_lower) or re.match(r'^n\s', meaning_lower):
            pos = 'noun'
        elif re.match(r'^(adj|a)\.', meaning_lower) or re.match(r'^adj\s', meaning_lower):
            pos = 'adj'
        elif re.match(r'^(adv|ad)\.', meaning_lower) or re.match(r'^adv\s', meaning_lower):
            pos = 'adv'

        # 4. 如果释义没有标准词性前缀，尝试从单词后缀推断
        if not pos:
            if word_lower.endswith(('ful', 'ous', 'ive', 'able', 'ible', 'al', 'less', 'ish', 'ic', 'ant', 'ent', 'ary', 'ory')):
                pos = 'adj'
            elif word_lower.endswith(('tion', 'sion', 'ment', 'ness', 'ity', 'ship', 'hood', 'ance', 'ence', 'dom', 'ism', 'ist')):
                pos = 'noun'
            elif word_lower.endswith(('ly', 'ward', 'wise')):
                pos = 'adv'
            elif word_lower.endswith(('ize', 'ise', 'ify', 'en', 'ate')):
                pos = 'verb'
            else:
                # 默认按名词处理（最常见的词性）
                pos = 'noun'

        if pos and pos in self.EXAMPLE_TEMPLATES:
            # 提取中文释义（去掉词性前缀、括号注释，只取第一条释义）
            zh_meaning = meaning_str
            # 只取第一行（ECDICT 多词性释义用换行分隔）
            zh_meaning = zh_meaning.split('\n')[0].strip()
            # 去掉所有词性前缀（包括 ECDICT 的 a./vi./vt./aux. 等格式）
            zh_meaning = re.sub(r'^(vi|vt|aux|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\.\s*', '', zh_meaning)
            zh_meaning = re.sub(r'^(vi|vt|aux|n|v|adj|adv|ad|a|prep|conj|pron|num|art|interj)\s+', '', zh_meaning)
            # 去掉方括号注释如 [体] [法] [医]
            zh_meaning = re.sub(r'\[.*?\]', '', zh_meaning)
            # 去掉圆括号注释如 (书名)
            zh_meaning = re.sub(r'（.*?）', '', zh_meaning)
            zh_meaning = re.sub(r'\(.*?\)', '', zh_meaning)
            # 只取第一条释义（分号或逗号分隔）
            zh_meaning = re.split(r'[;；,，]', zh_meaning)[0].strip()
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

    def _convert_phonetic(self, phonetic):
        """将 ECDICT 音标编码转换为标准 IPA 格式"""
        if not phonetic:
            return ''
        result = phonetic
        result = result.replace(':', '\u02d0')  # long vowel mark ː
        result = result.replace("'", '\u02c8')   # primary stress ˈ
        result = result.replace(',', '\u02cc')   # secondary stress ˌ
        return '/' + result + '/'

    def _clean_meaning(self, translation):
        """
        精简 ECDICT 释义：只保留常用释义（前1-2条），去除过长内容
        ECDICT translation 格式：用换行分隔不同词性的释义
        """
        if not translation:
            return ''
        # 按换行分割，取前2条
        lines = translation.strip().split('\n')
        # 过滤掉太长的行（可能是专业术语）和包含方括号的行（如 [法] [化]）
        clean_lines = []
        for line in lines[:3]:
            line = line.strip()
            if not line:
                continue
            # 去除行内方括号注释如 [体] [法] [网]
            import re as _re
            line = _re.sub(r'\[.*?\]', '', line).strip()
            if not line:
                continue
            # 跳过包含专业领域标记的行
            if any(line.startswith(f'[{tag}]') for tag in ['法', '化', '医', '药', '生', '计', '经', '农', '商']):
                continue
            # 如果一行内用分号或逗号分隔了多个释义，只取前3个
            parts = _re.split(r'[;；,，]', line)
            if len(parts) > 3:
                line = ','.join(parts[:3])
            # 限制每行长度
            if len(line) > 50:
                line = line[:50] + '...'
            clean_lines.append(line)
            if len(clean_lines) >= 2:
                break
        return '\n'.join(clean_lines) if clean_lines else lines[0].strip()

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

    def _try_compound_split(self, word):
        """
        第一层拆解：尝试将单词拆分为两个已知独立单词（复合词检测）
        例如: basketball -> basket + ball
        质量控制：两部分至少3字符，排除人名/地名/网络用语等非常用词
        """
        conn = self._ecdict
        if not conn:
            return None
        # 排除标记：翻译中包含这些标记的词条视为非常用词（人名、地名等）
        bad_markers = ['[人名]', '[地名]', '[网络]', '[药]', '[化]', '[生]', '[医]']
        for i in range(3, len(word) - 2):
            part1 = word[:i]
            part2 = word[i:]
            # 两部分都至少3个字符
            if len(part1) < 3 or len(part2) < 3:
                continue
            # 如果任一部分是已知前缀/后缀，不是复合词
            if part1 in self.PREFIXES or part2 in self.SUFFIXES or part1 in self.SUFFIXES or part2 in self.PREFIXES:
                continue
            try:
                r1 = conn.execute(
                    'SELECT translation FROM stardict WHERE word = ? COLLATE NOCASE AND translation IS NOT NULL AND translation != ""',
                    (part1,)
                ).fetchone()
                r2 = conn.execute(
                    'SELECT translation FROM stardict WHERE word = ? COLLATE NOCASE AND translation IS NOT NULL AND translation != ""',
                    (part2,)
                ).fetchone()
                if r1 and r2:
                    m1 = self._clean_meaning(r1[0] or '')
                    m2 = self._clean_meaning(r2[0] or '')
                    # 排除人名/地名/网络用语等
                    if any(bm in m1 for bm in bad_markers) or any(bm in m2 for bm in bad_markers):
                        continue
                    # 排除词条翻译以 suff./pref./abbr. 开头的（这些是词缀或缩写，不是独立单词）
                    m1_stripped = m1.strip()
                    m2_stripped = m2.strip()
                    if m1_stripped.startswith(('suff.', 'pref.', 'abbr.', 'prefix', 'suffix')) or \
                       m2_stripped.startswith(('suff.', 'pref.', 'abbr.', 'prefix', 'suffix')):
                        continue
                    # 翻译至少要有词性标记（如 n. v. adj.）或中文字符
                    has_meaning_1 = any(c for c in 'nvadjrp.' if c in m1[:5]) or any('\u4e00' <= c <= '\u9fff' for c in m1)
                    has_meaning_2 = any(c for c in 'nvadjrp.' if c in m2[:5]) or any('\u4e00' <= c <= '\u9fff' for c in m2)
                    if not has_meaning_1 or not has_meaning_2:
                        continue
                    m1 = m1.split('\n')[0][:60]
                    m2 = m2.split('\n')[0][:60]
                    return [
                        {
                            'part': part1,
                            'meaning': m1,
                            'original': part1,
                            'original_meaning': m1,
                            'transform': '原形不变',
                            'explain': '独立单词',
                        },
                        {
                            'part': part2,
                            'meaning': m2,
                            'original': part2,
                            'original_meaning': m2,
                            'transform': '原形不变',
                            'explain': '独立单词',
                        },
                    ]
            except Exception:
                pass
        return None

    def _decompose_with_ecdict(self, word, ecdict_data):
        """
        三层拆解逻辑（核心方法）：
        第一层：复合词拆解（如 basketball → basket + ball）
        第二层：变形词拆解（如 running → run + 现在分词变形）
        第三层：派生词拆解（如 unhappiness → un + happy + ness）
        如果都不能拆解，返回基础词信息
        """
        word_lower = word.lower().strip()
        exchange = self._parse_exchange(ecdict_data.get('exchange', ''))
        translation = self._clean_meaning(ecdict_data.get('translation', ''))
        phonetic = self._convert_phonetic(ecdict_data.get('phonetic', ''))
        pos_raw = ecdict_data.get('pos', '') or ''

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
            lemma_translation = self._clean_meaning(lemma_data.get('translation', '')) if lemma_data else ''
            lemma_phonetic = self._convert_phonetic(lemma_data.get('phonetic', '')) if lemma_data else ''

            # 查询原词的完整变形信息
            tenses = None
            if lemma_data:
                lemma_exchange = self._parse_exchange(lemma_data.get('exchange', ''))
                tenses = self._build_tenses_from_exchange(lemma, lemma_exchange)

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
                if root_check and root_check.get('translation'):
                    skip_compound = True
                    break
                # 也检查去后缀后的词根（如 unhappiness → un + happi + ness → happy）
                for suffix in sorted(self.SUFFIXES.keys(), key=len, reverse=True):
                    if candidate_root.endswith(suffix) and len(candidate_root) > len(suffix) + 1:
                        inner_root = candidate_root[:-len(suffix)]
                        if inner_root != word_lower:
                            inner_check = self._query_ecdict(inner_root)
                            if inner_check and inner_check.get('translation'):
                                skip_compound = True
                                break
                        # y/i 变体检查 (happy → happi)
                        if inner_root and inner_root + 'y' != word_lower:
                            y_check = self._query_ecdict(inner_root + 'y')
                            if y_check and y_check.get('translation'):
                                skip_compound = True
                                break
                if skip_compound:
                    break

        # ===== 第一层：复合词拆解（仅当没有明显前缀词根时）=====
        compound = None
        if not skip_compound:
            compound = self._try_compound_split(word_lower)
        if compound:
            # 复合词也可能有变形，尝试获取
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
                if candidate_data and candidate_data.get('translation'):
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
                        if inner_data and inner_data.get('translation'):
                            detected_prefix = prefix
                            detected_root = candidate
                            detected_suffix = suffix
                            final_root = inner
                            break
                        # y/i 变体检查: happi → happy
                        if inner and len(inner) >= 2 and inner[-1] == 'i':
                            y_candidate = inner[:-1] + 'y'
                            y_data = self._query_ecdict(y_candidate)
                            if y_data and y_data.get('translation'):
                                detected_prefix = prefix
                                detected_root = candidate
                                detected_suffix = suffix
                                final_root = y_candidate
                                break
                        # e 结尾检查: mak → make
                        if inner and not inner.endswith('e'):
                            e_candidate = inner + 'e'
                            e_data = self._query_ecdict(e_candidate)
                            if e_data and e_data.get('translation'):
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
            root_meaning = self._clean_meaning(root_data.get('translation', '')) if root_data else ''

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

        # 构建变形数据
        tenses = self._build_tenses_from_exchange(word_lower, exchange)

        # 如果 exchange 没有变形数据但 translation 表明是动词，尝试用旧方法
        if not tenses and translation:
            infl = self._get_inflections(word_lower, translation)
            if infl:
                tenses = infl

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
        将短语拆分为每个独立单词，分别查询释义，构建 split 数据

        参数:
            phrase: 短语字符串（已转为小写）

        返回:
            dict: 分析结果，包含整体释义和每个单词的拆解
        """
        parts = phrase.split()
        if len(parts) < 2:
            return None

        # 1. 尝试从 ECDICT 查询整个短语的释义
        phrase_data = self._query_ecdict(phrase)
        phrase_translation = ''
        phrase_phonetic = ''
        if phrase_data and phrase_data.get('translation'):
            phrase_translation = self._clean_meaning(phrase_data['translation'])
            phrase_phonetic = self._convert_phonetic(phrase_data.get('phonetic', ''))

        # 如果 ECDICT 没有整个短语的释义，尝试在线查词
        if not phrase_translation:
            online_result = self._online_lookup(phrase)
            if online_result and online_result.get('meaning'):
                phrase_translation = online_result['meaning']

        # 2. 拆分每个单词，查询各自释义
        split = []
        for part in parts:
            part_data = self._query_ecdict(part)
            if part_data and part_data.get('translation'):
                part_meaning = self._clean_meaning(part_data['translation'])
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
                    # 先精确匹配，再前缀匹配（处理 s3, p1 等复合代码）
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
                        lemma_meaning = self._clean_meaning(lemma_data['translation'])
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
                # ECDICT 没有该单词，尝试内置词典
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

        # ===== 短语/词组处理（包含空格的输入，如 "be good at"）=====
        if ' ' in word_lower:
            phrase_result = self._handle_phrase(word_lower)
            if phrase_result:
                return phrase_result

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
            result = {
                'phonetic': '',
                'meaning': meaning,
                'type': '动词',
                'split': [],
                'morph': [],
                'mnemonic': '',
                'examples': self._get_zhuanshenben_examples(word_lower, meaning),
                'tenses': self.VERB_TENSES[word_lower],
            }
            result['tenses']['inflection_type'] = 'tense'
            return result

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
                        mtexts = []
                        for m in entry.get('meanings', [])[:3]:
                            pos = m.get('partOfSpeech', '')
                            for d in m.get('definitions', [])[:2]:
                                dt = d.get('definition', '')
                                if dt:
                                    mtexts.append(f'{pos}. {dt}')
                        if mtexts:
                            meaning = '; '.join(mtexts[:5])
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
            meaning = self._clean_meaning(ecdict_data['translation'])
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
            return self._clean_meaning(ecdict_data['translation'])
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
