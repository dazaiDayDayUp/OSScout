"""代码质量评分引擎（0-25 分）：测试覆盖 / 静态分析 / 文档 / 复杂度"""

from pydantic import BaseModel


class ScoreItem(BaseModel):
    """单项评分结果"""

    score: int
    max_score: int
    raw_value: str
    description: str


class QualityScoreResult(BaseModel):
    """代码质量评分总结果"""

    total_score: int
    max_score: int = 25
    test_coverage: ScoreItem
    static_analysis: ScoreItem
    documentation: ScoreItem
    code_complexity: ScoreItem
    findings: list[str]
    risks: list[str]


def score_code_quality(raw_data: dict) -> QualityScoreResult:
    """
    计算代码质量评分

    Args:
        raw_data: 包含以下键的字典
            - radon: code-analysis-mcp run_radon 的返回结果
            - security: code-analysis-mcp run_security_scan 的返回结果
            - docs: filesystem-mcp 检查的文档存在性结果
            - tests: 测试相关检查结果

    Returns:
        QualityScoreResult：结构化的代码质量评分结果
    """
    findings: list[str] = []
    risks: list[str] = []

    # === 1. 代码复杂度（5 分）===
    radon = raw_data.get("radon", {})
    avg_complexity = radon.get("average_complexity", 0)
    total_blocks = radon.get("total_blocks", 0)

    if avg_complexity < 10:
        complexity_score = 5
        complexity_desc = f"平均圈复杂度 {avg_complexity}（<10，代码简洁易维护）"
    elif avg_complexity <= 15:
        complexity_score = 3
        complexity_desc = f"平均圈复杂度 {avg_complexity}（10-15，部分代码较复杂）"
        findings.append(f"代码复杂度中等，平均圈复杂度为 {avg_complexity}")
    else:
        complexity_score = 0
        complexity_desc = f"平均圈复杂度 {avg_complexity}（>15，代码难以维护）"
        risks.append(f"代码复杂度过高（{avg_complexity}），建议重构")

    if total_blocks == 0:
        complexity_score = 0
        complexity_desc = "无法分析代码复杂度（无 Python 文件或解析失败）"

    # === 2. 静态分析漏洞（7 分）===
    security = raw_data.get("security", {})
    sec_findings = security.get("findings", [])
    high_count = security.get("severity_counts", {}).get("HIGH", 0)
    medium_count = security.get("severity_counts", {}).get("MEDIUM", 0)

    if high_count == 0 and medium_count == 0:
        sec_score = 7
        sec_desc = "未发现高危或中危安全漏洞"
    elif high_count == 0:
        sec_score = max(7 - medium_count * 2, 0)
        sec_desc = f"发现 {medium_count} 个中危漏洞"
        findings.append(f"发现 {medium_count} 个中危安全漏洞")
    else:
        sec_score = 0
        sec_desc = f"发现 {high_count} 个高危漏洞，需立即修复"
        risks.append(f"发现 {high_count} 个高危安全漏洞")

    # === 3. 文档完整度（5 分）===
    docs = raw_data.get("docs", {})
    doc_items = {
        "README": docs.get("has_readme", False),
        "CHANGELOG": docs.get("has_changelog", False),
        "CONTRIBUTING": docs.get("has_contributing", False),
        "API 文档": docs.get("has_api_docs", False),
    }
    doc_count = sum(1 for v in doc_items.values() if v)

    if doc_count >= 4:
        doc_score = 5
        doc_desc = "文档齐全（README + CHANGELOG + CONTRIBUTING + API 文档）"
    elif doc_count >= 2:
        doc_score = 3
        doc_desc = f"文档基本完整（{doc_count}/4 项）"
        missing = [k for k, v in doc_items.items() if not v]
        findings.append(f"缺少文档: {', '.join(missing)}")
    elif doc_count >= 1:
        doc_score = 1
        doc_desc = f"文档不完整（仅 {doc_count}/4 项）"
        missing = [k for k, v in doc_items.items() if not v]
        findings.append(f"缺少文档: {', '.join(missing)}")
    else:
        doc_score = 0
        doc_desc = "缺少所有关键文档"
        risks.append("项目无任何文档，上手成本极高")

    # === 4. 测试覆盖率（8 分）——尽力检测 ===
    tests = raw_data.get("tests", {})
    has_tests_dir = tests.get("has_tests_dir", False)
    has_ci = tests.get("has_ci", False)

    if has_tests_dir and has_ci:
        test_score = 6
        test_desc = "有测试目录和 CI 配置（假设覆盖率达标）"
    elif has_tests_dir:
        test_score = 4
        test_desc = "有测试目录但无 CI 自动化"
        findings.append("有测试但无 CI 自动化，覆盖率可能不稳定")
    else:
        test_score = 0
        test_desc = "未检测到测试目录"
        risks.append("缺少自动化测试，代码质量无法保证")

    # 如果覆盖率具体数值可用，优先使用
    coverage_pct = tests.get("coverage_percentage")
    if coverage_pct is not None:
        if coverage_pct >= 80:
            test_score = 8
            test_desc = f"测试覆盖率 {coverage_pct}%（优秀）"
        elif coverage_pct >= 60:
            test_score = 5
            test_desc = f"测试覆盖率 {coverage_pct}%（良好）"
        elif coverage_pct >= 40:
            test_score = 2
            test_desc = f"测试覆盖率 {coverage_pct}%（不足）"
            findings.append(f"测试覆盖率仅 {coverage_pct}%，建议补充")
        else:
            test_score = 0
            test_desc = f"测试覆盖率 {coverage_pct}%（严重不足）"
            risks.append(f"测试覆盖率仅 {coverage_pct}%，代码可靠性存疑")

    total = test_score + sec_score + doc_score + complexity_score

    return QualityScoreResult(
        total_score=total,
        max_score=25,
        test_coverage=ScoreItem(
            score=test_score, max_score=8,
            raw_value=f"has_tests={has_tests_dir}, has_ci={has_ci}, coverage={coverage_pct}",
            description=test_desc,
        ),
        static_analysis=ScoreItem(
            score=sec_score, max_score=7,
            raw_value=f"high={high_count}, medium={medium_count}",
            description=sec_desc,
        ),
        documentation=ScoreItem(
            score=doc_score, max_score=5,
            raw_value=f"{doc_count}/4 项",
            description=doc_desc,
        ),
        code_complexity=ScoreItem(
            score=complexity_score, max_score=5,
            raw_value=f"avg={avg_complexity}, blocks={total_blocks}",
            description=complexity_desc,
        ),
        findings=findings,
        risks=risks,
    )
