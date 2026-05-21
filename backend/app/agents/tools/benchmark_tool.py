"""
行业基准数据查询 Tool

供 Agent 在分析过程中调用，获取同类项目的量化基准做对比。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import BenchmarkData


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
