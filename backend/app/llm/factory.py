"""
LLM Provider 工厂

根据配置字符串创建对应的 Provider 实例，
业务代码通过 get_llm_provider() 获取 Provider，无需关心具体实现。
"""
from app.config import settings
from app.core.logger import get_logger

from .base import LLMProvider
from .providers import DeepSeekProvider, KimiProvider

logger = get_logger(__name__)

# 支持的 Provider 映射表
_PROVIDER_MAP = {
    "kimi": KimiProvider,
    "deepseek": DeepSeekProvider,
}


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """
    根据名称创建对应的 LLM Provider 实例

    Args:
        provider_name: Provider 名称，可选值：kimi / deepseek。
            为 None 时使用配置中的默认值。

    Returns:
        LLMProvider: 对应 Provider 的实例

    Raises:
        ValueError: 不支持的 Provider 名称，或缺少必要的配置
    """
    name = (provider_name or settings.default_llm_provider).lower().strip()

    if name not in _PROVIDER_MAP:
        supported = ", ".join(_PROVIDER_MAP.keys())
        raise ValueError(
            f"不支持的 LLM Provider: '{name}'。"
            f"当前支持: {supported}"
        )

    provider_class = _PROVIDER_MAP[name]

    if name == "kimi":
        api_key = settings.kimi_api_key
        base_url = settings.kimi_base_url
        model = settings.kimi_model
    elif name == "deepseek":
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
    else:
        # 理论上不会走到这里，因为前面已经校验过
        raise ValueError(f"未知的 Provider: {name}")

    logger.info(
        "创建 LLM Provider",
        provider=name,
        model=model,
        base_url=base_url,
    )

    return provider_class(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
