"""引用追踪模块

Phase 4.7 核心实现。

统一追踪三类数据来源的引用：
1. 知识库（KB）：ChromaDB 向量检索结果，包含文档 ID、章节、来源文件
2. Web 搜索：Serper API fallback 结果，包含网页标题和链接
3. 行业基准（Benchmark）：OpenSSF Scorecard 等基准数据

设计原则：
- 所有检索/查询结果统一转换为 Citation 模型
- CitationCollector 负责收集、去重、排序
- 前端通过 citation.source_type 区分展示样式
"""

from pydantic import BaseModel, Field

# 内容片段最大长度（字符数）
SNIPPET_MAX_LEN = 200


class Citation(BaseModel):
    """统一引用来源模型

    描述一条结论所引用的数据来源，覆盖 KB / Web / Benchmark 三种类型。

    Attributes:
        source_type: 来源类型，"kb" | "web" | "benchmark"
        document_id: 文档唯一标识（chunk_id / web_id / benchmark_key）
        title: 文档标题（章节标题 / 网页标题 / 指标名称）
        category: 文档分类（case-study / methodology / benchmark 等）
        url: 外部链接（Web 来源时有值）
        snippet: 引用的内容片段（前 200 字符）
        confidence: 相关度或置信度（0-1，越高越相关）
    """

    source_type: str = Field(
        ...,
        description="来源类型：kb（知识库）/ web（网页搜索）/ benchmark（行业基准）",
    )
    document_id: str = Field(..., description="文档唯一标识")
    title: str = Field(..., description="文档标题或章节标题")
    category: str | None = Field(None, description="文档分类标签")
    url: str | None = Field(None, description="外部链接（Web 来源时必填）")
    snippet: str = Field(..., description="引用的内容片段")
    confidence: float | None = Field(None, description="相关度或置信度（0-1）")

    def to_display(self) -> str:
        """生成前端展示的简短描述"""
        if self.source_type == "web":
            return f"Web: {self.title}"
        elif self.source_type == "benchmark":
            return f"基准: {self.title}"
        else:
            return f"知识库: {self.title}"


def _make_snippet(content: str, max_len: int = SNIPPET_MAX_LEN) -> str:
    """从内容中提取片段，优先取前 max_len 字符并在合理位置截断"""
    content = content.strip()
    if len(content) <= max_len:
        return content
    # 在 max_len 附近找最后一个句号或换行，避免断句
    cutoff = max_len
    for i in range(max_len, max_len - 50, -1):
        if i < 0:
            break
        if content[i] in "。.\n":
            cutoff = i + 1
            break
    return content[:cutoff].rstrip() + "..."


def extract_citation_from_kb_result(result: dict) -> Citation:
    """从 KB 检索结果（向量库/ChromaDB）中提取 Citation

    Args:
        result: 检索结果字典，包含 id, content, metadata, distance

    Returns:
        Citation 对象
    """
    metadata = result.get("metadata", {})
    content = result.get("content", "")
    doc_id = result.get("id", "")
    distance = result.get("distance", 1.0)

    # 计算置信度：余弦距离 → 相似度（越小越相似）
    # distance 范围约 0-2，转换为 0-1 的置信度
    confidence = max(0.0, 1.0 - distance / 2.0)

    # 判断来源类型：category="benchmark" 时视为 benchmark
    category = metadata.get("category", "")
    source_type = "benchmark" if category == "benchmark" else "kb"

    # 标题：优先用 section_title，其次 topic，最后 source_file
    title = (
        metadata.get("section_title", "")
        or metadata.get("topic", "")
        or metadata.get("source_file", "")
        or "未知文档"
    )

    return Citation(
        source_type=source_type,
        document_id=doc_id,
        title=title,
        category=category or None,
        url=None,
        snippet=_make_snippet(content),
        confidence=round(confidence, 3),
    )


def extract_citations_from_kb_results(results: list[dict]) -> list[Citation]:
    """批量从 KB 检索结果中提取 Citation"""
    return [extract_citation_from_kb_result(r) for r in results]


def extract_citation_from_web_result(result: dict) -> Citation:
    """从 Web 搜索结果中提取 Citation

    Args:
        result: Web 搜索结果字典，包含 id, content, metadata

    Returns:
        Citation 对象
    """
    metadata = result.get("metadata", {})
    content = result.get("content", "")
    doc_id = result.get("id", "")

    return Citation(
        source_type="web",
        document_id=doc_id,
        title=metadata.get("title", "") or "网页搜索结果",
        category="web",
        url=metadata.get("link", None),
        snippet=_make_snippet(content),
        confidence=0.6,  # Web 结果固定置信度
    )


def extract_citations_from_web_results(results: list[dict]) -> list[Citation]:
    """批量从 Web 搜索结果中提取 Citation"""
    return [extract_citation_from_web_result(r) for r in results]


def extract_citation_from_benchmark_result(result: dict) -> Citation:
    """从 Benchmark 查询结果中提取 Citation

    Args:
        result: benchmark_tool.get_benchmark() 返回的字典

    Returns:
        Citation 对象
    """
    metric_name = result.get("metric_name", "未知指标")
    description = result.get("description", "")
    sample_count = result.get("sample_count", 0)
    data_version = result.get("data_version", "")

    # 构造标题：指标名 + 样本数
    title = f"{metric_name}"
    if sample_count > 0:
        title += f"（{sample_count} 个样本）"

    # 构造片段：描述 + 关键数值
    snippet_parts = []
    if description:
        snippet_parts.append(description)
    avg = result.get("avg_value")
    median = result.get("median_value")
    if avg is not None:
        snippet_parts.append(f"均值: {avg:.2f}")
    if median is not None:
        snippet_parts.append(f"中位数: {median:.2f}")

    snippet = " | ".join(snippet_parts) if snippet_parts else "行业基准数据"

    return Citation(
        source_type="benchmark",
        document_id=f"benchmark:{metric_name}:{data_version}",
        title=title,
        category="benchmark",
        url=None,
        snippet=_make_snippet(snippet),
        confidence=0.85,  # 基准数据置信度较高
    )


def extract_citations_from_benchmark_results(results: list[dict]) -> list[Citation]:
    """批量从 Benchmark 查询结果中提取 Citation"""
    return [extract_citation_from_benchmark_result(r) for r in results]


# ------------------------------------------------------------------
# CitationCollector：收集、去重、排序
# ------------------------------------------------------------------

class CitationCollector:
    """引用收集器

    负责收集多轮检索的引用，自动去重并按置信度排序。

    使用方式：
        collector = CitationCollector()
        collector.add_from_kb(kb_results)
        collector.add_from_web(web_results)
        collector.add_from_benchmark(benchmark_results)
        citations = collector.get_citations()
    """

    def __init__(self) -> None:
        """初始化空的引用收集器"""
        # document_id -> Citation，用于去重
        self._citations: dict[str, Citation] = {}

    def add(self, citation: Citation) -> None:
        """添加单个引用（自动去重：保留置信度更高的）"""
        existing = self._citations.get(citation.document_id)
        if existing is None:
            self._citations[citation.document_id] = citation
        else:
            # 已存在：保留置信度更高的
            new_conf = citation.confidence or 0.0
            old_conf = existing.confidence or 0.0
            if new_conf > old_conf:
                self._citations[citation.document_id] = citation

    def add_many(self, citations: list[Citation]) -> None:
        """批量添加引用"""
        for c in citations:
            self.add(c)

    def add_from_kb(self, results: list[dict]) -> None:
        """从 KB 检索结果中提取并添加引用"""
        self.add_many(extract_citations_from_kb_results(results))

    def add_from_web(self, results: list[dict]) -> None:
        """从 Web 搜索结果中提取并添加引用"""
        self.add_many(extract_citations_from_web_results(results))

    def add_from_benchmark(self, results: list[dict]) -> None:
        """从 Benchmark 查询结果中提取并添加引用"""
        self.add_many(extract_citations_from_benchmark_results(results))

    def get_citations(self, source_type: str | None = None) -> list[Citation]:
        """获取收集到的引用列表

        Args:
            source_type: 按来源类型过滤，None 则返回全部

        Returns:
            按置信度降序排列的 Citation 列表
        """
        citations = list(self._citations.values())
        if source_type:
            citations = [c for c in citations if c.source_type == source_type]
        # 按置信度降序
        citations.sort(key=lambda c: c.confidence or 0.0, reverse=True)
        return citations

    def get_unique_count(self) -> int:
        """返回去重后的引用数量"""
        return len(self._citations)

    def to_dict_list(self, source_type: str | None = None) -> list[dict]:
        """导出为字典列表（便于 JSON 序列化）"""
        return [c.model_dump() for c in self.get_citations(source_type)]
