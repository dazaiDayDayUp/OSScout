"""
应用配置管理
使用 Pydantic Settings 从环境变量和 .env 文件读取配置
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量，避免报错
    )

    # === 应用基础配置 ===
    debug: bool = False
    log_level: str = "INFO"
    analysis_timeout: int = 300  # 分析任务超时时间（秒）

    # === 数据库 ===
    database_url: str = "postgresql+asyncpg://user:pass@localhost/osscout"

    # === Redis ===
    redis_url: str = "redis://localhost:6379/0"

    # === LLM ===
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_llm_provider: str = "anthropic"
    default_llm_model: str = "claude-3-5-sonnet-20241022"

    # === GitHub ===
    github_token: str = ""  # 用于提高 API 限频

    # === 搜索 ===
    serper_api_key: str = ""  # Google Search API


# 全局配置实例，按需导入使用
settings = Settings()
