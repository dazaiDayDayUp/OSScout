"""安全评分引擎（0-25 分）：CVE / 依赖漏洞 / 许可证 / 响应速度"""

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
class SecurityScoreResult:
    """安全评分的完整结果"""

    total_score: int
    max_score: int = 25
    cve_record: ScoreItem | None = None
    dependency_vulns: ScoreItem | None = None
    license_risk: ScoreItem | None = None
    response_speed: ScoreItem | None = None
    findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════
# 许可证风险配置
# ═══════════════════════════════════════════════════════════════

# 安全许可证（商业友好，宽松）
_SAFE_LICENSES = {
    "MIT", "Apache-2.0", "Apache-2", "BSD-2-Clause", "BSD-3-Clause",
    "BSD-2", "BSD-3", "ISC", "Unlicense", "WTFPL", "CC0-1.0",
    "MPL-2.0", "EPL-2.0", "0BSD",
}

# 传染性许可证（使用此代码的项目也需开源）
_COPYLEFT_LICENSES = {
    "GPL-2.0", "GPL-3.0", "GPL-2.0-only", "GPL-3.0-only",
    "GPL-2.0-or-later", "GPL-3.0-or-later", "GPL", "AGPL-3.0",
    "AGPL-3.0-only", "AGPL", "LGPL-2.1", "LGPL-3.0",
    "LGPL-2.1-only", "LGPL-3.0-only", "LGPL",
    "SSPL-1.0", "EUPL-1.2",
}


# ═══════════════════════════════════════════════════════════════
# 四项独立评分函数
# ═══════════════════════════════════════════════════════════════


def score_cve_record(vulnerabilities: list[dict]) -> ScoreItem:
    """
    CVE 记录评分（10 分）

    按严重程度扣分：
    - 无漏洞：10 分
    - 每个低危（LOW）：-2 分
    - 每个中危（MEDIUM）：-5 分
    - 每个高危（HIGH）：-10 分
    - 最低 0 分
    """
    if not vulnerabilities:
        return ScoreItem(
            score=10,
            max_score=10,
            raw_value="0",
            description="未发现已知 CVE 漏洞",
        )

    high_count = sum(1 for v in vulnerabilities if v.get("severity") == "HIGH")
    medium_count = sum(1 for v in vulnerabilities if v.get("severity") == "MEDIUM")
    low_count = sum(1 for v in vulnerabilities if v.get("severity") == "LOW")

    deduction = high_count * 10 + medium_count * 5 + low_count * 2
    score = max(10 - deduction, 0)

    parts = []
    if high_count:
        parts.append(f"{high_count} 个高危")
    if medium_count:
        parts.append(f"{medium_count} 个中危")
    if low_count:
        parts.append(f"{low_count} 个低危")

    if score == 10:
        desc = "未发现高危/中危 CVE，低危数量可接受"
    elif score > 0:
        desc = f"发现 {', '.join(parts)}，已扣分"
    else:
        desc = f"漏洞严重，发现 {', '.join(parts)}，CVE 评分归零"

    return ScoreItem(
        score=score,
        max_score=10,
        raw_value=f"H={high_count}, M={medium_count}, L={low_count}",
        description=desc,
    )


def score_dependency_vulns(vulnerabilities: list[dict]) -> ScoreItem:
    """
    依赖漏洞评分（8 分）

    按漏洞数量扣分：
    - 0 个漏洞：8 分
    - 每 1 个漏洞：-2 分
    - 最低 0 分
    """
    count = len(vulnerabilities)

    if count == 0:
        return ScoreItem(
            score=8,
            max_score=8,
            raw_value="0",
            description="所有依赖均无已知漏洞",
        )

    score = max(8 - count * 2, 0)

    return ScoreItem(
        score=score,
        max_score=8,
        raw_value=str(count),
        description=f"发现 {count} 个依赖漏洞（每 1 个扣 2 分）",
    )


def score_license_risk(license_info: dict) -> ScoreItem:
    """
    许可证风险评分（5 分）

    评分标准：
    - MIT/Apache/BSD 等宽松许可证：5 分
    - GPL/AGPL 等传染性许可证：2 分（可用但需关注合规）
    - 无许可证或未知：0 分
    """
    spdx_id = (license_info.get("spdx_id") or "NOASSERTION").upper()
    name = license_info.get("name", "Unknown")

    # 安全许可证
    if spdx_id in _SAFE_LICENSES or any(
        safe in spdx_id for safe in _SAFE_LICENSES
    ):
        return ScoreItem(
            score=5,
            max_score=5,
            raw_value=spdx_id,
            description=f"宽松许可证（{name}），商业使用安全",
        )

    # 传染性许可证
    if spdx_id in _COPYLEFT_LICENSES or any(
        copyleft in spdx_id for copyleft in _COPYLEFT_LICENSES
    ):
        return ScoreItem(
            score=2,
            max_score=5,
            raw_value=spdx_id,
            description=f"传染性许可证（{name}），集成时需注意合规义务",
        )

    # 无许可证或未知
    if spdx_id in ("NOASSERTION", "NONE", "UNKNOWN", ""):
        return ScoreItem(
            score=0,
            max_score=5,
            raw_value=spdx_id,
            description="未声明许可证，存在法律风险",
        )

    # 其他许可证（保守处理）
    return ScoreItem(
        score=2,
        max_score=5,
        raw_value=spdx_id,
        description=f"非标准许可证（{name}），建议法务审核",
    )


def score_response_speed(vulnerabilities: list[dict]) -> ScoreItem:
    """
    安全响应速度评分（2 分）

    计算思路：
    从漏洞披露时间（published）到当前的天数，反映社区修复速度。
    - 平均披露天数 < 7 天（近期已修复或快速响应）：2 分
    - 平均披露天数 < 30 天：1 分
    - 否则（存在长期未修复的漏洞）：0 分

    如果没有漏洞数据，默认给 2 分（无法评估 = 暂无问题）。
    """
    if not vulnerabilities:
        return ScoreItem(
            score=2,
            max_score=2,
            raw_value="N/A",
            description="无漏洞记录，无法评估响应速度（默认安全）",
        )

    # 收集有 response_days 的漏洞
    days_list = [
        v["response_days"]
        for v in vulnerabilities
        if v.get("response_days") is not None
    ]

    if not days_list:
        return ScoreItem(
            score=2,
            max_score=2,
            raw_value="N/A",
            description="漏洞数据缺少时间信息，无法评估",
        )

    avg_days = sum(days_list) / len(days_list)

    if avg_days < 7:
        score = 2
        desc = f"漏洞平均已披露 {avg_days:.0f} 天，响应及时"
    elif avg_days < 30:
        score = 1
        desc = f"漏洞平均已披露 {avg_days:.0f} 天，响应一般"
    else:
        score = 0
        desc = f"漏洞平均已披露 {avg_days:.0f} 天，存在长期未修复漏洞"

    return ScoreItem(
        score=score,
        max_score=2,
        raw_value=f"{avg_days:.0f} 天",
        description=desc,
    )


# ═══════════════════════════════════════════════════════════════
# 总入口
# ═══════════════════════════════════════════════════════════════


def score_security(raw_data: dict[str, Any]) -> SecurityScoreResult:
    """
    安全评分总入口

    Args:
        raw_data: security_service.collect_security_data() 返回的数据字典，
                  包含 license / dependencies / vulnerabilities

    Returns:
        SecurityScoreResult：包含各项评分、总得分、关键发现和风险标记
    """
    vulnerabilities = raw_data.get("vulnerabilities", [])
    license_info = raw_data.get("license", {})

    # 分别计算四项指标
    cve = score_cve_record(vulnerabilities)
    deps = score_dependency_vulns(vulnerabilities)
    lic = score_license_risk(license_info)
    resp = score_response_speed(vulnerabilities)

    total = cve.score + deps.score + lic.score + resp.score

    # 生成关键发现和风险标记
    findings: list[str] = []
    risks: list[str] = []

    # CVE 相关
    if cve.score == 10:
        findings.append("CVE 记录干净，未发现已知安全漏洞")
    elif cve.score >= 5:
        findings.append(f"CVE 记录基本合格（{cve.raw_value}）")
    else:
        risks.append(f"存在严重 CVE 漏洞（{cve.raw_value}），建议评估影响")

    # 依赖漏洞相关
    if deps.score == 8:
        findings.append("所有依赖均无已知漏洞")
    elif deps.score > 0:
        findings.append(f"发现 {deps.raw_value} 个依赖漏洞，建议升级")
    else:
        risks.append(f"依赖漏洞过多（{deps.raw_value} 个），存在严重安全风险")

    # 许可证相关
    if lic.score == 5:
        findings.append(f"许可证友好（{lic.raw_value}），可放心使用")
    elif lic.score == 2:
        findings.append(f"许可证为 {lic.raw_value}，集成时需注意合规义务")
    else:
        risks.append("未声明许可证，存在法律不确定性")

    # 响应速度相关
    if resp.score == 2:
        findings.append(f"安全响应速度良好（{resp.raw_value}）")
    elif resp.score == 1:
        findings.append(f"安全响应速度一般（{resp.raw_value}）")
    elif vulnerabilities:
        risks.append(f"安全响应较慢（{resp.raw_value}），存在未修复漏洞")

    return SecurityScoreResult(
        total_score=total,
        max_score=25,
        cve_record=cve,
        dependency_vulns=deps,
        license_risk=lic,
        response_speed=resp,
        findings=findings,
        risks=risks,
    )
