"""
临时调试接口
用于在 Phase 0 验证 GitHub API 封装是否正常工作
进入 Phase 1 后可移除或保留作为运维排查入口
"""
from fastapi import APIRouter

from app.services import github_service_legacy as github_service

# 创建调试路由器，所有接口前缀为 /debug
router = APIRouter(prefix="/debug", tags=["调试接口"])


@router.get("/repo/{owner}/{repo}")
async def debug_repo_metadata(owner: str, repo: str):
    """
    获取单个仓库的元数据
    示例：/api/v1/debug/repo/vercel/next.js
    第一次调用会请求 GitHub API，之后命中 Redis 缓存
    """
    return await github_service.get_repo_metadata(owner, repo)


@router.get("/repo/{owner}/{repo}/contributors")
async def debug_contributors(owner: str, repo: str, limit: int = 30):
    """获取仓库贡献者列表（用于验证 list_contributors）"""
    return await github_service.list_contributors(owner, repo, limit=limit)


@router.get("/repo/{owner}/{repo}/all")
async def debug_all_metadata(owner: str, repo: str):
    """
    并行采集仓库的全部元数据，返回字段统计摘要
    覆盖 metadata + contributors + issues + PRs + releases + commit_activity
    用于验证 collect_all_metadata 的并发逻辑

    注意：完整数据可能有几十 MB，会导致 Swagger UI 卡死，
    这里只返回各字段的数量和关键字段摘录，验证并发是否成功即可
    """
    data = await github_service.collect_all_metadata(owner, repo)
    metadata = data.get("metadata") or {}
    contributors = data.get("contributors") or []
    license_obj = metadata.get("license") or {}

    return {
        # 各字段成功采集的数量，用于验证 6 个并发请求都到位
        "summary": {
            "metadata_loaded": bool(metadata),
            "contributors_count": len(contributors),
            "issues_count": len(data.get("issues") or []),
            "pull_requests_count": len(data.get("pull_requests") or []),
            "releases_count": len(data.get("releases") or []),
            "commit_activity_weeks": len(data.get("commit_activity") or []),
        },
        # 关键字段摘录，确认 metadata 内容确实是这个仓库的
        "metadata_excerpt": {
            "full_name": metadata.get("full_name"),
            "stargazers_count": metadata.get("stargazers_count"),
            "forks_count": metadata.get("forks_count"),
            "open_issues_count": metadata.get("open_issues_count"),
            "license": license_obj.get("spdx_id"),
            "primary_language": metadata.get("language"),
        },
        # 头部贡献者摘录，确认 contributors 数组的顺序
        "top_contributor": (
            {
                "login": contributors[0].get("login"),
                "contributions": contributors[0].get("contributions"),
            }
            if contributors
            else None
        ),
    }
