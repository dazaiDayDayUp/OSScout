"""社区健康度分析 Agent（规则评分 + LLM 推理增强）"""

from pydantic import BaseModel

from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.scoring.community import score_community_health
from app.services import github_service

from .llm_enhancer import COMMUNITY_ENHANCE_PROMPT, LLMEnhancer

logger = get_logger(__name__)


class CommunityAgentResult(BaseModel):
    """社区健康度 Agent 的输出模型"""

    dimension: str = "community"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    reasoning: str | None = None  # LLM 推理过程
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

    Phase 3.3 增强：在规则评分基础上接入 LLM 推理，
    增加 reasoning 字段和跨指标的关联分析。
    """

    def __init__(self) -> None:
        """初始化 Agent，创建 LLM 增强器实例"""
        self._enhancer = LLMEnhancer()

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

        # 3. 调用评分引擎（规则评分打底）
        score_result = score_community_health(raw_data)

        # 4. LLM 推理增强
        llm_result = await self._enhancer.enhance(
            dimension="community",
            prompt_template=COMMUNITY_ENHANCE_PROMPT,
            template_vars=self._build_prompt_vars(owner, repo, raw_data, score_result),
        )

        # 5. 组装输出（合并规则评分和 LLM 增强）
        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        # 合并 findings 和 risks（规则评分 + LLM 补充）
        all_findings = list(score_result.findings) + list(llm_result.additional_findings)
        all_risks = list(score_result.risks) + list(llm_result.additional_risks)

        return CommunityAgentResult(
            dimension="community",
            score=score_result.total_score,
            max_score=score_result.max_score,
            percentage=percentage,
            findings=all_findings,
            risks=all_risks,
            reasoning=llm_result.reasoning,
            details={
                "bus_factor": self._item_to_dict(score_result.bus_factor),
                "issue_response": self._item_to_dict(score_result.issue_response),
                "pr_merge_rate": self._item_to_dict(score_result.pr_merge_rate),
                "active_contributors": self._item_to_dict(score_result.active_contributors),
                "release_stability": self._item_to_dict(score_result.release_stability),
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )

    @staticmethod
    def _item_to_dict(item) -> dict:
        """安全地将 ScoreItem 转为字典（None 时返回空字典）"""
        if item is None:
            return {}
        return {
            "score": item.score,
            "max_score": item.max_score,
            "raw_value": item.raw_value,
            "description": item.description,
        }

    @staticmethod
    def _build_prompt_vars(owner: str, repo: str, raw_data: dict, score_result) -> dict:
        """构造 LLM 增强 Prompt 的模板变量"""
        metadata = raw_data.get("metadata", {})
        commit_activity = raw_data.get("commit_activity", {})

        # 计算最近 90 天 commits
        recent_commits = 0
        if isinstance(commit_activity, dict) and "all" in commit_activity:
            # 取最后 13 周的数据（约 90 天）
            recent_commits = sum(commit_activity["all"][-13:])

        def item_vals(item):
            if item is None:
                return {"score": 0, "max": 0, "raw": "N/A", "desc": "数据不可用"}
            return {
                "score": item.score,
                "max": item.max_score,
                "raw": item.raw_value,
                "desc": item.description,
            }

        bf = item_vals(score_result.bus_factor)
        ir = item_vals(score_result.issue_response)
        pr = item_vals(score_result.pr_merge_rate)
        ac = item_vals(score_result.active_contributors)
        rs = item_vals(score_result.release_stability)

        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        return {
            "owner": owner,
            "repo": repo,
            "bus_factor_score": bf["score"],
            "bus_factor_max": bf["max"],
            "bus_factor_raw": bf["raw"],
            "bus_factor_desc": bf["desc"],
            "issue_response_score": ir["score"],
            "issue_response_max": ir["max"],
            "issue_response_raw": ir["raw"],
            "issue_response_desc": ir["desc"],
            "pr_merge_rate_score": pr["score"],
            "pr_merge_rate_max": pr["max"],
            "pr_merge_rate_raw": pr["raw"],
            "pr_merge_rate_desc": pr["desc"],
            "active_contributors_score": ac["score"],
            "active_contributors_max": ac["max"],
            "active_contributors_raw": ac["raw"],
            "active_contributors_desc": ac["desc"],
            "release_stability_score": rs["score"],
            "release_stability_max": rs["max"],
            "release_stability_raw": rs["raw"],
            "release_stability_desc": rs["desc"],
            "total_score": score_result.total_score,
            "max_score": score_result.max_score,
            "percentage": percentage,
            "findings": "; ".join(score_result.findings) if score_result.findings else "无",
            "risks": "; ".join(score_result.risks) if score_result.risks else "无",
            "star_count": metadata.get("stargazers_count", "N/A"),
            "fork_count": metadata.get("forks_count", "N/A"),
            "open_issue_count": metadata.get("open_issues_count", "N/A"),
            "recent_commits": recent_commits,
        }
