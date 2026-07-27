"""
百度OCR服务模块
使用百度智能云通用文字识别高精度版，识别图片中的英文单词
"""
import base64
import re
import time
import requests
from config import Config


class OCRService:
    """百度OCR高精度版服务"""

    # 百度OAuth认证接口
    TOKEN_URL = 'https://aip.baidubce.com/oauth/2.0/token'
    # 百度高精度文字识别接口
    OCR_URL = 'https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic'

    def __init__(self):
        """初始化OCR服务"""
        self.api_key = Config.BAIDU_OCR_API_KEY
        self.secret_key = Config.BAIDU_OCR_SECRET_KEY
        # 缓存的access_token及其过期时间
        self.access_token = None
        self.token_expire_time = 0

    def is_available(self):
        """检查OCR服务是否可用（API Key是否已配置）"""
        return bool(self.api_key and self.secret_key)

    def get_access_token(self):
        """
        获取百度OCR的access_token
        百度API需要先获取token才能调用识别接口
        token有效期为30天，这里做了缓存处理
        """
        # 如果token未过期，直接返回缓存的token
        current_time = time.time()
        if self.access_token and current_time < self.token_expire_time:
            return self.access_token

        # 检查API Key是否配置
        if not self.api_key or not self.secret_key:
            raise RuntimeError('百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY')

        # 请求参数
        params = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.secret_key,
        }

        try:
            # 发送POST请求获取token
            response = requests.post(self.TOKEN_URL, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()

            if 'access_token' in result:
                self.access_token = result['access_token']
                # token有效期expires_in为秒数，提前1小时过期以避免边界问题
                expires_in = result.get('expires_in', 2592000)  # 默认30天
                self.token_expire_time = current_time + expires_in - 3600
                return self.access_token
            else:
                raise RuntimeError(f"获取百度OCR access_token失败: {result}")

        except requests.RequestException as e:
            raise RuntimeError(f"获取百度OCR access_token网络错误: {str(e)}")

    def recognize(self, image_path=None, image_base64=None):
        """
        识别图片中的文字，返回英文单词列表
        支持传入图片路径或base64编码的图片数据

        参数:
            image_path: 图片文件路径
            image_base64: 图片的base64编码（不含data:image前缀）

        返回:
            list[str]: 去重后的英文单词/词组列表
        """
        # 检查是否配置了API Key
        if not self.is_available():
            raise RuntimeError('百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY')

        # 获取access_token
        access_token = self.get_access_token()

        # 准备图片数据
        if image_path:
            # 从文件路径读取图片并转为base64
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
        elif image_base64:
            # 直接使用传入的base64数据
            # 去除可能存在的data:image前缀
            if ',' in image_base64 and image_base64.startswith('data:'):
                image_data = image_base64.split(',', 1)[1]
            else:
                image_data = image_base64
        else:
            raise ValueError('必须提供 image_path 或 image_base64 参数')

        # 请求百度OCR接口
        params = {
            'image': image_data,
            'language_type': 'ENG',  # 英文识别
        }

        # 构建带token的URL
        request_url = self.OCR_URL + '?access_token=' + access_token

        try:
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(request_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"百度OCR请求失败: {str(e)}")

        # 检查接口返回是否有错误
        if 'error_code' in result:
            raise RuntimeError(f"百度OCR识别错误({result['error_code']}): {result.get('error_msg', '未知错误')}")

        # 解析OCR结果，提取文字
        words_list = []
        if 'words_result' in result:
            for item in result['words_result']:
                line = item.get('words', '').strip()
                if line:
                    words_list.append(line)

        # 过滤并提取英文单词/词组
        filtered_words = self._extract_english_words(words_list)

        return filtered_words

    def _extract_english_words(self, lines):
        """
        从OCR识别的文本行中提取英文单词和词组
        过滤掉中文、标点符号、数字等

        参数:
            lines: OCR识别出的文本行列表

        返回:
            list[str]: 去重后的英文单词/词组列表
        """
        seen = set()
        result = []

        for line in lines:
            # 去除中文字符
            line = re.sub(r'[\u4e00-\u9fff]+', ' ', line)
            # 去除标点符号（保留字母、空格和连字符）
            line = re.sub(r"[^a-zA-Z\s\-']", ' ', line)
            # 去除多余空格
            line = line.strip()

            if not line:
                continue

            # 按空格分割，提取单词和词组
            # 如果一行有多个单词，可能是词组（如 "sports meeting"）
            # 也可能是多个独立单词
            # 这里将连续的英文字母组合作为单词或词组
            words_in_line = line.split()
            if not words_in_line:
                continue

            # 如果一行只有1-3个单词，作为词组保留
            if 1 <= len(words_in_line) <= 3:
                phrase = ' '.join(words_in_line).lower()
                # 确保至少包含一个长度>=2的单词（过滤掉单个字母）
                if any(len(w) >= 2 for w in words_in_line):
                    if phrase not in seen:
                        seen.add(phrase)
                        result.append(phrase)
            else:
                # 如果一行单词太多，可能是句子，拆分成单独的单词
                for word in words_in_line:
                    word = word.lower().strip("-'")
                    if len(word) >= 2 and word not in seen:
                        seen.add(word)
                        result.append(word)

        return result
