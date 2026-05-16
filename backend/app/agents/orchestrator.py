"""
Orchestrator 协调器（并发版）

职责：
1. 接收 GitHub 仓库地址
2. 通过 asyncio.gather 并发调度 4 个分析 Agent
3. 汇总各维度结果，计算综合评分
4. 输出结构化的尽调报告中间结果

错误隔离：单个 Agent 失败不影响其他 Agent 执行，
失败的维度输出降级结果（score=0，附带错误提示）。

使用方式：
    from app.agents.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    result = await orchestrator.analyze("https://github.com/python-poetry/poetry")
"""

import asyncio

from pydantic import BaseModel

from app.agents.community_agent import CommunityAgent, parse_repo_url
from app.agents.evolution_agent import EvolutionAgent
from app.agents.quality_agent import QualityAgent
from app.agents.security_agent import SecurityAgent


# 各维度的满分配置（用于降级结果）
_DIMENSION_MAX_SCORES = {
    "community": 30,
    "quality": 25,
    "security": 25,
    "evolution": 20,
}


class OrchestratorResult(BaseModel):
    """Orchestrator 的输出模型：尽调报告中间结果"""

    repo: dict
    dimensions: dict
    overall_score: int
    overall_max_score: int
    overall_percentage: float
    findings: list[str]
    risks: list[str]


class Orchestrator:
    """
    尽调分析协调器

    通过 asyncio.gather 并发调度 4 个分析 Agent，
    单个 Agent 失败时输出降级结果，不影响其他维度。
    """

    def __init__(self):
        """初始化各分析 Agent 实例"""
        self.community_agent = CommunityAgent()
        self.quality_agent = QualityAgent()
        self.security_agent = SecurityAgent()
        self.evolution_agent = EvolutionAgent()

    async def analyze(self, repo_url: str) -> OrchestratorResult:
        """
        执行完整的尽调分析流程（并发调度）

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            OrchestratorResult：包含各维度评分和综合评分的结构化结果
        """
        # 提前解析仓库标识，用于异常降级和报告头部
        owner, repo = parse_repo_url(repo_url)
        repo_info = {"owner": owner, "repo": repo, "url": repo_url}

        # 并发调度 4 个 Agent，return_exceptions=True 实现错误隔离
        results = await asyncio.gather(
            self.community_agent.analyze(repo_url),
            self.quality_agent.analyze(repo_url),
            self.security_agent.analyze(repo_url),
            self.evolution_agent.analyze(repo_url),
            return_exceptions=True,
        )

        # 将结果映射到维度名称
        dimension_names = ["community", "quality", "security", "evolution"]
        dimensions: dict[str, dict] = {}
        overall_score = 0
        overall_max_score = 0
        all_findings: list[str] = []
        all_risks: list[str] = []

        for name, result in zip(dimension_names, results):
            if isinstance(result, Exception):
                # Agent 失败，生成降级结果
                dim_result = self._fallback_result(name, repo_info, str(result))
                all_risks.append(f"{name} 维度分析失败: {result}")
            else:
                # Agent 成功，使用正常结果
                dim_result = result.model_dump()
                all_findings.extend(list(result.findings))
                all_risks.extend(list(result.risks))

            dimensions[name] = dim_result
            overall_score += dim_result["score"]
            overall_max_score += dim_result["max_score"]

        overall_percentage = round(overall_score / overall_max_score * 100, 1)

        return OrchestratorResult(
            repo=repo_info,
            dimensions=dimensions,
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            overall_percentage=overall_percentage,
            findings=all_findings,
            risks=all_risks,
        )

    @staticmethod
    def _fallback_result(dimension: str, repo: dict, error_msg: str) -> dict:
        """
        生成单个维度分析失败时的降级结果

        结构与正常 AgentResult.model_dump() 一致，确保 Reporter 可以正常渲染。
        """
        max_score = _DIMENSION_MAX_SCORES.get(dimension, 0)
        return {
            "dimension": dimension,
            "score": 0,
            "max_score": max_score,
            "percentage": 0.0,
            "findings": [],
            "risks": [f"分析失败: {error_msg}"],
            "details": {},
            "repo": repo,
        }
