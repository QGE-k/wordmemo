import os

# 本地开发：自动加载 .env 文件（部署到 Render 时无 .env，用平台环境变量，不影响）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # 没装 python-dotenv 也不影响运行


class Config:
    """应用配置类"""

    # 百度OCR配置（用户需填入自己的API Key）
    BAIDU_OCR_API_KEY = os.environ.get('BAIDU_OCR_API_KEY', '')
    BAIDU_OCR_SECRET_KEY = os.environ.get('BAIDU_OCR_SECRET_KEY', '')

    # Agnes AI配置（兼容OpenAI接口，用于单词拆解分析）
    # 部署到Render时，在环境变量里设置 AGNES_API_KEY
    AGNES_API_KEY = os.environ.get('AGNES_API_KEY', '')
    AGNES_BASE_URL = os.environ.get('AGNES_BASE_URL', 'https://apihub.agnes-ai.com/v1')
    AGNES_MODEL = os.environ.get('AGNES_MODEL', 'agnes-2.0-flash')  # 文本模型

    # 数据库配置
    # 优先使用环境变量 DATABASE_URL（Render的PostgreSQL会自动注入）
    # 本地开发默认用 SQLite
    DATABASE_URL = os.environ.get('DATABASE_URL', '')
    if DATABASE_URL:
        # Render的PostgreSQL URL格式是 postgres://，SQLAlchemy需要 postgresql://
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///wordmemo.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 上传文件配置
    UPLOAD_FOLDER = 'data/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB，限制上传文件大小
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

    # 应用密钥（用于session等），部署时务必在环境变量设置一个随机值
    SECRET_KEY = os.environ.get('SECRET_KEY', 'wordmemo-dev-secret-key-2024')
