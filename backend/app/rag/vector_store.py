"""ChromaDB 向量库封装

使用 ChromaDB 的 PersistentClient 模式（嵌入式），
无需单独启动服务，数据持久化到本地目录。

ChromaDB 核心概念：
- Client: 数据库连接入口
- Collection: 类似 SQL 的"表"，存储一组文档及其向量
- Document: 文本内容
- Embedding: 文本的向量表示
- Metadata: 每条文档的元数据字典，可用于过滤检索
"""

from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.logger import get_logger

from .embeddings import EmbeddingModel

logger = get_logger(__name__)

# 默认持久化目录：项目根目录下的 chroma_db/
DEFAULT_PERSIST_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "chroma_db")


class VectorStore:
    """ChromaDB 向量库封装

    提供文档的增删查改和语义检索功能，
    内部自动调用 Embedding 模型进行文本编码。
    """

    def __init__(
        self,
        collection_name: str,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        embedding_model: EmbeddingModel | None = None,
    ) -> None:
        """初始化向量库

        Args:
            collection_name: 集合名称（类似数据库表名）
            persist_dir: 数据持久化目录，默认项目根目录/chroma_db
            embedding_model: Embedding 模型实例，None 时自动创建
        """
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        self.embedding_model = embedding_model or EmbeddingModel()

        # 创建/连接持久化客户端
        self._client = chromadb.PersistentClient(path=persist_dir)

        # 获取或创建集合（get_or_create 确保幂等）
        self._collection: Collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # 使用余弦距离作为相似度度量
        )
        logger.info(
            "向量库初始化完成",
            collection=collection_name,
            persist_dir=persist_dir,
        )

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def add_documents(
        self,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """批量添加文档到向量库

        Args:
            documents: 文本内容列表
            ids: 唯一标识列表，与 documents 一一对应
            metadatas: 元数据字典列表，用于分类和过滤检索

        Raises:
            ValueError: documents 和 ids 长度不一致
        """
        if len(documents) != len(ids):
            raise ValueError(
                f"documents ({len(documents)}) 和 ids ({len(ids)}) 长度不一致"
            )

        if not documents:
            return

        logger.info(
            "正在向向量库添加文档...",
            count=len(documents),
            collection=self.collection_name,
        )

        # 计算所有文档的 Embedding
        embeddings = self.embedding_model.encode(documents)

        self._collection.add(
            documents=documents,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas,
        )

        logger.info("文档添加完成", count=len(documents))

    def add_document(
        self,
        document: str,
        doc_id: str,
        metadata: dict | None = None,
    ) -> None:
        """添加单条文档（add_documents 的便捷包装）"""
        self.add_documents(
            documents=[document],
            ids=[doc_id],
            metadatas=[metadata] if metadata else None,
        )

    def delete_documents(self, ids: list[str]) -> None:
        """按 ID 删除文档"""
        if not ids:
            return
        self._collection.delete(ids=ids)
        logger.info("文档删除完成", count=len(ids))

    # ------------------------------------------------------------------
    # 读操作
    # ------------------------------------------------------------------

    def search(
        self,
        query_text: str,
        n_results: int = 3,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        """语义检索：查询与给定文本最相似的文档

        Args:
            query_text: 查询文本
            n_results: 返回结果数量
            filter_dict: 元数据过滤条件，如 {"category": "case-study"}

        Returns:
            检索结果列表，每个元素包含：
            - id: 文档 ID
            - content: 文档内容
            - metadata: 元数据
            - distance: 余弦距离（0=完全相同，越小越相似）
        """
        query_embedding = self.embedding_model.encode_query(query_text)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=filter_dict,
            include=["documents", "metadatas", "distances"],
        )

        # 格式化输出（ChromaDB 返回的是嵌套列表，需要扁平化）
        formatted: list[dict] = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i],
            })

        return formatted

    def get_document_count(self) -> int:
        """返回集合中文档总数"""
        return self._collection.count()

    def peek(self, limit: int = 5) -> list[dict]:
        """查看集合中的前几条文档（用于调试）"""
        results = self._collection.peek(limit=limit)
        formatted: list[dict] = []
        for i in range(len(results["ids"])):
            formatted.append({
                "id": results["ids"][i],
                "content": results["documents"][i],
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
            })
        return formatted
