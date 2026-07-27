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
            # 合并动词时态数据（如果该词是动词且在时态表中）
            if word_lower in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[word_lower]
            return result

        # 尝试匹配复数形式（去掉末尾的s）
        if word_lower.endswith('s') and word_lower[:-1] in self.DICTIONARY:
            result = self.DICTIONARY[word_lower[:-1]].copy()
            if word_lower[:-1] in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[word_lower[:-1]]
            return result

        # 尝试匹配ing形式（去掉末尾的ing）
        if word_lower.endswith('ing') and word_lower[:-3] in self.DICTIONARY:
            result = self.DICTIONARY[word_lower[:-3]].copy()
            if word_lower[:-3] in self.VERB_TENSES:
                result['tenses'] = self.VERB_TENSES[word_lower[:-3]]
            return result

        # 即使不在DICTIONARY中，也检查是否是已知动词（提供时态数据）
        if word_lower in self.VERB_TENSES:
            return {'tenses': self.VERB_TENSES[word_lower]}

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
        return {
            'phonetic': '',
            'meaning': '',
            'type': word_type,
            'split': split,
            'morph': morph,
            'examples': [],
        }

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
