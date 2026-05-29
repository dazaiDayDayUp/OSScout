"""
MCP 客户端封装

提供与各个 MCP Server 的通信能力，让上层代码像调用普通函数一样使用工具。

支持的 Server：
- github-mcp：GitHub API 查询
- filesystem-mcp：文件系统操作（克隆、读取、遍历）
- code-analysis-mcp：代码静态分析（Semgrep、radon）
- osv-mcp：安全数据采集

设计说明：每个 async with 创建独立实例
--------------------------------
原方案使用进程级单例复用子进程，但在 Celery + asyncio 的并发场景下，
asyncio.Lock 跨事件循环绑定问题极难彻底修复（Python 3.12 移除 _loop 属性、
并发覆盖、竞态条件等）。

现方案：每个 async with 创建全新实例，独立启动/关闭子进程。
solo pool 一次只执行一个任务，最多同时存在 6 个子进程，Windows 可承受。
彻底消除单例共享带来的并发问题。
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class _BaseMCPClient:
    """
    MCP Client 通用基类（非单例，每次 async with 创建新实例）

    封装了 Server 进程生命周期管理（启动 → initialize 握手 → 请求 → 清理），
    子类只需覆盖 SERVER_MODULE 指定对应的 Server 目录名。
    """

    # 子类覆盖：对应 mcp-servers/ 下的目录名
    SERVER_MODULE = ""

    def __init__(self, server_command: list[str] | None = None):
        """初始化实例"""
        self.server_command = server_command or self._default_command()
        self._session: ClientSession | None = None
        self._exit_stack = AsyncExitStack()
        # 每个实例独立的并发锁（绑定到创建时的事件循环）
        self._call_lock = asyncio.Lock()

    def _default_command(self) -> list[str]:
        """
        自动探测 Server 启动方式

        优先从源码路径找到 server.py（开发模式），
        找不到则回退到 pip 安装的入口命令（生产模式）。
        """
        client_dir = os.path.dirname(__file__)
        server_py = os.path.abspath(
            os.path.join(
                client_dir, "..", "..", "..",
                "mcp-servers", self.SERVER_MODULE, "server.py"
            )
        )
        if os.path.exists(server_py):
            return ["python", server_py]
        # 回退：pip 安装的入口命令（如 github-mcp、filesystem-mcp）
        return [self.SERVER_MODULE]

    async def __aenter__(self):
        """进入上下文：启动子进程并完成 MCP 握手"""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文：关闭子进程"""
        await self._disconnect()
        return False

    async def _connect(self):
        """启动 Server 连接，完成 MCP initialize 握手"""
        params = StdioServerParameters(
            command=self.server_command[0],
            args=self.server_command[1:],
            env={**os.environ},
        )

        # 第一层：stdio 传输层
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        read_stream, write_stream = stdio_transport

        # 第二层：MCP 协议会话
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

    async def _disconnect(self):
        """关闭连接，清理资源"""
        if self._session is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
            self._session = None

    async def list_tools_detailed(self) -> list[dict]:
        """获取 Server 暴露的所有工具的详细信息

        返回列表中每个元素包含：
            - name: 工具名称
            - description: 工具描述
            - inputSchema: 参数 JSON Schema
        """
        if not self._session:
            raise RuntimeError("Client 未连接，请先使用 async with 进入上下文")

        async with self._call_lock:
            result = await self._session.list_tools()

        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema or {"type": "object"},
            }
            for tool in result.tools
        ]

    async def list_tools(self) -> list[str]:
        """获取 Server 暴露的所有工具名称"""
        if not self._session:
            raise RuntimeError("Client 未连接，请先使用 async with 进入上下文")

        async with self._call_lock:
            result = await self._session.list_tools()
        return [tool.name for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """
        调用指定的 MCP tool

        Args:
            name: Tool 名称
            arguments: Tool 参数

        Returns:
            Tool 返回的 JSON 数据，已解析为 Python 对象
        """
        if not self._session:
            raise RuntimeError("Client 未连接，请先使用 async with 进入上下文")

        async with self._call_lock:
            result = await self._session.call_tool(name, arguments)

            if result.isError:
                error_text = result.content[0].text if result.content else "未知错误"
                raise RuntimeError(f"MCP tool 调用失败 [{name}]: {error_text}")

            text = result.content[0].text
            return json.loads(text)


class GitHubMCPClient(_BaseMCPClient):
    """GitHub MCP Server 客户端"""
    SERVER_MODULE = "github-mcp"


class FilesystemMCPClient(_BaseMCPClient):
    """Filesystem MCP Server 客户端"""
    SERVER_MODULE = "filesystem-mcp"


class CodeAnalysisMCPClient(_BaseMCPClient):
    """Code Analysis MCP Server 客户端"""
    SERVER_MODULE = "code-analysis-mcp"


class OSVMCPClient(_BaseMCPClient):
    """OSV MCP Server 客户端（安全数据采集中心）"""
    SERVER_MODULE = "osv-mcp"
