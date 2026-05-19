"""RAG 查询引擎

提供高层的语义检索接口，供分析 Agent 调用进行知识库查询和基准校准。

核心设计：
- 统一入口 query()：通用的语义检索
- 专用接口 calibrate_*()：面向各分析维度的结构化检索
- 结果包含 content + metadata + distance，便于 Agent 判断引用可信度
"""

from app.core.logger import get_logger

from .vector_store import VectorStore

logger = get_logger(__name__)

# 默认返回的相似文档数量
DEFAULT_TOP_K = 3


class RAGQueryEngine:
    """RAG 查询引擎

    封装向量库的检索逻辑，提供面向业务场景的查询方法。
    所有检索结果按相似度排序（distance 越小越相似）。
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        collection_name: str = "osscout_kb",
    ) -> None:
        """初始化查询引擎

        Args:
            vector_store: 向量库实例，None 时自动创建
            collection_name: 自动创建向量库时使用的集合名称
        """
        if vector_store is None:
            vector_store = VectorStore(collection_name=collection_name)
        self.vector_store = vector_store

    # ------------------------------------------------------------------
    # 通用检索接口
    # ------------------------------------------------------------------

    def query(
        self,
        query_text: str,
        category: str | None = None,
        n_results: int = DEFAULT_TOP_K,
    ) -> list[dict]:
        """通用语义检索

        Args:
            query_text: 查询文本
            category: 限制检索范围，如 "case-study" / "methodology" / "competitor"
            n_results: 返回结果数量

        Returns:
            检索结果列表，每个元素格式：
            {
                "id": "文档ID",
                "content": "文档内容",
                "metadata": {"category": "...", "topic": "..."},
                "distance": 0.15,  # 余弦距离，越小越相似
            }
        """
        filter_dict = {"category": category} if category else None

        logger.info(
            "执行 RAG 检索",
            query=query_text[:80],
            category=category,
            n_results=n_results,
        )

        results = self.vector_store.search(
            query_text=query_text,
            n_results=n_results,
            filter_dict=filter_dict,
        )

        logger.info(
            "RAG 检索完成",
            query=query_text[:80],
            returned=len(results),
            best_distance=results[0]["distance"] if results else None,
        )

        return results

    # ------------------------------------------------------------------
    # 面向各维度的专用校准接口
    # ------------------------------------------------------------------

    def calibrate_community(self, metric_name: str = "") -> list[dict]:
        """社区健康维度校准：检索相关基准和失败案例

        用于回答："Bus Factor 低的项目历史上发生了什么？"
        """
        queries = [
            f"开源项目社区健康度评估标准 {metric_name}",
            "Bus Factor 风险 维护者退出 项目弃坑",
            "开源项目 contributor 流失 社区衰退",
        ]
        return self._multi_query_merge(queries, category="case-study")

    def calibrate_quality(self, concern: str = "") -> list[dict]:
        """代码质量维度校准"""
        queries = [
            f"代码质量评估标准 {concern}",
            "开源项目测试覆盖率不足 代码债务",
            "静态分析工具 代码复杂度 可维护性",
        ]
        return self._multi_query_merge(queries, category="methodology")

    def calibrate_security(self, concern: str = "") -> list[dict]:
        """安全维度校准"""
        queries = [
            f"开源安全漏洞评估 {concern}",
            "依赖漏洞 供应链攻击 恶意代码注入",
            "开源项目安全响应 CVE 披露",
        ]
        return self._multi_query_merge(queries, category="case-study")

    def calibrate_evolution(self, concern: str = "") -> list[dict]:
        """技术演进维度校准"""
        queries = [
            f"技术选型评估 项目活跃度 {concern}",
            "开源项目技术栈老化 版本更新",
            "Breaking Change 版本管理 迁移成本",
        ]
        return self._multi_query_merge(queries)

    # ------------------------------------------------------------------
    # 竞品对比
    # ------------------------------------------------------------------

    def query_competitors(self, domain: str) -> list[dict]:
        """检索某技术领域的竞品映射

        Args:
            domain: 领域名称，如 "frontend-framework", "backend-framework"

        Returns:
            竞品对比文档列表
        """
        return self.query(
            query_text=f"{domain} 技术选型对比",
            category="competitor",
            n_results=2,
        )

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _multi_query_merge(
        self, queries: list[str], category: str | None = None
    ) -> list[dict]:
        """多查询合并去重：执行多个查询，合并结果并按相似度排序去重

        不同角度的查询可能命中同一文档，需要去重保留最优结果。
        """
        seen_ids: set[str] = set()
        merged: list[dict] = []

        for q in queries:
            results = self.query(q, category=category, n_results=DEFAULT_TOP_K)
            for r in results:
                doc_id = r["id"]
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    merged.append(r)

        # 按 distance 升序排序（越相似越靠前）
        merged.sort(key=lambda x: x["distance"])
        return merged[:DEFAULT_TOP_K]
