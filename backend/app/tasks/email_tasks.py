"""
邮件推送 Celery 异步任务

分析完成后，由 analysis_tasks 触发，
在后台异步发送尽调报告通知邮件。
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.celery_app import celery_app
from app.core.models import AnalysisTask
from app.services.email_service import send_report_notification


def _create_session():
    """
    创建独立的数据库会话

    Celery Worker 运行在独立进程中，
    使用独立 engine + NullPool 避免连接池跨进程问题。
    """
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        echo=False,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


async def _async_send_email(task_id: int) -> dict:
    """
    异步执行邮件发送

    1. 查询 AnalysisTask 获取 notify_email
    2. 查询关联的 DueDiligenceReport 和 Repository
    3. 调用 email_service 发送 HTML 邮件
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    SessionLocal = _create_session()
    async with SessionLocal() as session:
        # 查询任务并预加载报告和仓库关联
        stmt = (
            select(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .options(
                selectinload(AnalysisTask.report),
                selectinload(AnalysisTask.repository),
            )
        )
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task or not task.notify_email:
            return {"task_id": task_id, "sent": False, "reason": "no_notify_email"}

        report = task.report
        if not report:
            return {"task_id": task_id, "sent": False, "reason": "no_report"}

        repo = task.repository
        if not repo:
            return {"task_id": task_id, "sent": False, "reason": "no_repo"}

        # 发送邮件
        await send_report_notification(
            to_email=task.notify_email,
            report=report,
            repo=repo,
        )

        return {"task_id": task_id, "sent": True, "to": task.notify_email}


@celery_app.task
def send_report_email(task_id: int) -> dict:
    """
    发送尽调报告通知邮件的 Celery 任务

    在分析完成后由 analysis_tasks 触发，
    异步发送 HTML 格式的报告邮件到用户邮箱。

    Args:
        task_id: AnalysisTask 记录 ID（从中获取 notify_email）

    Returns:
        {"task_id": int, "sent": bool, "to": str | None}
    """
    try:
        result = asyncio.run(_async_send_email(task_id))
        return result
    except Exception as exc:
        # 邮件发送失败不应影响分析流程，记录异常后静默返回
        return {"task_id": task_id, "sent": False, "error": str(exc)}
