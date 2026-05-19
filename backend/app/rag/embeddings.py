"""Embedding 模型封装

使用 sentence-transformers 的 all-MiniLM-L6-v2 模型，
将文本转为 384 维稠密向量，供 ChromaDB 存储和检索使用。

该模型特点：
- 轻量（约 80MB），本地推理无 API 成本
- 支持多语言（包含中文）
- 批量编码效率远高于逐条编码
"""

import numpy as np
from sentence_transformers import SentenceTransformer

from app.core.logger import get_logger

logger = get_logger(__name__)

# 默认使用的 Embedding 模型名称
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingModel:
    """Embedding 模型封装类

    封装 sentence-transformers 的加载和编码逻辑，
    提供统一的文本向量化接口。
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """初始化 Embedding 模型

        Args:
            model_name: HuggingFace 模型名称，默认 all-MiniLM-L6-v2
        """
        self.model_name = model_name
        logger.info("正在加载 Embedding 模型...", model=model_name)
        # 首次加载会自动下载模型文件到本地缓存（~/.cache/torch/sentence_transformers/）
        self._model = SentenceTransformer(model_name)
        self._embedding_dim = self._model.get_embedding_dimension()
        logger.info(
            "Embedding 模型加载完成",
            model=model_name,
            dimension=self._embedding_dim,
        )

    @property
    def embedding_dim(self) -> int:
        """返回向量维度数（all-MiniLM-L6-v2 为 384）"""
        return self._embedding_dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        """批量将文本编码为向量

        Args:
            texts: 待编码的文本列表

        Returns:
            向量列表，每个向量是 float 列表，长度为 embedding_dim
        """
        if not texts:
            return []

        # normalize_embeddings=True 使向量模长为 1，便于用余弦相似度计算
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        # 将 numpy array 转为 Python list，便于 JSON 序列化
        return embeddings.tolist()

    def encode_query(self, text: str) -> list[float]:
        """将单条查询文本编码为向量

        Args:
            text: 查询文本

        Returns:
            向量（float 列表）
        """
        embeddings = self.encode([text])
        return embeddings[0]

    def compute_similarity(
        self, embedding_a: list[float], embedding_b: list[float]
    ) -> float:
        """计算两个向量的余弦相似度

        由于使用了 normalize_embeddings=True，余弦相似度等价于点积。

        Args:
            embedding_a: 向量 A
            embedding_b: 向量 B

        Returns:
            相似度分数，范围 [-1, 1]，通常 >0.5 认为语义相关
        """
        a = np.array(embedding_a)
        b = np.array(embedding_b)
        return float(np.dot(a, b))
