"""LLM 推理增强模块

为各分析 Agent 提供统一的 LLM 推理增强能力。

设计原则：
1. 规则评分打底，LLM 只做补充分析，不覆盖规则评分
2. LLM 增强是"可选"的——API 调用失败时不影响规则评分结果
3. 所有 Agent 输出统一增加 reasoning 字段，解释评分的深层原因
4. LLM 擅长发现规则无法捕捉的模式（如"PR 合并率 60% 但核心维护者减少"）
"""

from pydantic import BaseModel, Field

from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.llm.schemas import LLMMessage
from app.llm.templates import PromptTemplate

from app.core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# LLM 增强输出 Schema（所有 Agent 共用）
# =============================================================================

class LLMEnhancementOutput(BaseModel):
    """LLM 推理增强的统一输出格式

    各 Agent 调用 LLM 时要求模型按此 Schema 返回结果，
    通过 chat_structured() 自动解析和校验。
    """

    reasoning: str = Field(
        ...,
        description="对规则评分的综合推理过程，解释为什么是这个分数，"
                    "以及指标之间是否存在矛盾或值得关注的关联。"
                    "例如：'虽然 PR 合并率为 65%（及格），但最近 3 个月核心维护者"
                    "从 5 人减少到 2 人，这是社区衰退的强烈信号。'",
    )

    additional_findings: list[str] = Field(
        default_factory=list,
        description="规则评分未能捕捉的额外发现，"
                    "基于数据模式和行业经验的推断。",
    )

    additional_risks: list[str] = Field(
        default_factory=list,
        description="规则评分未能识别的额外风险，"
                    "通常是跨指标关联分析才能发现的深层问题。"
                    "注意：必须是字符串列表，不要返回单个字符串。",
    )

    overall_assessment: str = Field(
        ...,
        description="一句话总结性评估，不超过 100 字。",
    )


# =============================================================================
# 通用增强器
# =============================================================================

class LLMEnhancer:
    """LLM 推理增强器

    封装 LLM 调用的通用逻辑：
    - 构造包含规则评分 + 原始数据的 Prompt
    - 调用 LLM 获取推理增强
    - 失败时安全降级（返回空增强结果，不影响规则评分）
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        """
        Args:
            provider: LLM Provider 实例，None 时自动从配置创建
        """
        self.provider = provider or get_llm_provider()

    async def enhance(
        self,
        dimension: str,
        prompt_template: PromptTemplate,
        template_vars: dict,
        max_tokens: int = 3000,
    ) -> LLMEnhancementOutput:
        """执行 LLM 推理增强

        Args:
            dimension: 维度名称（community/quality/security/evolution），用于日志
            prompt_template: PromptTemplate 实例
            template_vars: 模板变量字典
            max_tokens: 最大输出 token 数

        Returns:
            LLMEnhancementOutput：推理增强结果。
            如果 LLM 调用失败，返回一个包含错误提示的安全降级结果。
        """
        # 1. 渲染 Prompt
        try:
            prompt_text = prompt_template.render(**template_vars)
        except Exception as e:
            logger.error(
                "Prompt 渲染失败",
                dimension=dimension,
                error=str(e),
            )
            return self._fallback_output(f"Prompt 渲染失败: {e}")

        # 2. 构造消息
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "你是一位资深开源项目评估专家。"
                    "请根据提供的数据进行深度分析，返回结构化的推理结果。"
                    "你的分析应超越简单的数值判断，关注指标之间的关联和深层趋势。"
                    "注意：请保持简洁，reasoning 不超过 300 字，"
                    "additional_findings 和 additional_risks 每条不超过 100 字。"
                ),
            ),
            LLMMessage(role="user", content=prompt_text),
        ]

        # 3. 调用 LLM（结构化输出）
        try:
            result = await self.provider.chat_structured(
                messages=messages,
                output_schema=LLMEnhancementOutput,
                temperature=0.5,  # 适度创造性，同时保持一致性
                max_tokens=max_tokens,
            )
            logger.info(
                "LLM 推理增强完成",
                dimension=dimension,
                reasoning_preview=result.reasoning[:60],
                additional_findings=len(result.additional_findings),
                additional_risks=len(result.additional_risks),
            )
            return result

        except Exception as e:
            logger.warning(
                "LLM 推理增强失败，使用降级结果",
                dimension=dimension,
                error=str(e),
            )
            return self._fallback_output(f"LLM 调用失败: {e}")

    @staticmethod
    def _fallback_output(error_msg: str) -> LLMEnhancementOutput:
        """生成降级结果，确保即使 LLM 失败也不影响主流程"""
        return LLMEnhancementOutput(
            reasoning=f"[LLM 推理不可用] {error_msg}",
            additional_findings=[],
            additional_risks=[],
            overall_assessment="基于规则评分完成分析。",
        )


# =============================================================================
# 各维度的 Prompt 模板（Phase 3.3 使用）
# =============================================================================

COMMUNITY_ENHANCE_PROMPT = PromptTemplate(
    name="community_enhance",
    description="社区健康度 LLM 推理增强 Prompt",
    template="""## 社区健康度规则评分结果

仓库：{owner}/{repo}

### 各子项评分
| 指标 | 得分 | 满分 | 原始值 | 说明 |
|------|------|------|--------|------|
| Bus Factor | {bus_factor_score} | {bus_factor_max} | {bus_factor_raw} | {bus_factor_desc} |
| Issue 响应 | {issue_response_score} | {issue_response_max} | {issue_response_raw} | {issue_response_desc} |
| PR 合并率 | {pr_merge_rate_score} | {pr_merge_rate_max} | {pr_merge_rate_raw} | {pr_merge_rate_desc} |
| 活跃贡献者 | {active_contributors_score} | {active_contributors_max} | {active_contributors_raw} | {active_contributors_desc} |
| Release 稳定性 | {release_stability_score} | {release_stability_max} | {release_stability_raw} | {release_stability_desc} |

### 规则评分结论
- 总分：{total_score}/{max_score}（{percentage}%）
- 发现：{findings}
- 风险：{risks}

## 补充上下文

- Stars: {star_count}
- Forks: {fork_count}
- Open Issues: {open_issue_count}
- 最近 90 天 Commits: {recent_commits}

## 分析任务

请作为社区治理专家，基于以上数据进行深度分析：
1. 解释规则评分的合理性——为什么这个分数是准确的（或不准确的）
2. 关注指标之间的矛盾和关联（例如"PR 合并率高但贡献者减少"）
3. 识别"即将放弃维护"的早期信号
4. 给出基于行业经验的判断

请返回结构化的分析结果。""",
)

QUALITY_ENHANCE_PROMPT = PromptTemplate(
    name="quality_enhance",
    description="代码质量 LLM 推理增强 Prompt",
    template="""## 代码质量规则评分结果

仓库：{owner}/{repo}

### 各子项评分
| 指标 | 得分 | 满分 | 原始值 | 说明 |
|------|------|------|--------|------|
| 测试覆盖 | {test_coverage_score} | {test_coverage_max} | {test_coverage_raw} | {test_coverage_desc} |
| 静态分析 | {static_analysis_score} | {static_analysis_max} | {static_analysis_raw} | {static_analysis_desc} |
| 文档完整度 | {documentation_score} | {documentation_max} | {documentation_raw} | {documentation_desc} |
| 代码复杂度 | {code_complexity_score} | {code_complexity_max} | {code_complexity_raw} | {code_complexity_desc} |

### 规则评分结论
- 总分：{total_score}/{max_score}（{percentage}%）
- 发现：{findings}
- 风险：{risks}

## 分析任务

请作为代码质量专家，基于以上数据进行深度分析：
1. 解释规则评分的合理性
2. 识别代码中可能存在的架构或维护风险（规则难以量化的问题）
3. 评估文档质量和开发者体验
4. 给出改进建议

请返回结构化的分析结果。""",
)

SECURITY_ENHANCE_PROMPT = PromptTemplate(
    name="security_enhance",
    description="安全分析 LLM 推理增强 Prompt",
    template="""## 安全规则评分结果

仓库：{owner}/{repo}

### 各子项评分
| 指标 | 得分 | 满分 | 原始值 | 说明 |
|------|------|------|--------|------|
| CVE 记录 | {cve_record_score} | {cve_record_max} | {cve_record_raw} | {cve_record_desc} |
| 依赖漏洞 | {dependency_vulns_score} | {dependency_vulns_max} | {dependency_vulns_raw} | {dependency_vulns_desc} |
| 许可证风险 | {license_risk_score} | {license_risk_max} | {license_risk_raw} | {license_risk_desc} |
| 安全响应 | {response_speed_score} | {response_speed_max} | {response_speed_raw} | {response_speed_desc} |

### 规则评分结论
- 总分：{total_score}/{max_score}（{percentage}%）
- 发现：{findings}
- 风险：{risks}

## 补充上下文

- 许可证类型：{license}
- 近 1 年 CVE 详情：{cve_details}

## 分析任务

请作为开源安全专家，基于以上数据进行深度分析：
1. 解释安全评分的合理性
2. 评估漏洞影响面和修复优先级（规则无法判断的上下文问题）
3. 分析许可证风险（尤其是传染性许可证对商业使用的限制）
4. 评估供应链安全风险

请返回结构化的分析结果。""",
)

EVOLUTION_ENHANCE_PROMPT = PromptTemplate(
    name="evolution_enhance",
    description="技术演进 LLM 推理增强 Prompt",
    template="""## 技术演进规则评分结果

仓库：{owner}/{repo}

### 各子项评分
| 指标 | 得分 | 满分 | 原始值 | 说明 |
|------|------|------|--------|------|
| 发布频率 | {release_frequency_score} | {release_frequency_max} | {release_frequency_raw} | {release_frequency_desc} |
| 技术栈更新 | {tech_stack_freshness_score} | {tech_stack_freshness_max} | {tech_stack_freshness_raw} | {tech_stack_freshness_desc} |
| Breaking Change | {breaking_change_score} | {breaking_change_max} | {breaking_change_raw} | {breaking_change_desc} |
| 竞品对比 | {competitor_comparison_score} | {competitor_comparison_max} | {competitor_comparison_raw} | {competitor_comparison_desc} |

### 规则评分结论
- 总分：{total_score}/{max_score}（{percentage}%）
- 发现：{findings}
- 风险：{risks}

## 分析任务

请作为技术演进分析专家，基于以上数据进行深度分析：
1. 解释规则评分的合理性
2. 判断技术栈是否老化，以及老化风险程度
3. 评估版本发布策略的合理性
4. 给出技术选型建议

请返回结构化的分析结果。""",
)
