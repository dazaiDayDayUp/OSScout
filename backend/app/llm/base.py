"""
LLM Provider 抽象基类

定义所有 LLM Provider 必须实现的统一接口，
业务代码面向此基类编程，不依赖具体厂商实现。
"""
import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from app.core.logger import get_logger

from .schemas import LLMMessage, LLMResponse

logger = get_logger(__name__)

# 泛型约束：StructuredOutput 的子类
T = TypeVar("T")


class LLMProvider(ABC):
    """
    LLM Provider 抽象基类

    所有具体 Provider（Kimi、DeepSeek 等）必须继承此类，
    实现 chat() 方法即可。structured_output() 基于 chat() 封装，
    通过 Prompt 工程要求模型返回 JSON，再解析为 Pydantic 模型。
    """

    def __init__(self, provider_name: str, model: str) -> None:
        self.provider_name = provider_name
        self.model = model

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        通用对话接口

        Args:
            messages: 对话历史消息列表
            temperature: 采样温度，0~2，越低越确定
            max_tokens: 最大生成 token 数，None 表示不限制
            **kwargs: 额外参数（如 top_p、presence_penalty 等）

        Returns:
            LLMResponse: 统一格式的响应
        """
        ...

    async def chat_structured(
        self,
        messages: list[LLMMessage],
        output_schema: type[T],
        temperature: float = 0.3,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> T:
        """
        结构化输出接口

        在传入的 messages 末尾追加一条 system 指令，
        要求模型严格按照指定的 JSON Schema 返回结果，
        然后自动解析并校验为 Pydantic 模型。

        Args:
            messages: 原始对话消息
            output_schema: 期望的输出模型类（Pydantic BaseModel 子类）
            temperature: 建议较低（默认 0.3），提高 JSON 格式稳定性
            max_tokens: 最大生成 token 数
            **kwargs: 额外参数

        Returns:
            output_schema 的实例

        Raises:
            ValueError: JSON 解析失败或校验失败
        """
        # 构造 JSON 指令
        schema_json = output_schema.model_json_schema()
        json_instruction = (
            f"\n\n你必须严格按照以下 JSON Schema 返回结果，"
            f"不要输出任何其他内容（如 markdown 代码块标记、解释性文字等）：\n"
            f"{json.dumps(schema_json, ensure_ascii=False, indent=2)}"
        )

        # 复制消息列表，追加 JSON 指令
        structured_messages = [
            LLMMessage(role=msg.role, content=msg.content)
            for msg in messages
        ]
        structured_messages.append(
            LLMMessage(role="system", content=json_instruction)
        )

        response = await self.chat(
            messages=structured_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # 清理可能的 markdown 代码块标记
        raw_content = response.content.strip()
        if raw_content.startswith("```json"):
            raw_content = raw_content[7:]
        if raw_content.startswith("```"):
            raw_content = raw_content[3:]
        if raw_content.endswith("```"):
            raw_content = raw_content[:-3]
        raw_content = raw_content.strip()

        # 解析 JSON
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error(
                "LLM 返回内容 JSON 解析失败",
                provider=self.provider_name,
                model=self.model,
                raw_content=raw_content[:500],
                error=str(e),
            )
            raise ValueError(
                f"LLM 返回的内容不是有效的 JSON: {e}\n"
                f"原始内容（前 500 字符）: {raw_content[:500]}"
            ) from e

        # 校验为 Pydantic 模型
        try:
            return output_schema.model_validate(parsed)
        except Exception as e:
            logger.error(
                "JSON 内容校验失败",
                provider=self.provider_name,
                model=self.model,
                parsed=parsed,
                error=str(e),
            )
            raise ValueError(
                f"LLM 返回的 JSON 不符合预期的 Schema: {e}"
            ) from e
