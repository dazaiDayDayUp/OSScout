"""POST /api/v1/analyze — 提交尽调分析任务"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.analysis_service import AnalysisService

# 创建路由实例，前缀在 __init__.py 中统一注册
router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════


class AnalyzeRequest(BaseModel):
    """提交分析任务的请求体"""

    repo_url: str = Field(
        ...,
        description="GitHub 仓库地址，例如 https://github.com/python-poetry/poetry",
        examples=["https://github.com/python-poetry/poetry"],
    )
    notify_email: str | None = Field(
        default=None,
        description="分析完成后接收邮件通知的邮箱地址（可选）",
        examples=["user@example.com"],
    )


class AnalyzeResponse(BaseModel):
    """提交分析任务的响应体"""

    task_id: int = Field(..., description="分析任务唯一标识")
    status: str = Field(..., description="任务状态：running / pending")
    estimated_seconds: int = Field(
        default=120,
        description="预估分析耗时（秒）",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "task_id": 1,
                "status": "running",
                "estimated_seconds": 120,
            },
        },
    }


# ═══════════════════════════════════════════════════════════════
# 接口实现
# ═══════════════════════════════════════════════════════════════


@router.post(
    "",
    response_model=AnalyzeResponse,
    summary="提交分析任务",
    description="提交一个 GitHub 仓库的尽调分析任务，立即返回任务 ID。分析在后台异步执行，可通过 /tasks/{task_id} 查询进度。",
)
async def analyze(
    request: AnalyzeRequest,
    session: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """
    提交尽调分析任务

    Args:
        request: 包含 repo_url 的请求体
        session: 数据库会话（FastAPI 依赖注入）

    Returns:
        AnalyzeResponse: 包含 task_id 和状态的响应

    Raises:
        HTTPException 400: repo_url 格式不合法
    """
    # 基础 URL 格式校验（更严格的校验在 parse_repo_url 中）
    if not request.repo_url or not request.repo_url.strip():
        raise HTTPException(status_code=400, detail="repo_url 不能为空")

    try:
        service = AnalysisService(session)
        task = await service.submit_analysis(
            request.repo_url.strip(),
            notify_email=request.notify_email,
        )
    except ValueError as exc:
        # parse_repo_url 抛出的格式错误
        raise HTTPException(status_code=400, detail=str(exc))

    return AnalyzeResponse(
        task_id=task.id,
        status=task.status.value,
        estimated_seconds=120,  # 预估耗时，根据实际项目规模可调整
    )
