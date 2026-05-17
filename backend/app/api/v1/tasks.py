"""GET /api/v1/tasks/{task_id} — 查询分析任务状态"""

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


class TaskResponse(BaseModel):
    """任务状态查询响应体"""

    task_id: int = Field(..., description="分析任务唯一标识")
    status: str = Field(..., description="任务状态：pending / running / completed / failed")
    repo_id: int | None = Field(None, description="关联的仓库 ID")
    started_at: datetime | None = Field(None, description="分析开始时间")
    completed_at: datetime | None = Field(None, description="分析完成时间")
    report_id: int | None = Field(None, description="关联的报告 ID（仅 completed 状态有值）")
    error_message: str | None = Field(None, description="错误信息（仅 failed 状态有值）")
    duration_seconds: int | None = Field(None, description="分析耗时（秒）")

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": 1,
                "status": "completed",
                "repo_id": 1,
                "started_at": "2026-05-17T10:00:00",
                "completed_at": "2026-05-17T10:01:30",
                "report_id": 2,
                "error_message": None,
                "duration_seconds": 90,
            },
        },
    }


# ═══════════════════════════════════════════════════════════════
# 接口实现
# ═══════════════════════════════════════════════════════════════


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="查询任务状态",
    description="根据任务 ID 查询分析任务的执行状态。completed 状态会附带 report_id，可用于获取完整报告。",
)
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    查询分析任务状态

    Args:
        task_id: 分析任务 ID
        session: 数据库会话

    Returns:
        TaskResponse: 任务状态详情

    Raises:
        HTTPException 404: 任务不存在
    """
    service = AnalysisService(session)
    task = await service.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    # 计算耗时
    duration = None
    if task.started_at and task.completed_at:
        duration = int((task.completed_at - task.started_at).total_seconds())

    # 获取关联的报告 ID（如果已完成）
    report_id = None
    if task.status.value == "completed":
        report = await service.get_report_by_task(task_id)
        if report:
            report_id = report.id

    return TaskResponse(
        task_id=task.id,
        status=task.status.value,
        repo_id=task.repo_id,
        started_at=task.started_at,
        completed_at=task.completed_at,
        report_id=report_id,
        error_message=task.error_message,
        duration_seconds=duration,
    )
