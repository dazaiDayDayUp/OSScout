"""
行业基准数据查询 Tool

供 Agent 在分析过程中调用，获取同类项目的量化基准做对比。
Phase 5 中通过 @tool 装饰器自动注册为 LLM 可调用的 Tool。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger
from app.core.models import BenchmarkData

logger = get_logger(__name__)


async def get_benchmark(
    session: AsyncSession,
    project_type: str,
    metric_name: str | None = None,
) -> list[dict]:
    """
    查询某类项目的行业基准数据

    Agent 在需要行业对比时调用此 Tool，获取量化基准值。

    参数:
        session: 数据库会话（由调用方提供）
        project_type: 项目类型标签，可选值：
            - frontend-framework: 前端框架
            - backend-framework: 后端框架
            - cli-tool: CLI 构建工具
            - state-management: 状态管理库
            - testing-framework: 测试框架
            - ai-ml-library: AI/ML 库
            - security-library: 安全相关库
            - database-driver: 数据库驱动/ORM
            - package-manager: 包管理器
            - utility-library: 通用工具库
        metric_name: 指标名（可选），如 code_review_score、security_policy_score
                     不填则返回该类项目的所有指标基准

    返回:
        基准数据列表，每条包含：
        - metric_name: 指标名
        - avg_value: 平均值
        - median_value: 中位数
        - p25_value: 25 分位
        - p75_value: 75 分位
        - sample_count: 样本项目数
        - description: 自然语言描述（可直接用于报告）

    使用示例:
        # 查询前端框架的 Code-Review 基准
        results = await get_benchmark(session, "frontend-framework", "code_review_score")

        # 查询后端框架的所有安全指标基准
        results = await get_benchmark(session, "backend-framework")
    """
    stmt = select(BenchmarkData).where(
        BenchmarkData.project_type == project_type
    )

    if metric_name:
        stmt = stmt.where(BenchmarkData.metric_name == metric_name)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "metric_name": row.metric_name,
            "avg_value": row.avg_value,
            "median_value": row.median_value,
            "p25_value": row.p25_value,
            "p75_value": row.p75_value,
            "sample_count": row.sample_count,
            "description": row.description,
            "data_version": row.data_version,
        }
        for row in rows
    ]


async def list_project_types(session: AsyncSession) -> list[str]:
    """
    列出所有可用的项目类型标签

    Agent 在不确定类型名称时调用此 Tool 获取有效类型列表。
    """
    from sqlalchemy import distinct

    stmt = select(distinct(BenchmarkData.project_type))
    result = await session.execute(stmt)
    return [row[0] for row in result]


async def list_metrics(session: AsyncSession, project_type: str) -> list[str]:
    """
    列出某类项目下所有可用的指标名

    Agent 在不确定指标名称时调用此 Tool 获取有效指标列表。
    """
    from sqlalchemy import distinct

    stmt = (
        select(distinct(BenchmarkData.metric_name))
        .where(BenchmarkData.project_type == project_type)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result]


# ------------------------------------------------------------------
# Phase 5: LLM Function Calling 包装版本
# ------------------------------------------------------------------
# 延迟导入避免循环依赖：benchmark_tool 被 registry 导入时，
# registry 还未完成初始化。使用函数级导入解决。

async def _benchmark_query_impl(
    project_type: str,
    metric_name: str = "",
) -> list[dict]:
    """查询行业基准数据的 LLM Tool 实现（内部函数）"""
    async with AsyncSessionLocal() as session:
        return await get_benchmark(session, project_type, metric_name or None)


def _register_benchmark_tools():
    """注册 benchmark 相关 Tool 到 Registry"""
    from .registry import tool

    @tool(description="查询某类项目的行业基准数据")
    async def benchmark_query(
        project_type: str,
        metric_name: str = "",
    ) -> list[dict]:
        """查询行业基准数据（LLM 可调用的 Tool）

        在需要与同类项目做量化对比时调用此工具。
        例如："前端框架的平均 PR 合并率是多少？"

        Args:
            project_type: 项目类型标签，可选值：
                - frontend-framework: 前端框架
                - backend-framework: 后端框架
                - cli-tool: CLI 构建工具
                - state-management: 状态管理库
                - testing-framework: 测试框架
                - ai-ml-library: AI/ML 库
                - security-library: 安全相关库
                - database-driver: 数据库驱动/ORM
                - package-manager: 包管理器
                - utility-library: 通用工具库
            metric_name: 指标名（可选），如 code_review_score、
                         security_policy_score。不填则返回所有指标。

        Returns:
            基准数据列表
        """
        return await _benchmark_query_impl(project_type, metric_name)

    @tool(description="列出所有可用的项目类型标签")
    async def benchmark_list_project_types() -> list[str]:
        """列出所有可用的项目类型标签

        在不确定类型名称时调用此 Tool 获取有效类型列表。
        """
        async with AsyncSessionLocal() as session:
            return await list_project_types(session)

    @tool(description="列出某类项目下所有可用的指标名")
    async def benchmark_list_metrics(project_type: str) -> list[str]:
        """列出某类项目下所有可用的指标名

        在不确定指标名称时调用此 Tool 获取有效指标列表。

        Args:
            project_type: 项目类型标签
        """
        async with AsyncSessionLocal() as session:
            return await list_metrics(session, project_type)


# 模块导入时注册（延迟执行，避免循环依赖）
_register_benchmark_tools()
