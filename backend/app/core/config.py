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

    # AI Provider 选择（vllm | anthropic）
    ai_provider: str = "vllm"
    ai_timeout_seconds: int = 90
    ai_auto_no_think: bool = True            # vLLM/Qwen 族：user text 自动补 /no_think
    ai_max_tokens_default: int = 512
    ai_max_tokens_extract_json: int = 1024
    ai_max_tokens_cap: int = 1536            # 死守 2048 - 512 prompt buffer
    ai_image_compress: bool = True
    ai_image_max_edge_px: int = 1280
    ai_image_jpeg_quality: int = 85          # 0~95

    # vLLM (OpenAI-compatible)
    vllm_base_url: str = "http://43.133.197.65:8000/v1"
    vllm_api_key: str = ""                   # 必须通过 env 注入
    vllm_model: str = "qwen3.6-27b"
    vllm_enable_thinking: bool = False
    # True 时请求体追加 chat_template_kwargs；切回阿里云百炼若被 400 拒绝可设 False
    vllm_enable_chat_template_kwargs: bool = True

    # 旧 Qwen 保留别名（回滚到阿里云百炼用；兼容老 env）
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.6-plus"
    qwen_enable_thinking: bool = False       # 已弃用，保留避免 env 报错

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # 文件上传
    upload_dir: str = "uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50MB

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
