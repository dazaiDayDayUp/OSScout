"""分析任务服务层：封装任务提交 → 后台分析 → 结果入库的完整生命周期"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import asyncio

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
        """根据 ID 获取尽调报告（预加载 repository 关联）"""
        result = await self.session.execute(
            select(DueDiligenceReport)
            .where(DueDiligenceReport.id == report_id)
            .options(selectinload(DueDiligenceReport.repository)),
        )
        return result.scalar_one_or_none()

    async def get_report_by_task(self, task_id: int) -> DueDiligenceReport | None:
        """根据任务 ID 获取关联的报告（预加载 repository）"""
        result = await self.session.execute(
            select(DueDiligenceReport)
            .where(DueDiligenceReport.task_id == task_id)
            .options(selectinload(DueDiligenceReport.repository)),
        )
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        page: int = 1,
        page_size: int = 20,
        repo_id: int | None = None,
    ) -> tuple[list[DueDiligenceReport], int]:
        """
        分页查询报告列表

        Args:
            page: 当前页码（从 1 开始）
            page_size: 每页条数
            repo_id: 按仓库 ID 过滤（可选）

        Returns:
            (报告列表, 总条数)
        """
        # 构建基础查询条件
        where_clause = []
        if repo_id is not None:
            where_clause.append(DueDiligenceReport.repo_id == repo_id)

        # 查询总条数
        count_stmt = select(func.count(DueDiligenceReport.id))
        if where_clause:
            count_stmt = count_stmt.where(*where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页查询数据，预加载 repository 关联，按创建时间倒序
        offset = (page - 1) * page_size
        stmt = (
            select(DueDiligenceReport)
            .options(selectinload(DueDiligenceReport.repository))
            .order_by(DueDiligenceReport.created_at.desc())
        )
        if where_clause:
            stmt = stmt.where(*where_clause)
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.session.execute(stmt)
        reports = result.scalars().all()

        return list(reports), total

    async def get_repo_history(self, repo_id: int) -> list[DueDiligenceReport]:
        """
        获取某仓库的历史报告列表（用于趋势分析）

        Args:
            repo_id: 仓库 ID

        Returns:
            按创建时间升序排列的报告列表
        """
        stmt = (
            select(DueDiligenceReport)
            .options(selectinload(DueDiligenceReport.repository))
            .where(DueDiligenceReport.repo_id == repo_id)
            .order_by(DueDiligenceReport.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def compare_repositories(
        self,
        repo_urls: list[str],
        max_wait_seconds: int = 300,
    ) -> dict:
        """
        多仓库对比分析

        流程：
        1. 为每个仓库提交分析任务
        2. 轮询等待所有任务完成（最多等 max_wait_seconds）
        3. 汇总各仓库报告，生成对比数据

        Args:
            repo_urls: GitHub 仓库地址列表
            max_wait_seconds: 最大等待时间（秒）

        Returns:
            对比结果字典，包含各仓库评分、维度对比、排名等
        """
        # 提交所有分析任务
        tasks_info = []
        for repo_url in repo_urls:
            try:
                task = await self.submit_analysis(repo_url)
                tasks_info.append({"task_id": task.id, "repo_url": repo_url, "status": "submitted"})
            except Exception as exc:
                tasks_info.append({"task_id": None, "repo_url": repo_url, "status": "failed", "error": str(exc)})

        # 轮询等待所有任务完成
        pending_task_ids = [
            t["task_id"] for t in tasks_info if t["task_id"] is not None
        ]
        waited = 0
        while pending_task_ids and waited < max_wait_seconds:
            await asyncio.sleep(2)
            waited += 2

            # 回滚会话，清除 SQLAlchemy 缓存，确保从数据库读取最新状态
            await self.session.rollback()

            still_pending = []
            for task_id in pending_task_ids:
                task = await self.get_task(task_id)
                if task and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    # 更新任务信息
                    for t in tasks_info:
                        if t["task_id"] == task_id:
                            t["status"] = task.status.value
                            if task.status == TaskStatus.FAILED:
                                t["error"] = task.error_message
                else:
                    still_pending.append(task_id)
            pending_task_ids = still_pending

        # 收集所有成功完成的报告
        reports = []
        for t in tasks_info:
            if t["status"] == "completed" and t["task_id"]:
                report = await self.get_report_by_task(t["task_id"])
                if report:
                    reports.append(report)

        if not reports:
            raise ValueError("所有仓库分析均失败，无法生成对比报告")

        # 构造对比结果
        return self._build_comparison(reports)

    def _build_comparison(self, reports: list[DueDiligenceReport]) -> dict:
        """根据报告列表构建对比数据"""
        # 各仓库评分概览
        repo_summaries = []
        for report in reports:
            repo = report.repository
            repo_summaries.append({
                "repo_id": report.repo_id,
                "owner": repo.owner if repo else "unknown",
                "name": repo.repo if repo else "unknown",
                "url": repo.url if repo else "",
                "overall_score": report.overall_score,
                "overall_rating": report.overall_rating,
                "community_score": report.community_score,
                "quality_score": report.quality_score,
                "security_score": report.security_score,
                "evolution_score": report.evolution_score,
            })

        # 按总分排序
        ranking = sorted(repo_summaries, key=lambda x: x["overall_score"], reverse=True)

        # 各维度并排对比
        dimension_comparison = {
            "overall": [{"repo": r["name"], "score": r["overall_score"]} for r in repo_summaries],
            "community": [{"repo": r["name"], "score": r["community_score"]} for r in repo_summaries],
            "quality": [{"repo": r["name"], "score": r["quality_score"]} for r in repo_summaries],
            "security": [{"repo": r["name"], "score": r["security_score"]} for r in repo_summaries],
            "evolution": [{"repo": r["name"], "score": r["evolution_score"]} for r in repo_summaries],
        }

        # 关键差异：找出各维度最高和最低
        key_differences = []
        for dim_name, dim_key in [
            ("综合得分", "overall_score"),
            ("社区健康度", "community_score"),
            ("代码质量", "quality_score"),
            ("安全评分", "security_score"),
            ("技术演进", "evolution_score"),
        ]:
            scores = [(r["name"], r[dim_key]) for r in repo_summaries]
            scores.sort(key=lambda x: x[1], reverse=True)
            if len(scores) >= 2 and scores[0][1] != scores[-1][1]:
                key_differences.append({
                    "dimension": dim_name,
                    "highest": {"repo": scores[0][0], "score": scores[0][1]},
                    "lowest": {"repo": scores[-1][0], "score": scores[-1][1]},
                    "gap": scores[0][1] - scores[-1][1],
                })

        return {
            "repositories": repo_summaries,
            "ranking": [{"rank": i + 1, **r} for i, r in enumerate(ranking)],
            "dimension_comparison": dimension_comparison,
            "key_differences": key_differences,
            "analyzed_at": datetime.utcnow().isoformat(),
        }
