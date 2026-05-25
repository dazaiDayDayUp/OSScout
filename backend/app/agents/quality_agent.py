"""代码质量分析 Agent（规则评分 + LLM 推理增强）"""

import asyncio

from pydantic import BaseModel

from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.mcp.client import CodeAnalysisMCPClient, FilesystemMCPClient
from app.scoring.quality import score_code_quality

from .llm_enhancer import LLMEnhancer, QUALITY_ENHANCE_PROMPT

logger = get_logger(__name__)


class QualityAgentResult(BaseModel):
    """代码质量 Agent 的输出模型"""

    dimension: str = "quality"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
    reasoning: str | None = None  # LLM 推理过程
    details: dict
    repo: dict


class QualityAgent:
    """
    代码质量分析 Agent

    分析维度覆盖 PROJECT_PLAN §7.3 的四项指标：
    - 测试覆盖率
    - 静态分析漏洞
    - 文档完整度
    - 代码复杂度

    在规则评分基础上接入 LLM 推理。
    """

    def __init__(self) -> None:
        """初始化 Agent，创建 LLM 增强器实例"""
        self._enhancer = LLMEnhancer()

    async def analyze(self, repo_url: str) -> QualityAgentResult:
        """
        分析指定仓库的代码质量

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            QualityAgentResult：结构化的代码质量分析结果
        """
        # 1. 解析仓库标识
        owner, repo = parse_repo_url(repo_url)

        # 2. 启动两个 MCP Client
        async with FilesystemMCPClient() as fs_client, CodeAnalysisMCPClient() as ca_client:
            # 2.1 克隆仓库
            clone_result = await fs_client.call_tool("clone_repo", {
                "url": repo_url,
                "depth": 1,
            })
            local_path = clone_result["path"]

            # 2.2 并行执行所有采集任务
            docs, tests, radon_result, security_result = await asyncio.gather(
                self._check_documentation(fs_client, local_path),
                self._check_tests(fs_client, local_path),
                ca_client.call_tool("run_radon", {"path": local_path}),
                ca_client.call_tool("run_security_scan", {"path": local_path}),
            )

        # 3. 组装原始数据
        raw_data = {
            "radon": radon_result,
            "security": security_result,
            "docs": docs,
            "tests": tests,
        }

        # 4. 调用评分引擎（规则评分打底）
        score_result = score_code_quality(raw_data)

        # 5. LLM 推理增强
        llm_result = await self._enhancer.enhance(
            dimension="quality",
            prompt_template=QUALITY_ENHANCE_PROMPT,
            template_vars=self._build_prompt_vars(owner, repo, score_result),
        )

        # 6. 组装输出
        percentage = round(score_result.total_score / 25 * 100, 1)

        all_findings = list(score_result.findings) + list(llm_result.additional_findings)
        all_risks = list(score_result.risks) + list(llm_result.additional_risks)

        return QualityAgentResult(
            dimension="quality",
            score=score_result.total_score,
            max_score=25,
            percentage=percentage,
            findings=all_findings,
            risks=all_risks,
            reasoning=llm_result.reasoning,
            details={
                "test_coverage": self._item_to_dict(score_result.test_coverage),
                "static_analysis": self._item_to_dict(score_result.static_analysis),
                "documentation": self._item_to_dict(score_result.documentation),
                "code_complexity": self._item_to_dict(score_result.code_complexity),
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
    def _build_prompt_vars(owner: str, repo: str, score_result) -> dict:
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

        tc = item_vals(score_result.test_coverage)
        sa = item_vals(score_result.static_analysis)
        doc = item_vals(score_result.documentation)
        cc = item_vals(score_result.code_complexity)

        percentage = round(score_result.total_score / 25 * 100, 1)

        return {
            "owner": owner,
            "repo": repo,
            "test_coverage_score": tc["score"],
            "test_coverage_max": tc["max"],
            "test_coverage_raw": tc["raw"],
            "test_coverage_desc": tc["desc"],
            "static_analysis_score": sa["score"],
            "static_analysis_max": sa["max"],
            "static_analysis_raw": sa["raw"],
            "static_analysis_desc": sa["desc"],
            "documentation_score": doc["score"],
            "documentation_max": doc["max"],
            "documentation_raw": doc["raw"],
            "documentation_desc": doc["desc"],
            "code_complexity_score": cc["score"],
            "code_complexity_max": cc["max"],
            "code_complexity_raw": cc["raw"],
            "code_complexity_desc": cc["desc"],
            "total_score": score_result.total_score,
            "max_score": 25,
            "percentage": percentage,
            "findings": "; ".join(score_result.findings) if score_result.findings else "无",
            "risks": "; ".join(score_result.risks) if score_result.risks else "无",
        }

    async def _check_documentation(self, fs_client: FilesystemMCPClient, path: str) -> dict:
        """检查项目文档是否齐全"""
        results = await asyncio.gather(
            fs_client.call_tool("file_exists", {"path": f"{path}/README.md"}),
            fs_client.call_tool("file_exists", {"path": f"{path}/CHANGELOG.md"}),
            fs_client.call_tool("file_exists", {"path": f"{path}/CONTRIBUTING.md"}),
            fs_client.call_tool("file_exists", {"path": f"{path}/docs"}),
            return_exceptions=True,
        )
        return {
            "has_readme": self._safe_result(results[0], "exists", False),
            "has_changelog": self._safe_result(results[1], "exists", False),
            "has_contributing": self._safe_result(results[2], "exists", False),
            "has_api_docs": self._safe_result(results[3], "exists", False),
        }

    async def _check_tests(self, fs_client: FilesystemMCPClient, path: str) -> dict:
        """检查测试基础设施"""
        results = await asyncio.gather(
            fs_client.call_tool("file_exists", {"path": f"{path}/tests"}),
            fs_client.call_tool("file_exists", {"path": f"{path}/test"}),
            fs_client.call_tool("file_exists", {"path": f"{path}/.github/workflows"}),
            return_exceptions=True,
        )
        has_tests_dir = (
            self._safe_result(results[0], "exists", False)
            or self._safe_result(results[1], "exists", False)
        )
        return {
            "has_tests_dir": has_tests_dir,
            "has_ci": self._safe_result(results[2], "exists", False),
        }

    def _safe_result(self, result, key: str, default):
        """安全地提取结果，处理异常情况"""
        if isinstance(result, Exception):
            return default
        try:
            return result.get(key, default)
        except Exception:
            return default
