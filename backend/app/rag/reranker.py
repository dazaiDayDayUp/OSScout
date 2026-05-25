"""交叉编码器重排序器

Phase 4.5 核心实现。

两阶段检索架构：
    第一阶段（召回）：HybridRetriever 用向量 + BM25 快速召回 TOP-20
    第二阶段（精排）：CrossEncoderReranker 对候选逐一精细打分，取 TOP-5

Cross-Encoder 与 Bi-Encoder（Embedding 模型）的核心区别：
- Bi-Encoder：分别编码 query 和 doc 为独立向量，然后点积算相似度
          优点是快（doc 向量可预计算），缺点是精度有限
- Cross-Encoder：将 query 和 doc 拼接输入，注意力机制直接计算词级交互
          优点是精度高（通常提升 10-20%），缺点是慢（每次都要重新编码）

因此 Cross-Encoder 只适合对小批量候选（如 TOP-20）做精排，
不能替代第一阶段的召回。
"""

import numpy as np
from sentence_transformers import CrossEncoder

from app.core.logger import get_logger

logger = get_logger(__name__)

# 默认使用的交叉编码器模型
# ms-marco-MiniLM-L-6-v2：约 80MB，推理快，精度足够用于重排序
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# 默认批处理大小（一次送入模型的 query-doc 对数）
# 20 个候选分 2 批处理，平衡速度和内存
DEFAULT_BATCH_SIZE = 16

# 重排后的返回数量
DEFAULT_RERANK_TOP_K = 5


class CrossEncoderReranker:
    """交叉编码器重排序器

    对召回阶段返回的候选文档进行精细相关性打分，
    按分数降序重新排列后返回最相关的 TOP-K。

    Args:
        model_name: HuggingFace 模型名称
        batch_size: 批处理大小
        device: 运行设备，None 时自动选择（优先 GPU）
    """

    def __init__(
        self,
        model_name: str = DEFAULT_RERANKER_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        device: str | None = None,
    ) -> None:
        """初始化交叉编码器重排序器

        首次加载会自动从 HuggingFace 下载模型文件（约 80MB）。
        下载后缓存到 ~/.cache/huggingface/hub/，后续无需联网。
        """
        self.model_name = model_name
        self.batch_size = batch_size

        logger.info("正在加载交叉编码器重排序模型...", model=model_name)
        self._model = CrossEncoder(model_name, device=device)
        logger.info(
            "重排序模型加载完成",
            model=model_name,
            max_length=self._model.max_length,
        )

    def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = DEFAULT_RERANK_TOP_K,
    ) -> list[dict]:
        """对候选文档进行重排序

        Args:
            query: 查询文本
            candidates: 候选文档列表，每个元素格式与 VectorStore.search() 一致
            top_k: 重排后返回的文档数

        Returns:
            重排后的文档列表，按相关性分数降序排列，
            每个元素附加 "rerank_score" 字段（0~1，越高越相关）
        """
        if not candidates:
            return []

        # 构造 (query, document) 对
        pairs = [(query, c["content"]) for c in candidates]

        logger.info(
            "开始重排序",
            query=query[:80],
            candidates=len(candidates),
            top_k=top_k,
        )

        # 批量推理，获取相关性分数
        # CrossEncoder 输出的是 logits，通过 sigmoid 转为 0~1 概率
        scores = self._model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        # CrossEncoder 输出的是 logits，通过 sigmoid 转为 0~1 概率
        scores = 1 / (1 + np.exp(-scores))

        # 将分数附加到候选结果上，按分数降序排列
        scored = []
        for candidate, score in zip(candidates, scores):
            item = dict(candidate)
            item["rerank_score"] = round(float(score), 4)
            scored.append(item)

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)

        logger.info(
            "重排序完成",
            query=query[:80],
            best_score=scored[0]["rerank_score"] if scored else None,
            returned=min(top_k, len(scored)),
        )

        return scored[:top_k]

    def rerank_with_details(
        self,
        query: str,
        candidates: list[dict],
    ) -> dict:
        """带详细信息的重排序（调试/分析用）

        Returns:
            {
                "before": [...],  # 重排前（按原始顺序）
                "after": [...],   # 重排后（按 rerank_score 降序）
            }
        """
        after = self.rerank(query, candidates, top_k=len(candidates))
        return {
            "before": candidates,
            "after": after,
        }
