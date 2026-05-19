"""知识库初始化脚本

遍历 knowledge-base/ 目录下的所有 Markdown 文档，
计算 Embedding 后写入 ChromaDB 向量库。

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

from app.rag import VectorStore  # noqa: E402


# 知识库根目录
KB_DIR = Path(__file__).resolve().parent.parent / "knowledge-base"

# 分类映射：目录名 -> category 标签
CATEGORY_MAP = {
    "methodology": "methodology",
    "case-studies": "case-study",
    "competitors": "competitor",
    "benchmarks": "benchmark",
}


def discover_documents() -> list[dict]:
    """扫描 knowledge-base 目录，收集所有 Markdown 文档

    Returns:
        文档列表，每个元素包含：
        - id: 唯一标识（文件相对路径）
        - content: 文档全文
        - metadata: {category, topic, source_file}
    """
    documents: list[dict] = []

    for category_dir in KB_DIR.iterdir():
        if not category_dir.is_dir():
            continue

        category = CATEGORY_MAP.get(category_dir.name, category_dir.name)

        for md_file in category_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # 从文件名提取 topic
            topic = md_file.stem.replace("-", " ")

            doc = {
                "id": f"{category_dir.name}/{md_file.name}",
                "content": content,
                "metadata": {
                    "category": category,
                    "topic": topic,
                    "source_file": str(md_file.name),
                },
            }
            documents.append(doc)

    return documents


def main() -> None:
    """主函数：扫描文档并写入向量库"""
    print("=" * 50)
    print("OSScout 知识库初始化")
    print("=" * 50)

    # 1. 扫描文档
    print("\n[1/3] 扫描知识库文档...")
    docs = discover_documents()
    print(f"      发现 {len(docs)} 个文档")

    for d in docs:
        print(f"      - {d['id']} ({len(d['content'])} 字符)")

    if not docs:
        print("      未找到任何文档，请检查 knowledge-base/ 目录")
        return

    # 2. 初始化向量库
    print("\n[2/3] 初始化 ChromaDB 向量库...")
    store = VectorStore(
        collection_name="osscout_kb",
        persist_dir=str(KB_DIR.parent / "chroma_db"),
    )

    # 清空已有数据（重新初始化）
    existing_count = store.get_document_count()
    if existing_count > 0:
        print(f"      检测到已有 {existing_count} 条数据，将清空后重新入库")
        # ChromaDB 删除 collection 后重建
        store._client.delete_collection("osscout_kb")
        store._collection = store._client.create_collection(
            name="osscout_kb",
            metadata={"hnsw:space": "cosine"},
        )

    # 3. 批量入库
    print("\n[3/3] 计算 Embedding 并入库...")
    store.add_documents(
        documents=[d["content"] for d in docs],
        ids=[d["id"] for d in docs],
        metadatas=[d["metadata"] for d in docs],
    )

    # 4. 验证
    final_count = store.get_document_count()
    print(f"\n      入库完成！向量库中共有 {final_count} 条文档")

    # 5. 快速测试检索
    print("\n[验证] 执行示例检索...")
    test_queries = [
        ("Bus Factor 低的风险是什么", "case-study"),
        ("开源项目安全评估标准", "methodology"),
        ("React 和 Vue 哪个更好", "competitor"),
    ]

    for query_text, category in test_queries:
        results = store.search(
            query_text=query_text,
            n_results=2,
            filter_dict={"category": category} if category else None,
        )
        print(f"\n    查询: \"{query_text}\"")
        for r in results:
            topic = r["metadata"].get("topic", "未知")
            dist = r["distance"]
            print(f"      → {topic} (distance={dist:.3f})")

    print("\n" + "=" * 50)
    print("知识库初始化完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
