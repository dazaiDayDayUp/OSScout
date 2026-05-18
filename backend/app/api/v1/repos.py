"""GET /api/v1/repos/{repo_id}/history — 仓库历史趋势"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analysis_service import AnalysisService

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 响应模型
# ═══════════════════════════════════════════════════════════════


class MetricDataPoint(BaseModel):
    """单个指标的时间点数据"""

    date: datetime = Field(..., description="记录时间")
    value: int = Field(..., description="指标值")


class TrendMetrics(BaseModel):
    """各维度趋势数据"""

    overall: list[MetricDataPoint] = Field(default_factory=list, description="综合得分趋势")
    community: list[MetricDataPoint] = Field(default_factory=list, description="社区健康度趋势")
    quality: list[MetricDataPoint] = Field(default_factory=list, description="代码质量趋势")
    security: list[MetricDataPoint] = Field(default_factory=list, description="安全评分趋势")
    evolution: list[MetricDataPoint] = Field(default_factory=list, description="技术演进趋势")


class RepoHistoryResponse(BaseModel):
    """仓库历史趋势响应体"""

    repo_id: int = Field(..., description="仓库 ID")
    repo_owner: str = Field(..., description="仓库所有者")
    repo_name: str = Field(..., description="仓库名称")
    total_analyses: int = Field(..., description="分析次数")
    trends: TrendMetrics = Field(..., description="各维度趋势数据")


# ═══════════════════════════════════════════════════════════════
# 接口实现
# ═══════════════════════════════════════════════════════════════


@router.get(
    "/{repo_id}/history",
    response_model=RepoHistoryResponse,
    summary="仓库历史趋势",
    description="获取某仓库历次尽调分析的指标趋势，用于观察项目健康度随时间的变化。",
)
async def get_repo_history(
    repo_id: int,
    session: AsyncSession = Depends(get_db),
) -> RepoHistoryResponse:
    """
    查询仓库历史分析趋势

    Args:
        repo_id: 仓库 ID
        session: 数据库会话

    Returns:
        RepoHistoryResponse: 各维度指标时序数据

    Raises:
        HTTPException 404: 仓库无历史分析记录
    """
    service = AnalysisService(session)
    reports = await service.get_repo_history(repo_id)

    if not reports:
        raise HTTPException(
            status_code=404,
            detail=f"仓库 {repo_id} 暂无历史分析记录",
        )

    # 提取时序指标
    overall_trend = []
    community_trend = []
    quality_trend = []
    security_trend = []
    evolution_trend = []

    for report in reports:
        overall_trend.append(MetricDataPoint(date=report.created_at, value=report.overall_score))
        community_trend.append(MetricDataPoint(date=report.created_at, value=report.community_score))
        quality_trend.append(MetricDataPoint(date=report.created_at, value=report.quality_score))
        security_trend.append(MetricDataPoint(date=report.created_at, value=report.security_score))
        evolution_trend.append(MetricDataPoint(date=report.created_at, value=report.evolution_score))

    # 获取仓库信息（所有报告属于同一仓库，取第一条的关联即可）
    repo = reports[0].repository

    return RepoHistoryResponse(
        repo_id=repo_id,
        repo_owner=repo.owner if repo else "unknown",
        repo_name=repo.repo if repo else "unknown",
        total_analyses=len(reports),
        trends=TrendMetrics(
            overall=overall_trend,
            community=community_trend,
            quality=quality_trend,
            security=security_trend,
            evolution=evolution_trend,
        ),
    )
