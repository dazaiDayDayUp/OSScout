"""综合报告 Agent（Synthesis Agent）

接收 4 个分析 Agent 的结果 + RAG 校准数据，
调用 LLM 生成结构化的最终尽调报告。

核心设计：
1. 输入：OrchestratorResult（含 dimensions / calibrations / conflicts / react_summary）
2. 处理：LLM 综合推理，生成执行摘要、风险矩阵、明确建议
3. 输出：SynthesisReport（结构化 Pydantic 模型）
4. 可解释性：每条结论标注数据来源（规则评分 / LLM 推理 / RAG 引用）

报告结构（PROJECT_PLAN §7.2 + §9.3）：
- 执行摘要
- 各维度一句话总结
- 风险矩阵（高/中/低）
- 明确建议（3-5条）
- 数据来源标注
"""

from pydantic import BaseModel, Field

from app.core.logger import get_logger
from app.llm.factory import get_llm_provider
from app.llm.schemas import LLMMessage
from app.llm.templates import PromptTemplate

from .llm_enhancer import LLMEnhancementOutput

logger = get_logger(__name__)


# =============================================================================
# 综合报告输出 Schema
# =============================================================================

class DimensionSummary(BaseModel):
    """单个维度的一句话总结"""

    name: str = Field(description="维度名称：community/quality/security/evolution")
    score: int = Field(description="得分")
    max_score: int = Field(description="满分")
    percentage: float = Field(description="百分比")
    assessment: str = Field(
        description="一句话评估，不超过 80 字，包含核心判断和关键风险"
    )


class RiskItem(BaseModel):
    """风险矩阵单项"""

    level: str = Field(description="风险等级：high / medium / low")
    category: str = Field(description="所属维度或跨维度")
    description: str = Field(description="风险描述，不超过 100 字")
    source: str = Field(
        description="数据来源：规则评分 / LLM推理 / RAG引用 / 冲突检测"
    )


class SynthesisReport(BaseModel):
    """综合报告的完整结构化输出"""

    executive_summary: str = Field(
        description="执行摘要：面向决策者的 150 字以内的核心结论，"
                    "包含评级、核心优势和最关键风险"
    )

    overall_rating: str = Field(description="综合评级：A+/A/B+/B/C/D")
    overall_score: int = Field(description="总分：0-100")

    dimension_summaries: list[DimensionSummary] = Field(
        description="4 个维度的一句话总结"
    )

    risk_matrix: list[RiskItem] = Field(
        description="风险矩阵：按严重程度排序的风险列表"
    )

    top_recommendations: list[str] = Field(
        description="3-5 条明确、可操作的建议，按优先级排序"
    )

    data_source_summary: str = Field(
        description="数据来源概述：说明本报告基于规则评分、LLM推理和RAG引用的综合判断"
    )


# =============================================================================
# Prompt 模板
# =============================================================================

SYNTHESIS_PROMPT = PromptTemplate(
    name="synthesis_report",
    description="综合报告 Agent 的 Prompt",
    template="""你是一位资深技术顾问，正在为技术团队撰写开源项目尽调报告。

## 分析数据

### 项目信息
- 仓库：{owner}/{repo}
- 综合评分：{overall_score}/{overall_max_score}（{overall_percentage}%）

### 各维度评分

【社区健康度】{community_score}/30（{community_percentage}%）
- 关键发现：{community_findings}
- 风险：{community_risks}
- LLM 推理：{community_reasoning}

【代码质量】{quality_score}/25（{quality_percentage}%）
- 关键发现：{quality_findings}
- 风险：{quality_risks}
- LLM 推理：{quality_reasoning}

【安全评分】{security_score}/25（{security_percentage}%）
- 关键发现：{security_findings}
- 风险：{security_risks}
- LLM 推理：{security_reasoning}

【技术演进】{evolution_score}/20（{evolution_percentage}%）
- 关键发现：{evolution_findings}
- 风险：{evolution_risks}
- LLM 推理：{evolution_reasoning}

### RAG 知识库校准引用
{calibration_summary}

### 维度间冲突检测
{conflicts_summary}

## 报告要求

请基于以上数据生成结构化的尽调报告：

1. **执行摘要**：150 字以内，面向决策者，包含评级和核心判断
2. **各维度总结**：每个维度一句话，包含得分和关键风险
3. **风险矩阵**：识别所有 high/medium/low 风险，按严重程度排序
4. **明确建议**：3-5 条可操作的建议，按优先级排序
5. **数据来源**：说明每条结论的依据（规则评分 / LLM推理 / RAG引用）

注意：
- 必须基于提供的数据，不要编造数据
- 风险等级判断标准：high=必须立即处理，medium=需要关注，low=了解即可
- 建议必须具体可操作，避免空泛的"加强测试"之类的表述""",
)


# =============================================================================
# Synthesis Agent
# =============================================================================

class SynthesisAgent:
    """
    综合报告 Agent

    接收 Orchestrator 的分析结果，调用 LLM 生成结构化的最终报告。
    报告强调可解释性——每条结论都标注数据来源。
    """

    def __init__(self) -> None:
        """初始化 Agent，创建 LLM Provider 实例"""
        self._provider = get_llm_provider()

    async def generate(self, orchestrator_result: dict) -> SynthesisReport:
        """
        生成综合报告

        Args:
            orchestrator_result: OrchestratorResult.model_dump() 后的字典

        Returns:
            SynthesisReport：结构化的综合报告
        """
        logger.info(
            "开始生成综合报告",
            repo=f"{orchestrator_result['repo']['owner']}/{orchestrator_result['repo']['repo']}",
            overall_score=orchestrator_result["overall_score"],
        )

        # 1. 构造 Prompt 变量
        template_vars = self._build_template_vars(orchestrator_result)

        # 2. 渲染 Prompt
        prompt_text = SYNTHESIS_PROMPT.render(**template_vars)

        # 3. 构造消息
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "你是一位资深开源项目评估专家和技术顾问。"
                    "请基于提供的数据生成专业的尽调报告。"
                    "注意：请保持简洁，executive_summary 不超过 150 字，"
                    "每条 risk 和 recommendation 不超过 100 字。"
                ),
            ),
            LLMMessage(role="user", content=prompt_text),
        ]

        # 4. 调用 LLM（结构化输出）
        try:
            result = await self._provider.chat_structured(
                messages=messages,
                output_schema=SynthesisReport,
                temperature=0.5,
                max_tokens=3000,
            )
            logger.info(
                "综合报告生成完成",
                rating=result.overall_rating,
                risks=len(result.risk_matrix),
                recommendations=len(result.top_recommendations),
            )
            return result

        except Exception as e:
            logger.warning(
                "综合报告 LLM 生成失败，使用降级报告",
                error=str(e),
            )
            return self._fallback_report(orchestrator_result)

    @staticmethod
    def _build_template_vars(result: dict) -> dict:
        """从 OrchestratorResult 构造 Prompt 模板变量"""
        repo = result["repo"]
        dims = result["dimensions"]

        def dim_summary(name: str) -> dict:
            d = dims.get(name, {})
            return {
                "score": d.get("score", 0),
                "percentage": d.get("percentage", 0),
                "findings": "; ".join(d.get("findings", [])[:3]) or "无",
                "risks": "; ".join(d.get("risks", [])[:3]) or "无",
                "reasoning": (d.get("reasoning") or "无")[:200],
            }

        community = dim_summary("community")
        quality = dim_summary("quality")
        security = dim_summary("security")
        evolution = dim_summary("evolution")

        # RAG 校准摘要
        calibrations = result.get("calibrations", {})
        cal_lines: list[str] = []
        for dim_name, cals in calibrations.items():
            if cals:
                topics = [c.get("metadata", {}).get("topic", "") for c in cals[:2]]
                cal_lines.append(f"- {dim_name}: {', '.join(topics)}")
        calibration_summary = "\n".join(cal_lines) if cal_lines else "无校准引用"

        # 冲突摘要
        conflicts = result.get("conflicts", [])
        conflicts_summary = "\n".join(f"- {c}" for c in conflicts) if conflicts else "无冲突"

        return {
            "owner": repo["owner"],
            "repo": repo["repo"],
            "overall_score": result["overall_score"],
            "overall_max_score": result["overall_max_score"],
            "overall_percentage": result["overall_percentage"],
            "community_score": community["score"],
            "community_percentage": community["percentage"],
            "community_findings": community["findings"],
            "community_risks": community["risks"],
            "community_reasoning": community["reasoning"],
            "quality_score": quality["score"],
            "quality_percentage": quality["percentage"],
            "quality_findings": quality["findings"],
            "quality_risks": quality["risks"],
            "quality_reasoning": quality["reasoning"],
            "security_score": security["score"],
            "security_percentage": security["percentage"],
            "security_findings": security["findings"],
            "security_risks": security["risks"],
            "security_reasoning": security["reasoning"],
            "evolution_score": evolution["score"],
            "evolution_percentage": evolution["percentage"],
            "evolution_findings": evolution["findings"],
            "evolution_risks": evolution["risks"],
            "evolution_reasoning": evolution["reasoning"],
            "calibration_summary": calibration_summary,
            "conflicts_summary": conflicts_summary,
        }

    @staticmethod
    def _fallback_report(result: dict) -> SynthesisReport:
        """LLM 生成失败时的降级报告"""
        dims = result.get("dimensions", {})
        percentage = result.get("overall_percentage", 0)

        # 简单评级判断
        if percentage >= 90:
            rating = "A+"
        elif percentage >= 80:
            rating = "A"
        elif percentage >= 70:
            rating = "B+"
        elif percentage >= 60:
            rating = "B"
        elif percentage >= 50:
            rating = "C"
        else:
            rating = "D"

        dim_summaries = []
        for name in ["community", "quality", "security", "evolution"]:
            d = dims.get(name, {})
            dim_summaries.append(DimensionSummary(
                name=name,
                score=d.get("score", 0),
                max_score=d.get("max_score", 0),
                percentage=d.get("percentage", 0),
                assessment="基于规则评分生成的降级总结",
            ))

        all_risks = []
        for name in ["community", "quality", "security", "evolution"]:
            d = dims.get(name, {})
            for risk in d.get("risks", []):
                all_risks.append(RiskItem(
                    level="medium",
                    category=name,
                    description=risk,
                    source="规则评分",
                ))

        return SynthesisReport(
            executive_summary=(
                f"{result['repo']['owner']}/{result['repo']['repo']} "
                f"综合评分 {result.get('overall_score', 0)}/100（{percentage}%），评级 {rating}。"
                f"[LLM 综合报告生成失败，此为降级版本]"
            ),
            overall_rating=rating,
            overall_score=result.get("overall_score", 0),
            dimension_summaries=dim_summaries,
            risk_matrix=all_risks[:5],
            top_recommendations=["建议重新运行分析以获取完整的 LLM 综合报告"],
            data_source_summary="基于规则评分的降级报告，LLM 综合推理不可用",
        )
