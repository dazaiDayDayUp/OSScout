"""
MCP 工具注册表 — 批量注册所有 MCP Server 的工具

Phase 5.2 核心组件：统一入口，自动发现并注册所有 MCP Server 的工具。

用法：
    from app.agents.tools.mcp_registry import initialize_mcp_tools

    # 在应用启动时调用
    await initialize_mcp_tools()

设计原则：
- 配置即代码：所有 Server 在 MCP_SERVER_CONFIGS 中声明
- 失败隔离：某个 Server 连接失败，不影响其他 Server
- 并行注册：asyncio.gather 同时连接多个 Server
"""

import asyncio
from dataclasses import dataclass
from typing import Type

from app.core.logger import get_logger
from app.mcp.client import (
    CodeAnalysisMCPClient,
    FilesystemMCPClient,
    GitHubMCPClient,
    OSVMCPClient,
    _BaseMCPClient,
)

from .mcp_adapter import MCPAdapter
from .registry import ToolRegistry, get_registry
from .tool import Tool, ToolSource

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# MCP Server 配置
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MCPServerConfig:
    """单个 MCP Server 的配置"""

    client_class: Type[_BaseMCPClient]  # Client 类（如 GitHubMCPClient）
    namespace: str  # 命名空间前缀（如 "github"）
    display_name: str  # 显示名称（用于日志）


# 所有已知的 MCP Server 配置
# 新增 Server 只需在此列表中添加一行
MCP_SERVER_CONFIGS: list[MCPServerConfig] = [
    MCPServerConfig(
        client_class=GitHubMCPClient,
        namespace="github",
        display_name="GitHub",
    ),
    MCPServerConfig(
        client_class=FilesystemMCPClient,
        namespace="filesystem",
        display_name="Filesystem",
    ),
    MCPServerConfig(
        client_class=CodeAnalysisMCPClient,
        namespace="code_analysis",
        display_name="Code Analysis",
    ),
    MCPServerConfig(
        client_class=OSVMCPClient,
        namespace="osv",
        display_name="OSV Security",
    ),
]


# ---------------------------------------------------------------------------
# 批量注册
# ---------------------------------------------------------------------------

async def initialize_mcp_tools(
    registry: ToolRegistry | None = None,
    configs: list[MCPServerConfig] | None = None,
) -> dict[str, list[Tool]]:
    """初始化并注册所有 MCP Server 的工具

    并行连接所有配置的 MCP Server，自动发现工具并注册到 Registry。
    某个 Server 连接失败时只记录错误，不影响其他 Server。

    Args:
        registry: 目标注册表，默认使用全局单例
        configs: Server 配置列表，默认使用 MCP_SERVER_CONFIGS

    Returns:
        按 namespace 分组的成功注册 Tool 列表
        例如：{"github": [Tool(...), ...], "filesystem": [...]}
    """
    target_registry = registry or get_registry()
    server_configs = configs or MCP_SERVER_CONFIGS

    logger.info(
        "开始注册 MCP 工具",
        server_count=len(server_configs),
        servers=[c.display_name for c in server_configs],
    )

    adapter = MCPAdapter(registry=target_registry)

    # 为每个 Server 创建注册任务
    async def _register_single(config: MCPServerConfig) -> tuple[str, list[Tool]]:
        """注册单个 Server 的工具，封装异常处理"""
        try:
            tools = await adapter.discover_and_register(
                client_class=config.client_class,
                namespace=config.namespace,
            )
            return config.namespace, tools
        except Exception as e:
            logger.error(
                "MCP Server 注册失败",
                server=config.display_name,
                namespace=config.namespace,
                error=str(e),
                error_type=type(e).__name__,
            )
            return config.namespace, []

    # 并行执行所有注册任务（带失败隔离）
    # 使用 return_exceptions=True 确保 gather 不会因为一个任务失败而全部取消
    tasks = [_register_single(cfg) for cfg in server_configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 收集结果
    registered: dict[str, list[Tool]] = {}
    total_tools = 0
    success_servers = 0

    for result in results:
        if isinstance(result, Exception):
            logger.error("MCP 注册任务异常", error=str(result))
            continue

        namespace, tools = result
        if tools:
            registered[namespace] = tools
            total_tools += len(tools)
            success_servers += 1

    logger.info(
        "MCP 工具注册完成",
        total_tools=total_tools,
        success_servers=f"{success_servers}/{len(server_configs)}",
        namespaces=list(registered.keys()),
    )

    return registered


# ---------------------------------------------------------------------------
# 查询摘要
# ---------------------------------------------------------------------------

def get_mcp_tools_summary(registry: ToolRegistry | None = None) -> dict:
    """获取已注册的 MCP 工具摘要

    返回结构化数据，方便日志记录、调试和前端展示。

    Returns:
        {
            "total": 12,
            "by_namespace": {
                "github": 6,
                "filesystem": 4,
                ...
            },
            "tools": [
                {"name": "github.get_repo_metadata", "source": "mcp", ...},
                ...
            ]
        }
    """
    target_registry = registry or get_registry()

    mcp_tools = target_registry.list_by_source(ToolSource.MCP)

    # 按命名空间分组计数
    by_namespace: dict[str, int] = {}
    tool_details: list[dict] = []

    for tool in mcp_tools:
        namespace = tool.metadata.get("namespace", "unknown")
        by_namespace[namespace] = by_namespace.get(namespace, 0) + 1

        tool_details.append({
            "name": tool.name,
            "description": tool.description[:100] + "..."
            if len(tool.description) > 100
            else tool.description,
            "namespace": namespace,
            "mcp_tool_name": tool.metadata.get("mcp_tool_name", ""),
        })

    return {
        "total": len(mcp_tools),
        "by_namespace": by_namespace,
        "tools": tool_details,
    }
