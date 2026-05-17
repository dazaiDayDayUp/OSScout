"""GitHub 数据采集服务：通过 github-mcp Server 获取仓库元数据"""

import asyncio
from typing import Any

from app.mcp.client import GitHubMCPClient


async def collect_all_metadata(owner: str, repo: str) -> dict[str, Any]:
    """
    通过 MCP Client 并行采集仓库全部元数据

    内部启动 github-mcp Server 子进程，并发调用 6 个 tool，
    结果结构与 github_service.collect_all_metadata 完全一致。

    Args:
        owner: 仓库所有者
        repo: 仓库名称

    Returns:
        包含所有维度数据的字典
    """
    async with GitHubMCPClient() as client:
        results = await asyncio.gather(
            client.call_tool("get_repo_metadata", {"owner": owner, "repo": repo}),
            client.call_tool("list_contributors", {"owner": owner, "repo": repo}),
            client.call_tool("list_issues", {"owner": owner, "repo": repo, "state": "all"}),
            client.call_tool("list_pull_requests", {"owner": owner, "repo": repo, "state": "all"}),
            client.call_tool("list_releases", {"owner": owner, "repo": repo}),
            client.call_tool("get_commit_activity", {"owner": owner, "repo": repo}),
            return_exceptions=True,
        )

    return {
        "metadata": results[0] if not isinstance(results[0], Exception) else {},
        "contributors": results[1] if not isinstance(results[1], Exception) else [],
        "issues": results[2] if not isinstance(results[2], Exception) else [],
        "pull_requests": results[3] if not isinstance(results[3], Exception) else [],
        "releases": results[4] if not isinstance(results[4], Exception) else [],
        "commit_activity": results[5] if not isinstance(results[5], Exception) else [],
    }
