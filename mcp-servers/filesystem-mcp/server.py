#!/usr/bin/env python3
"""
Filesystem MCP Server

提供文件系统操作能力，供 Agent 安全地访问文件系统。
核心职责：
- 克隆 Git 仓库到受控的临时目录
- 读取文件内容
- 列出目录结构
- 检查文件是否存在

Agent 不直接操作文件系统，所有文件操作都通过本 Server 的工具调用完成。
"""

import asyncio
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# 临时目录根：放在项目根目录下的 tmp/ 中，避免占用 C 盘空间
# 推导路径：mcp-servers/filesystem-mcp/server.py → .. → .. → .. → 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMP_ROOT = _PROJECT_ROOT / "tmp" / "osscout-repos"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

# 线程池用于执行同步的 git 命令
_executor = ThreadPoolExecutor(max_workers=2)

server = Server("filesystem-mcp")

TOOLS = [
    Tool(
        name="clone_repo",
        description="克隆 Git 仓库到本地临时目录，返回本地绝对路径。已存在的同名目录会被覆盖。",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Git 仓库 HTTPS 或 SSH URL"},
                "depth": {"type": "integer", "description": "克隆深度，默认 1（浅克隆，只拉最近 1 个 commit，速度快）", "default": 1},
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="read_file",
        description="读取指定文件的内容（UTF-8 编码），文件过大时自动截断到 500KB",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件绝对路径"},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="list_dir",
        description="列出指定目录下的文件和子目录（不递归）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录绝对路径"},
            },
            "required": ["path"],
        },
    ),
    Tool(
        name="file_exists",
        description="检查指定路径是否存在（文件或目录均可）",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录路径"},
            },
            "required": ["path"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """返回所有可用的文件系统工具"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """处理工具调用请求"""
    if name == "clone_repo":
        url = arguments["url"]
        depth = arguments.get("depth", 1)

        # 从 URL 提取仓库名称作为目录名
        repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        target = _TEMP_ROOT / repo_name

        # 如果目录已存在，先删除（避免 git clone 报错）
        # Windows 上 .git 下的文件是只读的，需要特殊处理权限
        if target.exists():
            def _on_remove_error(func, path, _):
                os.chmod(path, stat.S_IWRITE)
                func(path)
            shutil.rmtree(target, onexc=_on_remove_error)

        # 执行浅克隆 + 单分支，最大程度减少下载量
        cmd = [
            "git", "clone",
            "--depth", str(depth),
            "--single-branch",
            "--no-tags",
            url, str(target),
        ]

        def _run_git():
            kwargs = {
                "capture_output": True,
                "text": True,
                "timeout": 300,
                "close_fds": True,
                # 关键：禁止 git 继承 Server 的 stdin，防止读取 MCP 通信数据
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startupinfo
            return subprocess.run(cmd, **kwargs)

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, _run_git),
                timeout=305,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("git clone 超时（300秒），请检查网络连接")

        if result.returncode != 0:
            raise RuntimeError(f"git clone 失败: {result.stderr}")

        return [TextContent(
            type="text",
            text=json.dumps({
                "path": str(target),
                "repo_name": repo_name,
            }, ensure_ascii=False)
        )]

    elif name == "read_file":
        path = Path(arguments["path"])

        # 大文件截断，避免内存问题和传输超时
        MAX_SIZE = 500 * 1024  # 500KB
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_SIZE:
            content = content[:MAX_SIZE] + "\n\n[文件过大，已截断]"

        # 包装为 JSON，保持与其他 tool 返回格式一致
        return [TextContent(
            type="text",
            text=json.dumps({"content": content}, ensure_ascii=False)
        )]

    elif name == "list_dir":
        path = Path(arguments["path"])

        items = []
        for item in sorted(path.iterdir()):
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            })

        return [TextContent(
            type="text",
            text=json.dumps(items, ensure_ascii=False)
        )]

    elif name == "file_exists":
        path = Path(arguments["path"])
        return [TextContent(
            type="text",
            text=json.dumps({"exists": path.exists()}, ensure_ascii=False)
        )]

    else:
        raise ValueError(f"未知工具: {name}")


async def main() -> None:
    """启动 MCP Server（stdio 模式）"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
