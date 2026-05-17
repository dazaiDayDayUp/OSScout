"""技术演进分析 Agent"""

from pydantic import BaseModel

from app.core.utils import parse_repo_url
from app.scoring.evolution import score_evolution, EvolutionScoreResult
from app.services.evolution_service import collect_evolution_data


class EvolutionAgentResult(BaseModel):
    """技术演进 Agent 的输出模型"""

    dimension: str = "evolution"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    details: dict
    repo: dict


class EvolutionAgent:
    """
    技术演进分析 Agent

    分析维度覆盖 PROJECT_PLAN §7.3 的四项指标：
    - 发布频率（最近 12 个月 release 数量）
    - 技术栈更新（核心依赖最新版本差距）
    - Breaking Change 密度（release notes + major version bump）
    - 竞品对比（Phase 1 跳过）
    """

    async def analyze(self, repo_url: str) -> EvolutionAgentResult:
        """
        分析指定仓库的技术演进状况

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            EvolutionAgentResult：结构化的技术演进分析结果
        """
        # 1. 解析仓库标识
        owner, repo = parse_repo_url(repo_url)

        # 2. 采集技术演进数据
        raw_data = await collect_evolution_data(owner, repo)

        # 3. 调用评分引擎
        score_result = score_evolution(raw_data)

        # 4. 组装输出
        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        return EvolutionAgentResult(
            dimension="evolution",
            score=score_result.total_score,
            max_score=score_result.max_score,
            percentage=percentage,
            findings=score_result.findings,
            risks=score_result.risks,
            details={
                "release_frequency": {
                    "score": score_result.release_frequency.score,
                    "max_score": score_result.release_frequency.max_score,
                    "raw_value": score_result.release_frequency.raw_value,
                    "description": score_result.release_frequency.description,
                },
                "tech_stack_freshness": {
                    "score": score_result.tech_stack_freshness.score,
                    "max_score": score_result.tech_stack_freshness.max_score,
                    "raw_value": score_result.tech_stack_freshness.raw_value,
                    "description": score_result.tech_stack_freshness.description,
                },
                "breaking_change": {
                    "score": score_result.breaking_change.score,
                    "max_score": score_result.breaking_change.max_score,
                    "raw_value": score_result.breaking_change.raw_value,
                    "description": score_result.breaking_change.description,
                },
                "competitor_comparison": {
                    "score": score_result.competitor_comparison.score,
                    "max_score": score_result.competitor_comparison.max_score,
                    "raw_value": score_result.competitor_comparison.raw_value,
                    "description": score_result.competitor_comparison.description,
                },
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )
