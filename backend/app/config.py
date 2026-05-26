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
    kimi_model: str = "kimi-k2.6"

    # DeepSeek 配置
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"

    # 默认使用的 LLM Provider
    default_llm_provider: str = "kimi"  # 可选: kimi / deepseek
    default_llm_model: str = ""  # 为空时自动使用对应 provider 的默认模型

    # === GitHub ===
    github_token: str = ""  # 用于提高 API 限频

    # === Web 搜索 Fallback（Serper API） ===
    # Serper API Key: https://serper.dev/（每月 2500 次免费查询）
    serper_api_key: str = ""

    # === 邮件推送配置（FastAPI-Mail + QQ 邮箱 SMTP） ===
    # QQ 邮箱 SMTP 设置：
    #   SMTP 服务器：smtp.qq.com
    #   端口：465（SSL）或 587（TLS）
    #   密码：QQ 邮箱的「授权码」，不是登录密码
    #   获取方式：QQ 邮箱设置 → 账户 → 开启 SMTP 服务 → 获取授权码
    mail_username: str = ""           # QQ 邮箱地址，如 123456@qq.com
    mail_password: str = ""           # QQ 邮箱授权码（不是登录密码）
    mail_from: str = ""               # 发件人显示名称，默认与 mail_username 一致
    mail_server: str = "smtp.qq.com"  # SMTP 服务器地址
    mail_port: int = 465              # SMTP 端口（QQ 邮箱用 465 SSL）
    mail_starttls: bool = False       # 是否启用 STARTTLS（QQ 邮箱用 SSL，此项为 False）
    mail_ssl_tls: bool = True         # 是否启用 SSL/TLS（QQ 邮箱必须为 True）
    mail_use_credentials: bool = True # 是否需要认证
    mail_validate_certs: bool = True  # 是否验证 SSL 证书


# 全局配置实例，按需导入使用
settings = Settings()

# 将关键 Token 同步到 os.environ，供 MCP Server 子进程继承
# MCP Server 通过 stdio 启动，env={**os.environ} 复制父进程环境变量
if settings.github_token:
    os.environ["GITHUB_TOKEN"] = settings.github_token
if settings.serper_api_key:
    os.environ["SERPER_API_KEY"] = settings.serper_api_key
