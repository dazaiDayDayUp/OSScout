"""文本报告格式化器：将结构化结果转换为 Markdown 风格文本报告"""

from app.agents.orchestrator import OrchestratorResult


class Reporter:
    """
    尽调报告格式化器

    当前版本输出 Markdown 风格的纯文本，后续可扩展为 HTML、JSON 等格式。
    """

    def format_text(self, result: OrchestratorResult) -> str:
        """
        将 OrchestratorResult 格式化为文本报告

        Args:
            result: Orchestrator 分析结果

        Returns:
            Markdown 风格的文本报告字符串
        """
        lines = []
        repo = result.repo

        # 标题
        lines.append("=" * 60)
        lines.append(f"OSScout 开源项目尽调报告")
        lines.append("=" * 60)
        lines.append("")

        # 项目信息
        lines.append(f"项目: {repo['owner']}/{repo['repo']}")
        lines.append(f"地址: {repo['url']}")
        lines.append("")

        # 综合评分
        lines.append("-" * 60)
        lines.append("综合评分")
        lines.append("-" * 60)
        rating, rating_desc = self._get_rating(result.overall_percentage)
        lines.append(f"评级: {rating}  ({rating_desc})")
        lines.append(self._render_score_bar(
            result.overall_score,
            result.overall_max_score,
            result.overall_percentage,
        ))
        lines.append("")

        # 各维度评分
        lines.append("-" * 60)
        lines.append("各维度评分")
        lines.append("-" * 60)
        lines.append("")

        # 社区健康度
        community = result.dimensions.get("community", {})
        if community:
            lines.append(self._render_dimension(community))
            lines.append("")

        # 代码质量
        quality = result.dimensions.get("quality", {})
        if quality:
            lines.append(self._render_dimension(quality))
            lines.append("")

        # 安全分析
        security = result.dimensions.get("security", {})
        if security:
            lines.append(self._render_dimension(security))
            lines.append("")

        # 技术演进
        evolution = result.dimensions.get("evolution", {})
        if evolution:
            lines.append(self._render_dimension(evolution))
            lines.append("")

        # 关键发现
        if result.findings:
            lines.append("-" * 60)
            lines.append("关键发现")
            lines.append("-" * 60)
            for finding in result.findings:
                lines.append(f"  + {finding}")
            lines.append("")

        # 风险提示
        if result.risks:
            lines.append("-" * 60)
            lines.append("风险提示")
            lines.append("-" * 60)
            for risk in result.risks:
                lines.append(f"  ! {risk}")
            lines.append("")

        # 页脚
        lines.append("-" * 60)
        lines.append("报告生成时间: 见调用时间戳")
        lines.append("=" * 60)

        return "\n".join(lines)

    def _get_rating(self, percentage: float) -> tuple[str, str]:
        """
        根据总分百分比计算综合评级

        评级标准（PROJECT_PLAN §7.2）：
        - A+ (90-100): 强烈推荐，项目非常健康
        - A  (80-89):  推荐，可以安全使用
        - B+ (70-79):  谨慎推荐，存在可接受的小风险
        - B  (60-69):  可用，但需要关注特定风险点
        - C  (50-59):  谨慎使用，存在明显风险
        - D  (<50):    不建议使用
        """
        if percentage >= 90:
            return "A+", "强烈推荐，项目非常健康"
        elif percentage >= 80:
            return "A", "推荐，可以安全使用"
        elif percentage >= 70:
            return "B+", "谨慎推荐，存在可接受的小风险"
        elif percentage >= 60:
            return "B", "可用，但需要关注特定风险点"
        elif percentage >= 50:
            return "C", "谨慎使用，存在明显风险"
        else:
            return "D", "不建议使用"

    def _render_score_bar(self, score: int, max_score: int, percentage: float) -> str:
        """
        渲染评分进度条

        例如：总分 18/30 [██████████░░░░░░░░░░] 60.0%
        """
        bar_width = 20
        filled = int(bar_width * percentage / 100)
        empty = bar_width - filled
        bar = "#" * filled + "-" * empty
        return f"总分 {score}/{max_score} [{bar}] {percentage}%"

    def _render_dimension(self, dim: dict) -> str:
        """
        渲染单个维度的详细评分

        Args:
            dim: 维度数据字典，来自 CommunityAgentResult.model_dump()
        """
        lines = []
        lines.append(f"【{dim.get('dimension', 'unknown')}】")
        lines.append(f"  得分: {dim['score']}/{dim['max_score']} ({dim['percentage']}%)")
        lines.append("")

        # 各项详细指标
        details = dim.get("details", {})
        for key, item in details.items():
            name_map = {
                "bus_factor": "Bus Factor",
                "issue_response": "Issue 响应速度",
                "pr_merge_rate": "PR 合并率",
                "active_contributors": "活跃贡献者",
                "release_stability": "Release 稳定性",
                "test_coverage": "测试覆盖率",
                "static_analysis": "静态分析漏洞",
                "documentation": "文档完整度",
                "code_complexity": "代码复杂度",
                "cve_record": "CVE 记录",
                "dependency_vulns": "依赖漏洞",
                "license_risk": "许可证风险",
                "response_speed": "安全响应速度",
                "release_frequency": "发布频率",
                "tech_stack_freshness": "技术栈更新",
                "breaking_change": "Breaking Change",
                "competitor_comparison": "竞品对比",
            }
            name = name_map.get(key, key)
            score = item.get("score", 0)
            max_score = item.get("max_score", 0)
            raw = item.get("raw_value", "N/A")
            desc = item.get("description", "")

            lines.append(f"  - {name}: {score}/{max_score} ({raw})")
            lines.append(f"    {desc}")

        return "\n".join(lines)
