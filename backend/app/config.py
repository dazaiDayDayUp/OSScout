"""
应用配置管理
使用 Pydantic Settings 从环境变量和 .env 文件读取配置
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 文件路径：基于本文件所在目录向上查找
# 确保无论从哪里启动 Python，都能找到正确的 .env
_CONFIG_DIR = Path(__file__).resolve().parent
_ENV_FILE = _CONFIG_DIR.parent / ".env"


class Settings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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

    # === LLM（Kimi + DeepSeek）===
    # Kimi (Moonshot AI) 配置
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"

    # DeepSeek 配置
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 默认使用的 LLM Provider
    default_llm_provider: str = "kimi"  # 可选: kimi / deepseek
    default_llm_model: str = ""  # 为空时自动使用对应 provider 的默认模型

    # === GitHub ===
    github_token: str = ""  # 用于提高 API 限频

    # === 搜索 ===
    serper_api_key: str = ""  # Google Search API


# 全局配置实例，按需导入使用
settings = Settings()

# 将关键 Token 同步到 os.environ，供 MCP Server 子进程继承
# MCP Server 通过 stdio 启动，env={**os.environ} 复制父进程环境变量
if settings.github_token:
    os.environ["GITHUB_TOKEN"] = settings.github_token
