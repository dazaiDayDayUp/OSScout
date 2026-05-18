"""
LLM 模块

为 OSScout 各 Agent 提供统一的 LLM 调用能力。

支持的 Provider：
- Kimi (Moonshot AI)
- DeepSeek

使用示例：
    from app.llm import get_llm_provider, LLMMessage

    provider = get_llm_provider()  # 使用默认配置
    response = await provider.chat([
        LLMMessage(role="system", content="你是一位专家"),
        LLMMessage(role="user", content="请分析..."),
    ])
    print(response.content)

    # 结构化输出
    from pydantic import BaseModel
    class AnalysisResult(BaseModel):
        score: int
        findings: list[str]

    result = await provider.chat_structured(
        messages=[...],
        output_schema=AnalysisResult,
    )
    print(result.score)
"""
from .base import LLMProvider
from .factory import get_llm_provider
from .schemas import LLMMessage, LLMResponse, LLMUsage, StructuredOutput

__all__ = [
    "LLMProvider",
    "get_llm_provider",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    "StructuredOutput",
]
