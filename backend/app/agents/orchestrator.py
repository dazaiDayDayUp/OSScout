"""Orchestrator 协调器：并行调度 + RAG 校准 + 冲突消解 + ReAct Loop

Orchestrator 包含三层能力：
1. 并行调度 4 个分析 Agent（已有）
2. RAG 校准：每个 Agent 分析完成后检索知识库进行基准对比
3. 冲突消解：检测维度间的矛盾结论，由 Orchestrator 协调

ReAct Loop 设计：
- Thought: 分析各维度结果，识别矛盾和知识缺口
- Action: 并行调度 Agent + RAG 检索
- Observation: 获取 Agent 结果 + RAG 校准数据
- 下一轮 Thought: 基于 RAG 结果做最终汇总判断
"""

import asyncio

from pydantic import BaseModel

from app.agents.community_agent import CommunityAgent
from app.agents.evolution_agent import EvolutionAgent
from app.agents.quality_agent import QualityAgent
from app.agents.security_agent import SecurityAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.core.logger import get_logger
from app.core.utils import parse_repo_url
from app.rag.citations import CitationCollector
from app.rag.query import RAGQueryEngine

logger = get_logger(__name__)

# 各维度的满分配置（用于降级结果）
_DIMENSION_MAX_SCORES = {
    "community": 30,
    "quality": 25,
    "security": 25,
    "evolution": 20,
}

# 维度名称映射（用于日志和输出）
_DIMENSION_NAMES = {
    "community": "社区健康度",
    "quality": "代码质量",
    "security": "安全分析",
    "evolution": "技术演进",
}

# 冲突检测模式：当维度 A 的百分比 > threshold_a 且维度 B 的百分比 < threshold_b 时触发
_CONFLICT_PATTERNS = [
    {
        "dim_a": "community",
        "threshold_a": 70,
        "dim_b": "security",
        "threshold_b": 50,
        "message": "社区活跃度高但安全评分偏低，需关注安全漏洞修复速度和供应链风险",
    },
    {
        "dim_a": "quality",
        "threshold_a": 70,
        "dim_b": "evolution",
        "threshold_b": 50,
        "message": "代码质量好但技术演进停滞，可能是核心维护者倦怠或项目进入维护模式",
    },
    {
        "dim_a": "community",
        "threshold_a": 70,
        "dim_b": "quality",
        "threshold_b": 50,
        "message": "社区活跃但代码债务较重，需关注长期可维护性",
    },
    {
        "dim_a": "security",
        "threshold_a": 70,
        "dim_b": "evolution",
        "threshold_b": 50,
        "message": "安全性好但技术演进缓慢，可能存在技术栈老化风险",
    },
]


class OrchestratorResult(BaseModel):
    """Orchestrator 的输出模型：尽调报告完整结果"""

    repo: dict
    dimensions: dict
    overall_score: int
    overall_max_score: int
    overall_percentage: float
    findings: list[str]
    risks: list[str]
    calibrations: dict  # 各维度的 RAG 校准结果
    conflicts: list[str]  # 维度间冲突检测结论
    react_summary: str  # ReAct Loop 最终总结
    synthesis: dict  # 综合报告 Agent 生成的结构化报告
    citations: list[dict]  # 引用来源列表（去重后）


class Orchestrator:
    """
    尽调分析协调器

    通过 asyncio.gather 并发调度 4 个分析 Agent，
    单个 Agent 失败时输出降级结果，不影响其他维度。
    包含 RAG 校准、冲突消解和 ReAct Loop 骨架。
    """

    def __init__(self) -> None:
        """初始化各分析 Agent 实例、RAG 查询引擎和综合报告 Agent"""
        self.community_agent = CommunityAgent()
        self.quality_agent = QualityAgent()
        self.security_agent = SecurityAgent()
        self.evolution_agent = EvolutionAgent()
        self.rag_engine = RAGQueryEngine()
        self.synthesis_agent = SynthesisAgent()

    async def analyze(self, repo_url: str) -> OrchestratorResult:
        """
        执行完整的尽调分析流程（ReAct Loop）

        Args:
            repo_url: GitHub 仓库地址

        Returns:
            OrchestratorResult：包含各维度评分、RAG 校准和冲突消解的结构化结果
        """
        # ========== Step 1: Thought ==========
        # 解析仓库标识，提前准备好用于异常降级和报告头部
        owner, repo = parse_repo_url(repo_url)
        repo_info = {"owner": owner, "repo": repo, "url": repo_url}
        logger.info(
            "开始尽调分析 (ReAct Loop)",
            owner=owner,
            repo=repo,
        )

        # ========== Step 2: Action ==========
        # 并发调度 4 个 Agent，return_exceptions=True 实现错误隔离
        logger.info("Action: 并发调度 4 个分析 Agent")
        results = await asyncio.gather(
            self.community_agent.analyze(repo_url),
            self.quality_agent.analyze(repo_url),
            self.security_agent.analyze(repo_url),
            self.evolution_agent.analyze(repo_url),
            return_exceptions=True,
        )

        # ========== Step 3: Observation ==========
        # 处理 Agent 结果 + RAG 校准 + 冲突检测
        logger.info("Observation: 处理结果 + RAG 校准 + 冲突检测")

        dimension_names = ["community", "quality", "security", "evolution"]
        dimensions: dict[str, dict] = {}
        calibrations: dict[str, list[dict]] = {}
        overall_score = 0
        overall_max_score = 0
        all_findings: list[str] = []
        all_risks: list[str] = []

        # 引用收集器，汇总所有维度的引用来源
        citation_collector = CitationCollector()

        for name, result in zip(dimension_names, results):
            if isinstance(result, asyncio.CancelledError):
                # Agent 被异步取消（通常是外部超时或 Worker 终止信号）
                dim_result = self._fallback_result(name, repo_info, "分析任务被取消")
                all_risks.append(f"{name} 维度分析被取消")
                calibrations[name] = []
            elif isinstance(result, Exception):
                # Agent 失败，生成降级结果
                dim_result = self._fallback_result(name, repo_info, str(result))
                all_risks.append(f"{name} 维度分析失败: {result}")
                calibrations[name] = []
            else:
                # Agent 成功，使用正常结果
                dim_result = result.model_dump()
                all_findings.extend(list(result.findings))
                all_risks.extend(list(result.risks))

                # RAG 校准：检索相关知识库进行基准对比
                calibration = await self._calibrate_dimension(name, dim_result)
                calibrations[name] = calibration

                # 从校准结果中提取引用
                for cal in calibration:
                    if "citation" in cal:
                        from app.rag.citations import Citation
                        citation_collector.add(Citation(**cal["citation"]))

            dimensions[name] = dim_result
            overall_score += dim_result["score"]
            overall_max_score += dim_result["max_score"]

        overall_percentage = round(overall_score / overall_max_score * 100, 1)

        # 冲突消解：检测维度间矛盾
        conflicts = self._detect_conflicts(dimensions)

        # ========== Step 4: Thought (Final) ==========
        # 基于 RAG 校准和冲突检测结果，生成最终汇总判断
        react_summary = self._generate_react_summary(
            repo_info, dimensions, calibrations, conflicts, overall_percentage
        )

        logger.info(
            "尽调分析完成",
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            overall_percentage=overall_percentage,
            conflicts=len(conflicts),
        )

        # ========== Step 5: Synthesis ==========
        # 调用综合报告 Agent 生成最终结构化报告
        logger.info("Synthesis: 生成综合报告")

        # 汇总去重后的引用列表
        all_citations = citation_collector.to_dict_list()
        logger.info("引用汇总完成", unique_citations=len(all_citations))

        orchestrator_data = {
            "repo": repo_info,
            "dimensions": dimensions,
            "overall_score": overall_score,
            "overall_max_score": overall_max_score,
            "overall_percentage": overall_percentage,
            "findings": all_findings,
            "risks": all_risks,
            "calibrations": calibrations,
            "conflicts": conflicts,
            "react_summary": react_summary,
            "citations": all_citations,
        }
        synthesis_report = await self.synthesis_agent.generate(orchestrator_data)

        logger.info(
            "尽调分析完成",
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            overall_percentage=overall_percentage,
            conflicts=len(conflicts),
            synthesis_rating=synthesis_report.overall_rating,
            citations=len(all_citations),
        )

        return OrchestratorResult(
            repo=repo_info,
            dimensions=dimensions,
            overall_score=overall_score,
            overall_max_score=overall_max_score,
            overall_percentage=overall_percentage,
            findings=all_findings,
            risks=all_risks,
            calibrations=calibrations,
            conflicts=conflicts,
            react_summary=react_summary,
            synthesis=synthesis_report.model_dump(),
            citations=all_citations,
        )

    # ------------------------------------------------------------------
    # RAG 校准
    # ------------------------------------------------------------------

    async def _calibrate_dimension(
        self, dimension: str, dim_result: dict
    ) -> list[dict]:
        """
        对单个维度进行 RAG 校准：检索知识库中的相关基准和案例

        Args:
            dimension: 维度名称
            dim_result: 维度分析结果字典

        Returns:
            RAG 检索结果列表
        """
        try:
            if dimension == "community":
                # 提取关键指标用于校准查询
                bus_factor = (
                    dim_result.get("details", {})
                    .get("bus_factor", {})
                    .get("raw_value", "")
                )
                results = self.rag_engine.calibrate_community(
                    metric_name=f"Bus Factor {bus_factor}"
                )

            elif dimension == "quality":
                complexity = (
                    dim_result.get("details", {})
                    .get("code_complexity", {})
                    .get("raw_value", "")
                )
                results = self.rag_engine.calibrate_quality(
                    concern=f"复杂度 {complexity}"
                )

            elif dimension == "security":
                cve = (
                    dim_result.get("details", {})
                    .get("cve_record", {})
                    .get("raw_value", "")
                )
                results = self.rag_engine.calibrate_security(
                    concern=f"CVE {cve}"
                )

            elif dimension == "evolution":
                freq = (
                    dim_result.get("details", {})
                    .get("release_frequency", {})
                    .get("raw_value", "")
                )
                results = self.rag_engine.calibrate_evolution(
                    concern=f"发布频率 {freq}"
                )
            else:
                results = []

            logger.info(
                "RAG 校准完成",
                dimension=dimension,
                results=len(results),
            )
            return results

        except Exception as e:
            logger.warning(
                "RAG 校准失败",
                dimension=dimension,
                error=str(e),
            )
            return []

    # ------------------------------------------------------------------
    # 冲突消解
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_conflicts(dimensions: dict[str, dict]) -> list[str]:
        """
        检测各维度之间的矛盾结论

        例如：社区健康度高但安全评分低，
        说明虽然社区活跃但安全漏洞修复不及时。

        Args:
            dimensions: 各维度分析结果字典

        Returns:
            冲突描述列表
        """
        conflicts: list[str] = []

        for pattern in _CONFLICT_PATTERNS:
            dim_a = pattern["dim_a"]
            dim_b = pattern["dim_b"]

            if dim_a not in dimensions or dim_b not in dimensions:
                continue

            score_a = dimensions[dim_a].get("percentage", 0)
            score_b = dimensions[dim_b].get("percentage", 0)

            if score_a >= pattern["threshold_a"] and score_b <= pattern["threshold_b"]:
                conflicts.append(pattern["message"])

        # 额外检测：如果任何维度完全失败（score=0 且是因为异常），也标记
        for name, dim in dimensions.items():
            if dim.get("score", 0) == 0 and any(
                "分析失败" in r for r in dim.get("risks", [])
            ):
                cn_name = _DIMENSION_NAMES.get(name, name)
                conflicts.append(
                    f"{cn_name}维度分析失败，该维度的评估结果不可靠，建议手动复核"
                )

        return conflicts

    # ------------------------------------------------------------------
    # ReAct 最终总结
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_react_summary(
        repo_info: dict,
        dimensions: dict[str, dict],
        calibrations: dict[str, list[dict]],
        conflicts: list[str],
        overall_percentage: float,
    ) -> str:
        """
        基于所有观察结果生成 ReAct Loop 的最终总结

        综合各维度评分、RAG 校准引用和冲突检测结论，
        生成一句话的核心判断。
        """
        owner = repo_info["owner"]
        repo = repo_info["repo"]

        # 评级判断
        if overall_percentage >= 80:
            rating = "推荐"
        elif overall_percentage >= 60:
            rating = "谨慎推荐"
        elif overall_percentage >= 50:
            rating = "谨慎使用"
        else:
            rating = "不建议"

        # 收集校准引用
        calibration_refs: list[str] = []
        for dim_name, results in calibrations.items():
            if results:
                topics = [r["metadata"].get("topic", "") for r in results[:1]]
                if topics:
                    calibration_refs.append(topics[0])

        # 构建总结
        parts = [f"{owner}/{repo} 综合评级：{rating}（{overall_percentage}%）。"]

        if conflicts:
            parts.append(
                f"检测到 {len(conflicts)} 个维度间冲突："
                f"{conflicts[0][:60]}..."
            )

        if calibration_refs:
            parts.append(
                f"知识库引用：{', '.join(calibration_refs[:2])}。"
            )

        return "".join(parts)

    # ------------------------------------------------------------------
    # 降级结果生成
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_result(dimension: str, repo: dict, error_msg: str) -> dict:
        """
        生成单个维度分析失败时的降级结果

        结构与正常 AgentResult.model_dump() 一致，确保 Reporter 可以正常渲染。
        """
        max_score = _DIMENSION_MAX_SCORES.get(dimension, 0)
        return {
            "dimension": dimension,
            "score": 0,
            "max_score": max_score,
            "percentage": 0.0,
            "findings": [],
            "risks": [f"分析失败: {error_msg}"],
            "reasoning": None,
            "details": {},
            "repo": repo,
        }
