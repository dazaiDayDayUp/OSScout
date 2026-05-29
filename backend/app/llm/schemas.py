"""
LLM 模块的数据模型定义

使用 Pydantic 定义统一的请求/响应数据结构，
屏蔽不同厂商 LLM 的差异。
"""
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """单条对话消息

    支持 Function Calling 的扩展字段：
    - tool_calls: assistant 消息中包含的工具调用请求
    - name: tool 消息中的工具名称
    - tool_call_id: tool 消息中对应的 tool_call ID
    """

    role: str = Field(
        ...,
        description="消息角色：system / user / assistant / tool",
    )
    content: str = Field(default="", description="消息内容")
    tool_calls: list[dict] | None = Field(
        default=None, description="assistant 消息中的工具调用列表（Function Calling）"
    )
    name: str | None = Field(
        default=None, description="tool 消息中的工具名称"
    )
    tool_call_id: str | None = Field(
        default=None, description="tool 消息对应的 tool_call ID"
    )
    reasoning_content: str | None = Field(
        default=None, description="思考模型的推理过程（kimi-k2 系列 tool_calls 消息需要）"
    )


class LLMUsage(BaseModel):
    """Token 用量统计"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCall(BaseModel):
    """LLM 输出的单个工具调用请求

    兼容 OpenAI 的 tool_calls 格式：
    {
      "id": "call_xxx",
      "type": "function",
      "function": {"name": "tool_name", "arguments": "{...}"}
    }
    """

    id: str = Field(..., description="工具调用唯一标识")
    type: str = Field(default="function", description="调用类型，通常为 function")
    name: str = Field(..., description="要调用的工具名称")
    arguments: str = Field(..., description="工具参数（JSON 字符串）")


class ToolResult(BaseModel):
    """工具执行后的结果，用于将 observation 返回给 LLM"""

    tool_call_id: str = Field(..., description="对应 ToolCall 的 ID")
    name: str = Field(..., description="工具名称")
    content: str = Field(..., description="工具执行结果的字符串表示（observation）")
    is_error: bool = Field(default=False, description="是否执行失败")


class LLMResponse(BaseModel):
    """LLM 调用返回的统一响应格式"""

    content: str = Field(..., description="模型生成的文本内容")
    usage: LLMUsage = Field(default_factory=LLMUsage, description="Token 用量")
    model: str = Field(..., description="实际调用的模型名称")
    provider: str = Field(..., description="Provider 标识：kimi / deepseek")
    reasoning_content: str | None = Field(
        default=None, description="思考模型的推理过程（kimi-k2 系列）"
    )
    tool_calls: list[ToolCall] | None = Field(
        default=None, description="LLM 请求调用的工具列表（Function Calling）"
    )


class StructuredOutput(BaseModel):
    """
    结构化输出基类

    各 Agent 定义自己的输出 Schema，继承此类，
    通过 chat_structured() 方法自动完成 JSON 解析和校验。
    """

    model_config = {"extra": "allow"}
