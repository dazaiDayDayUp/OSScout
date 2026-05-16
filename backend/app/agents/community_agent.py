"""
社区健康度分析 Agent

职责：
1. 接收 GitHub 仓库地址
2. 调用 github_service 采集原始数据
3. 调用 scoring 模块计算评分
4. 输出结构化的社区健康度分析结果

使用方式：
    from app.agents.community_agent import CommunityAgent
    agent = CommunityAgent()
    result = await agent.analyze("https://github.com/python-poetry/poetry")
"""

from urllib.parse import urlparse

from pydantic import BaseModel

from app.scoring.community import score_community_health, CommunityScoreResult
from app.services import mcp_github_service as github_service


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


def parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    从 GitHub 仓库地址中解析 owner 和 repo 名称

    支持的格式：
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - github.com/owner/repo

    Args:
        repo_url: GitHub 仓库地址

    Returns:
        (owner, repo) 元组

    Raises:
        ValueError: URL 格式不合法
    """
    # 去掉 .git 后缀
    url = repo_url.strip().removesuffix(".git")

    # 如果没有协议头，补一个以便 urlparse 正确解析
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]

    if len(path_parts) < 2:
        raise ValueError(
            f"无效的 GitHub 仓库地址：{repo_url}\n"
            "期望格式：https://github.com/owner/repo"
        )

    owner = path_parts[0]
    repo = path_parts[1]

    return owner, repo
