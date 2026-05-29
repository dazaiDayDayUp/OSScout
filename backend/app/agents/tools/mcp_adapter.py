"""
MCP Adapter

将 MCP Server 的工具自动转换为 LLM Function Calling 的 Tool 对象。

连接流程：
1. adapter.discover_and_register(GitHubMCPClient)  传入 Client 类
2. Adapter 内部 async with client_class() 连接 Server
3. 自动发现所有工具，每个 MCP Tool → Tool(name, description, ..., source=MCP)
4. handler 内部每次调用时新建 client 连接，转发到 MCP Server

设计说明（Phase 5.2 重构）：
- discover_and_register 接收 client_class（类）而非实例
- 原因：_BaseMCPClient 采用"每个 async with 独立实例"设计，
  实例在退出上下文后 disconnect。handler 闭包若捕获实例，
  后续调用时 client 已断开。
- 解决方案：handler 闭包捕获 client_class，每次调用时内部新建连接。
"""
from typing import Type

from app.core.logger import get_logger
from app.mcp.client import _BaseMCPClient

from .registry import ToolRegistry, get_registry
from .tool import Tool, ToolSource

logger = get_logger(__name__)


class MCPAdapter:
    """MCP Server → Tool 转换适配器

    每个 MCP Server（github-mcp、filesystem-mcp 等）都可以通过这个 Adapter
    自动发现可用工具并注册到 ToolRegistry 中。
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        """
        Args:
            registry: 目标注册表，默认使用全局单例
        """
        self.registry = registry or get_registry()

    async def discover_and_register(
        self,
        client_class: Type[_BaseMCPClient],
        namespace: str | None = None,
    ) -> list[Tool]:
        """从 MCP Client 类发现所有工具并注册到 Registry

        Args:
            client_class: MCP Client 类（如 GitHubMCPClient），
                          非实例。Adapter 内部自行实例化并连接。
            namespace: 命名空间前缀，如 "github"、"filesystem"。
                       如果不传，自动从 Client 类名推导。

        Returns:
            注册成功的 Tool 列表
        """
        # 自动推导命名空间
        if namespace is None:
            namespace = self._derive_namespace(client_class)

        # 临时连接 Server，发现所有工具
        try:
            async with client_class() as client:
                mcp_tools = await client.list_tools_detailed()
        except Exception as e:
            logger.error(
                "MCP 工具发现失败",
                client_class=client_class.__name__,
                error=str(e),
            )
            return []

        tools: list[Tool] = []
        for mcp_tool in mcp_tools:
            # 构造工具全名：namespace.tool_name
            tool_name = f"{namespace}.{mcp_tool['name']}"

            # 创建 handler（闭包捕获 client_class，每次调用时新建连接）
            handler = self._make_handler(client_class, mcp_tool["name"])

            tool = Tool(
                name=tool_name,
                description=mcp_tool.get("description", f"MCP tool: {mcp_tool['name']}"),
                parameters=mcp_tool.get("inputSchema", {"type": "object"}),
                handler=handler,
                source=ToolSource.MCP,
                metadata={
                    "mcp_client_class": client_class.__name__,
                    "mcp_tool_name": mcp_tool["name"],
                    "namespace": namespace,
                },
            )

            self.registry.register(tool)
            tools.append(tool)

        logger.info(
            "MCP 工具注册完成",
            namespace=namespace,
            client_class=client_class.__name__,
            tool_count=len(tools),
            tool_names=[t.name for t in tools],
        )
        return tools

    @staticmethod
    def _derive_namespace(client_class: Type[_BaseMCPClient]) -> str:
        """从 Client 类名自动推导命名空间

        例如：GitHubMCPClient → github
              FilesystemMCPClient → filesystem
        """
        class_name = client_class.__name__
        # 去掉 "MCPClient" / "Client" 后缀
        for suffix in ("MCPClient", "Client"):
            if class_name.endswith(suffix):
                class_name = class_name[: -len(suffix)]
                break
        return class_name.lower()

    @staticmethod
    def _make_handler(
        client_class: Type[_BaseMCPClient], original_tool_name: str
    ) -> callable:
        """创建 handler 闭包

        handler 被 ToolExecutor 调用时，内部新建 client 实例并连接，
        然后转发到 MCP Client 的 call_tool。调用完成后自动清理。
        """

        async def handler(**kwargs) -> any:
            async with client_class() as client:
                return await client.call_tool(original_tool_name, kwargs)

        # handler 的参数由 Tool.parameters（JSON Schema）决定，
        # ToolExecutor 会根据 JSON Schema 的 properties 来传参，
        # 所以 handler 接受 **kwargs 即可。
        handler.__name__ = original_tool_name
        handler.__doc__ = f"MCP tool: {original_tool_name}"
        return handler
