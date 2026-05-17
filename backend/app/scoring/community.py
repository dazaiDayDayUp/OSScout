"""社区健康度评分引擎（0-30 分）：Bus Factor / Issue 响应 / PR 合并率 / 活跃贡献者 / Release 稳定性"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class ScoreItem:
    """单项指标的评分结果"""

    score: int
    max_score: int
    raw_value: str
    description: str


@dataclass
class CommunityScoreResult:
    """社区健康度的完整评分结果"""

    total_score: int
    max_score: int = 30
    bus_factor: ScoreItem | None = None
    issue_response: ScoreItem | None = None
    pr_merge_rate: ScoreItem | None = None
    active_contributors: ScoreItem | None = None
    release_stability: ScoreItem | None = None
    findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 五项指标的独立评分函数
# ═══════════════════════════════════════════════════════════════


def score_bus_factor(contributors: list[dict]) -> ScoreItem:
    """
    Bus Factor：覆盖 50% 总贡献的最小贡献者数

    计算方法：按 contributions 降序排列，累计到 ≥50% 时的人数。
    例如 3 个人贡献了 80%，则 Bus Factor = 3。
    """
    if not contributors:
        return ScoreItem(
            score=0,
            max_score=10,
            raw_value="0",
            description="无贡献者数据",
        )

    # 提取有效贡献数，按降序排列
    contribs = sorted(
        [c.get("contributions", 0) for c in contributors],
        reverse=True,
    )
    total = sum(contribs)

    if total == 0:
        return ScoreItem(
            score=0,
            max_score=10,
            raw_value="0",
            description="总贡献数为 0",
        )

    # 累计到 ≥50% 需要多少人
    cumulative = 0
    bus_factor = 0
    for c in contribs:
        cumulative += c
        bus_factor += 1
        if cumulative / total >= 0.5:
            break

    # 评分：≥5 得 10；3-4 得 6；<3 得 0
    if bus_factor >= 5:
        score = 10
    elif bus_factor >= 3:
        score = 6
    else:
        score = 0

    return ScoreItem(
        score=score,
        max_score=10,
        raw_value=str(bus_factor),
        description=f"Bus Factor = {bus_factor}（覆盖 50% 贡献的最小人数）",
    )


def score_issue_response(issues: list[dict]) -> ScoreItem:
    """
    Issue 响应速度：Issue 从创建到关闭的中位处理时间

    Phase 1.1 简化方案：用已关闭 Issue 的 (closed_at - created_at) 中位数
    作为响应速度的代理指标。后续接入 LLM 后可获取评论时间做更精确计算。
    """
    # 筛选已关闭且有关闭时间的 issue
    closed_issues = [
        issue for issue in issues
        if issue.get("state") == "closed" and issue.get("closed_at")
    ]

    if len(closed_issues) < 3:
        return ScoreItem(
            score=0,
            max_score=8,
            raw_value="N/A",
            description=f"已关闭 Issue 数量过少（{len(closed_issues)} 个），无法计算中位数",
        )

    # 计算每个 issue 的处理时长（天）
    durations = []
    for issue in closed_issues:
        created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
        closed = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
        durations.append((closed - created).total_seconds() / 86400)

    # 中位数
    durations.sort()
    n = len(durations)
    median = durations[n // 2] if n % 2 == 1 else (durations[n // 2 - 1] + durations[n // 2]) / 2

    # 评分：<1 天 8 分；<3 天 6 分；<7 天 3 分；≥7 天 0 分
    if median < 1:
        score = 8
    elif median < 3:
        score = 6
    elif median < 7:
        score = 3
    else:
        score = 0

    return ScoreItem(
        score=score,
        max_score=8,
        raw_value=f"{median:.1f} 天",
        description=f"Issue 中位处理时间 = {median:.1f} 天（基于 {len(closed_issues)} 个已关闭 Issue）",
    )


def score_pr_merge_rate(pull_requests: list[dict]) -> ScoreItem:
    """
    PR 合并率：已合并 PR 数 / PR 总数

    GitHub PR 对象的 merged_at 字段非空即表示已合并。
    """
    if not pull_requests:
        return ScoreItem(
            score=0,
            max_score=6,
            raw_value="N/A",
            description="无 Pull Request 数据",
        )

    total = len(pull_requests)
    merged = sum(1 for pr in pull_requests if pr.get("merged_at"))
    rate = merged / total if total > 0 else 0
    rate_pct = rate * 100

    # 评分：≥70% 得 6；50-69% 得 4；30-49% 得 2；<30% 得 0
    if rate_pct >= 70:
        score = 6
    elif rate_pct >= 50:
        score = 4
    elif rate_pct >= 30:
        score = 2
    else:
        score = 0

    return ScoreItem(
        score=score,
        max_score=6,
        raw_value=f"{rate_pct:.1f}%",
        description=f"PR 合并率 = {merged}/{total} = {rate_pct:.1f}%",
    )


def score_active_contributors(contributors: list[dict]) -> ScoreItem:
    """
    活跃贡献者：GitHub contributors 接口返回的列表长度

    注意：GitHub API 仅返回有推送到默认分支的贡献者，已过滤掉无意义提交。
    """
    count = len(contributors)

    # 评分：≥10 得 4；5-9 得 2；<5 得 0
    if count >= 10:
        score = 4
    elif count >= 5:
        score = 2
    else:
        score = 0

    return ScoreItem(
        score=score,
        max_score=4,
        raw_value=str(count),
        description=f"活跃贡献者 = {count} 人",
    )


def score_release_stability(releases: list[dict]) -> ScoreItem:
    """
    Release 稳定性：最近 6 个月内是否有 release

    简化判断：只看最近一次 release 是否在 6 个月内。
    Phase 1.5 可扩展为检查频率稳定性（标准差）。
    """
    if not releases:
        return ScoreItem(
            score=0,
            max_score=2,
            raw_value="无",
            description="没有任何 Release 记录",
        )

    # 取最近一个 release 的发布时间
    latest = releases[0]
    published_at = latest.get("published_at")
    if not published_at:
        return ScoreItem(
            score=0,
            max_score=2,
            raw_value="未知",
            description="最近的 Release 无发布时间信息",
        )

    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    months_ago = (now - published).days / 30

    # 评分：6 个月内有 release 得 2 分，否则 0 分
    if months_ago <= 6:
        score = 2
        description = f"最近 Release 在 {months_ago:.1f} 个月前（{latest.get('tag_name', 'unknown')}）"
    else:
        score = 0
        description = f"最近 Release 在 {months_ago:.1f} 个月前，超过 6 个月未发布"

    return ScoreItem(
        score=score,
        max_score=2,
        raw_value=f"{months_ago:.1f} 个月前",
        description=description,
    )


# ═══════════════════════════════════════════════════════════════
# 总入口
# ═══════════════════════════════════════════════════════════════


def score_community_health(raw_data: dict[str, Any]) -> CommunityScoreResult:
    """
    社区健康度总评分入口

    Args:
        raw_data: github_service.collect_all_metadata() 返回的原始数据字典，
                  包含 metadata / contributors / issues / pull_requests / releases / commit_activity

    Returns:
        CommunityScoreResult：包含各项评分、总得分、关键发现和风险标记
    """
    contributors = raw_data.get("contributors", [])
    issues = raw_data.get("issues", [])
    pull_requests = raw_data.get("pull_requests", [])
    releases = raw_data.get("releases", [])

    # 分别计算五项指标
    bus = score_bus_factor(contributors)
    issue = score_issue_response(issues)
    pr = score_pr_merge_rate(pull_requests)
    contrib = score_active_contributors(contributors)
    release = score_release_stability(releases)

    total = bus.score + issue.score + pr.score + contrib.score + release.score

    # 生成关键发现和风险标记
    findings = []
    risks = []

    if bus.score == 10:
        findings.append(f"Bus Factor 健康（{bus.raw_value}），核心贡献者分散，不会因单人离开而停滞")
    elif bus.score == 6:
        findings.append(f"Bus Factor 一般（{bus.raw_value}），存在集中风险")
    else:
        risks.append(f"Bus Factor 过低（{bus.raw_value}），项目可能因核心维护者离开而停滞")

    if issue.score >= 6:
        findings.append(f"Issue 处理速度良好（中位时间 {issue.raw_value}）")
    elif issue.score > 0:
        findings.append(f"Issue 处理速度一般（中位时间 {issue.raw_value}）")
    else:
        risks.append(f"Issue 响应慢（中位时间 {issue.raw_value}），社区维护可能不足")

    if pr.score >= 4:
        findings.append(f"PR 合并率 {pr.raw_value}，社区协作顺畅")
    else:
        risks.append(f"PR 合并率仅 {pr.raw_value}，贡献者体验可能较差")

    if contrib.score == 4:
        findings.append(f"活跃贡献者 {contrib.raw_value} 人，社区生态健康")
    elif contrib.score == 2:
        findings.append(f"活跃贡献者 {contrib.raw_value} 人，处于中等水平")
    else:
        risks.append(f"活跃贡献者仅 {contrib.raw_value} 人，社区规模过小")

    if release.score == 2:
        findings.append(f"Release 节奏正常（{release.raw_value}）")
    else:
        risks.append(f"Release 节奏异常（{release.raw_value}），可能缺乏持续维护")

    return CommunityScoreResult(
        total_score=total,
        max_score=30,
        bus_factor=bus,
        issue_response=issue,
        pr_merge_rate=pr,
        active_contributors=contrib,
        release_stability=release,
        findings=findings,
        risks=risks,
    )
