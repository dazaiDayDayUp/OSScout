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
        # 子类可覆盖：是否支持 response_format={"type": "json_object"}
        self.supports_json_mode = False

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
            f"\n\n你必须严格按照以下 JSON Schema 返回结果。"
            f"直接输出合法 JSON，不要输出任何其他内容"
            f"（如 markdown 代码块标记、解释性文字、思考过程等）：\n"
            f"{json.dumps(schema_json, ensure_ascii=False, indent=2)}"
        )

        # 复制消息列表，将 JSON 指令追加到最后一条 user 消息中
        # 注意：最后一条消息必须是 user 角色，否则部分模型（如 kimi-k2.6）不会响应
        structured_messages = [
            LLMMessage(role=msg.role, content=msg.content)
            for msg in messages
        ]

        # 找到最后一条 user 消息，将 JSON 指令追加到其内容中
        last_user_idx = -1
        for i in range(len(structured_messages) - 1, -1, -1):
            if structured_messages[i].role == "user":
                last_user_idx = i
                break

        if last_user_idx >= 0:
            original = structured_messages[last_user_idx].content
            structured_messages[last_user_idx] = LLMMessage(
                role="user",
                content=original + json_instruction,
            )
        else:
            # 没有 user 消息时，添加一条新的 user 消息
            structured_messages.append(
                LLMMessage(role="user", content=json_instruction)
            )

        # 如果 Provider 支持 json_object 响应格式，强制模型输出 JSON
        if self.supports_json_mode:
            kwargs.setdefault("response_format", {"type": "json_object"})

        # 对于 Kimi k2 系列思考模型，禁用思考能力以确保 JSON 输出稳定性。
        # 思考模型会在 reasoning_content 中输出分析过程，与 content 分离，
        # 但 chat_structured 只读取 content 进行 JSON 解析，因此禁用思考
        # 让模型把所有输出都放在 content 中。
        if self.provider_name == "kimi" and self.model.startswith("kimi-k2"):
            kwargs.setdefault("extra_body", {"thinking": {"type": "disabled"}})

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

        # 自动修复常见格式错误（如字符串应转为列表）
        parsed = self._normalize_parsed_data(parsed, output_schema)

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

    @staticmethod
    def _normalize_parsed_data(data: dict, schema: type[T]) -> dict:
        """
        自动修复 LLM 返回 JSON 中的常见格式错误

        kimi-k2.6 等模型即使禁用思考 + json_object 模式，
        仍可能把 list[str] 字段输出为单个字符串。
        这里根据 Schema 定义自动将字符串转为单元素列表。
        """
        if not isinstance(data, dict):
            return data

        # 遍历 Schema 的所有字段，找出类型为 list 的字段
        for field_name, field_info in schema.model_fields.items():
            if field_name not in data:
                continue
            value = data[field_name]
            annotation = field_info.annotation

            # 检测字段期望类型是否为 list[str] 或 list
            is_list_type = False
            if hasattr(annotation, "__origin__"):
                is_list_type = annotation.__origin__ is list
            elif isinstance(annotation, type) and annotation is list:
                is_list_type = True

            # 如果期望是 list 但实际收到 str，自动包装为单元素列表
            if is_list_type and isinstance(value, str):
                data[field_name] = [value]

        return data
