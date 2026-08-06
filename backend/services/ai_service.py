"""
Agnes AI 单词分析服务
兼容OpenAI接口，调用AI对单词进行词法分析、拆解
"""
import json
import base64
import io
import requests
from config import Config


class AIService:
    """Agnes AI 单词分析服务（兼容OpenAI接口）"""

    def __init__(self):
        """初始化AI服务配置"""
        self.api_key = Config.AGNES_API_KEY
        self.base_url = Config.AGNES_BASE_URL
        self.model = Config.AGNES_MODEL

    def is_available(self):
        """检查AI服务是否可用（API Key是否已配置）"""
        return bool(self.api_key)

    def analyze_word(self, word):
        """
        用AI分析单词的组成和词根词缀

        分析返回的数据结构：
        {
            "phonetic": "/spɔːts ˈmiːtɪŋ/",      # 音标
            "meaning": "n. 运动会",                # 释义
            "type": "复合词",                      # 类型：复合词/派生词/基础词
            "split": [                             # 拆解（复合词和派生词都填这里）
                {
                    "part": "sports",              # 当前部分
                    "meaning": "n. 运动",           # 这部分的意思
                    "original": "sport",           # 原词（这部分从哪个词变来）
                    "original_meaning": "n. 运动",  # 原词的意思
                    "transform": "加 -s 变复数",    # 变形规则（怎么从原词变过来的）
                    "explain": "复数形式作定语，修饰 meeting"
                }
            ],
            "morph": [...],                        # 词根词缀（派生词的另一种视角，可选）
            "mnemonic": "运动会就是'sports'(运动) + 'meeting'(聚会)，字面意思'运动的聚会'",  # 记忆方法
            "examples": [{"en": "...", "zh": "..."}]
        }

        参数:
            word: 要分析的单词或词组

        返回:
            dict: 分析结果字典
        """
        if not self.is_available():
            raise RuntimeError('Agnes AI API Key未配置')

        # 构建系统提示词：定义AI的角色和任务
        system_prompt = """你是一位专业的英语词法分析专家，专门帮助英语基础薄弱的中国学生理解单词构成。你的任务是对英语单词或词组进行深度拆解，让学生看懂每个部分"从哪来、怎么变、什么意思"，并给出好记的记忆方法。

【核心原则】
1. 能拆解的单词都要拆，不要只拆复合词，派生词也要拆开给学生看。
2. 【释义优先规则】split 中每个部分的 meaning 必须是该词/词缀最常用的释义（专升本考试常见释义），不能使用生僻释义。例如：
   - look → "v. 看"（不是"vi. 注意"）
   - take → "v. 拿，取"（不是"vt. 带领"）
   - pressure → "n. 压力"（不是"n. 强制"）
   - to → "prep. 朝向/向"（不是"prep. 趋于"）
   - be → "v. 是，存在"（不是"v. 表示"）
   - much → "adj./adv. 多，大量"（不是"adv. 几乎"）
   - care → "n. 关心，照顾"（不是"n. 小心"）
3. 【前缀同化规则】拉丁语前缀在不同字母前会发生同化变化，拆解时必须识别：
   - sub- 在 c 前变为 suc-（如 success = suc- + cess）
   - sub- 在 g 前变为 sug-（如 suggest = sug- + gest）
   - sub- 在 p 前变为 sup-（如 support = sup- + port）
   - sub- 在 f 前变为 suf-（如 suffer = suf- + fer）
   - sub- 在 m 前变为 sum-（如 summon = sum- + mon）
   - ad- 在 p 前变为 ap-（如 appear = ap- + pear）
   - ad- 在 c 前变为 ac-（如 accept = ac- + cept）
   - in- 在 p 前变为 im-（如 important = im- + port + -ant）
   - in- 在 r 前变为 ir-（如 irregular = ir- + regular）
   - con- 在 l 前变为 col-（如 collect = col- + lect）
   - con- 在 r 前变为 cor-（如 correct = cor- + rect）
   - ob- 在 c 前变为 oc-（如 occur = oc- + cur）
   拆解时 original 填原始前缀（如 sub-），transform 说明同化变化（如"sub- 在 c 前同化为 suc-"）
4. 【基础词不拆原则】以下情况不要强行拆解：
   - 整体借入英语的外来词：develop（法语）、culture（拉丁语）、imagine（拉丁语）、traffic（意大利语）
   - 古英语基础词：water, thing, apple, book
   - 看似有前缀但实际不是的词：develop（de-不是英语前缀，是法语残留）
   这些词 type 设为"基础词"，split 留空 []，但 mnemonic 必须给出记忆方法

分析要求：
1. 判断单词类型：
   - 复合词（compound）：由两个或以上独立单词组合而成，如 classroom = class + room
   - 派生词（derivative）：由词根+词缀构成，如 happiness = happy + -ness，running = run + -ing
   - 基础词（base）：无法进一步拆分的简单词，如 apple, book, develop, culture

2. 【重要】split 字段：无论是复合词还是派生词，只要能拆，都填到 split 数组里
   每个部分必须包含：
   - part: 当前看到的这部分（如 sports、-ing、-ness、run）
   - meaning: 这部分的意思（如 "n. 运动"、"动名词后缀，将动词转为名词"）
   - original: 这部分的原词是什么（如 sport）。对词缀来说，original 填 part 本身（如 -ing 的 original 就是 -ing）
   - original_meaning: 原词的意思。词缀的 original_meaning 填 part 的含义
   - transform: 从原词怎么变成 part 的，用通俗中文说清楚变形规则（如 "加 -s 变复数"、"去掉词尾 e 加 -ing"、"原形不变"、"本身是后缀，无变形"）
   - explain: 这部分在整体单词中的作用或关联说明

   【时态标注规则】当词根是动词、后缀涉及时态变化时，meaning 和 transform 必须明确标出时态名称：
   - -ing 后缀：meaning 写"现在分词/动名词后缀，表示进行时或动作本身"，transform 写"加 -ing 构成现在分词"
   - -ed 后缀：meaning 写"过去式/过去分词后缀，表示动作已完成"，transform 写"加 -ed 构成过去式"
   - -s 后缀（动词）：meaning 写"第三人称单数后缀"，transform 写"加 -s 构成第三人称单数"
   - -s 后缀（名词）：meaning 写"复数后缀"，transform 写"加 -s 变复数"
   示例：running 的 -ing 应标注为"现在分词/动名词后缀"，而非仅写"动名词后缀"

   【后缀原词规则】后缀/前缀如果源自或形似某独立英语单词，必须把 original 填为该独立单词、original_meaning 填为该单词的意思，让原词意思显示出来（只有 original_meaning 与 meaning 不同时前端才会展示原词意思）：
   - -ful 源自 full：original="full", original_meaning="adj. 满的", transform="缩略为后缀 -ful"
   - -ly 源自 like：original="like", original_meaning="adj. 相似的", transform="缩略为后缀 -ly"
   - -less 形似 less：original="less", original_meaning="adj. 较少的", transform="缩略为后缀 -less，表示'无、没有'"（助记：少到没有）
   - -ship 形似 shape（关系/形态）：original="shape", original_meaning="n. 形态，形态", transform="演变为后缀 -ship"
   - -ness、-ment、-ing、-er 等纯后缀无对应独立词：original 填 part 本身，original_meaning 填后缀含义
   示例：careful 的 -ful 应为 original="full", original_meaning="adj. 满的"，让学生看到 -ful 来自 full（满的）

3. 派生词拆解示例（必须把词根和词缀都放进 split，注意时态标注和后缀原词）：
   - running: split = [{part:"run", original:"run", original_meaning:"v. 跑", meaning:"v. 跑", transform:"双写词尾 n 再加 -ing（短元音+辅音结尾规则）", explain:"词根"}, {part:"-ing", original:"-ing", original_meaning:"现在分词/动名词后缀", meaning:"现在分词/动名词后缀，表示进行时或动作本身", transform:"加 -ing 构成现在分词", explain:"把动词变成名词或进行时态，表示'跑'这件事/正在跑"}]
   - happiness: split = [{part:"happy", original:"happy", original_meaning:"adj. 快乐的", meaning:"adj. 快乐的", transform:"把 y 改成 i", explain:"词根"}, {part:"-ness", original:"-ness", original_meaning:"名词后缀，表示状态", meaning:"名词后缀，表示状态", transform:"本身是后缀，无变形", explain:"把形容词变成名词，表示'快乐的状态'"}]
   - teacher: split = [{part:"teach", original:"teach", original_meaning:"v. 教", meaning:"v. 教", transform:"原形不变", explain:"词根"}, {part:"-er", original:"-er", original_meaning:"名词后缀，表示做某事的人", meaning:"名词后缀，表示做某事的人", transform:"本身是后缀，无变形", explain:"把动词变成名词，表示'教书的人'即老师"}]
   - careful: split = [{part:"care", original:"care", original_meaning:"n. 小心，关怀", meaning:"n. 小心，关怀", transform:"原形不变，直接加后缀", explain:"词根"}, {part:"-ful", original:"full", original_meaning:"adj. 满的", meaning:"形容词后缀，表示'充满...的'", transform:"缩略为后缀 -ful", explain:"源自 full（满的），把名词变成形容词，表示'充满小心的'"}]
   - success: split = [{part:"suc-", original:"sub-", original_meaning:"前缀，表示'在...之后'", meaning:"前缀，表示'在...之后'（sub- 的变体）", transform:"sub- 在 c 前同化为 suc-", explain:"前缀，表示'紧随其后'"}, {part:"cess", original:"cess", original_meaning:"词根，表示'走'", meaning:"词根，表示'走、行'", transform:"原形不变", explain:"词根，'紧跟其后走'引申为'成功'"}]
   - suggest: split = [{part:"sug-", original:"sub-", original_meaning:"前缀，表示'在...之下'", meaning:"前缀，表示'在...下面'（sub- 的变体）", transform:"sub- 在 g 前同化为 sug-", explain:"前缀，表示'从下面托起'"}, {part:"gest", original:"gest", original_meaning:"词根，表示'带来'", meaning:"词根，表示'带来、携带'", transform:"原形不变", explain:"词根，'从下面带来'引申为'提出建议'"}]
   - important: split = [{part:"im-", original:"in-", original_meaning:"前缀，表示'进入'", meaning:"前缀，表示'进入'（in- 在 p 前的变体）", transform:"in- 变为 im-（在 p 前同化）", explain:"前缀，表示'带入'"}, {part:"port", original:"port", original_meaning:"v. 搬运", meaning:"v. 搬运，携带", transform:"原形不变", explain:"词根，'带入分量'引申为'重要的'"}, {part:"-ant", original:"-ant", original_meaning:"形容词后缀", meaning:"形容词后缀，表示'具有...性质的'", transform:"本身是后缀，无变形", explain:"把动词变成形容词"}]
   - education: split = [{part:"educate", original:"educate", original_meaning:"v. 教育", meaning:"v. 教育", transform:"去掉词尾 e", explain:"词根"}, {part:"-ion", original:"-ion", original_meaning:"名词后缀", meaning:"名词后缀，表示行为或状态", transform:"本身是后缀，无变形", explain:"把动词变成名词"}]
   - develop: type="基础词", split=[], mnemonic="develop 来自法语 développer（展开）。de- 是法语残留，不是英语前缀，所以 develop 是基础词不拆解。"

4. 复合词拆解示例（sports meeting）：
   - sports: 原词 sport（n. 运动），变形规则"加 -s 变复数"，复数作定语修饰 meeting
   - meeting: 原词 meet（v. 遇见），变形规则"去掉词尾不发音的 e，加 -ing"，变成名词表示"聚会"

5. morph 字段：派生词可以额外在 morph 里再标注一遍词根词缀（type: root/prefix/suffix），作为补充视角；复合词和基础词的 morph 留空

6. mnemonic 字段（记忆方法）：必须给出 1-2 句好记的中文记忆口诀，可以是：
   - 联想法：把单词各部分串成一句话或画面（如 classroom = class + room = "班级"的"房间" = 教室）
   - 谐音法：利用发音联想（如 ambulance "俺不能死" = 救护车）
   - 词根法：通过词根词缀逻辑推导（如 happiness = happy 快乐 + -ness 状态 = 快乐的状态）
   - 对比法：和已学过的词对比记忆
   选最适合这个词的方法，让学生一看就记住。

7. 基础词（无法拆解的）：split 和 morph 都留空，但 mnemonic 必须给出记忆方法

8. 【变形数据 tenses】所有单词都要提供 tenses 字段，根据词性提供不同的变形信息：
   【动词】提供五种形态：base(原形), third_singular(第三人称单数), past(过去式), past_participle(过去分词), present_participle(现在分词)
   示例：run 的 tenses = {base:"run", third_singular:"runs", past:"ran", past_participle:"run", present_participle:"running", inflection_type:"tense"}
   注意不规则动词（如 go→went→gone, run→ran→run, write→wrote→written）要给出正确的不规则变形。

   【形容词】提供级变化：positive(原级), comparative(比较级), superlative(最高级)
   示例：good 的 tenses = {positive:"good", comparative:"better", superlative:"best", inflection_type:"degree"}
   示例：big 的 tenses = {positive:"big", comparative:"bigger", superlative:"biggest", inflection_type:"degree"}

   【名词】提供复数变形：singular(单数), plural(复数)
   示例：book 的 tenses = {singular:"book", plural:"books", inflection_type:"plural"}
   示例：child 的 tenses = {singular:"child", plural:"children", inflection_type:"plural"}

   【副词/介词/连词等】tenses 留空 null
   必须包含 inflection_type 字段（"tense"/"degree"/"plural"），用于前端区分按钮类型。

9. 提供2个实用例句，例句尽量使用江西专升本英语考试中常见的语境和话题（如学习、教育、大学生活、职业发展、社会热点等），难度适中。例句中的英文必须语法正确、表达自然。
   【例句翻译要求】中文翻译必须准确、通顺、符合中文表达习惯，不能逐词机翻。翻译要传达英文句子的完整含义，而不是逐字对应。

10. 【强制规则】以下字段必须非空：
    - meaning：必须包含词性标注（n./v./adj./adv./prep./conj. 等）和中文释义，如 "n. 苹果"、"v. 跑"。即使是生僻词也要给出释义，不能返回空字符串。翻译必须准确，不能编造意思。
    【释义精简规则】meaning 只给1-2个最常用的专升本考试释义，不要给太多释义。最常考的释义放在最前面。
    例如：good → "adj. 好的，令人满意的"（不要给"善行"等生僻义）
         worse → "adj. 更坏的，更差的"（不要给"更坏的事物"等生僻义）
         take → "v. 拿，取"（不要给太多释义）
    - phonetic：必须给出音标，如 "/æpl/"。不确定时给出最接近的音标。
    - mnemonic：必须给出记忆方法，不能为空。
    如果单词是短语/词组（如 "sports meeting"、"take care of"），meaning 给出整体释义，split 拆解每个组成单词。

11. 【短语/词组处理】如果输入是短语或词组（包含空格），按复合词处理：
    - meaning 给出整个短语最常用的中文意思，只给1个最常用释义。如 "take care of" → "v. 照顾"，"the best" → "最好的（人或物）"，"have a good knowledge of" → "v. 精通，掌握"
    - split 把每个独立单词拆开，标注原形和变形
    - type 填"复合词"
    - 短语的翻译必须准确反映短语的整体含义，不能逐词翻译。如果不确定短语的意思，给出最常见的用法释义。

12. 【拆解原则】split 必须基于单词的实际构成来拆解：
    - 只拆解确实由多个部分组成的词（复合词拆成独立单词，派生词拆成词根+词缀）
    - 基础词（无法拆分的简单词，如 apple, book, water）split 留空数组 []，不要强行拆解
    - 不要把单词的字母随意分割，每个 part 必须是有意义的英语词素（独立单词或词缀）

请严格返回以下JSON格式，不要包含任何其他文字：
{
    "phonetic": "音标",
    "meaning": "词性和释义",
    "type": "复合词/派生词/基础词",
    "split": [
        {
            "part": "当前部分",
            "meaning": "这部分的意思",
            "original": "原词",
            "original_meaning": "原词的意思",
            "transform": "变形规则，通俗中文说明怎么从原词变过来",
            "explain": "这部分在整体中的作用说明"
        }
    ],
    "morph": [{"type": "root/prefix/suffix", "word": "词根或词缀", "meaning": "含义"}],
    "mnemonic": "1-2句中文记忆口诀",
    "tenses": {"inflection_type": "tense/degree/plural", "...": "根据类型填入对应字段"},
    "examples": [{"en": "英文例句", "zh": "中文翻译"}]
}"""

        # 构建用户提示词
        user_prompt = f"请分析以下英语单词或词组：{word}"

        # 请求消息体（OpenAI兼容格式）
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.3,  # 较低的温度保证输出稳定
            # 推理模型需要大量token用于reasoning_content，4000不够
            'max_tokens': 16000,
            # 注意：不使用response_format，部分推理模型不支持，改用提示词约束
        }

        # 请求头
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

        # 构建请求URL
        url = f'{self.base_url.rstrip("/")}/chat/completions'

        try:
            # 发送请求
            response = requests.post(url, json=payload, headers=headers, timeout=120)  # 推理模型需要更长时间
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Agnes AI请求失败: {str(e)}")

        # 解析AI返回的内容
        try:
            content = result['choices'][0]['message']['content']
            # 尝试直接解析JSON
            analysis = json.loads(content)
            # 规范化数据结构，确保所有字段都存在
            return self._normalize_result(analysis, word)
        except (KeyError, json.JSONDecodeError) as e:
            # 如果解析失败，尝试从文本中提取JSON
            try:
                analysis = self._extract_json_from_text(content if 'content' in dir() else '')
                return self._normalize_result(analysis, word)
            except Exception:
                raise RuntimeError(f"Agnes AI返回数据解析失败: {str(e)}")

    def _normalize_result(self, data, word):
        """
        规范化AI返回的结果，确保所有字段都存在且有默认值

        参数:
            data: AI返回的原始数据
            word: 原始单词

        返回:
            dict: 规范化后的结果
        """
        # 确保type字段是有效值
        word_type = data.get('type', '基础词')
        if word_type not in ('复合词', '派生词', '基础词'):
            word_type = '基础词'

        # 规范化 split 数组，确保每项都有新字段 original/original_meaning/transform
        raw_split = data.get('split', []) if isinstance(data.get('split'), list) else []
        split_normalized = []
        for item in raw_split:
            if not isinstance(item, dict):
                continue
            part = item.get('part', '')
            split_normalized.append({
                'part': part,
                'meaning': item.get('meaning', ''),
                # 新字段：原词与变形规则（兼容旧数据，缺失时给出合理默认值）
                'original': item.get('original', '') or part,
                'original_meaning': item.get('original_meaning', '') or item.get('meaning', ''),
                'transform': item.get('transform', '') or ('原形不变' if item.get('original', '') == part else ''),
                'explain': item.get('explain', ''),
            })

        # 规范化 tenses 字段：支持动词时态、形容词级变化、名词复数
        raw_tenses = data.get('tenses')
        tenses_normalized = None
        if isinstance(raw_tenses, dict):
            infl_type = raw_tenses.get('inflection_type', '')
            # 动词时态
            if raw_tenses.get('base') or infl_type == 'tense':
                tenses_normalized = {
                    'base': raw_tenses.get('base', ''),
                    'third_singular': raw_tenses.get('third_singular', ''),
                    'past': raw_tenses.get('past', ''),
                    'past_participle': raw_tenses.get('past_participle', ''),
                    'present_participle': raw_tenses.get('present_participle', ''),
                    'inflection_type': 'tense',
                }
            # 形容词级变化
            elif raw_tenses.get('positive') or raw_tenses.get('comparative') or raw_tenses.get('superlative') or infl_type == 'degree':
                tenses_normalized = {
                    'positive': raw_tenses.get('positive', ''),
                    'comparative': raw_tenses.get('comparative', ''),
                    'superlative': raw_tenses.get('superlative', ''),
                    'inflection_type': 'degree',
                }
            # 名词复数
            elif raw_tenses.get('singular') or raw_tenses.get('plural') or infl_type == 'plural':
                tenses_normalized = {
                    'singular': raw_tenses.get('singular', ''),
                    'plural': raw_tenses.get('plural', ''),
                    'inflection_type': 'plural',
                }

        # meaning 兜底：AI 偶尔返回空释义，此时尝试从 split 推断，仍为空则给提示
        meaning = data.get('meaning', '') or ''
        if not meaning.strip():
            if split_normalized:
                # 从拆解部分拼接一个基础释义
                parts_meaning = '；'.join(
                    f"{s.get('part','')}: {s.get('meaning','')}" for s in split_normalized if s.get('meaning')
                )
                meaning = parts_meaning or f'{word}（暂无释义，可点击编辑补充）'
            else:
                meaning = f'{word}（暂无释义，可点击编辑补充）'

        # phonetic 兜底
        phonetic = data.get('phonetic', '') or ''
        if not phonetic.strip():
            phonetic = ''

        return {
            'phonetic': phonetic,
            'meaning': meaning,
            'type': word_type,
            'split': split_normalized,
            'morph': data.get('morph', []) if isinstance(data.get('morph'), list) else [],
            'mnemonic': data.get('mnemonic', '') or '',
            'examples': data.get('examples', []) if isinstance(data.get('examples'), list) else [],
            'tenses': tenses_normalized,
        }

    def generate_examples(self, word, meaning=''):
        """
        用AI为单词生成2个高质量例句（比完整分析更轻量，速度更快）

        参数:
            word: 单词
            meaning: 单词释义（帮助AI理解词义上下文）

        返回:
            list: [{en, zh}, ...] 例句列表
        """
        if not self.is_available():
            return []

        system_prompt = """你是一位资深的大学英语教师，专门为江西专升本英语考试编写例句。

【核心要求】
1. 生成2个例句，两个例句的句式结构、场景、话题、主语必须完全不同
   - 禁止两个例句使用相同的主语开头（如不能两个都是"She..."或两个都是"The..."）
   - 禁止两个例句使用相同的句型（如不能两个都是陈述句）
   - 两个例句必须展示该单词的不同用法或不同语境
   - 建议组合示例：
     * 一个疑问句 + 一个陈述句
     * 一个感叹句 + 一个条件句
     * 一个被动语态 + 一个主动语态
     * 一个日常对话 + 一个正式书面语

2. 【主语多样化】两个例句绝不能以相同单词开头。请从以下主语中选不同的：
   避免"She"和"The"被过度使用。尽量使用更多样的主语，如：
   I, You, He, They, We, Many people, Students, The teacher, My friend, Nobody, Everyone, It, There, What, How, If, Although, Driving, Reading, Learning...

3. 例句难度：大学英语三级水平，词汇量控制在四级以内
4. 例句必须语法正确、表达自然地道，像真实英语文章或对话中的句子
5. 例句内容要有实际意义和信息量，讲述一个小故事或描述一个具体场景
6. 例句应该展示该单词最常见的用法和搭配
7. 中文翻译必须准确、通顺、符合中文表达习惯，不能逐词机翻
8. 如果是短语（如look up to），例句必须正确使用该短语的语法形式

【话题方向】两个例句应选择不同的话题领域：
学习与教育、大学生活、职业发展、社会热点、文化交流、健康生活、科技发展、环境保护、日常生活、旅行、购物、运动

【严格禁止事项】
- 禁止使用以下模板句式：
  * "X is very important to us/in our life/in modern society"
  * "I learned a lot from this X"
  * "X has changed our lives"
  * "We should pay more attention to X"
  * "It is important to X"
  * "Students should learn how to X"
  * "X plays an important role in Y"
  * "We should do/try our best to X"
  * "It is necessary to X"
  * "X is one of the most important Y"
- 禁止例句之间句式雷同（只换单词不换结构）
- 禁止中文翻译逐字对应英文，必须意译
- 禁止两个例句讨论相同话题
- 禁止例句过于简单空洞（如"She is a good student."），必须有具体细节

严格返回以下JSON格式，不要包含任何其他文字：
{"examples": [{"en": "英文例句", "zh": "中文翻译"}, {"en": "英文例句", "zh": "中文翻译"}]}"""

        meaning_hint = f'\n该单词的释义是：{meaning}' if meaning else ''
        user_prompt = f'请为单词或短语 "{word}" 生成2个高质量、句式完全不同的例句。{meaning_hint}'

        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': 0.8,
            'max_tokens': 2000,
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

        url = f'{self.base_url.rstrip("/")}/chat/completions'

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            result = response.json()

            content = self._extract_response_content(result)
            if not content:
                return []

            # 清理推理标签和markdown包裹
            content = self._clean_model_output(content)
            if not content:
                return []

            # 尝试直接解析JSON，失败则从文本中提取
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = self._extract_json_from_text(content)

            examples = data.get('examples', [])
            if isinstance(examples, list) and examples:
                valid = []
                for ex in examples[:2]:
                    if isinstance(ex, dict) and ex.get('en') and ex.get('zh'):
                        valid.append({'en': ex['en'].strip(), 'zh': ex['zh'].strip()})
                return valid
        except Exception as e:
            print(f'[ai] generate_examples fail({word}): {e}')

        return []

    def _extract_json_from_text(self, text):
        """
        从文本中提取JSON内容（当模型不直接返回JSON时使用）

        参数:
            text: 可能包含JSON的文本

        返回:
            dict: 解析出的字典
        """
        if not text:
            raise ValueError("文本为空")

        # 尝试找到JSON块的开始和结束
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            return json.loads(json_str)

        raise ValueError("文本中未找到有效的JSON内容")

    def _extract_response_content(self, result):
        """
        从AI响应中提取实际内容，兼容推理模型的多种返回格式

        推理模型（如 agnes-2.0-flash、DeepSeek-R1 等）可能：
        1. content 字段为空，实际回答在 reasoning_content 中
        2. content 包含 <think>...</think> 推理过程，实际答案在标签外
        3. content 直接是正常文本

        参数:
            result: API返回的完整JSON响应

        返回:
            str: 提取出的实际内容（可能为空字符串）
        """
        try:
            message = result['choices'][0]['message']
        except (KeyError, IndexError, TypeError):
            return ''

        # 优先取 content，如果为空则取 reasoning_content
        content = message.get('content') or ''
        if not content.strip():
            # content 为空，尝试 reasoning_content
            reasoning = message.get('reasoning_content') or ''
            if reasoning.strip():
                print(f"[AI] content为空，使用reasoning_content，长度: {len(reasoning)}")
                return reasoning
            # 两者都为空
            return ''

        return content

    def _clean_model_output(self, content):
        """
        清理模型输出文本，去除推理标签和markdown包裹

        参数:
            content: 原始内容

        返回:
            str: 清理后的内容
        """
        import re
        cleaned = content.strip()

        # 去除 <think>...</think> 标签及内容（推理模型的思考过程）
        cleaned = re.sub(r'<think>.*?</think>', '', cleaned, flags=re.DOTALL)
        # 去除残留的 <think> 或 </think> 标签
        cleaned = cleaned.replace('<think>', '').replace('</think>', '')
        cleaned = cleaned.strip()

        # 去除 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）
        if cleaned.startswith('```'):
            lines = cleaned.split('\n')
            if len(lines) > 1:
                lines = lines[1:]  # 去掉第一行 ```json 或 ```
            # 去掉最后的 ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            cleaned = '\n'.join(lines).strip()

        return cleaned

    def _compress_image_base64(self, image_base64, max_size=1568):
        """
        压缩图片base64数据，确保不超过API限制
        使用Pillow进行压缩：限制最长边为max_size像素，JPEG质量85

        参数:
            image_base64: 原始base64编码（可含data:image前缀）
            max_size: 最长边像素上限（OpenAI建议1568px）

        返回:
            str: 压缩后的data URL
        """
        try:
            from PIL import Image
        except ImportError:
            # 没装Pillow，直接返回原始数据
            if ',' in image_base64 and image_base64.startswith('data:'):
                return image_base64
            return f'data:image/jpeg;base64,{image_base64}'

        # 提取纯base64数据
        if ',' in image_base64 and image_base64.startswith('data:'):
            header, raw_b64 = image_base64.split(',', 1)
        else:
            raw_b64 = image_base64

        try:
            raw_bytes = base64.b64decode(raw_b64)
            img = Image.open(io.BytesIO(raw_bytes))

            # 转为RGB（去除alpha通道）
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            # 按比例缩小，最长边不超过max_size
            w, h = img.size
            if max(w, h) > max_size:
                if w >= h:
                    new_w = max_size
                    new_h = int(h * max_size / w)
                else:
                    new_h = max_size
                    new_w = int(w * max_size / h)
                img = img.resize((new_w, new_h), Image.LANCZOS)

            # 保存为JPEG，质量95（提高质量保证文字清晰）
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=95)
            compressed_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            original_kb = len(raw_bytes) / 1024
            compressed_kb = len(buf.getvalue()) / 1024
            print(f"[AI识别] 图片压缩: {original_kb:.0f}KB -> {compressed_kb:.0f}KB")

            return f'data:image/jpeg;base64,{compressed_b64}'
        except Exception as e:
            print(f"[AI识别] 图片压缩失败，使用原始数据: {e}")
            if ',' in image_base64 and image_base64.startswith('data:'):
                return image_base64
            return f'data:image/jpeg;base64,{image_base64}'

    def recognize_image(self, image_base64):
        """
        用AI视觉模型识别图片中的英语单词和中文释义

        参数:
            image_base64: 图片的base64编码（可含data:image前缀）

        返回:
            list[dict]: 识别到的单词列表，每项 {word, meaning}
        """
        if not self.is_available():
            raise RuntimeError('Agnes AI API Key未配置')

        # 压缩图片，减少请求体积
        image_data_url = self._compress_image_base64(image_base64, max_size=1568)

        # 构建提示词
        system_prompt = """你是一个英语单词识别助手。用户会上传英语课本、单词表或练习册的图片，你需要识别图片中所有的英语单词及其对应的中文释义。

图片中可能包含：
1. 印刷体单词（通常带有序号，如 918. coverage 新闻报道）
2. 手写的单词和笔记（蓝色或黑色笔迹，可能不太清晰）
3. 手写的补充词汇、形近词标注等

请严格按以下JSON数组格式返回，不要包含任何其他文字：
[
    {"word": "apple", "meaning": "n. 苹果"},
    {"word": "beautiful", "meaning": "adj. 美丽的"}
]

规则：
1. word 字段只保留英文单词或词组（小写），如 "apple"、"sports meeting"
2. meaning 字段保留图片中对应的中文释义，包含词性标注（如 n./v./adj./adv. 等）
3. 如果图片中某单词没有标注中文释义，meaning 填空字符串 ""
4. 忽略图片中的句子、段落、页码、标题等非单词内容
5. 去除重复的单词
6. 必须识别图片中的手写单词！手写单词也是用户需要学习的词汇
7. 如果手写单词看不清，请根据上下文和词形智能推测最可能的单词
8. 如果手写的是补充词汇或形近词（如chef旁边写了chief），也要识别出来
9. 序号不需要保留在word字段中
10. 如果图片中没有英文单词，返回空数组 []"""

        # 请求消息体（OpenAI视觉模型格式）
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': [
                    {'type': 'text', 'text': '请识别这张图片中的所有英语单词及其中文释义。'},
                    {'type': 'image_url', 'image_url': {'url': image_data_url}},
                ]},
            ],
            'temperature': 0.1,
            # 推理模型(agnes-2.0-flash)需要大量token用于reasoning_content，
            # 实测识别5个单词推理用~3000 tokens + 正式回答~80 tokens
            # 16000足够识别一页单词(约30-50个)
            'max_tokens': 16000,
        }

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }

        url = f'{self.base_url.rstrip("/")}/chat/completions'

        try:
            print(f"[AI识别] 发送请求到 {url}，模型: {self.model}")
            response = requests.post(url, json=payload, headers=headers, timeout=120)
        except requests.Timeout:
            raise RuntimeError('AI视觉识别请求超时（120秒），请稍后重试')
        except requests.ConnectionError as e:
            raise RuntimeError(f'AI视觉识别连接失败: {str(e)}')
        except requests.RequestException as e:
            raise RuntimeError(f"AI视觉识别请求失败: {str(e)}")

        # 检查HTTP状态码，捕获详细的API错误信息
        if response.status_code != 200:
            error_detail = ''
            try:
                error_data = response.json()
                if 'error' in error_data:
                    err_obj = error_data['error']
                    error_detail = err_obj.get('message', '') if isinstance(err_obj, dict) else str(err_obj)
                else:
                    error_detail = response.text[:500]
            except Exception:
                error_detail = response.text[:500] if response.text else '无响应内容'

            print(f"[AI识别] API返回错误 {response.status_code}: {error_detail}")
            raise RuntimeError(f'AI识别失败(HTTP {response.status_code}): {error_detail}')

        try:
            result = response.json()
        except json.JSONDecodeError:
            print(f"[AI识别] 响应不是有效JSON: {response.text[:500]}")
            raise RuntimeError('AI视觉识别返回数据格式错误')

        # 检查API是否返回了错误对象
        if 'error' in result:
            err_msg = result['error'].get('message', '') if isinstance(result['error'], dict) else str(result['error'])
            print(f"[AI识别] API返回错误对象: {err_msg}")
            raise RuntimeError(f'AI识别失败: {err_msg}')

        # 推理模型（如 agnes-2.0-flash）可能将实际回答放在 reasoning_content 中，
        # 或者 content 为空、包含 <think> 标签。需要兼容多种情况。
        content = self._extract_response_content(result)
        if not content:
            print(f"[AI识别] content和reasoning_content均为空，完整响应: {json.dumps(result, ensure_ascii=False)[:800]}")
            raise RuntimeError('AI视觉识别返回数据解析失败：AI返回内容为空')

        print(f"[AI识别] 获取到内容，长度: {len(content)}，前100字符: {content[:100]}")

        # 清理内容：去除 <think> 标签、markdown代码块标记、首尾空白等
        cleaned = self._clean_model_output(content)

        # 尝试直接解析JSON数组
        try:
            words = json.loads(cleaned)
            if isinstance(words, list):
                return words
            if isinstance(words, dict) and 'words' in words:
                return words['words']
            return []
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取JSON数组（找最外层的 [ ] ）
        try:
            start = cleaned.find('[')
            end = cleaned.rfind(']')
            if start != -1 and end != -1 and end > start:
                words = json.loads(cleaned[start:end + 1])
                return words if isinstance(words, list) else []
        except json.JSONDecodeError:
            pass

        # 尝试逐行提取（某些模型会每行一个JSON对象）
        try:
            words = []
            for line in cleaned.split('\n'):
                line = line.strip().rstrip(',')
                if line.startswith('{') and line.endswith('}'):
                    obj = json.loads(line)
                    if isinstance(obj, dict) and 'word' in obj:
                        words.append(obj)
            if words:
                return words
        except json.JSONDecodeError:
            pass

        # 所有解析方式均失败，把原始内容附加到错误信息中，方便诊断
        print(f"[AI识别] 解析失败，原始内容前500字符: {content[:500]}")
        raise RuntimeError(f'AI视觉识别返回数据解析失败。AI原始返回(前300字): {content[:300]}')
