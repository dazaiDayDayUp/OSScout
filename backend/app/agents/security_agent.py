"""安全分析 Agent（规则评分 + LLM 推理增强）"""

from pydantic import BaseModel

from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.scoring.security import score_security
from app.services import security_service

from .llm_enhancer import LLMEnhancer, SECURITY_ENHANCE_PROMPT

logger = get_logger(__name__)


class SecurityAgentResult(BaseModel):
    """安全分析 Agent 的输出模型"""

    dimension: str = "security"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    reasoning: str | None = None  # LLM 推理过程
    details: dict
    repo: dict


class SecurityAgent:
    """
    安全分析 Agent

    分析维度覆盖 PROJECT_PLAN §7.3 的四项指标：
    - CVE 记录（已知漏洞严重程度）
    - 依赖漏洞（依赖包漏洞数量）
    - 许可证风险（许可证商业友好度）
    - 安全响应速度（漏洞修复及时性）

    在规则评分基础上接入 LLM 推理。
    """

    def __init__(self) -> None:
        """初始化 Agent，创建 LLM 增强器实例"""
        self._enhancer = LLMEnhancer()

    async def analyze(self, repo_url: str) -> SecurityAgentResult:
        """
        分析指定仓库的安全状况

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            SecurityAgentResult：结构化的安全分析结果
        """
        # 1. 解析仓库标识
        owner, repo = parse_repo_url(repo_url)

        # 2. 采集安全数据（许可证 + 依赖 + OSV 漏洞）
        raw_data = await security_service.collect_security_data(owner, repo)

        # 3. 调用评分引擎（规则评分打底）
        score_result = score_security(raw_data)

        # 4. LLM 推理增强
        llm_result = await self._enhancer.enhance(
            dimension="security",
            prompt_template=SECURITY_ENHANCE_PROMPT,
            template_vars=self._build_prompt_vars(owner, repo, raw_data, score_result),
        )

        # 5. 组装输出
        percentage = round(score_result.total_score / 25 * 100, 1)

        all_findings = list(score_result.findings) + list(llm_result.additional_findings)
        all_risks = list(score_result.risks) + list(llm_result.additional_risks)

        return SecurityAgentResult(
            dimension="security",
            score=score_result.total_score,
            max_score=25,
            percentage=percentage,
            findings=all_findings,
            risks=all_risks,
            reasoning=llm_result.reasoning,
            details={
                "cve_record": self._item_to_dict(score_result.cve_record),
                "dependency_vulns": self._item_to_dict(score_result.dependency_vulns),
                "license_risk": self._item_to_dict(score_result.license_risk),
                "response_speed": self._item_to_dict(score_result.response_speed),
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
    def _build_prompt_vars(owner: str, repo: str, raw_data: dict, score_result) -> dict:
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

        cve = item_vals(score_result.cve_record)
        dep = item_vals(score_result.dependency_vulns)
        lic = item_vals(score_result.license_risk)
        resp = item_vals(score_result.response_speed)

        license_info = raw_data.get("license", {})
        license_name = license_info.get("license", "未知") if isinstance(license_info, dict) else "未知"

        # CVE 详情摘要
        vulnerabilities = raw_data.get("vulnerabilities", [])
        cve_details = ""
        if vulnerabilities:
            high = sum(1 for v in vulnerabilities if v.get("severity") in ("HIGH", "CRITICAL"))
            medium = sum(1 for v in vulnerabilities if v.get("severity") == "MODERATE")
            low = sum(1 for v in vulnerabilities if v.get("severity") == "LOW")
            cve_details = f"高危 {high} 个, 中危 {medium} 个, 低危 {low} 个"
        else:
            cve_details = "未发现已知漏洞"

        percentage = round(score_result.total_score / 25 * 100, 1)

        return {
            "owner": owner,
            "repo": repo,
            "cve_record_score": cve["score"],
            "cve_record_max": cve["max"],
            "cve_record_raw": cve["raw"],
            "cve_record_desc": cve["desc"],
            "dependency_vulns_score": dep["score"],
            "dependency_vulns_max": dep["max"],
            "dependency_vulns_raw": dep["raw"],
            "dependency_vulns_desc": dep["desc"],
            "license_risk_score": lic["score"],
            "license_risk_max": lic["max"],
            "license_risk_raw": lic["raw"],
            "license_risk_desc": lic["desc"],
            "response_speed_score": resp["score"],
            "response_speed_max": resp["max"],
            "response_speed_raw": resp["raw"],
            "response_speed_desc": resp["desc"],
            "total_score": score_result.total_score,
            "max_score": 25,
            "percentage": percentage,
            "findings": "; ".join(score_result.findings) if score_result.findings else "无",
            "risks": "; ".join(score_result.risks) if score_result.risks else "无",
            "license": license_name,
            "cve_details": cve_details,
        }
