"""技术演进分析 Agent（规则评分 + LLM 推理增强）"""

from pydantic import BaseModel

from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.scoring.evolution import score_evolution
from app.services.evolution_service import collect_evolution_data

from .llm_enhancer import EVOLUTION_ENHANCE_PROMPT, LLMEnhancer

logger = get_logger(__name__)


class EvolutionAgentResult(BaseModel):
    """技术演进 Agent 的输出模型"""

    dimension: str = "evolution"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    reasoning: str | None = None  # LLM 推理过程
    details: dict
    repo: dict


class EvolutionAgent:
    """
    技术演进分析 Agent

    分析维度覆盖 PROJECT_PLAN §7.3 的四项指标：
    - 发布频率（最近 12 个月 release 数量）
    - 技术栈更新（核心依赖最新版本差距）
    - Breaking Change 密度（release notes + major version bump）
    - 竞品对比（当前未启用）

    在规则评分基础上接入 LLM 推理。
    """

    def __init__(self) -> None:
        """初始化 Agent，创建 LLM 增强器实例"""
        self._enhancer = LLMEnhancer()

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

        # 3. 调用评分引擎（规则评分打底）
        score_result = score_evolution(raw_data)

        # 4. LLM 推理增强
        llm_result = await self._enhancer.enhance(
            dimension="evolution",
            prompt_template=EVOLUTION_ENHANCE_PROMPT,
            template_vars=self._build_prompt_vars(owner, repo, score_result),
        )

        # 5. 组装输出
        percentage = round(score_result.total_score / 20 * 100, 1)

        all_findings = list(score_result.findings) + list(llm_result.additional_findings)
        all_risks = list(score_result.risks) + list(llm_result.additional_risks)

        return EvolutionAgentResult(
            dimension="evolution",
            score=score_result.total_score,
            max_score=20,
            percentage=percentage,
            findings=all_findings,
            risks=all_risks,
            reasoning=llm_result.reasoning,
            details={
                "release_frequency": self._item_to_dict(score_result.release_frequency),
                "tech_stack_freshness": self._item_to_dict(score_result.tech_stack_freshness),
                "breaking_change": self._item_to_dict(score_result.breaking_change),
                "competitor_comparison": self._item_to_dict(score_result.competitor_comparison),
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )

    @staticmethod
    def _item_to_dict(item) -> dict:
        """安全地将 ScoreItem 转为字典"""
        if item is None:
            return {}
        return {
            "score": getattr(item, "score", 0),
            "max_score": getattr(item, "max_score", 0),
            "raw_value": getattr(item, "raw_value", "N/A"),
            "description": getattr(item, "description", ""),
        }

    @staticmethod
    def _build_prompt_vars(owner: str, repo: str, score_result) -> dict:
        """构造 LLM 增强 Prompt 的模板变量"""
        def item_vals(item):
            if item is None:
                return {"score": 0, "max": 0, "raw": "N/A", "desc": "数据不可用"}
            return {
                "score": getattr(item, "score", 0),
                "max": getattr(item, "max_score", 0),
                "raw": getattr(item, "raw_value", "N/A"),
                "desc": getattr(item, "description", ""),
            }

        freq = item_vals(score_result.release_frequency)
        tech = item_vals(score_result.tech_stack_freshness)
        bc = item_vals(score_result.breaking_change)
        comp = item_vals(score_result.competitor_comparison)

        percentage = round(score_result.total_score / 20 * 100, 1)

        return {
            "owner": owner,
            "repo": repo,
            "release_frequency_score": freq["score"],
            "release_frequency_max": freq["max"],
            "release_frequency_raw": freq["raw"],
            "release_frequency_desc": freq["desc"],
            "tech_stack_freshness_score": tech["score"],
            "tech_stack_freshness_max": tech["max"],
            "tech_stack_freshness_raw": tech["raw"],
            "tech_stack_freshness_desc": tech["desc"],
            "breaking_change_score": bc["score"],
            "breaking_change_max": bc["max"],
            "breaking_change_raw": bc["raw"],
            "breaking_change_desc": bc["desc"],
            "competitor_comparison_score": comp["score"],
            "competitor_comparison_max": comp["max"],
            "competitor_comparison_raw": comp["raw"],
            "competitor_comparison_desc": comp["desc"],
            "total_score": score_result.total_score,
            "max_score": 20,
            "percentage": percentage,
            "findings": "; ".join(score_result.findings) if score_result.findings else "无",
            "risks": "; ".join(score_result.risks) if score_result.risks else "无",
        }
