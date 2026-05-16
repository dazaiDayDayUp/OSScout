"""
安全分析 Agent

职责：
1. 接收 GitHub 仓库地址
2. 调用 security_service 采集安全数据（许可证、依赖、漏洞）
3. 调用 scoring 模块计算评分
4. 输出结构化的安全分析结果

使用方式：
    from app.agents.security_agent import SecurityAgent
    agent = SecurityAgent()
    result = await agent.analyze("https://github.com/python-poetry/poetry")
"""

from pydantic import BaseModel

from app.agents.community_agent import parse_repo_url
from app.scoring.security import score_security, SecurityScoreResult
from app.services import security_service


class SecurityAgentResult(BaseModel):
    """安全分析 Agent 的输出模型"""

    dimension: str = "security"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
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
    """

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

        # 3. 调用评分引擎
        score_result = score_security(raw_data)

        # 4. 组装输出
        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        return SecurityAgentResult(
            dimension="security",
            score=score_result.total_score,
            max_score=score_result.max_score,
            percentage=percentage,
            findings=score_result.findings,
            risks=score_result.risks,
            details={
                "cve_record": {
                    "score": score_result.cve_record.score,
                    "max_score": score_result.cve_record.max_score,
                    "raw_value": score_result.cve_record.raw_value,
                    "description": score_result.cve_record.description,
                },
                "dependency_vulns": {
                    "score": score_result.dependency_vulns.score,
                    "max_score": score_result.dependency_vulns.max_score,
                    "raw_value": score_result.dependency_vulns.raw_value,
                    "description": score_result.dependency_vulns.description,
                },
                "license_risk": {
                    "score": score_result.license_risk.score,
                    "max_score": score_result.license_risk.max_score,
                    "raw_value": score_result.license_risk.raw_value,
                    "description": score_result.license_risk.description,
                },
                "response_speed": {
                    "score": score_result.response_speed.score,
                    "max_score": score_result.response_speed.max_score,
                    "raw_value": score_result.response_speed.raw_value,
                    "description": score_result.response_speed.description,
                },
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )
