"""
LLM 模块的数据模型定义

使用 Pydantic 定义统一的请求/响应数据结构，
屏蔽不同厂商 LLM 的差异。
"""
from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    """单条对话消息"""

    role: str = Field(
        ...,
        description="消息角色：system / user / assistant",
    )
    content: str = Field(..., description="消息内容")


class LLMUsage(BaseModel):
    """Token 用量统计"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    """LLM 调用返回的统一响应格式"""

    content: str = Field(..., description="模型生成的文本内容")
    usage: LLMUsage = Field(default_factory=LLMUsage, description="Token 用量")
    model: str = Field(..., description="实际调用的模型名称")
    provider: str = Field(..., description="Provider 标识：kimi / deepseek")
    reasoning_content: str | None = Field(
        default=None, description="思考模型的推理过程（kimi-k2 系列）"
    )


class StructuredOutput(BaseModel):
    """
    结构化输出基类

    各 Agent 定义自己的输出 Schema，继承此类，
    通过 chat_structured() 方法自动完成 JSON 解析和校验。
    """

    model_config = {"extra": "allow"}
