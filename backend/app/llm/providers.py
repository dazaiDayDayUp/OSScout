"""
LLM Provider 具体实现

Kimi (Moonshot AI) 和 DeepSeek 都兼容 OpenAI API 格式，
因此共享一个 _OpenAICompatibleProvider 基类，只需切换 base_url 和模型名。
"""
from typing import Any

import openai

from app.core.logger import get_logger

from .base import LLMProvider
from .schemas import LLMMessage, LLMResponse, LLMUsage, ToolCall

logger = get_logger(__name__)


class _OpenAICompatibleProvider(LLMProvider):
    """
    兼容 OpenAI API 格式的 Provider 基类

    Kimi 和 DeepSeek 都提供了与 OpenAI 兼容的 REST API，
    因此可以用 openai.AsyncOpenAI 客户端统一接入，
    只需传入不同的 base_url 和 api_key 即可。
    """

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        super().__init__(provider_name, model)
        if not api_key:
            raise ValueError(
                f"{provider_name} 的 API Key 未配置，"
                f"请在 .env 文件中设置对应的环境变量"
            )
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        # 默认不支持 json_object 响应格式，子类可覆盖
        self.supports_json_mode = False

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """调用底层 OpenAI 兼容接口"""
        request_messages = []
        for msg in messages:
            req_msg: dict = {"role": msg.role, "content": msg.content}
            if msg.tool_calls is not None:
                req_msg["tool_calls"] = msg.tool_calls
            if msg.name is not None:
                req_msg["name"] = msg.name
            if msg.tool_call_id is not None:
                req_msg["tool_call_id"] = msg.tool_call_id
            # kimi-k2 系列：assistant tool_calls 消息需要 reasoning_content
            if msg.reasoning_content is not None:
                req_msg["reasoning_content"] = msg.reasoning_content
            request_messages.append(req_msg)

        call_kwargs = {
            "model": self.model,
            "messages": request_messages,
            "temperature": temperature,
            **kwargs,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens

        # 传入 tools 参数（Function Calling）
        if tools:
            call_kwargs["tools"] = tools
            # 强制启用 tool_choice="auto"，让模型自主决定是否调用工具
            call_kwargs.setdefault("tool_choice", "auto")

        try:
            completion = await self._client.chat.completions.create(
                **call_kwargs
            )
        except openai.APIError as e:
            logger.error(
                "LLM API 调用失败",
                provider=self.provider_name,
                model=self.model,
                error=str(e),
            )
            raise

        # 提取响应内容
        choice = completion.choices[0]
        content = choice.message.content or ""

        # 提取思考过程（kimi-k2 系列）
        reasoning_content = None
        if hasattr(choice.message, "reasoning_content"):
            reasoning_content = getattr(choice.message, "reasoning_content", None) or None

        # 仅在非结构化输出且没有 tool_calls 时，才允许从 reasoning_content fallback。
        # 原因：
        # 1. 结构化输出（chat_structured）要求严格的 JSON，reasoning_content 不能作为备选
        # 2. tool_calls 场景下 content 为空是正常的，不应被 reasoning_content 污染
        #    （第二轮对话需要传回原始的 reasoning_content，不能混到 content 中）
        is_structured = kwargs.get("response_format", {}).get("type") == "json_object"
        has_tool_calls = choice.message.tool_calls is not None
        if not content and not is_structured and not has_tool_calls and reasoning_content:
            logger.debug(
                "从 reasoning_content 提取内容（非结构化输出模式）",
                provider=self.provider_name,
                model=self.model,
            )
            content = reasoning_content

        # 提取 tool_calls（Function Calling）
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    type=tc.type or "function",
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in choice.message.tool_calls
            ]
            logger.info(
                "LLM 请求调用工具",
                provider=self.provider_name,
                model=self.model,
                tools=[tc.name for tc in tool_calls],
            )

        # 提取 token 用量（部分 Provider 可能不返回 usage）
        usage = completion.usage
        if usage:
            usage_obj = LLMUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            )
        else:
            usage_obj = LLMUsage()

        logger.debug(
            "LLM 调用完成",
            provider=self.provider_name,
            model=self.model,
            tokens=usage_obj.total_tokens,
            tool_calls=len(tool_calls) if tool_calls else 0,
        )

        return LLMResponse(
            content=content,
            usage=usage_obj,
            model=self.model,
            provider=self.provider_name,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )


class KimiProvider(_OpenAICompatibleProvider):
    """
    Kimi (Moonshot AI) Provider

    官网：https://platform.moonshot.cn/
    兼容 OpenAI API 格式，base_url 为 https://api.moonshot.cn/v1

    可用模型：
    - kimi-k2.6        : 思考模型，适合深度分析（强制 temperature=1.0）
    - moonshot-v1-8k   : 8K 上下文，适合简单任务
    - moonshot-v1-32k  : 32K 上下文，适合中等长度分析
    - moonshot-v1-128k : 128K 上下文，适合长文本分析
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        super().__init__(
            provider_name="kimi",
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        # kimi 支持 json_object 响应格式，可强制模型输出 JSON
        self.supports_json_mode = True

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Kimi 特定模型的温度修正

        kimi-k2.6 / kimi-k2.5 / kimi-k2-thinking 等思考模型
        强制要求 temperature=1.0，传入其他值会报 400 错误。
        这里自动修正并记录日志，避免业务代码需要关心这个限制。
        """
        # k2 系列思考模型强制 temperature=1.0（API 端最新限制）
        if self.model.startswith("kimi-k2") and temperature != 1.0:
            logger.debug(
                "kimi 思考模型 temperature 自动修正为 1.0",
                model=self.model,
                requested_temperature=temperature,
            )
            temperature = 1.0

        return await super().chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            **kwargs,
        )


class DeepSeekProvider(_OpenAICompatibleProvider):
    """
    DeepSeek Provider

    官网：https://platform.deepseek.com/
    兼容 OpenAI API 格式，base_url 为 https://api.deepseek.com/v1

    可用模型：
    - deepseek-v4-pro  : 深度推理模型，适合复杂分析任务
    - deepseek-chat    : 通用对话模型，适合大多数分析任务
    - deepseek-reasoner: 推理模型，适合需要深度思考的场景
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        super().__init__(
            provider_name="deepseek",
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
