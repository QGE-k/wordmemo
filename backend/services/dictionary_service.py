"""
本地词典服务模块
作为AI不可用时的fallback方案
包含预置的常用单词词典和基于规则的单词分析
"""
import re


class DictionaryService:
    """本地词典服务，提供离线单词查询和规则分析"""

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
            {'en': 'We should try to {word} as often as possible.', 'zh': '我们应该尽可能经常地去{zh}。'},
            {'en': 'It is necessary for students to {word} in their studies.', 'zh': '学生在学习中需要{zh}。'},
        ],
        'noun': [
            {'en': 'This {word} plays an important role in our daily life.', 'zh': '这个{zh}在我们的日常生活中起着重要作用。'},
            {'en': 'Everyone should understand the value of {word}.', 'zh': '每个人都应该理解{zh}的价值。'},
        ],
        'adj': [
            {'en': 'It is very {word} for college students to learn English well.', 'zh': '对大学生来说学好英语非常{zh}。'},
            {'en': 'She has made {word} progress in her studies.', 'zh': '她在学习上取得了{zh}的进步。'},
        ],
        'adv': [
            {'en': 'He finished his homework {word} and went to bed.', 'zh': '他{zh}地完成了作业然后去睡觉了。'},
            {'en': 'The students listened to the teacher {word}.', 'zh': '学生们{zh}地听老师讲课。'},
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
        meaning_str = (meaning or '').strip()
        meaning_lower = meaning_str.lower()
        pos = None
        if meaning_lower.startswith('v.') or meaning_lower.startswith('v '):
            pos = 'verb'
        elif meaning_lower.startswith('n.') or meaning_lower.startswith('n '):
            pos = 'noun'
        elif meaning_lower.startswith('adj.') or meaning_lower.startswith('adj '):
            pos = 'adj'
        elif meaning_lower.startswith('adv.') or meaning_lower.startswith('adv '):
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
            # 提取中文释义（去掉词性前缀如 "n. ", "v. " 等）
            import re
            zh_meaning = re.sub(r'^(n|v|adj|adv|prep|conj|pron|num|art|interj)\.\s*', '', meaning_str)
            zh_meaning = re.sub(r'^(n|v|adj|adv|prep|conj|pron|num|art|interj)\s+', '', zh_meaning)
            zh_meaning = zh_meaning.strip() or word_lower

            templates = self.EXAMPLE_TEMPLATES[pos]
            examples = []
            for tpl in templates:
                examples.append({
                    'en': tpl['en'].replace('{word}', word_lower),
                    'zh': tpl['zh'].replace('{word}', word_lower).replace('{zh}', zh_meaning),
                })
            return examples

        return []

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

        # 未找到返回None
        return None

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
        # 根据前后缀推断基础释义（避免返回空 meaning）
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
        # 完全无法推断时给出提示
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
