"""POST /api/v1/compare — 多仓库对比分析"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analysis_service import AnalysisService

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════


class CompareRequest(BaseModel):
    """多仓库对比请求体"""

    repo_urls: list[str] = Field(
        ...,
        description="GitHub 仓库地址列表，支持 2-5 个仓库",
        examples=[[
            "https://github.com/psf/requests",
            "https://github.com/kennethreitz/requests",
        ]],
    )


class RepoSummary(BaseModel):
    """对比中的仓库评分概览"""

    repo_id: int
    owner: str
    name: str
    url: str
    overall_score: int
    overall_rating: str
    community_score: int
    quality_score: int
    security_score: int
    evolution_score: int


class DimensionCompareItem(BaseModel):
    """单个维度的对比项"""

    repo: str
    score: int


class KeyDifference(BaseModel):
    """关键差异项"""

    dimension: str
    highest: dict
    lowest: dict
    gap: int


class CompareResponse(BaseModel):
    """多仓库对比响应体"""

    repositories: list[RepoSummary]
    ranking: list[dict]
    dimension_comparison: dict
    key_differences: list[KeyDifference]
    analyzed_at: str


# ═══════════════════════════════════════════════════════════════
# 接口实现
# ═══════════════════════════════════════════════════════════════


@router.post(
    "",
    response_model=CompareResponse,
    summary="多仓库对比分析",
    description="批量提交多个 GitHub 仓库进行对比分析，返回各维度评分对比和排名。",
)
async def compare_repositories(
    request: CompareRequest,
    session: AsyncSession = Depends(get_db),
) -> CompareResponse:
    """
    多仓库尽调对比

    Args:
        request: 包含 repo_urls 列表的请求体
        session: 数据库会话

    Returns:
        CompareResponse: 对比结果，包含各仓库评分、排名、维度对比

    Raises:
        HTTPException 400: repo_urls 数量不合法
        HTTPException 500: 所有仓库分析失败
    """
    # 校验仓库数量
    if not request.repo_urls or len(request.repo_urls) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个仓库进行对比")
    if len(request.repo_urls) > 5:
        raise HTTPException(status_code=400, detail="最多支持 5 个仓库同时对比")

    # 去重
    unique_urls = list(dict.fromkeys(request.repo_urls))

    try:
        service = AnalysisService(session)
        result = await service.compare_repositories(unique_urls)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return CompareResponse(**result)
