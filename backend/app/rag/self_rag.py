"""Self-RAG 检索自验证模块

Phase 4.6 核心实现。

Self-RAG（Self-Reflective Retrieval-Augmented Generation）是一种让 LLM
在"使用检索结果"之前先"判断检索结果是否相关"的框架。

核心流程：
    1. 执行混合检索 + 重排序，获取候选文档
    2. LLM 验证：判断候选文档是否真正回答了查询
    3. 如果验证通过 → 返回结果
    4. 如果验证不通过：
       a. 查询扩展：用 LLM 生成多角度扩展查询，重新检索
       b. 再次验证
       c. 仍不通过 → Web 搜索 fallback
    5. 返回最终结果（标注置信度和来源）

Self-RAG 的关键价值：
- 避免"检索到什么就用什么"的盲目性
- 在知识库覆盖不足时主动发现
- 为最终报告提供"为什么引用这个来源"的可解释性
"""

from pydantic import BaseModel, Field

from app.core.logger import get_logger
from app.llm import LLMMessage, get_llm_provider
from app.llm.schemas import StructuredOutput

from .citations import CitationCollector
from .hybrid_retriever import HybridRetriever
from .reranker import CrossEncoderReranker
from .vector_store import VectorStore
from .web_search import WebSearchClient

logger = get_logger(__name__)

# 验证通过阈值
RELEVANCE_CONFIDENCE_THRESHOLD = 0.7

# 最多扩展查询轮次
MAX_EXPANSION_ROUNDS = 1

# 最多扩展查询数量
MAX_EXPANDED_QUERIES = 3


# ------------------------------------------------------------------
# 结构化输出 Schema
# ------------------------------------------------------------------

class RetrievalValidationResult(StructuredOutput):
    """检索结果自验证的输出格式"""

    is_relevant: bool = Field(
        ...,
        description="检索结果是否包含足够且准确的信息来回答用户查询",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="你对判断的置信度，0=完全不确定，1=完全确定",
    )
    missing_info: str = Field(
        default="",
        description="如果信息不完整，缺少哪些关键信息（不超过50字）",
    )
    suggested_queries: list[str] = Field(
        default_factory=list,
        description="如果检索结果不相关，建议用哪些替代查询来重新检索（最多3个）",
    )
    reasoning: str = Field(
        ...,
        description="你的判断理由（不超过100字）",
    )


class QueryExpansionResult(StructuredOutput):
    """查询扩展的输出格式"""

    expanded_queries: list[str] = Field(
        ...,
        description="基于原始查询生成的扩展查询列表，每个查询从不同角度切入（最多3个）",
    )
    reasoning: str = Field(
        ...,
        description="为什么需要这些扩展查询（不超过50字）",
    )


# ------------------------------------------------------------------
# Self-RAG 查询引擎
# ------------------------------------------------------------------

class SelfRAGQueryEngine:
    """Self-RAG 查询引擎

    在 HybridRetriever 的基础上增加 LLM 自验证和查询扩展能力。

    使用方式：
        engine = SelfRAGQueryEngine()
        results = await engine.query("开源项目安全评估标准")

    Args:
        hybrid_retriever: 混合检索器实例
        enable_web_fallback: 是否启用 Web 搜索 fallback（需配置 SERPER_API_KEY）
    """

    def __init__(
        self,
        hybrid_retriever: HybridRetriever | None = None,
        enable_web_fallback: bool = True,
    ) -> None:
        if hybrid_retriever is None:
            hybrid_retriever = HybridRetriever(
                vector_store=VectorStore(collection_name="osscout_kb"),
            )
        self.retriever = hybrid_retriever

        # LLM Provider（用于自验证和查询扩展）
        self._llm = get_llm_provider()

        # Web 搜索客户端（可选）
        self._web_search: WebSearchClient | None = None
        if enable_web_fallback:
            try:
                self._web_search = WebSearchClient()
                logger.info("Self-RAG 已启用 Web 搜索 fallback")
            except Exception as e:
                logger.warning("Web 搜索客户端初始化失败", error=str(e))

    async def query(
        self,
        query_text: str,
        category: str | None = None,
        n_results: int = 5,
    ) -> dict:
        """Self-RAG 检索：带自验证和 fallback 的完整检索流程

        Args:
            query_text: 查询文本
            category: 限制检索范围
            n_results: 返回结果数

        Returns:
            {
                "results": [...],           # 检索结果列表
                "validation": {...},        # 验证结果
                "source": "kb" | "web",     # 数据来源
                "expanded_queries": [...],  # 使用的扩展查询（如有）
                "confidence": float,        # 整体置信度
                "citations": [...],         # 引用来源列表
            }
        """
        logger.info("Self-RAG 检索开始", query=query_text[:80], category=category)

        # Step 1: 初始检索
        initial_results = self.retriever.search(
            query_text=query_text,
            n_results=n_results,
            category=category,
        )

        if not initial_results:
            logger.info("初始检索无结果，尝试 Web fallback")
            return await self._fallback_to_web(query_text, n_results)

        # Step 2: LLM 自验证
        validation = await self._validate_retrieval(query_text, initial_results)

        if validation.is_relevant and validation.confidence >= RELEVANCE_CONFIDENCE_THRESHOLD:
            logger.info(
                "Self-RAG 验证通过",
                query=query_text[:80],
                confidence=validation.confidence,
            )
            collector = CitationCollector()
            collector.add_from_kb(initial_results)
            return {
                "results": initial_results,
                "validation": validation.model_dump(),
                "source": "kb",
                "expanded_queries": [],
                "confidence": validation.confidence,
                "citations": collector.to_dict_list(),
            }

        # Step 3: 查询扩展 + 重新检索
        if validation.suggested_queries:
            expanded_results = await self._expand_and_reretrieve(
                original_query=query_text,
                suggested_queries=validation.suggested_queries,
                category=category,
                n_results=n_results,
            )

            if expanded_results:
                # 合并原始结果和扩展结果，去重
                merged = self._merge_results(initial_results, expanded_results)

                # 对合并结果再次验证
                revalidation = await self._validate_retrieval(query_text, merged)

                if revalidation.is_relevant and revalidation.confidence >= RELEVANCE_CONFIDENCE_THRESHOLD:
                    logger.info(
                        "Self-RAG 扩展查询后验证通过",
                        query=query_text[:80],
                        confidence=revalidation.confidence,
                    )
                    collector = CitationCollector()
                    collector.add_from_kb(merged[:n_results])
                    return {
                        "results": merged[:n_results],
                        "validation": revalidation.model_dump(),
                        "source": "kb",
                        "expanded_queries": validation.suggested_queries,
                        "confidence": revalidation.confidence,
                        "citations": collector.to_dict_list(),
                    }

        # Step 4: Web 搜索 fallback
        logger.info("Self-RAG 本地知识库验证不通过，尝试 Web fallback", query=query_text[:80])
        return await self._fallback_to_web(query_text, n_results, validation.model_dump())

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _validate_retrieval(
        self,
        query: str,
        results: list[dict],
    ) -> RetrievalValidationResult:
        """LLM 自验证：判断检索结果是否真正回答了查询"""

        # 构造验证提示
        docs_text = "\n\n".join(
            f"【文档 {i+1}】\n来源: {r['metadata'].get('topic', '未知')}\n内容: {r['content'][:1200]}"
            for i, r in enumerate(results[:3])  # 最多验证前3个，每个 1200 字
        )

        prompt = (
            f"用户查询：{query}\n\n"
            f"检索到的文档（共 {len(results)} 篇，展示前 {min(len(results), 5)} 篇）：\n"
            f"{docs_text}\n\n"
            f"请评估这些检索结果是否包含足够且准确的信息来回答用户的查询。"
        )

        messages = [
            LLMMessage(
                role="system",
                content=(
                    "你是一位检索质量评估专家。你的任务是判断给定的检索结果"
                    "是否真正回答了用户的查询。要客观、严格——"
                    "如果只是表面相关但实际没有提供实质性信息，请判断为不相关。"
                ),
            ),
            LLMMessage(role="user", content=prompt),
        ]

        try:
            result = await self._llm.chat_structured(
                messages=messages,
                output_schema=RetrievalValidationResult,
                temperature=0.3,
                max_tokens=800,
            )
            logger.info(
                "Self-RAG 验证完成",
                query=query[:80],
                is_relevant=result.is_relevant,
                confidence=result.confidence,
            )
            return result
        except Exception as e:
            logger.warning("Self-RAG 验证失败，默认通过", query=query[:80], error=str(e))
            # 验证失败时保守处理：默认通过，但给低置信度
            return RetrievalValidationResult(
                is_relevant=True,
                confidence=0.5,
                missing_info="验证过程出错",
                suggested_queries=[],
                reasoning=f"验证调用失败: {e}",
            )

    async def _expand_and_reretrieve(
        self,
        original_query: str,
        suggested_queries: list[str],
        category: str | None,
        n_results: int,
    ) -> list[dict] | None:
        """用建议的扩展查询重新检索，合并结果"""
        all_results: list[dict] = []

        for sq in suggested_queries[:MAX_EXPANDED_QUERIES]:
            logger.info("Self-RAG 执行扩展查询", original=original_query[:80], expanded=sq[:80])
            results = self.retriever.search(
                query_text=sq,
                n_results=n_results,
                category=category,
            )
            all_results.extend(results)

        if not all_results:
            return None

        # 去重：按 ID 去重，保留第一个出现的结果
        seen_ids: set[str] = set()
        unique: list[dict] = []
        for r in all_results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                unique.append(r)

        return unique

    async def _fallback_to_web(
        self,
        query: str,
        n_results: int,
        previous_validation: dict | None = None,
    ) -> dict:
        """Web 搜索 fallback"""
        if self._web_search is None:
            logger.warning("Web 搜索未启用，返回空结果", query=query[:80])
            return {
                "results": [],
                "validation": previous_validation or {},
                "source": "none",
                "expanded_queries": [],
                "confidence": 0.0,
                "citations": [],
            }

        try:
            web_results = self._web_search.search(query, num_results=n_results)
            logger.info(
                "Web 搜索 fallback 完成",
                query=query[:80],
                results=len(web_results),
            )
            collector = CitationCollector()
            collector.add_from_web(web_results)
            return {
                "results": web_results,
                "validation": {
                    "is_relevant": len(web_results) > 0,
                    "confidence": 0.6 if web_results else 0.0,
                    "reasoning": "信息来自 Web 搜索引擎",
                },
                "source": "web",
                "expanded_queries": [],
                "confidence": 0.6 if web_results else 0.0,
                "citations": collector.to_dict_list(),
            }
        except Exception as e:
            logger.error("Web 搜索 fallback 失败", query=query[:80], error=str(e))
            return {
                "results": [],
                "validation": previous_validation or {},
                "source": "none",
                "expanded_queries": [],
                "confidence": 0.0,
                "citations": [],
            }

    @staticmethod
    def _merge_results(
        original: list[dict],
        expanded: list[dict],
    ) -> list[dict]:
        """合并原始检索结果和扩展查询结果，去重"""
        seen: set[str] = set()
        merged: list[dict] = []

        for r in original + expanded:
            if r["id"] not in seen:
                seen.add(r["id"])
                merged.append(r)

        return merged
