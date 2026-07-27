"""
Agnes AI 单词分析服务
兼容OpenAI接口，调用AI对单词进行词法分析、拆解
"""
import json
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

【核心原则】能拆解的单词都要拆，不要只拆复合词，派生词也要拆开给学生看。

分析要求：
1. 判断单词类型：
   - 复合词（compound）：由两个或以上独立单词组合而成，如 classroom = class + room
   - 派生词（derivative）：由词根+词缀构成，如 happiness = happy + -ness，running = run + -ing
   - 基础词（base）：无法进一步拆分的简单词，如 apple, book

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

8. 【动词时态】如果该单词是动词（或包含动词词性），必须提供 tenses 字段，列出该动词的五种形态。非动词（纯名词/形容词/副词等）tenses 留空 null。
   - base: 原形（动词原形）
   - third_singular: 第三人称单数形式
   - past: 过去式
   - past_participle: 过去分词
   - present_participle: 现在分词
   注意不规则动词（如 go→went→gone, run→ran→run, write→wrote→written）要给出正确的不规则变形。
   示例：run 的 tenses = {base:"run", third_singular:"runs", past:"ran", past_participle:"run", present_participle:"running"}

9. 提供2个实用例句，例句尽量使用江西专升本英语考试中常见的语境和话题（如学习、教育、大学生活、职业发展、社会热点等），难度适中。例句中的英文必须语法正确、表达自然。

10. 【强制规则】以下字段必须非空：
    - meaning：必须包含词性标注（n./v./adj./adv./prep./conj. 等）和中文释义，如 "n. 苹果"、"v. 跑"。即使是生僻词也要给出释义，不能返回空字符串。翻译必须准确，不能编造意思。
    - phonetic：必须给出音标，如 "/æpl/"。不确定时给出最接近的音标。
    - mnemonic：必须给出记忆方法，不能为空。
    如果单词是短语/词组（如 "sports meeting"、"take care of"），meaning 给出整体释义，split 拆解每个组成单词。

11. 【短语/词组处理】如果输入是短语或词组（包含空格），按复合词处理：
    - meaning 给出整个短语的意思，如 "take care of" → "v. 照顾，照料"
    - split 把每个独立单词拆开，标注原形和变形
    - type 填"复合词"

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
    "tenses": {"base": "原形", "third_singular": "第三人称单数", "past": "过去式", "past_participle": "过去分词", "present_participle": "现在分词"},
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
            'max_tokens': 4000,  # agnes-2.0-flash是推理模型，需要更多token
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

        # 规范化 tenses 字段（动词五种形态），非动词为 None
        raw_tenses = data.get('tenses')
        tenses_normalized = None
        if isinstance(raw_tenses, dict) and raw_tenses.get('base'):
            tenses_normalized = {
                'base': raw_tenses.get('base', ''),
                'third_singular': raw_tenses.get('third_singular', ''),
                'past': raw_tenses.get('past', ''),
                'past_participle': raw_tenses.get('past_participle', ''),
                'present_participle': raw_tenses.get('present_participle', ''),
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

        # 处理base64数据，确保格式正确
        if ',' in image_base64 and image_base64.startswith('data:'):
            image_data_url = image_base64
        else:
            image_data_url = f'data:image/jpeg;base64,{image_base64}'

        # 构建提示词
        system_prompt = """你是一个英语单词识别助手。用户会上传英语课本、单词表或练习册的图片，你需要识别图片中所有的英语单词及其对应的中文释义。

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
6. 如果图片中没有英文单词，返回空数组 []"""

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
            'max_tokens': 4000,
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
        except requests.RequestException as e:
            raise RuntimeError(f"AI视觉识别请求失败: {str(e)}")

        try:
            content = result['choices'][0]['message']['content']
            # 尝试直接解析JSON数组
            words = json.loads(content)
            if isinstance(words, list):
                return words
            # 如果返回的是字典，尝试提取
            if isinstance(words, dict) and 'words' in words:
                return words['words']
            return []
        except (KeyError, json.JSONDecodeError):
            # 尝试从文本中提取JSON数组
            try:
                start = content.find('[')
                end = content.rfind(']')
                if start != -1 and end != -1 and end > start:
                    words = json.loads(content[start:end + 1])
                    return words if isinstance(words, list) else []
            except Exception:
                pass
            raise RuntimeError('AI视觉识别返回数据解析失败')
