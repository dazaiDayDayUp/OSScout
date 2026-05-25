"""知识库初始化脚本（分块版）

遍历 knowledge-base/ 目录下的所有 Markdown 文档，
使用语义分块策略拆分后计算 Embedding，写入 ChromaDB 向量库。

执行方式：
    cd backend && ../venv/Scripts/python.exe ../scripts/init_kb.py

或：
    cd scripts && ../backend/venv/Scripts/python.exe init_kb.py
"""

import sys
from pathlib import Path

# 将 backend 加入 Python 路径，以便导入 app.rag 模块
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag import MarkdownChunker, VectorStore  # noqa: E402


# 知识库根目录
KB_DIR = Path(__file__).resolve().parent.parent / "knowledge-base"

# 分类映射：目录名 -> category 标签
CATEGORY_MAP = {
    "methodology": "methodology",
    "case-studies": "case-study",
    "competitors": "competitor",
    "benchmarks": "benchmark",
    "governance": "governance",
    "security": "security",
}

# 分块参数
CHUNKER_CONFIG = {
    "target_chars": 1600,   # 目标 chunk 大小 ≈ 400 tokens
    "min_chars": 800,       # 最小 chunk 大小 ≈ 200 tokens
    "max_chars": 3200,      # 最大 chunk 大小 ≈ 800 tokens
    "overlap_ratio": 0.2,   # 20% 重叠窗口
}


def discover_and_chunk_documents(chunker: MarkdownChunker) -> tuple[list[str], list[str], list[dict]]:
    """扫描知识库目录，对所有 Markdown 文档进行语义分块

    Returns:
        (documents, ids, metadatas) — 可直接传入 VectorStore.add_documents()
    """
    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict] = []

    # 统计信息
    stats = {
        "total_files": 0,
        "total_chunks": 0,
        "files_by_category": {},
        "chunks_by_category": {},
    }

    for category_dir in sorted(KB_DIR.iterdir()):
        if not category_dir.is_dir():
            continue

        category = CATEGORY_MAP.get(category_dir.name, category_dir.name)
        stats["files_by_category"][category] = 0
        stats["chunks_by_category"][category] = 0

        # 递归遍历子目录中的 .md 文件
        for md_file in sorted(category_dir.rglob("*.md")):
            stats["total_files"] += 1
            stats["files_by_category"][category] += 1

            # 语义分块
            chunks = chunker.chunk_file(md_file, category=category)

            for chunk in chunks:
                documents.append(chunk.content)
                ids.append(chunk.chunk_id)
                metadatas.append({
                    "category": chunk.category,
                    "topic": chunk.topic,
                    "source_file": chunk.source_file,
                    "section_title": chunk.section_title,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                })

            stats["total_chunks"] += len(chunks)
            stats["chunks_by_category"][category] += len(chunks)

    # 打印统计
    print(f"\n      扫描完成：{stats['total_files']} 个文件 → {stats['total_chunks']} 个 chunk")
    for cat, file_count in sorted(stats["files_by_category"].items()):
        chunk_count = stats["chunks_by_category"][cat]
        avg = chunk_count / file_count if file_count > 0 else 0
        print(f"      - {cat}: {file_count} 文件 → {chunk_count} chunk (平均 {avg:.1f} 个/文件)")

    return documents, ids, metadatas


def main() -> None:
    """主函数：分块扫描文档并写入向量库"""
    print("=" * 60)
    print("OSScout 知识库初始化（分块版）")
    print("=" * 60)

    # 1. 初始化分块器
    print("\n[1/4] 初始化 Markdown 分块器...")
    chunker = MarkdownChunker(**CHUNKER_CONFIG)
    print(f"      目标大小: {CHUNKER_CONFIG['target_chars']} 字符")
    print(f"      大小范围: {CHUNKER_CONFIG['min_chars']} ~ {CHUNKER_CONFIG['max_chars']} 字符")
    print(f"      重叠比例: {CHUNKER_CONFIG['overlap_ratio'] * 100:.0f}%")

    # 2. 扫描并分块
    print("\n[2/4] 扫描知识库文档并分块...")
    documents, ids, metadatas = discover_and_chunk_documents(chunker)

    if not documents:
        print("      未找到任何文档，请检查 knowledge-base/ 目录")
        return

    # 3. 初始化向量库
    print("\n[3/4] 初始化 ChromaDB 向量库...")
    store = VectorStore(
        collection_name="osscout_kb",
        persist_dir=str(KB_DIR.parent / "chroma_db"),
    )

    # 清空已有数据（重新初始化）
    existing_count = store.get_document_count()
    if existing_count > 0:
        print(f"      检测到已有 {existing_count} 条数据，将清空后重新入库")
        store._client.delete_collection("osscout_kb")
        store._collection = store._client.create_collection(
            name="osscout_kb",
            metadata={"hnsw:space": "cosine"},
        )

    # 4. 批量入库
    print("\n[4/4] 计算 Embedding 并入库...")
    print(f"      共 {len(documents)} 个 chunk，开始计算...")
    store.add_documents(
        documents=documents,
        ids=ids,
        metadatas=metadatas,
    )

    # 5. 验证
    final_count = store.get_document_count()
    print(f"\n      入库完成！向量库中共有 {final_count} 条 chunk")

    # 6. 快速测试检索
    print("\n[验证] 执行示例检索...")
    test_queries = [
        ("Bus Factor 低的风险是什么", "case-study"),
        ("开源项目安全评估标准", "methodology"),
        ("React 和 Vue 哪个更好", "competitor"),
        ("PR 合并率多少算健康", "benchmark"),
    ]

    for query_text, category in test_queries:
        results = store.search(
            query_text=query_text,
            n_results=3,
            filter_dict={"category": category} if category else None,
        )
        print(f"\n    查询: \"{query_text}\"")
        for r in results:
            topic = r["metadata"].get("topic", "未知")
            section = r["metadata"].get("section_title", "")
            idx = r["metadata"].get("chunk_index", 0)
            total = r["metadata"].get("total_chunks", 1)
            dist = r["distance"]
            section_info = f" | 章节: {section}" if section else ""
            print(f"      → {topic}#{idx}/{total}{section_info} (distance={dist:.3f})")

    print("\n" + "=" * 60)
    print("知识库初始化完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
