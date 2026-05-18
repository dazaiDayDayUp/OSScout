"""
Celery 异步任务定义

尽调分析的核心异步任务，由 Celery Worker 执行。

使用方式：
    from app.tasks.analysis_tasks import run_due_diligence
    run_due_diligence.delay(task_id, repo_id, repo_url)
"""

import asyncio
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.agents.orchestrator import Orchestrator
from app.config import settings
from app.core.celery_app import celery_app
from app.core.models import AnalysisTask, DueDiligenceReport, TaskStatus


def _create_session():
    """
    创建独立的数据库会话

    每个 Celery 任务使用独立的 engine + session，
    NullPool 禁用连接池，避免跨事件循环复用 asyncpg 连接。
    """
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        echo=False,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    return SessionLocal


def _calculate_rating(percentage: float) -> str:
    """
    根据总分百分比计算综合评级

    评级标准（PROJECT_PLAN §7.2）：
    - A+ (90-100): 强烈推荐
    - A  (80-89):  推荐
    - B+ (70-79):  谨慎推荐
    - B  (60-69):  可用但需关注
    - C  (50-59):  谨慎使用
    - D  (<50):    不建议使用
    """
    if percentage >= 90:
        return "A+"
    elif percentage >= 80:
        return "A"
    elif percentage >= 70:
        return "B+"
    elif percentage >= 60:
        return "B"
    elif percentage >= 50:
        return "C"
    else:
        return "D"


async def _async_run_analysis(
    task_id: int,
    repo_id: int,
    repo_url: str,
) -> None:
    """
    异步分析执行体

    被同步的 Celery 任务函数用 asyncio.run() 驱动。
    流程与 analysis_service.AnalysisService._run_analysis 一致：
    调 Orchestrator → 计算评级 → 生成报告 → 更新任务状态。
    """
    SessionLocal = _create_session()
    async with SessionLocal() as session:
        # 执行 Orchestrator 分析
        orchestrator = Orchestrator()
        result = await orchestrator.analyze(repo_url)

        # 计算综合评级
        rating = _calculate_rating(result.overall_percentage)

        # 构造原始结果字典
        raw_results = {
            "dimensions": result.dimensions,
            "repo": result.repo,
            "overall_score": result.overall_score,
            "overall_max_score": result.overall_max_score,
            "overall_percentage": result.overall_percentage,
        }

        # 创建 DueDiligenceReport 记录
        report = DueDiligenceReport(
            task_id=task_id,
            repo_id=repo_id,
            overall_score=result.overall_score,
            overall_rating=rating,
            community_score=result.dimensions.get("community", {}).get("score", 0),
            quality_score=result.dimensions.get("quality", {}).get("score", 0),
            security_score=result.dimensions.get("security", {}).get("score", 0),
            evolution_score=result.dimensions.get("evolution", {}).get("score", 0),
            key_findings=result.findings,
            recommendations=result.risks,
            raw_results=raw_results,
        )
        session.add(report)

        # 更新任务状态为 completed
        task = await session.get(AnalysisTask, task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()

        await session.commit()


async def _async_mark_failed(task_id: int, error_msg: str) -> None:
    """异步标记任务失败"""
    SessionLocal = _create_session()
    async with SessionLocal() as session:
        task = await session.get(AnalysisTask, task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = error_msg
            task.completed_at = datetime.utcnow()
        await session.commit()


@celery_app.task
def run_due_diligence(task_id: int, repo_id: int, repo_url: str) -> dict:
    """
    执行尽调分析的 Celery 任务

    这是 Celery Worker 实际调用的入口函数。
    内部用 asyncio.run() 驱动异步分析流程。

    Args:
        task_id: AnalysisTask 记录 ID
        repo_id: Repository 记录 ID
        repo_url: GitHub 仓库地址

    Returns:
        包含 task_id 和状态的字典
    """
    try:
        asyncio.run(_async_run_analysis(task_id, repo_id, repo_url))
        return {"task_id": task_id, "status": "completed"}

    except Exception as exc:
        # 分析失败，标记任务状态
        asyncio.run(_async_mark_failed(task_id, str(exc)))
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
