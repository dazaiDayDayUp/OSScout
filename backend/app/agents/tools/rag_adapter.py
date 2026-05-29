"""
RAG Adapter

将 RAGQueryEngine 的检索能力封装为 LLM 可调用的 Tool。

核心改进（解决 Phase 4 遗留问题 #1）：
- RAG Tool 返回完整文档内容（content），而不仅是标题
- LLM 拿到内容后自主判断引用哪些段落支撑结论

封装为 3 个 Tool：
1. rag.query_knowledge: 通用语义检索知识库
2. rag.get_benchmark: 查询行业基准数据（对接 benchmark_tool）
3. rag.get_competitors: 检索竞品对比信息
"""
import json

from app.core.logger import get_logger
from app.rag.query import RAGQueryEngine

from .registry import ToolRegistry, get_registry
from .tool import Tool, ToolSource

logger = get_logger(__name__)


class RAGAdapter:
    """RAG 检索能力 → Tool 转换适配器

    将 RAGQueryEngine 的 query、query_competitors 等方法
    封装为 LLM 可以通过 Function Calling 调用的 Tool。
    """

    def __init__(
        self,
        rag_engine: RAGQueryEngine | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        """
        Args:
            rag_engine: RAGQueryEngine 实例，None 时自动创建
            registry: 目标注册表，默认使用全局单例
        """
        self.rag_engine = rag_engine or RAGQueryEngine()
        self.registry = registry or get_registry()

    def register_tools(self) -> list[Tool]:
        """注册所有 RAG Tool 到 Registry

        Returns:
            注册成功的 Tool 列表
        """
        tools = [
            self._make_query_tool(),
            self._make_benchmark_tool(),
            self._make_competitor_tool(),
        ]

        for tool in tools:
            self.registry.register(tool)

        logger.info(
            "RAG Tool 注册完成",
            tool_count=len(tools),
            tool_names=[t.name for t in tools],
        )
        return tools

    @staticmethod
    def _format_results(results: list[dict], query_info: dict) -> str:
        """统一格式化 RAG 检索结果为 JSON 字符串

        参数:
            results: RAG 引擎返回的原始结果列表
            query_info: 查询相关信息（如 query、category 等）

        Returns:
            格式化的 JSON 字符串
        """
        formatted = [
            {
                "content": r.get("content", ""),
                "metadata": r.get("metadata", {}),
                "distance": r.get("distance"),
                "citation": r.get("citation"),
            }
            for r in results
        ]

        return json.dumps(
            {
                **query_info,
                "results_count": len(formatted),
                "results": formatted,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _make_query_tool(self) -> Tool:
        """创建通用知识检索 Tool"""

        def handler(
            query_text: str,
            category: str = "",
            n_results: int = 5,
        ) -> str:
            """检索知识库，获取与查询相关的权威资料

            在分析过程中需要引用外部知识、行业标准、历史案例时调用此工具。
            返回完整的文档内容，可用于支撑分析结论。

            Args:
                query_text: 查询文本，描述你想了解的知识点
                category: 限制检索类别（可选），可选值：
                          - "case-study": 失败案例
                          - "methodology": 评估方法论
                          - "competitor": 竞品映射
                          - "governance": 项目治理
                          - "benchmark": 行业基准
                n_results: 返回结果数量（默认 5，最多 10）

            Returns:
                检索结果列表的 JSON 字符串，每个结果包含：
                - content: 文档完整内容
                - metadata: 来源信息（source_file, category, topic）
                - distance: 相似度分数（越小越相似）
                - citation: 引用信息
            """
            # 限制最大返回数量
            n_results = min(max(n_results, 1), 10)

            # 调用 RAG 引擎检索
            cat = category if category else None
            results = self.rag_engine.query(
                query_text=query_text,
                category=cat,
                n_results=n_results,
            )

            # 格式化结果：保留完整 content，让 LLM 自主判断引用
            return self._format_results(
                results,
                {"query": query_text, "category": category or "all"},
            )

        return Tool(
            name="rag.query_knowledge",
            description=(
                "检索知识库获取权威资料。在分析过程中需要引用行业标准、"
                "历史案例、评估方法论时调用。返回完整文档内容，"
                "LLM 可自主判断引用哪些段落支撑结论。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": "查询文本，描述你想了解的知识点",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "限制检索类别（可选）。可选值："
                            "case-study（失败案例）、methodology（评估方法论）、"
                            "competitor（竞品映射）、governance（项目治理）、"
                            "benchmark（行业基准）"
                        ),
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "返回结果数量（默认 5，最多 10）",
                    },
                },
                "required": ["query_text"],
            },
            handler=handler,
            source=ToolSource.RAG,
            metadata={"rag_tool_type": "query"},
        )

    def _make_benchmark_tool(self) -> Tool:
        """创建行业基准查询 Tool"""

        def handler(
            project_type: str,
            metric_name: str = "",
        ) -> str:
            """查询某类项目的行业基准数据

            在需要与同类项目做量化对比时调用此工具。
            例如："前端框架的平均 PR 合并率是多少？"

            Args:
                project_type: 项目类型标签，可选值：
                    - frontend-framework: 前端框架
                    - backend-framework: 后端框架
                    - cli-tool: CLI 工具
                    - state-management: 状态管理库
                    - testing-framework: 测试框架
                    - ai-ml-library: AI/ML 库
                    - security-library: 安全相关库
                    - database-driver: 数据库驱动/ORM
                    - package-manager: 包管理器
                    - utility-library: 通用工具库
                metric_name: 指标名（可选），如 code_review_score、
                             security_policy_score。不填则返回所有指标。

            Returns:
                基准数据列表的 JSON 字符串
            """
            # 先通过 RAG 检索知识库中的基准数据
            query = f"{project_type} 行业基准 {metric_name}".strip()
            results = self.rag_engine.query(
                query_text=query,
                category="benchmark",
                n_results=5,
            )

            return self._format_results(
                results,
                {"project_type": project_type, "metric_name": metric_name or "all"},
            )

        return Tool(
            name="rag.get_benchmark",
            description=(
                "查询某类项目的行业基准数据。在评估项目指标时需要"
                "与同类项目做量化对比时调用。例如查询前端框架的平均 PR 合并率。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "project_type": {
                        "type": "string",
                        "description": (
                            "项目类型标签。可选值：frontend-framework（前端框架）、"
                            "backend-framework（后端框架）、cli-tool（CLI 工具）、"
                            "security-library（安全库）等"
                        ),
                    },
                    "metric_name": {
                        "type": "string",
                        "description": "指标名（可选），如 code_review_score",
                    },
                },
                "required": ["project_type"],
            },
            handler=handler,
            source=ToolSource.RAG,
            metadata={"rag_tool_type": "benchmark"},
        )

    def _make_competitor_tool(self) -> Tool:
        """创建竞品对比查询 Tool"""

        def handler(
            tech_domain: str,
        ) -> str:
            """检索某技术领域的竞品对比信息

            在需要了解项目所处竞争格局时调用此工具。

            Args:
                tech_domain: 技术领域，如 "frontend framework"、
                             "backend framework"、"state management library"

            Returns:
                竞品对比文档列表的 JSON 字符串
            """
            results = self.rag_engine.query_competitors(domain=tech_domain)

            return self._format_results(
                results,
                {"tech_domain": tech_domain},
            )

        return Tool(
            name="rag.get_competitors",
            description=(
                "检索某技术领域的竞品对比信息。在评估项目竞争力和"
                "市场定位时调用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tech_domain": {
                        "type": "string",
                        "description": (
                            "技术领域名称，如 frontend framework、"
                            "backend framework、state management library"
                        ),
                    },
                },
                "required": ["tech_domain"],
            },
            handler=handler,
            source=ToolSource.RAG,
            metadata={"rag_tool_type": "competitor"},
        )
