"""GET /api/v1/reports/{report_id} — 获取尽调报告"""

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


class DimensionScore(BaseModel):
    """单个维度的评分详情"""

    score: int = Field(..., description="实际得分")
    max_score: int = Field(..., description="满分")
    percentage: float = Field(..., description="得分百分比")
    findings: list[str] = Field(default_factory=list, description="关键发现")
    risks: list[str] = Field(default_factory=list, description="风险提示")
    details: dict = Field(default_factory=dict, description="详细指标")


class ReportResponse(BaseModel):
    """尽调报告响应体"""

    report_id: int = Field(..., description="报告唯一标识")
    task_id: int = Field(..., description="关联的任务 ID")
    repo: dict = Field(..., description="仓库信息")
    overall: dict = Field(..., description="综合评分")
    dimensions: dict = Field(..., description="各维度评分详情")
    key_findings: list[str] = Field(default_factory=list, description="关键发现")
    recommendations: list[str] = Field(default_factory=list, description="建议")
    created_at: datetime | None = Field(None, description="报告生成时间")


# ═══════════════════════════════════════════════════════════════
# 接口实现
# ═══════════════════════════════════════════════════════════════


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="获取尽调报告",
    description="根据报告 ID 获取完整的尽调报告，包含各维度评分、关键发现和建议。",
)
async def get_report(
    report_id: int,
    session: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    获取尽调报告详情

    Args:
        report_id: 报告 ID
        session: 数据库会话

    Returns:
        ReportResponse: 完整的报告内容

    Raises:
        HTTPException 404: 报告不存在
    """
    service = AnalysisService(session)
    report = await service.get_report(report_id)

    if not report:
        raise HTTPException(status_code=404, detail=f"报告 {report_id} 不存在")

    # 从 raw_results 中提取维度详情
    raw = report.raw_results or {}
    dimensions_raw = raw.get("dimensions", {})
    repo_raw = raw.get("repo", {})

    # 构造 dimensions 响应结构
    dimensions = {}
    for dim_name, dim_data in dimensions_raw.items():
        if isinstance(dim_data, dict):
            dimensions[dim_name] = {
                "score": dim_data.get("score", 0),
                "max_score": dim_data.get("max_score", 0),
                "percentage": dim_data.get("percentage", 0.0),
                "findings": dim_data.get("findings", []),
                "risks": dim_data.get("risks", []),
                "details": dim_data.get("details", {}),
            }

    # 构造 overall 结构
    overall = {
        "score": report.overall_score,
        "rating": report.overall_rating,
        "max_score": raw.get("overall_max_score", 100),
        "percentage": raw.get("overall_percentage", 0.0),
    }

    return ReportResponse(
        report_id=report.id,
        task_id=report.task_id,
        repo=repo_raw,
        overall=overall,
        dimensions=dimensions,
        key_findings=report.key_findings or [],
        recommendations=report.recommendations or [],
        created_at=report.created_at,
    )
