"""
Agent 可调用的 Tool 集合（Phase 5 Function Calling 基础设施）

核心组件：
- Tool / ToolSource / ToolExecutionResult: Tool 数据模型
- ToolRegistry / @tool: 工具注册中心 + 装饰器
- ToolExecutor: 解析 tool_calls 并执行工具
- MCPAdapter: 将 MCP Server 工具转换为 Tool
- RAGAdapter: 将 RAG 检索封装为 Tool

用法示例：
    from app.agents.tools import ToolRegistry, tool, ToolExecutor

    @tool(description="获取仓库元数据")
    async def get_repo_metadata(owner: str, repo: str) -> dict:
        ...

    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    result = await executor.execute({"name": "get_repo_metadata", "arguments": "{...}"})
"""

from .executor import ToolExecutor
from .mcp_adapter import MCPAdapter
from .mcp_registry import get_mcp_tools_summary, initialize_mcp_tools
from .rag_adapter import RAGAdapter
from .registry import ToolRegistry, get_registry, tool
from .tool import Tool, ToolExecutionResult, ToolSource

__all__ = [
    # 数据模型
    "Tool",
    "ToolSource",
    "ToolExecutionResult",
    # Registry + 装饰器
    "ToolRegistry",
    "get_registry",
    "tool",
    # Executor
    "ToolExecutor",
    # Adapter
    "MCPAdapter",
    "RAGAdapter",
    # MCP 批量注册
    "initialize_mcp_tools",
    "get_mcp_tools_summary",
]
