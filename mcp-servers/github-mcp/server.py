#!/usr/bin/env python3
"""
GitHub MCP Server

通过 MCP 协议暴露 GitHub API 工具，供 Agent 调用。
通信方式：stdio（标准输入输出），JSON-RPC 2.0 格式。
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# === GitHub API 配置 ===
GITHUB_API_BASE = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "osscout-github-mcp",
}
# 从环境变量读取 Token（提高 API 限频，可选）
if token := os.environ.get("GITHUB_TOKEN"):
    _HEADERS["Authorization"] = f"token {token}"

# 并发控制：GitHub API 认证用户限频 5000 req/hour
# 限制并发数可以避免短时间内 burst 请求触发限频
_semaphore = asyncio.Semaphore(6)


async def _github_get(path: str, params: dict | None = None) -> dict | list:
    """
    发送 GitHub API GET 请求

    使用信号量控制并发，避免触发 GitHub API 限频。
    超时 30 秒，适配 GitHub API 偶尔响应慢的情况。
    """
    async with _semaphore:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as client:
            url = f"{GITHUB_API_BASE}{path}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


# === Tool 定义 ===
# 每个 Tool 对应一个 GitHub API 接口，inputSchema 用 JSON Schema 描述参数

TOOLS = [
    Tool(
        name="get_repo_metadata",
        description="获取 GitHub 仓库基础元数据，包括 stars、forks、语言、许可证、创建时间等",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者用户名或组织名"},
                "repo": {"type": "string", "description": "仓库名称"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_contributors",
        description="获取仓库贡献者列表，按贡献度降序排列",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
                "limit": {"type": "integer", "description": "最大返回数量，默认 100，上限 100", "default": 100},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_issues",
        description="获取仓库 Issues 列表（不包含 Pull Request）",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Issue 状态筛选，默认 all",
                    "default": "all",
                },
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_pull_requests",
        description="获取仓库 Pull Requests 列表",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "PR 状态筛选，默认 all",
                    "default": "all",
                },
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_releases",
        description="获取仓库 Release 列表",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="get_commit_activity",
        description="获取仓库最近一年的每周提交活动统计，用于分析活跃度趋势",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "仓库所有者"},
                "repo": {"type": "string", "description": "仓库名称"},
            },
            "required": ["owner", "repo"],
        },
    ),
]


# === MCP Server 初始化 ===

server = Server("github-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """返回所有可用的 GitHub API 工具列表"""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    处理工具调用请求

    根据 tool name 路由到对应的 GitHub API 调用，
    结果序列化为 JSON 字符串，包装为 TextContent 返回。
    """
    owner = arguments.get("owner")
    repo = arguments.get("repo")

    if name == "get_repo_metadata":
        data = await _github_get(f"/repos/{owner}/{repo}")

    elif name == "list_contributors":
        limit = arguments.get("limit", 100)
        data = await _github_get(
            f"/repos/{owner}/{repo}/contributors",
            params={"per_page": min(limit, 100)},
        )

    elif name == "list_issues":
        state = arguments.get("state", "all")
        data = await _github_get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": 100},
        )

    elif name == "list_pull_requests":
        state = arguments.get("state", "all")
        data = await _github_get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": 100},
        )

    elif name == "list_releases":
        data = await _github_get(
            f"/repos/{owner}/{repo}/releases",
            params={"per_page": 100},
        )

    elif name == "get_commit_activity":
        # 使用 participation 端点替代 commit_activity
        # 原因：commit_activity 端点需要 GitHub 后台异步计算，首次请求常返回 202 空数据
        # participation 端点直接返回最近 52 周的提交统计，无需等待
        raw = await _github_get(f"/repos/{owner}/{repo}/stats/participation")
        weekly_totals = raw.get("all", []) if isinstance(raw, dict) else []

        # 构建与 commit_activity 兼容的时间序列格式
        now = datetime.now()
        monday = now - timedelta(days=now.weekday())
        data = []
        for i, total in enumerate(reversed(weekly_totals)):
            week_ts = int((monday - timedelta(weeks=i)).timestamp())
            data.append({"week": week_ts, "total": total})

    else:
        raise ValueError(f"未知工具: {name}")

    # 结果序列化为 JSON 字符串返回
    # ensure_ascii=False 保证中文字符不转义，方便阅读
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False))]


async def main() -> None:
    """启动 MCP Server（stdio 模式）"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
