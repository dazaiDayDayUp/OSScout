"""
Orchestrator 协调器（串行版）

职责：
1. 接收 GitHub 仓库地址
2. 按顺序调度各分析 Agent
3. 汇总各维度结果，计算综合评分
4. 输出结构化的尽调报告中间结果

Phase 1.1 仅调度 community_agent。
Phase 1.5 将升级为 asyncio.gather 并发调度 4 个 Agent。

使用方式：
    from app.agents.orchestrator import Orchestrator
    orchestrator = Orchestrator()
    result = await orchestrator.analyze("https://github.com/python-poetry/poetry")
"""

from pydantic import BaseModel

from app.agents.community_agent import CommunityAgent, CommunityAgentResult


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

    当前版本（Phase 1.1）只调度社区健康度 Agent，
    后续会依次加入代码质量、安全分析、技术演进 Agent。
    """

    def __init__(self):
        """初始化各分析 Agent 实例"""
        self.community_agent = CommunityAgent()

    async def analyze(self, repo_url: str) -> OrchestratorResult:
        """
        执行完整的尽调分析流程

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            OrchestratorResult：包含各维度评分和综合评分的结构化结果
        """
        # Phase 1.1：串行执行社区健康度分析
        community_result = await self.community_agent.analyze(repo_url)

        # 汇总各维度结果
        dimensions = {
            "community": community_result.model_dump(),
        }

        # 计算综合评分（目前只有社区健康度一个维度）
        overall_score = community_result.score
        overall_max_score = community_result.max_score
        overall_percentage = round(overall_score / overall_max_score * 100, 1)

        # 汇总所有发现和风险
        all_findings = list(community_result.findings)
        all_risks = list(community_result.risks)

        return OrchestratorResult(
            repo=community_result.repo,
            dimensions=dimensions,
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            overall_percentage=overall_percentage,
            findings=all_findings,
            risks=all_risks,
        )
