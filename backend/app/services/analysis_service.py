"""分析任务服务层：封装任务提交 → 后台分析 → 结果入库的完整生命周期"""

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import parse_repo_url
from app.agents.orchestrator import Orchestrator
from app.core.database import AsyncSessionLocal
from app.core.models import AnalysisTask, DueDiligenceReport, Repository, TaskStatus
from app.services import github_service


class AnalysisService:
    """
    分析任务服务

    负责分析任务的全生命周期管理，从提交到结果入库。
    submit_analysis() 会立即返回，实际分析在后台 asyncio task 中执行。
    """

    def __init__(self, session: AsyncSession):
        """初始化，注入数据库会话"""
        self.session = session

    async def submit_analysis(self, repo_url: str) -> AnalysisTask:
        """
        提交分析任务

        流程：
        1. 解析仓库标识（owner/repo）
        2. 获取或创建 Repository 记录
        3. 创建 AnalysisTask 记录（status=running）
        4. 启动后台分析任务（不阻塞）
        5. 返回 task 对象（此时分析已在后台运行）

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            AnalysisTask: 新创建的任务记录
        """
        owner, repo = parse_repo_url(repo_url)

        # 获取或创建 Repository 记录
        repository = await self._get_or_create_repo(owner, repo, repo_url)

        # 创建 AnalysisTask 记录
        task = AnalysisTask(
            repo_id=repository.id,
            status=TaskStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)

        # 启动后台分析任务，不等待完成
        # Phase 2.2 将替换为 Celery 任务
        asyncio.create_task(
            self._run_analysis(task.id, repository.id, repo_url),
        )

        return task

    async def _get_or_create_repo(
        self,
        owner: str,
        repo: str,
        url: str,
    ) -> Repository:
        """
        获取或创建 Repository 记录

        先查数据库，已存在则直接返回；
        不存在则从 GitHub API 拉取基础信息后创建。

        Args:
            owner: 仓库所有者
            repo: 仓库名称
            url: 完整仓库地址

        Returns:
            Repository: 数据库中的仓库记录
        """
        result = await self.session.execute(
            select(Repository).where(
                Repository.owner == owner,
                Repository.repo == repo,
            ),
        )
        repository = result.scalar_one_or_none()

        if repository:
            return repository

        # 从 GitHub API 获取基础元数据
        try:
            metadata = await github_service.collect_all_metadata(owner, repo)
            repo_meta = metadata.get("metadata", {})
        except Exception:
            # GitHub API 调用失败时，用最小信息创建记录
            repo_meta = {}

        license_info = repo_meta.get("license") or {}

        repository = Repository(
            owner=owner,
            repo=repo,
            url=url,
            description=repo_meta.get("description"),
            primary_language=repo_meta.get("language"),
            star_count=repo_meta.get("stargazers_count", 0) or 0,
            fork_count=repo_meta.get("forks_count", 0) or 0,
            open_issue_count=repo_meta.get("open_issues_count", 0) or 0,
            license=license_info.get("spdx_id"),
        )
        self.session.add(repository)
        await self.session.commit()
        await self.session.refresh(repository)
        return repository

    async def _run_analysis(
        self,
        task_id: int,
        repo_id: int,
        repo_url: str,
    ) -> None:
        """
        执行分析（后台任务）

        此函数在 asyncio.create_task() 中运行，使用独立的数据库会话，
        因为原 session 可能随 HTTP 请求结束而关闭。

        分析完成后写入 DueDiligenceReport，更新 AnalysisTask 状态。
        任何异常都会被捕获，任务状态标记为 failed。

        Args:
            task_id: AnalysisTask 记录 ID
            repo_id: Repository 记录 ID
            repo_url: 仓库地址
        """
        async with AsyncSessionLocal() as session:
            try:
                # 执行 Orchestrator 分析
                orchestrator = Orchestrator()
                result = await orchestrator.analyze(repo_url)

                # 计算综合评级
                rating = self._calculate_rating(result.overall_percentage)

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
                    recommendations=result.risks,  # Phase 2.1 用 risks 占位，Phase 3 接入 LLM 生成真正建议
                    raw_results=raw_results,
                )
                session.add(report)

                # 更新任务状态为 completed
                task = await session.get(AnalysisTask, task_id)
                if task:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.utcnow()

                await session.commit()

            except Exception as exc:
                # 分析失败，更新任务状态为 failed
                task = await session.get(AnalysisTask, task_id)
                if task:
                    task.status = TaskStatus.FAILED
                    task.error_message = str(exc)
                    task.completed_at = datetime.utcnow()
                await session.commit()

    @staticmethod
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

    # ═══════════════════════════════════════════════════════════════
    # 查询方法
    # ═══════════════════════════════════════════════════════════════

    async def get_task(self, task_id: int) -> AnalysisTask | None:
        """根据 ID 获取分析任务"""
        result = await self.session.execute(
            select(AnalysisTask).where(AnalysisTask.id == task_id),
        )
        return result.scalar_one_or_none()

    async def get_report(self, report_id: int) -> DueDiligenceReport | None:
        """根据 ID 获取尽调报告"""
        result = await self.session.execute(
            select(DueDiligenceReport).where(DueDiligenceReport.id == report_id),
        )
        return result.scalar_one_or_none()

    async def get_report_by_task(self, task_id: int) -> DueDiligenceReport | None:
        """根据任务 ID 获取关联的报告"""
        result = await self.session.execute(
            select(DueDiligenceReport).where(DueDiligenceReport.task_id == task_id),
        )
        return result.scalar_one_or_none()
