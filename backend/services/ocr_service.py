"""
百度OCR服务模块
使用百度智能云通用文字识别高精度版，识别图片中的英文单词
"""
import base64
import json
import os
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
    # 全局每月最大调用次数（所有用户共享）
    GLOBAL_MONTHLY_LIMIT = 800
    # 普通用户每月调用次数上限（管理员不受此限制，但仍受全局上限约束）
    USER_MONTHLY_LIMIT = 50
    # 调用次数记录文件
    USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'ocr_usage.json')

    def __init__(self):
        """初始化OCR服务"""
        self.api_key = Config.BAIDU_OCR_API_KEY
        self.secret_key = Config.BAIDU_OCR_SECRET_KEY
        # 缓存的access_token及其过期时间
        self.access_token = None
        self.token_expire_time = 0

    def is_available(self, user_id=None, role='user'):
        """
        检查OCR服务是否可用
        - API Key已配置
        - 全局调用次数未超过800
        - 普通用户当月调用次数未超过50（管理员不受此限制）
        """
        if not (self.api_key and self.secret_key):
            return False
        global_count, user_counts = self._get_usage()
        # 检查全局限额
        if global_count >= self.GLOBAL_MONTHLY_LIMIT:
            return False
        # 普通用户检查个人限额
        if role != 'admin' and user_id is not None:
            user_count = user_counts.get(str(user_id), 0)
            if user_count >= self.USER_MONTHLY_LIMIT:
                return False
        return True

    def _get_usage(self):
        """
        读取当月OCR调用记录
        返回: (全局调用次数, {user_id_str: count, ...})
        """
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        try:
            if os.path.exists(self.USAGE_FILE):
                with open(self.USAGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('month') == current_month:
                    return data.get('global_count', 0), data.get('users', {})
        except Exception:
            pass
        return 0, {}

    def _increment_usage(self, user_id=None, role='user'):
        """递增调用次数（全局+个人）"""
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        global_count, users = self._get_usage()
        global_count += 1
        uid_str = str(user_id) if user_id else 'anonymous'
        users[uid_str] = users.get(uid_str, 0) + 1
        try:
            os.makedirs(os.path.dirname(self.USAGE_FILE), exist_ok=True)
            with open(self.USAGE_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'month': current_month,
                    'global_count': global_count,
                    'users': users,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[OCR] 写入调用次数失败: {e}")
        print(f"[OCR] 当月调用: 全局 {global_count}/{self.GLOBAL_MONTHLY_LIMIT}, 用户{uid_str}({role}) {users[uid_str]}/{('∞' if role=='admin' else self.USER_MONTHLY_LIMIT)}")
        return global_count, users[uid_str]

    def get_usage_info(self, user_id=None, role='user'):
        """
        获取当月用量信息（供前端展示）
        返回全局用量和当前用户个人用量
        """
        global_count, users = self._get_usage()
        uid_str = str(user_id) if user_id else 'anonymous'
        user_count = users.get(uid_str, 0)
        user_limit = self.GLOBAL_MONTHLY_LIMIT if role == 'admin' else self.USER_MONTHLY_LIMIT
        return {
            'global_count': global_count,
            'global_limit': self.GLOBAL_MONTHLY_LIMIT,
            'global_remaining': max(0, self.GLOBAL_MONTHLY_LIMIT - global_count),
            'user_count': user_count,
            'user_limit': user_limit,
            'user_remaining': max(0, user_limit - user_count),
            'is_admin': role == 'admin',
        }

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

    def recognize(self, image_path=None, image_base64=None, user_id=None, role='user'):
        """
        识别图片中的文字，返回英文单词列表
        支持传入图片路径或base64编码的图片数据

        参数:
            image_path: 图片文件路径
            image_base64: 图片的base64编码（不含data:image前缀）
            user_id: 调用者用户ID（用于限额统计）
            role: 调用者角色（admin/user）

        返回:
            list[str]: 去重后的英文单词/词组列表
        """
        # 检查是否配置了API Key
        if not (self.api_key and self.secret_key):
            raise RuntimeError('百度OCR API Key未配置，请在环境变量中设置 BAIDU_OCR_API_KEY 和 BAIDU_OCR_SECRET_KEY')

        # 检查限额
        global_count, user_counts = self._get_usage()
        if global_count >= self.GLOBAL_MONTHLY_LIMIT:
            raise RuntimeError(f'当月全局OCR识别次数已达上限（{self.GLOBAL_MONTHLY_LIMIT}次），请下月再使用或切换到AI精准模式')
        if role != 'admin' and user_id is not None:
            user_count = user_counts.get(str(user_id), 0)
            if user_count >= self.USER_MONTHLY_LIMIT:
                raise RuntimeError(f'您当月OCR识别次数已达上限（{self.USER_MONTHLY_LIMIT}次），请下月再使用或切换到AI精准模式')

        # 获取access_token
        access_token = self.get_access_token()

        # 准备图片数据
        if image_path:
            # 从文件路径读取图片，先压缩再转base64
            image_data = self._compress_image(image_path)
        elif image_base64:
            # 直接使用传入的base64数据，压缩后使用
            # 去除可能存在的data:image前缀
            if ',' in image_base64 and image_base64.startswith('data:'):
                raw_b64 = image_base64.split(',', 1)[1]
            else:
                raw_b64 = image_base64
            image_data = self._compress_image_base64(raw_b64)
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
            # 注意：必须用 data= 而非 params=，否则image base64会被拼到URL里导致413
            response = requests.post(request_url, data=params, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"百度OCR请求失败: {str(e)}")

        # 检查接口返回是否有错误
        if 'error_code' in result:
            raise RuntimeError(f"百度OCR识别错误({result['error_code']}): {result.get('error_msg', '未知错误')}")

        # 识别成功，递增当月调用次数（全局+个人）
        self._increment_usage(user_id=user_id, role=role)

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

            # 保持每行原始识别结果，不自动拆分
            # OCR每行识别一条内容（单词或词组），原样保留
            words_in_line = line.split()
            if not words_in_line:
                continue

            phrase = ' '.join(words_in_line).lower()
            # 确保至少包含一个长度>=2的单词（过滤掉单个字母和纯标点）
            if any(len(w) >= 2 for w in words_in_line):
                if phrase not in seen:
                    seen.add(phrase)
                    result.append(phrase)

        return result

    def _compress_image(self, image_path, max_size=1920, quality=90):
        """
        压缩图片文件，返回base64编码
        百度OCR高精度版要求图片base64编码后不超过约4MB。
        过大的图片会导致HTTP 413错误，但分辨率太低会显著降低识别率。
        这里限制最长边1920px、JPEG质量90，在API限制内保留尽可能高的清晰度，
        以保证整页/密集单词本照片中的小字也能被识别出来。

        参数:
            image_path: 图片文件路径
            max_size: 最长边像素上限
            quality: JPEG质量（1-100）

        返回:
            str: 压缩后的base64编码（不含data:image前缀）
        """
        try:
            from PIL import Image, ImageOps, ImageEnhance
            import io

            img = Image.open(image_path)

            # 转到RGB（去除alpha通道）
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

            # 增强对比度 + 适度锐化，让文字更清晰（对偏暗/偏灰的拍照图片尤其有效）
            img = ImageOps.autocontrast(img, cutoff=2)
            img = ImageEnhance.Contrast(img).enhance(1.1)
            img = ImageEnhance.Sharpness(img).enhance(1.15)

            # 保存为JPEG，提高质量保证文字清晰
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=max(quality, 95))
            compressed_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            original_kb = os.path.getsize(image_path) / 1024
            compressed_kb = len(buf.getvalue()) / 1024
            print(f"[OCR] 图片压缩: {original_kb:.0f}KB -> {compressed_kb:.0f}KB")

            return compressed_b64
        except ImportError:
            # 没装Pillow，回退到原始方式
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            print(f"[OCR] 图片压缩失败，使用原始数据: {e}")
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')

    def _compress_image_base64(self, raw_b64, max_size=1920, quality=90):
        """
        压缩base64编码的图片，返回压缩后的base64

        参数:
            raw_b64: 原始base64编码（不含data:image前缀）
            max_size: 最长边像素上限
            quality: JPEG质量

        返回:
            str: 压缩后的base64编码
        """
        try:
            from PIL import Image, ImageOps, ImageEnhance
            import io

            raw_bytes = base64.b64decode(raw_b64)
            img = Image.open(io.BytesIO(raw_bytes))

            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            w, h = img.size
            if max(w, h) > max_size:
                if w >= h:
                    new_w = max_size
                    new_h = int(h * max_size / w)
                else:
                    new_h = max_size
                    new_w = int(w * max_size / h)
                img = img.resize((new_w, new_h), Image.LANCZOS)

            # 增强对比度 + 适度锐化，让文字更清晰
            img = ImageOps.autocontrast(img, cutoff=2)
            img = ImageEnhance.Contrast(img).enhance(1.1)
            img = ImageEnhance.Sharpness(img).enhance(1.15)

            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=max(quality, 95))
            compressed_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            original_kb = len(raw_bytes) / 1024
            compressed_kb = len(buf.getvalue()) / 1024
            print(f"[OCR] 图片压缩: {original_kb:.0f}KB -> {compressed_kb:.0f}KB")

            return compressed_b64
        except ImportError:
            return raw_b64
        except Exception as e:
            print(f"[OCR] 图片压缩失败，使用原始数据: {e}")
            return raw_b64
