"""
Prompt 模板管理

集中管理各 Agent 使用的 Prompt 模板，
支持变量插值，便于统一维护和调优。
"""
from app.core.logger import get_logger

logger = get_logger(__name__)


class PromptTemplate:
    """
    Prompt 模板类

    使用 Python f-string 风格的变量插值，
    通过 render() 方法传入变量字典生成最终 Prompt。
    """

    def __init__(
        self,
        name: str,
        template: str,
        description: str = "",
    ) -> None:
        self.name = name
        self.template = template
        self.description = description

    def render(self, **kwargs: str) -> str:
        """
        渲染模板，将占位符替换为实际值

        Args:
            **kwargs: 模板变量名和值

        Returns:
            渲染后的完整 Prompt 文本
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            logger.error(
                "Prompt 模板渲染失败，缺少变量",
                template=self.name,
                missing_variable=str(e),
            )
            raise ValueError(
                f"模板 '{self.name}' 渲染失败，缺少变量: {e}"
            ) from e


# =============================================================================
# 预定义 Prompt 模板（Phase 3.3 起各 Agent 会使用）
# =============================================================================

COMMUNITY_ANALYSIS_PROMPT = PromptTemplate(
    name="community_analysis",
    description="社区健康度 Agent 的分析 Prompt",
    template="""你是一位开源社区分析专家。请根据以下 GitHub 仓库数据，评估该项目的社区健康度。

## 仓库数据

- 仓库：{owner}/{repo}
- Stars：{star_count}
- Forks：{fork_count}
- Open Issues：{open_issue_count}
- Contributors（最近 90 天）：{active_contributors}
- Bus Factor（贡献度 >50% 的最小贡献者数）：{bus_factor}
- Issue 首次响应中位数（天）：{issue_response_median}
- PR 合并率：{pr_merge_rate}%
- 最近 12 个月 Release 数：{release_count}
- 最近 90 天 Commits 数：{recent_commits}

## 分析要求

1. 综合评估社区健康度，给出 0-30 分的评分
2. 列出 2-4 条关键发现（优势和风险）
3. 判断是否存在"即将放弃维护"的早期信号
4. 给出明确的推荐建议

请返回结构化的分析结果。""",
)

QUALITY_ANALYSIS_PROMPT = PromptTemplate(
    name="quality_analysis",
    description="代码质量 Agent 的分析 Prompt",
    template="""你是一位代码质量评估专家。请根据以下静态分析数据，评估该项目的代码质量。

## 分析数据

- 仓库：{owner}/{repo}
- 平均圈复杂度：{avg_complexity}
- 高危静态分析发现：{high_severity_count}
- 中危静态分析发现：{medium_severity_count}
- 测试覆盖率：{test_coverage}%
- 文档文件数（README/CHANGELOG/CONTRIBUTING）：{doc_files_count}

## 分析要求

1. 综合评估代码质量，给出 0-25 分的评分
2. 列出 2-4 条关键发现
3. 识别代码中可能存在的架构或维护风险
4. 给出改进建议

请返回结构化的分析结果。""",
)

SECURITY_ANALYSIS_PROMPT = PromptTemplate(
    name="security_analysis",
    description="安全分析 Agent 的分析 Prompt",
    template="""你是一位开源安全分析专家。请根据以下安全扫描数据，评估该项目的安全风险。

## 安全数据

- 仓库：{owner}/{repo}
- 已知 CVE 数量（近 1 年）：{cve_count}
- 高危 CVE：{high_cve_count}
- 中危 CVE：{medium_cve_count}
- 依赖漏洞数量：{dependency_vuln_count}
- 许可证：{license}

## 分析要求

1. 综合评估安全状况，给出 0-25 分的评分
2. 列出具体的安全风险和漏洞清单
3. 评估许可证风险（尤其是 GPL/AGPL 的传染性风险）
4. 给出安全使用建议

请返回结构化的分析结果。""",
)

EVOLUTION_ANALYSIS_PROMPT = PromptTemplate(
    name="evolution_analysis",
    description="技术演进 Agent 的分析 Prompt",
    template="""你是一位技术演进趋势分析专家。请根据以下数据，评估该项目的技术演进状况。

## 演进数据

- 仓库：{owner}/{repo}
- 最近 12 个月 Release 数：{release_count}
- 平均发布频率（次/月）：{release_frequency}
- Breaking Change 密度：{breaking_change_density}
- 核心依赖最新版本差距：{dependency_gap}

## 分析要求

1. 综合评估技术演进状况，给出 0-20 分的评分
2. 判断项目的技术栈是否老化
3. 评估版本发布策略是否合理
4. 给出技术选型建议

请返回结构化的分析结果。""",
)

SYNTHESIS_PROMPT = PromptTemplate(
    name="synthesis",
    description="综合报告 Agent 的汇总 Prompt",
    template="""你是一位资深技术顾问。请根据以下四个维度的分析结果，生成一份最终的开源项目尽调报告。

## 各维度分析结果

### 社区健康度
- 评分：{community_score}/30
- 发现：{community_findings}

### 代码质量
- 评分：{quality_score}/25
- 发现：{quality_findings}

### 安全评分
- 评分：{security_score}/25
- 发现：{security_findings}

### 技术演进
- 评分：{evolution_score}/20
- 发现：{evolution_findings}

## 综合评估要求

1. 计算总分，给出综合评级（A+/A/B+/B/C/D）
2. 总结项目的核心优势和主要风险
3. 给出明确的推荐结论（强烈推荐/推荐/谨慎推荐/谨慎使用/不建议）
4. 列出 3-5 条具体、可操作的建议

请返回结构化的综合报告。""",
)
