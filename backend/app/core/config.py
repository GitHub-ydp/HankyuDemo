"""应用配置管理"""
from pydantic_settings import BaseSettings


DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://localhost:5177",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:5176",
    "http://127.0.0.1:5177",
    "http://[::1]:3000",
    "http://[::1]:5173",
    "http://[::1]:5174",
    "http://[::1]:5175",
    "http://[::1]:5176",
    "http://[::1]:5177",
]


class Settings(BaseSettings):
    # 应用
    app_name: str = "阪急阪神入札業務効率化システム"
    app_env: str = "development"
    debug: bool = True

    # 数据库
    database_url: str = "postgresql://postgres:postgres@localhost:5432/hankyu_hanshin"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = DEFAULT_CORS_ORIGINS

    # 邮箱 IMAP
    email_imap_host: str = "imap.qiye.aliyun.com"
    email_imap_port: int = 993
    email_address: str = ""
    email_password: str = ""

    # 通义千问 Qwen（阿里云百炼，OpenAI 兼容模式，支持多模态）
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.6-plus"
    qwen_enable_thinking: bool = False

    # Claude API
    anthropic_api_key: str = ""

    # 文件上传
    upload_dir: str = "uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
