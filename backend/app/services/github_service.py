"""GitHub 数据采集服务：通过 github-mcp Server 获取仓库元数据"""

import asyncio
import logging
from typing import Any

from app.mcp.client import GitHubMCPClient

logger = logging.getLogger(__name__)


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

    # 构建结果，异常项记录日志（避免静默失败）
    names = ["metadata", "contributors", "issues", "pull_requests", "releases", "commit_activity"]
    data = {}
    for i, name in enumerate(names):
        if isinstance(results[i], Exception):
            logger.warning("github-mcp %s 采集失败: %s", name, results[i])
            data[name] = {} if name == "metadata" else []
        else:
            data[name] = results[i]
    return data
