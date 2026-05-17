"""代码质量分析 Agent"""

import asyncio

from pydantic import BaseModel

from app.core.utils import parse_repo_url
from app.mcp.client import CodeAnalysisMCPClient, FilesystemMCPClient
from app.scoring.quality import score_code_quality


class QualityAgentResult(BaseModel):
    """代码质量 Agent 的输出模型"""

    dimension: str = "quality"
    score: int
    max_score: int
    percentage: float
    findings: list[str]
    risks: list[str]
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
    """

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

        # 4. 调用评分引擎
        score_result = score_code_quality(raw_data)

        # 5. 组装输出
        percentage = round(score_result.total_score / score_result.max_score * 100, 1)

        return QualityAgentResult(
            dimension="quality",
            score=score_result.total_score,
            max_score=score_result.max_score,
            percentage=percentage,
            findings=score_result.findings,
            risks=score_result.risks,
            details={
                "test_coverage": {
                    "score": score_result.test_coverage.score,
                    "max_score": score_result.test_coverage.max_score,
                    "raw_value": score_result.test_coverage.raw_value,
                    "description": score_result.test_coverage.description,
                },
                "static_analysis": {
                    "score": score_result.static_analysis.score,
                    "max_score": score_result.static_analysis.max_score,
                    "raw_value": score_result.static_analysis.raw_value,
                    "description": score_result.static_analysis.description,
                },
                "documentation": {
                    "score": score_result.documentation.score,
                    "max_score": score_result.documentation.max_score,
                    "raw_value": score_result.documentation.raw_value,
                    "description": score_result.documentation.description,
                },
                "code_complexity": {
                    "score": score_result.code_complexity.score,
                    "max_score": score_result.code_complexity.max_score,
                    "raw_value": score_result.code_complexity.raw_value,
                    "description": score_result.code_complexity.description,
                },
            },
            repo={
                "owner": owner,
                "repo": repo,
                "url": repo_url,
            },
        )

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
