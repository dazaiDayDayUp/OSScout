"""
技术演进评分引擎

根据 PROJECT_PLAN §7.3 的四项指标计算 0-20 分技术演进评分：
- 发布频率（6 分）
- 技术栈更新（6 分）
- Breaking Change（4 分）
- 竞品对比（4 分，Phase 1 跳过）

使用方式：
    from app.scoring.evolution import score_evolution
    result = score_evolution(raw_data)
    print(result.total_score, result.findings)
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreItem:
    """单项指标的评分结果"""

    score: int
    max_score: int
    raw_value: str
    description: str


@dataclass
class EvolutionScoreResult:
    """技术演进评分的完整结果"""

    total_score: int
    max_score: int = 20
    release_frequency: ScoreItem | None = None
    tech_stack_freshness: ScoreItem | None = None
    breaking_change: ScoreItem | None = None
    competitor_comparison: ScoreItem | None = None
    findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 版本号解析（与 evolution_service 中保持一致）
# ═══════════════════════════════════════════════════════════════


def _parse_major(version_str: str | None) -> int:
    """从版本号字符串提取 major 版本号"""
    if not version_str:
        return 0
    s = version_str.strip().lstrip("vV")
    parts = s.split(".")
    if parts and parts[0].isdigit():
        return int(parts[0])
    return 0


# ═══════════════════════════════════════════════════════════════
# 三项独立评分函数
# ═══════════════════════════════════════════════════════════════


def score_release_frequency(release_count_12m: int) -> ScoreItem:
    """
    发布频率评分（6 分）

    评分标准：
    - ≥1 次/月（12 个月内 ≥12 次）：6 分
    - 每 2 月 1 次（≥6 次）：4 分
    - 每季度 1 次（≥4 次）：2 分
    - 否则：0 分
    """
    if release_count_12m >= 12:
        return ScoreItem(
            score=6,
            max_score=6,
            raw_value=f"{release_count_12m} 次/年（≥1 次/月）",
            description="发布频率高，持续迭代活跃",
        )
    elif release_count_12m >= 6:
        return ScoreItem(
            score=4,
            max_score=6,
            raw_value=f"{release_count_12m} 次/年（约每 2 月 1 次）",
            description="发布频率正常，保持常规迭代节奏",
        )
    elif release_count_12m >= 4:
        return ScoreItem(
            score=2,
            max_score=6,
            raw_value=f"{release_count_12m} 次/年（约每季度 1 次）",
            description="发布频率偏低，迭代节奏较慢",
        )
    else:
        return ScoreItem(
            score=0,
            max_score=6,
            raw_value=f"{release_count_12m} 次/年",
            description="发布频率过低，可能维护不力或已趋于稳定",
        )


def score_tech_stack_freshness(dependency_versions: list[dict]) -> ScoreItem:
    """
    技术栈更新评分（6 分）

    评分标准：
    - 核心依赖均最新大版本：6 分
    - 落后 1 个大版本：4 分
    - 落后 ≥2 个大版本：0 分
    - 无版本数据：3 分（无法评估）
    """
    if not dependency_versions:
        return ScoreItem(
            score=3,
            max_score=6,
            raw_value="N/A",
            description="无法获取依赖版本信息，无法评估技术栈更新状态",
        )

    # 筛选有 current 和 latest 的数据点
    valid_deps: list[dict] = []
    for dep in dependency_versions:
        current = dep.get("current")
        latest = dep.get("latest")
        if current and latest:
            valid_deps.append(dep)

    if not valid_deps:
        return ScoreItem(
            score=3,
            max_score=6,
            raw_value="N/A",
            description="依赖版本数据不完整，无法评估",
        )

    # 计算每个依赖的 major 版本差距
    gaps: list[tuple[str, int]] = []
    has_major_gap_1 = False
    has_major_gap_2_plus = False

    for dep in valid_deps:
        name = dep["name"]
        current_major = _parse_major(dep.get("current"))
        latest_major = _parse_major(dep.get("latest"))
        gap = abs(latest_major - current_major)
        gaps.append((name, gap))

        if gap >= 2:
            has_major_gap_2_plus = True
        elif gap == 1:
            has_major_gap_1 = True

    # 生成详细描述
    gap_parts = [f"{name}: 落后 {gap} 个大版本" for name, gap in gaps if gap > 0]
    if not gap_parts:
        gap_desc = "所有依赖均为最新版本"
    else:
        gap_desc = "; ".join(gap_parts[:5])  # 最多显示 5 个
        if len(gap_parts) > 5:
            gap_desc += f" 等共 {len(gap_parts)} 个依赖需更新"

    # 评分
    if has_major_gap_2_plus:
        return ScoreItem(
            score=0,
            max_score=6,
            raw_value=gap_desc,
            description="部分核心依赖严重落后（≥2 个大版本），存在技术债务风险",
        )
    elif has_major_gap_1:
        return ScoreItem(
            score=4,
            max_score=6,
            raw_value=gap_desc,
            description="部分依赖落后 1 个大版本，建议规划升级",
        )
    else:
        return ScoreItem(
            score=6,
            max_score=6,
            raw_value="所有依赖均为最新",
            description="技术栈保持最新，无版本落后风险",
        )


def score_breaking_change(breaking_data: dict) -> ScoreItem:
    """
    Breaking Change 评分（4 分）

    从两个维度评估：
    1. major version bump 频率（通过 tag_name 版本号推断）
    2. release notes 中是否说明 Breaking Change

    评分标准：
    - 无 major bump 或每个 major bump 都有文档说明：4 分
    - 存在 major bump 但文档不完整：2 分
    - 存在 major bump 但完全无文档说明：0 分
    - 样本不足（releases < 3）：2 分
    """
    total_releases = breaking_data.get("total_releases", 0)
    breaking_notes = breaking_data.get("releases_with_breaking_notes", 0)
    major_bump = breaking_data.get("major_bump_count", 0)

    if total_releases == 0:
        return ScoreItem(
            score=2,
            max_score=4,
            raw_value="无 release 数据",
            description="未获取到发布历史，无法评估 Breaking Change 情况",
        )

    if total_releases < 3:
        return ScoreItem(
            score=2,
            max_score=4,
            raw_value=f"仅 {total_releases} 个 release",
            description="发布样本不足，无法准确评估 Breaking Change 策略",
        )

    # 没有 major version bump
    if major_bump == 0:
        return ScoreItem(
            score=4,
            max_score=4,
            raw_value=f"{total_releases} 个 release，无 major bump",
            description="版本策略保守，API 兼容性好",
        )

    # 有 major bump，且都有文档说明
    if breaking_notes >= major_bump:
        return ScoreItem(
            score=4,
            max_score=4,
            raw_value=f"{major_bump} 次 major bump，均伴有说明文档",
            description="Breaking Change 策略规范，有文档说明和迁移指引",
        )

    # 有 major bump，部分有文档
    if breaking_notes > 0:
        return ScoreItem(
            score=2,
            max_score=4,
            raw_value=f"{major_bump} 次 major bump，仅 {breaking_notes} 次有文档说明",
            description="Breaking Change 文档不完整，升级时可能缺少迁移指引",
        )

    # 有 major bump，但完全没有文档
    return ScoreItem(
        score=0,
        max_score=4,
        raw_value=f"{major_bump} 次 major bump，无说明文档",
        description="存在未文档化的 Breaking Change，升级风险高",
    )


def score_competitor_comparison() -> ScoreItem:
    """
    竞品对比评分（4 分）

    Phase 1 跳过，固定返回 0 分。
    待 Phase 2/3 接入竞品搜索和对比功能。
    """
    return ScoreItem(
        score=0,
        max_score=4,
        raw_value="Phase 1 未实现",
        description="竞品对比功能将在后续阶段接入",
    )


# ═══════════════════════════════════════════════════════════════
# 总入口
# ═══════════════════════════════════════════════════════════════


def score_evolution(raw_data: dict[str, Any]) -> EvolutionScoreResult:
    """
    技术演进评分总入口

    Args:
        raw_data: evolution_service.collect_evolution_data() 返回的数据字典

    Returns:
        EvolutionScoreResult：包含各项评分、总得分、关键发现和风险标记
    """
    release_count = raw_data.get("release_count_12m", 0)
    dep_versions = raw_data.get("dependency_versions", [])
    breaking = raw_data.get("breaking_change", {})

    # 分别计算四项指标
    freq = score_release_frequency(release_count)
    tech = score_tech_stack_freshness(dep_versions)
    breaking_score = score_breaking_change(breaking)
    comp = score_competitor_comparison()

    total = freq.score + tech.score + breaking_score.score + comp.score

    # 生成关键发现和风险标记
    findings: list[str] = []
    risks: list[str] = []

    # 发布频率相关
    if freq.score >= 4:
        findings.append(f"发布频率良好（{freq.raw_value}）")
    elif freq.score >= 2:
        findings.append(f"发布频率一般（{freq.raw_value}）")
    else:
        risks.append(f"发布频率过低（{freq.raw_value}），可能已停止活跃维护")

    # 技术栈更新相关
    if tech.score == 6:
        findings.append("技术栈保持最新，无版本落后")
    elif tech.score == 4:
        findings.append(f"技术栈部分落后（{tech.raw_value}），建议规划升级")
    elif tech.score == 0:
        risks.append(f"技术栈严重落后（{tech.raw_value}），存在较大技术债务")
    else:
        findings.append("无法评估技术栈更新状态")

    # Breaking Change 相关
    if breaking_score.score == 4:
        findings.append("Breaking Change 策略规范，有文档说明")
    elif breaking_score.score == 2:
        findings.append(f"Breaking Change 文档不完整（{breaking_score.raw_value}）")
    elif breaking_score.score == 0:
        risks.append(f"存在未文档化的 Breaking Change（{breaking_score.raw_value}）")

    # 竞品对比
    findings.append("竞品对比功能待 Phase 2 接入")

    return EvolutionScoreResult(
        total_score=total,
        max_score=20,
        release_frequency=freq,
        tech_stack_freshness=tech,
        breaking_change=breaking_score,
        competitor_comparison=comp,
        findings=findings,
        risks=risks,
    )
