"""分析任务服务层：封装任务提交 → 后台分析 → 结果入库的完整生命周期"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import parse_repo_url
from app.core.models import AnalysisTask, DueDiligenceReport, Repository, TaskStatus
from app.services import github_service
from app.tasks.analysis_tasks import run_due_diligence


class AnalysisService:
    """
    分析任务服务

    负责分析任务的全生命周期管理，从提交到结果入库。
    submit_analysis() 会立即返回，实际分析由 Celery Worker 异步执行。
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

        # 提交 Celery 异步任务，立即返回不阻塞
        run_due_diligence.delay(task.id, repository.id, repo_url)

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
