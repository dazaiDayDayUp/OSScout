"""
Orchestration Layer — Phase 5.4 Plan-and-Execute 编排引擎

Layer 2 编排引擎，负责：
1. PlanEngine: LLM 自主制定分析计划
2. ExecuteEngine: 按 DAG 依赖自动并行执行
3. SharedMemory: 进程内缓存，数据只采一次

使用方式：
    from app.agents.orchestration import PlanEngine, ExecuteEngine, SharedMemory

    # 制定计划
    plan_engine = PlanEngine()
    plan = await plan_engine.create_plan(repo_url, llm)

    # 执行计划
    execute_engine = ExecuteEngine(llm=llm)
    results = await execute_engine.run(plan, context={"owner": "a", "repo": "b"})
"""

from .execute_engine import ExecuteEngine
from .plan_engine import AnalysisPlan, PlanEngine, PlanStep
from .shared_memory import SharedMemory

__all__ = [
    "SharedMemory",
    "PlanEngine",
    "PlanStep",
    "AnalysisPlan",
    "ExecuteEngine",
]
