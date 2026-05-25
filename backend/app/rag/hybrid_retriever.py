"""混合检索器：向量检索 + BM25 关键词检索 + RRF 融合

Phase 4.4 核心实现。将两种互补的检索方式结合，
向量检索负责语义相似度，BM25 负责精确关键词匹配，
RRF 负责公平融合两路结果。

使用方式：
    retriever = HybridRetriever(vector_store)
    results = retriever.search("开源项目安全评估标准", n_results=5)
"""

import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.core.logger import get_logger

from .reranker import CrossEncoderReranker
from .vector_store import VectorStore

logger = get_logger(__name__)

# RRF 融合常数 k，论文推荐值 60
# k 越大，高排名文档之间的分数差距越小，越鼓励多样性
RRF_K = 60

# 每路检索的召回数量（融合前取 TOP-N，融合后输出更少）
DEFAULT_VECTOR_TOP_K = 20
DEFAULT_BM25_TOP_K = 20


# ------------------------------------------------------------------
# 分词器
# ------------------------------------------------------------------

_TOKEN_REGEX = re.compile(r"[a-zA-Z]+|\d+|[一-鿿]+")


def _tokenize(text: str) -> list[str]:
    """轻量分词器

    策略：
    - 英文单词序列作为一个 token（转小写）
    - 数字序列作为一个 token
    - 中文字符串作为一个 token（按连续块，不按单字）

    例如：
        "Bus Factor = 1 的代价" → ['bus', 'factor', '1', '的', '代价']
        "CVE-2021-44228 漏洞" → ['cve', '2021', '44228', '漏洞']
    """
    return _TOKEN_REGEX.findall(text.lower())


# ------------------------------------------------------------------
# BM25 索引
# ------------------------------------------------------------------

class BM25Index:
    """基于 rank-bm25 的本地倒排索引

    从 ChromaDB 中读取所有文档，构建 BM25 索引并保存在内存中。
    适合文档量不大（<10k）的场景，查询延迟 <100ms。

    Args:
        vector_store: ChromaDB 向量库实例，用于获取文档数据
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store
        self._ids: list[str] = []
        self._contents: list[str] = []
        self._metadatas: list[dict] = []
        self._bm25: BM25Okapi | None = None

        self._build_index()

    def _build_index(self) -> None:
        """从 ChromaDB 读取所有文档，构建 BM25 索引"""
        logger.info("正在构建 BM25 索引...")

        # 获取集合中的所有文档
        count = self.vector_store.get_document_count()
        if count == 0:
            logger.warning("向量库为空，BM25 索引未构建")
            return

        # ChromaDB 没有直接获取所有文档的接口，用 peek 只能取前几条
        # 需要用 get() 获取全部
        collection = self.vector_store._collection
        results = collection.get(include=["documents", "metadatas"])

        self._ids = results["ids"]
        self._contents = results["documents"]
        self._metadatas = results["metadatas"] if results["metadatas"] else [{}] * len(self._ids)

        # 对所有文档分词
        tokenized_corpus = [_tokenize(doc) for doc in self._contents]

        # 构建 BM25 索引
        self._bm25 = BM25Okapi(tokenized_corpus)

        logger.info(
            "BM25 索引构建完成",
            doc_count=len(self._ids),
            avg_tokens=sum(len(t) for t in tokenized_corpus) / max(len(tokenized_corpus), 1),
        )

    def search(
        self,
        query: str,
        n_results: int = DEFAULT_BM25_TOP_K,
        category: str | None = None,
    ) -> list[dict]:
        """BM25 关键词检索

        Args:
            query: 查询文本
            n_results: 返回结果数
            category: 按 category 元数据过滤

        Returns:
            检索结果列表，格式与 VectorStore.search() 一致
        """
        if self._bm25 is None:
            return []

        # 查询分词
        tokenized_query = _tokenize(query)
        if not tokenized_query:
            return []

        # 计算所有文档的 BM25 分数
        scores = self._bm25.get_scores(tokenized_query)

        # 按分数降序排序，取 TOP-N
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results: list[dict] = []
        for idx, score in indexed_scores:
            metadata = self._metadatas[idx]

            # category 过滤
            if category and metadata.get("category") != category:
                continue

            results.append({
                "id": self._ids[idx],
                "content": self._contents[idx],
                "metadata": metadata,
                "distance": -score,  # BM25 分数越高越好，转为负值统一为"越小越好"
            })

            if len(results) >= n_results:
                break

        return results

    def refresh(self) -> None:
        """重新从向量库构建索引（文档更新后调用）"""
        self._build_index()


# ------------------------------------------------------------------
# 混合检索器
# ------------------------------------------------------------------

class HybridRetriever:
    """混合检索器：向量检索 + BM25 + RRF 融合

    同时发起语义检索和关键词检索，用 RRF 算法融合结果排序。

    RRF 公式（Reciprocal Rank Fusion）：
        RRF_score(d) = Σ 1 / (k + rank_i(d))
    其中 rank_i(d) 是文档 d 在第 i 路检索中的排名，k 为常数（默认 60）。

    特点：
    - 不依赖各路检索的具体分数（向量余弦距离和 BM25 分数量纲不同）
    - 只依赖排名位置，天然公平
    - 无参数（k 为固定常数），无需调参
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        bm25_index: BM25Index | None = None,
        rrf_k: int = RRF_K,
        reranker: CrossEncoderReranker | None = None,
        enable_rerank: bool = True,
    ) -> None:
        """初始化混合检索器

        Args:
            vector_store: 向量库实例，None 时自动创建
            bm25_index: BM25 索引实例，None 时自动从 vector_store 构建
            rrf_k: RRF 融合常数
            reranker: 重排序器实例，None 时根据 enable_rerank 自动创建
            enable_rerank: 是否启用重排序（Phase 4.5）
        """
        if vector_store is None:
            vector_store = VectorStore(collection_name="osscout_kb")
        self.vector_store = vector_store

        if bm25_index is None:
            bm25_index = BM25Index(vector_store)
        self.bm25_index = bm25_index

        self.rrf_k = rrf_k

        # Phase 4.5：重排序器
        self._reranker = reranker
        self._enable_rerank = enable_rerank
        if enable_rerank and reranker is None:
            try:
                self._reranker = CrossEncoderReranker()
                logger.info("混合检索器已启用交叉编码器重排序")
            except Exception as e:
                logger.warning("重排序器初始化失败，回退到无重排序模式", error=str(e))
                self._reranker = None

        logger.info(
            "混合检索器初始化完成",
            rrf_k=rrf_k,
            vector_docs=vector_store.get_document_count(),
            rerank_enabled=self._reranker is not None,
        )

    def search(
        self,
        query_text: str,
        n_results: int = 10,
        category: str | None = None,
        vector_top_k: int = DEFAULT_VECTOR_TOP_K,
        bm25_top_k: int = DEFAULT_BM25_TOP_K,
    ) -> list[dict]:
        """混合检索：向量 + BM25，RRF 融合

        Args:
            query_text: 查询文本
            n_results: 返回结果数
            category: 按 category 过滤
            vector_top_k: 向量检索召回数量
            bm25_top_k: BM25 检索召回数量

        Returns:
            融合后的检索结果，按 RRF 分数降序排列
        """
        logger.info(
            "执行混合检索",
            query=query_text[:80],
            category=category,
            vector_k=vector_top_k,
            bm25_k=bm25_top_k,
        )

        # 1. 向量检索
        vector_results = self.vector_store.search(
            query_text=query_text,
            n_results=vector_top_k,
            filter_dict={"category": category} if category else None,
        )

        # 2. BM25 检索
        bm25_results = self.bm25_index.search(
            query=query_text,
            n_results=bm25_top_k,
            category=category,
        )

        # 3. RRF 融合
        fused = self._rrf_fuse(vector_results, bm25_results)

        # 4. Phase 4.5：交叉编码器重排序
        if self._reranker is not None and len(fused) > 0:
            # 重排序候选数：至少 n_results 个，最多 20 个
            rerank_candidates = fused[:max(n_results, 20)]
            final_results = self._reranker.rerank(
                query=query_text,
                candidates=rerank_candidates,
                top_k=n_results,
            )
            logger.info(
                "混合检索完成（含重排序）",
                query=query_text[:80],
                vector_hits=len(vector_results),
                bm25_hits=len(bm25_results),
                fused_hits=len(fused),
                returned=len(final_results),
            )
        else:
            # 无重排序，直接取 TOP-n_results
            final_results = fused[:n_results]
            logger.info(
                "混合检索完成（无重排序）",
                query=query_text[:80],
                vector_hits=len(vector_results),
                bm25_hits=len(bm25_results),
                fused_hits=len(fused),
                returned=len(final_results),
            )

        return final_results

    def _rrf_fuse(
        self,
        vector_results: list[dict],
        bm25_results: list[dict],
    ) -> list[dict]:
        """RRF 融合两路检索结果

        对每篇文档，计算其在各路检索中的 RRF 分数并求和，
        按总分降序排列返回。
        """
        # 文档 ID -> {score, result}
        doc_scores: dict[str, dict] = {}

        # 向量检索结果（排名从 1 开始）
        for rank, result in enumerate(vector_results, start=1):
            doc_id = result["id"]
            rrf_score = 1.0 / (self.rrf_k + rank)

            if doc_id in doc_scores:
                doc_scores[doc_id]["rrf_score"] += rrf_score
            else:
                doc_scores[doc_id] = {
                    "rrf_score": rrf_score,
                    "result": result,
                }

        # BM25 检索结果
        for rank, result in enumerate(bm25_results, start=1):
            doc_id = result["id"]
            rrf_score = 1.0 / (self.rrf_k + rank)

            if doc_id in doc_scores:
                doc_scores[doc_id]["rrf_score"] += rrf_score
            else:
                doc_scores[doc_id] = {
                    "rrf_score": rrf_score,
                    "result": result,
                }

        # 按 RRF 分数降序排列
        sorted_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1]["rrf_score"],
            reverse=True,
        )

        # 组装最终输出（添加 rrf_score 到结果中）
        fused: list[dict] = []
        for doc_id, info in sorted_docs:
            result = dict(info["result"])
            result["rrf_score"] = round(info["rrf_score"], 4)
            fused.append(result)

        return fused

    def search_with_details(
        self,
        query_text: str,
        n_results: int = 10,
        category: str | None = None,
    ) -> dict:
        """带详细信息的混合检索（调试/分析用）

        Returns:
            {
                "vector_results": [...],
                "bm25_results": [...],
                "fused_results": [...],
            }
        """
        vector_results = self.vector_store.search(
            query_text=query_text,
            n_results=DEFAULT_VECTOR_TOP_K,
            filter_dict={"category": category} if category else None,
        )

        bm25_results = self.bm25_index.search(
            query=query_text,
            n_results=DEFAULT_BM25_TOP_K,
            category=category,
        )

        fused = self._rrf_fuse(vector_results, bm25_results)[:n_results]

        return {
            "vector_results": vector_results[:n_results],
            "bm25_results": bm25_results[:n_results],
            "fused_results": fused,
        }
