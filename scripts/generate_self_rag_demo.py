"""生成 Self-RAG 完整流程演示文档"""

import sys
import asyncio

sys.path.insert(0, "D:/PythonProjects/OSScout/backend")

from app.rag import HybridRetriever, VectorStore, SelfRAGQueryEngine
from app.llm import LLMMessage
from app.rag.self_rag import RetrievalValidationResult

# 初始化
store = VectorStore(collection_name="osscout_kb")
retriever = HybridRetriever(vector_store=store, enable_rerank=False)
engine = SelfRAGQueryEngine(hybrid_retriever=retriever, enable_web_fallback=True)
llm = engine._llm

doc_lines = []


def log(title, content=""):
    doc_lines.append(f"## {title}")
    if content:
        doc_lines.append(f"\n{content}\n")


def code_block(text, lang=""):
    doc_lines.append(f"\n```{lang}")
    doc_lines.append(text)
    doc_lines.append("```\n")


# 文档头部
doc_lines.append("# Self-RAG 完整流程演示")
doc_lines.append("")
doc_lines.append("> 本文档展示 Self-RAG 每个阶段的输入、输出和决策过程。")
doc_lines.append("> 生成时间：2026-05-25")
doc_lines.append("> 知识库规模：167 文件 / 810 chunk")
doc_lines.append("")

# 测试用例
queries = [
    ("Bus Factor 低的风险", "知识库中有丰富案例，预期验证通过"),
    ("开源项目代码审查标准", "知识库中有 OpenSSF 方法论，预期验证通过"),
    ("2024 年开源项目供应链攻击事件", "知识库中无 2024 年信息，预期触发 Web fallback"),
]


async def run_validation(query, results):
    """执行 LLM 自验证"""
    docs_text = "\n\n".join(
        f"【文档 {i+1}】\n来源: {r['metadata'].get('topic', '未知')}\n内容: {r['content'][:1200]}"
        for i, r in enumerate(results[:3])
    )

    prompt = (
        f"用户查询：{query}\n\n"
        f"检索到的文档（共 {len(results)} 篇，展示前 {min(len(results), 3)} 篇）：\n"
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

    return await llm.chat_structured(
        messages=messages,
        output_schema=RetrievalValidationResult,
        temperature=0.3,
        max_tokens=800,
    )


async def main():
    for idx, (query, expectation) in enumerate(queries, 1):
        doc_lines.append("---")
        doc_lines.append("")
        doc_lines.append(f"# 测试 {idx}：{query}")
        doc_lines.append(f"\n**预期**：{expectation}")
        doc_lines.append("")

        # 阶段 1：混合检索
        doc_lines.append("## 阶段 1：混合检索（召回）")
        doc_lines.append("")
        doc_lines.append("**输入**：")
        doc_lines.append(f"- 查询文本：`{query}`")
        doc_lines.append("- 召回策略：向量检索 TOP-20 + BM25 TOP-20，RRF 融合")
        doc_lines.append("")

        results = engine.retriever.search(query, n_results=5)
        doc_lines.append(f"**输出**：召回 {len(results)} 条结果")
        doc_lines.append("")
        for i, r in enumerate(results, 1):
            topic = r["metadata"].get("topic", "未知")
            cat = r["metadata"].get("category", "")
            dist = r["distance"]
            rrf = r.get("rrf_score", 0)
            content_preview = r["content"][:200].replace("\n", " ")
            doc_lines.append(f"### 结果 {i}")
            doc_lines.append(f"- ID：`{r['id']}`")
            doc_lines.append(f"- 来源分类：`{cat}`")
            doc_lines.append(f"- 主题：`{topic}`")
            doc_lines.append(f"- RRF 分数：`{rrf}`")
            doc_lines.append(f"- 距离：`{dist:.3f}`")
            doc_lines.append(f"- 内容预览：`{content_preview}...`")
            doc_lines.append("")

        # 阶段 2：LLM 自验证
        doc_lines.append("## 阶段 2：LLM 自验证")
        doc_lines.append("")

        docs_text = "\n\n".join(
            f"【文档 {i+1}】\n来源: {r['metadata'].get('topic', '未知')}\n内容: {r['content'][:1200]}"
            for i, r in enumerate(results[:3])
        )

        prompt = (
            f"用户查询：{query}\n\n"
            f"检索到的文档（共 {len(results)} 篇，展示前 {min(len(results), 3)} 篇）：\n"
            f"{docs_text}\n\n"
            f"请评估这些检索结果是否包含足够且准确的信息来回答用户的查询。"
        )

        doc_lines.append("**输入（给 LLM 的 Prompt）**：")
        code_block(prompt, "text")

        try:
            val = await run_validation(query, results)

            doc_lines.append("**输出（LLM 判断结果）**：")
            doc_lines.append(f"- is_relevant：`{val.is_relevant}`")
            doc_lines.append(f"- confidence：`{val.confidence}`")
            doc_lines.append(f"- missing_info：`{val.missing_info}`")
            doc_lines.append(f"- suggested_queries：`{val.suggested_queries}`")
            doc_lines.append(f"- reasoning：`{val.reasoning}`")
            doc_lines.append("")

            if val.is_relevant and val.confidence >= 0.7:
                doc_lines.append("**决策**：验证通过，直接返回检索结果。")
                doc_lines.append("")
                doc_lines.append("## 最终结果")
                doc_lines.append("")
                doc_lines.append(f"- 来源：`kb`")
                doc_lines.append(f"- 结果数：{len(results)}")
                doc_lines.append(f"- 置信度：{val.confidence}")
                doc_lines.append("")
                continue

            # 阶段 3：查询扩展
            doc_lines.append("**决策**：验证不通过，进入查询扩展阶段。")
            doc_lines.append("")
            doc_lines.append("## 阶段 3：查询扩展")
            doc_lines.append("")
            doc_lines.append("**输入**：基于 LLM 建议的扩展查询")
            doc_lines.append("")

            expanded_results = []
            for j, sq in enumerate(val.suggested_queries[:3], 1):
                doc_lines.append(f"**扩展查询 {j}**：`{sq}`")
                er = engine.retriever.search(sq, n_results=3)
                doc_lines.append(f"- 召回 {len(er)} 条结果")
                for k, r in enumerate(er[:2], 1):
                    topic = r["metadata"].get("topic", "")
                    doc_lines.append(f"  - {topic}")
                doc_lines.append("")
                expanded_results.extend(er)

            # 去重合并
            seen = set()
            merged = []
            for r in results + expanded_results:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    merged.append(r)

            # 阶段 4：再次验证
            doc_lines.append("## 阶段 4：再次验证（合并后）")
            doc_lines.append("")

            val2 = await run_validation(query, merged)

            doc_lines.append("**输出（LLM 再次判断）**：")
            doc_lines.append(f"- is_relevant：`{val2.is_relevant}`")
            doc_lines.append(f"- confidence：`{val2.confidence}`")
            doc_lines.append(f"- reasoning：`{val2.reasoning}`")
            doc_lines.append("")

            if val2.is_relevant and val2.confidence >= 0.7:
                doc_lines.append("**决策**：扩展查询后验证通过，返回合并结果。")
                doc_lines.append("")
                doc_lines.append("## 最终结果")
                doc_lines.append("")
                doc_lines.append(f"- 来源：`kb`")
                doc_lines.append(f"- 结果数：{len(merged)}")
                doc_lines.append(f"- 置信度：{val2.confidence}")
                doc_lines.append(f"- 使用的扩展查询：{val.suggested_queries}")
                doc_lines.append("")
                continue

            # 阶段 5：Web fallback
            doc_lines.append("**决策**：本地知识库验证仍不通过，触发 Web 搜索 fallback。")
            doc_lines.append("")
            doc_lines.append("## 阶段 5：Web 搜索 Fallback")
            doc_lines.append("")
            doc_lines.append(f"**输入**：查询文本 `{query}`")
            doc_lines.append("")

            if engine._web_search:
                web_results = engine._web_search.search(query, num_results=3)
                doc_lines.append(f"**输出**：Web 搜索返回 {len(web_results)} 条结果")
                doc_lines.append("")
                for i, r in enumerate(web_results, 1):
                    title = r["metadata"].get("title", "")
                    link = r["metadata"].get("link", "")
                    content = r["content"][:200].replace("\n", " ")
                    doc_lines.append(f"### Web 结果 {i}")
                    doc_lines.append(f"- 标题：`{title}`")
                    doc_lines.append(f"- 链接：`{link}`")
                    doc_lines.append(f"- 内容：`{content}...`")
                    doc_lines.append("")

                doc_lines.append("## 最终结果")
                doc_lines.append("")
                doc_lines.append("- 来源：`web`")
                doc_lines.append(f"- 结果数：{len(web_results)}")
                doc_lines.append("- 置信度：0.6")
                doc_lines.append("")
            else:
                doc_lines.append("**输出**：Web 搜索未启用，返回空结果。")
                doc_lines.append("")

        except Exception as e:
            doc_lines.append(f"**错误**：{type(e).__name__}: {str(e)[:200]}")
            doc_lines.append("")

    # 保存文档
    content = "\n".join(doc_lines)
    output_path = "D:/PythonProjects/OSScout/SELF_RAG_DEMO.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"文档已生成：{output_path}")
    print(f"总行数：{len(doc_lines)}")


if __name__ == "__main__":
    asyncio.run(main())
