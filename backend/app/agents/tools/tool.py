"""
Tool 数据模型定义

Phase 5 的核心抽象：所有能力——本地 Python 函数、MCP Server 的远程工具、
RAG 知识库检索——统一抽象为 Tool 对象。

LLM 看到的就是 {name, description, parameters}，
不需要关心工具是本地跑的还是远程调用的。
"""
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


class ToolSource(str, Enum):
    """工具来源类型"""

    LOCAL = "local"       # 本地 Python 函数
    MCP = "mcp"           # 来自 MCP Server 的远程工具
    RAG = "rag"           # RAG 知识库检索


@dataclass
class Tool:
    """工具的一等公民抽象

    属性:
        name: 唯一标识，建议格式为 "namespace.tool_name"
                例如 "github.get_repo_metadata"、"rag.query_knowledge"
        description: LLM 决定"什么时候用"这个工具的依据。
                     必须清晰描述工具的功能、使用场景和返回值格式。
        parameters: JSON Schema（OpenAI 格式），描述参数结构。
                    包含 type、properties、required 等字段。
        handler: 实际执行函数。接收参数 dict，返回结果（任意类型）。
                 可以是同步或异步函数。
        source: 工具来源，标识是本地函数 / MCP / RAG
        metadata: 额外元数据，如 MCP server 名称、RAG 类别等
    """

    name: str
    description: str
    parameters: dict  # JSON Schema，OpenAI function schema 格式
    handler: Callable[..., Any] | Callable[..., Coroutine[Any, Any, Any]]
    source: ToolSource = ToolSource.LOCAL
    metadata: dict = field(default_factory=dict)

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI API 兼容的 tool schema

        OpenAI 格式：
        {
            "type": "function",
            "function": {
                "name": "github.get_repo_metadata",
                "description": "获取仓库元数据",
                "parameters": {...}
            }
        }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolExecutionResult:
    """工具执行结果

    ToolExecutor 执行 handler 后返回的统一格式，
    后续会被序列化为 observation 字符串返回给 LLM。
    """

    tool_name: str
    tool_call_id: str
    output: Any  # handler 的原始返回结果
    is_error: bool = False
    error_message: str | None = None
    execution_time_ms: float = 0.0

    def to_observation(self) -> str:
        """将执行结果序列化为 observation 字符串

        这是 LLM 在下一轮 Thought 中看到的"观察结果"。
        """
        if self.is_error:
            return f"[工具执行失败] {self.tool_name}: {self.error_message}"

        # 尝试 JSON 序列化，如果失败则用 str()
        try:
            if isinstance(self.output, (dict, list)):
                content = json.dumps(self.output, ensure_ascii=False, indent=2)
            else:
                content = str(self.output)
        except (TypeError, ValueError):
            content = str(self.output)

        return f"[工具执行结果] {self.tool_name}:\n{content}"
