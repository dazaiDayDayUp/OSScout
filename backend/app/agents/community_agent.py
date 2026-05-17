"""社区健康度分析 Agent"""

from pydantic import BaseModel

from app.core.utils import parse_repo_url
from app.scoring.community import score_community_health, CommunityScoreResult
from app.services import github_service


class CommunityAgentResult(BaseModel):
    """社区健康度 Agent 的输出模型"""

    dimension: str = "community"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    details: dict
    repo: dict


class CommunityAgent:
    """
    社区健康度分析 Agent

    分析维度覆盖 PROJECT_PLAN §7.3 的五项指标：
    - Bus Factor（贡献者集中度）
    - Issue 响应速度
    - PR 合并率
    - 活跃贡献者数量
    - Release 稳定性
    """

    async def analyze(self, repo_url: str) -> CommunityAgentResult:
        """
        分析指定仓库的社区健康度

        Args:
            repo_url: GitHub 仓库地址，例如 https://github.com/python-poetry/poetry

        Returns:
            CommunityAgentResult：结构化的社区健康度分析结果
        """
        # 1. 解析仓库标识
        owner, repo = parse_repo_url(repo_url)

        # 2. 并行采集全部原始数据
        raw_data = await github_service.collect_all_metadata(owner, repo)

        # 3. 调用评分引擎
        score_result = score_community_health(raw_data)

        # 4. 组装输出
        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        return CommunityAgentResult(
            dimension="community",
            score=score_result.total_score,
            max_score=score_result.max_score,
            percentage=percentage,
            findings=score_result.findings,
            risks=score_result.risks,
            details={
                "bus_factor": {
                    "score": score_result.bus_factor.score,
                    "max_score": score_result.bus_factor.max_score,
                    "raw_value": score_result.bus_factor.raw_value,
                    "description": score_result.bus_factor.description,
                },
                "issue_response": {
                    "score": score_result.issue_response.score,
                    "max_score": score_result.issue_response.max_score,
                    "raw_value": score_result.issue_response.raw_value,
                    "description": score_result.issue_response.description,
                },
                "pr_merge_rate": {
                    "score": score_result.pr_merge_rate.score,
                    "max_score": score_result.pr_merge_rate.max_score,
                    "raw_value": score_result.pr_merge_rate.raw_value,
                    "description": score_result.pr_merge_rate.description,
                },
                "active_contributors": {
                    "score": score_result.active_contributors.score,
                    "max_score": score_result.active_contributors.max_score,
                    "raw_value": score_result.active_contributors.raw_value,
                    "description": score_result.active_contributors.description,
                },
                "release_stability": {
                    "score": score_result.release_stability.score,
                    "max_score": score_result.release_stability.max_score,
                    "raw_value": score_result.release_stability.raw_value,
                    "description": score_result.release_stability.description,
                },
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )
