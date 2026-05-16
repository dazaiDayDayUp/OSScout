"""
GitHub API 封装服务（Legacy 版本）

Phase 1.1 之前的直接调用实现，含 Redis 缓存和并发控制。
Phase 1.2 后，正式链路改用 mcp_github_service.py + github-mcp Server。
此文件保留用于 debug.py 调试接口和应急回退。
"""
import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.core.cache import delete_cache, get_cache, set_cache

# GitHub API 基础地址
GITHUB_API_BASE = "https://api.github.com"

# 请求头，包含认证 Token（如果有）
_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "osscout-agent",
}
if settings.github_token:
    _HEADERS["Authorization"] = f"token {settings.github_token}"

# 并发控制：最多 10 个并行请求
_semaphore = asyncio.Semaphore(10)


async def _github_get(path: str, params: dict | None = None) -> dict | list:
    """
    发送 GitHub API GET 请求
    优先读取 Redis 缓存，缓存未命中再请求 API
    """
    # 构造缓存键：github:{path}:{sorted_params}
    cache_key = f"github:{path}"
    if params:
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cache_key += f"?{param_str}"

    # 先查缓存
    cached = await get_cache(cache_key)
    if cached is not None:
        return cached

    # 缓存未命中，请求 API（受并发控制）
    async with _semaphore:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as client:
            url = f"{GITHUB_API_BASE}{path}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

    # 写入缓存（24 小时 TTL）
    await set_cache(cache_key, data)
    return data


async def get_repo_metadata(owner: str, repo: str) -> dict[str, Any]:
    """获取仓库基础元数据"""
    return await _github_get(f"/repos/{owner}/{repo}")


async def list_contributors(owner: str, repo: str, limit: int = 100) -> list[dict]:
    """获取仓库贡献者列表"""
    return await _github_get(
        f"/repos/{owner}/{repo}/contributors",
        params={"per_page": min(limit, 100)},
    )


async def list_issues(owner: str, repo: str, state: str = "all") -> list[dict]:
    """获取仓库 Issues 列表"""
    return await _github_get(
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": 100},
    )


async def list_pull_requests(owner: str, repo: str, state: str = "all") -> list[dict]:
    """获取仓库 Pull Requests 列表"""
    return await _github_get(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": 100},
    )


async def list_releases(owner: str, repo: str) -> list[dict]:
    """获取仓库 Release 列表"""
    return await _github_get(
        f"/repos/{owner}/{repo}/releases",
        params={"per_page": 100},
    )


async def get_commit_activity(owner: str, repo: str) -> list[dict]:
    """
    获取仓库最近一年的每周提交活动统计
    使用 participation 端点替代 commit_activity，避免 GitHub 后台异步计算导致的 202 空数据问题
    participation 返回的数据结构与 commit_activity 一致，可直接用于活跃度趋势分析
    """
    data = await _github_get(f"/repos/{owner}/{repo}/stats/participation")

    # participation 返回 {"all": [...], "owner": [...]}，提取每周提交总数
    weekly_totals = data.get("all", []) if isinstance(data, dict) else []
    if not weekly_totals:
        return []

    # 构建与 commit_activity 兼容的格式：最近 52 周的每周统计
    now = datetime.utcnow()
    monday = now - timedelta(days=now.weekday())

    result = []
    for i, total in enumerate(reversed(weekly_totals)):
        week_ts = int((monday - timedelta(weeks=i)).timestamp())
        result.append({"week": week_ts, "total": total})

    return result


async def collect_all_metadata(owner: str, repo: str) -> dict[str, Any]:
    """
    并行采集仓库全部元数据
    返回包含所有维度数据的字典
    """
    results = await asyncio.gather(
        get_repo_metadata(owner, repo),
        list_contributors(owner, repo),
        list_issues(owner, repo),
        list_pull_requests(owner, repo),
        list_releases(owner, repo),
        get_commit_activity(owner, repo),
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
