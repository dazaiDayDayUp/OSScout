"""Markdown 文档分块器

按 Markdown 标题边界进行语义分块，支持重叠窗口和元数据保留。

核心策略：
- 以 ## 和 ### 级别的标题为分块边界
- 相邻 chunk 保留 20% 重叠
- 每个 chunk 携带元数据（来源文档、章节标题等）
- 小文档（< 最小分块大小）不拆分
- 过滤掉低价值内容（图片引用、贡献者列表等）

分块流程：
    1. 解析 YAML frontmatter，提取元数据
    2. 按 Markdown 标题拆分文档为 section
    3. 合并过小的相邻 section（避免碎片化）
    4. 为每个 chunk 添加 20% 重叠文本
    5. 生成 chunk ID 和元数据
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


# 默认分块参数
# 目标 chunk 大小约 300-500 tokens
# 中英文混合文本粗略估算：1 token ≈ 4 字符
DEFAULT_TARGET_CHARS = 1600  # ≈ 400 tokens
DEFAULT_MIN_CHARS = 800      # ≈ 200 tokens
DEFAULT_MAX_CHARS = 3200     # ≈ 800 tokens
DEFAULT_OVERLAP_RATIO = 0.2  # 20% 重叠

# 低价值内容模式：匹配后跳过
LOW_VALUE_PATTERNS = [
    r"^!\[.*?\]\(.*?\)\s*$",           # 纯图片引用行
    r"^\*Figure \d+.*\*$",              # 图片说明行
    r"^\*\*Figure \d+.*\*\*$",         # 加粗图片说明
    r"^<!--.*?-->$",                     # HTML 注释
    r"^<span markdown=.*?</span>\s*$",  # markdown span 标签
    r"^<details>.*?</details>\s*$",     # details 标签（单行）
    r"^Context tags:.*$",                # CHAOSS 上下文标签
    r"^Keyword tags:.*$",                # CHAOSS 关键词标签
]
LOW_VALUE_REGEX = re.compile("|".join(f"(?:{p})" for p in LOW_VALUE_PATTERNS), re.MULTILINE | re.IGNORECASE | re.DOTALL)

# Markdown 标题正则
HEADER_REGEX = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# YAML frontmatter 正则
FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class DocumentChunk:
    """单个文档分块的数据结构"""

    chunk_id: str                    # 唯一标识，格式："source_file#chunk_index"
    content: str                     # 分块文本内容
    source_file: str                 # 来源文档文件名
    category: str                    # 文档分类
    topic: str                       # 文档主题
    section_title: str = ""          # 所属章节标题
    chunk_index: int = 0             # 在原文档中的分块序号
    total_chunks: int = 1            # 原文档总分块数
    frontmatter: dict = field(default_factory=dict)  # YAML frontmatter 元数据


class MarkdownChunker:
    """Markdown 文档分块器

    将 Markdown 文档按语义边界拆分为多个 chunk，
    每个 chunk 携带完整的元数据信息。

    Args:
        target_chars: 目标 chunk 字符数（默认 1600 ≈ 400 tokens）
        min_chars: 最小 chunk 字符数，小于此值会尝试与相邻 section 合并
        max_chars: 最大 chunk 字符数，超过此值会在段落边界强制拆分
        overlap_ratio: 相邻 chunk 重叠比例（默认 20%）
    """

    def __init__(
        self,
        target_chars: int = DEFAULT_TARGET_CHARS,
        min_chars: int = DEFAULT_MIN_CHARS,
        max_chars: int = DEFAULT_MAX_CHARS,
        overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    ) -> None:
        self.target_chars = target_chars
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.overlap_ratio = overlap_ratio

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def chunk_file(self, file_path: Path, category: str = "") -> list[DocumentChunk]:
        """对单个 Markdown 文件进行分块

        Args:
            file_path: Markdown 文件路径
            category: 文档分类标签

        Returns:
            分块列表
        """
        content = file_path.read_text(encoding="utf-8")
        topic = file_path.stem.replace("-", " ")
        source_file = f"{file_path.parent.name}/{file_path.name}"

        return self.chunk_text(
            text=content,
            source_file=source_file,
            category=category,
            topic=topic,
        )

    def chunk_text(
        self,
        text: str,
        source_file: str,
        category: str,
        topic: str,
    ) -> list[DocumentChunk]:
        """对 Markdown 文本进行分块（不依赖文件路径）

        Args:
            text: Markdown 原文
            source_file: 来源文件名（用于生成 chunk_id）
            category: 分类标签
            topic: 主题标签

        Returns:
            分块列表
        """
        # 1. 提取 frontmatter
        frontmatter, body = self._extract_frontmatter(text)

        # 2. 过滤低价值内容
        body = self._filter_low_value_content(body)

        # 3. 如果整篇很短，直接作为单个 chunk
        if len(body) <= self.target_chars:
            return [
                DocumentChunk(
                    chunk_id=f"{source_file}#0",
                    content=body.strip(),
                    source_file=source_file,
                    category=category,
                    topic=topic,
                    section_title=frontmatter.get("title", topic),
                    chunk_index=0,
                    total_chunks=1,
                    frontmatter=frontmatter,
                )
            ]

        # 4. 按标题拆分为 section
        sections = self._split_by_headers(body)

        # 5. 合并过小的 section
        sections = self._merge_small_sections(sections)

        # 6. 构建 chunks（带重叠）
        chunks = self._build_chunks(
            sections=sections,
            source_file=source_file,
            category=category,
            topic=topic,
            frontmatter=frontmatter,
        )

        return chunks

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_frontmatter(text: str) -> tuple[dict, str]:
        """提取 YAML frontmatter 和正文

        Returns:
            (frontmatter_dict, body_text)
        """
        match = FRONTMATTER_REGEX.match(text)
        if not match:
            return {}, text

        fm_text = match.group(1)
        body = text[match.end():]

        # 简单解析 YAML key-value（本项目 frontmatter 格式简单，无需完整 YAML 库）
        fm = {}
        for line in fm_text.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip().strip('"').strip("'")

        return fm, body

    @staticmethod
    def _filter_low_value_content(text: str) -> str:
        """过滤掉低价值内容（图片引用、贡献者列表等）

        同时清理空行和多余空白。
        """
        lines = text.split("\n")
        filtered = []

        for line in lines:
            # 跳过纯低价值行
            if LOW_VALUE_REGEX.match(line.strip()):
                continue
            # 跳过 CHAOSS 文档底部的 Contributors 列表块
            if re.match(r"^\*\s+[A-Z][a-zA-Z\s\.]+$", line.strip()):
                continue
            filtered.append(line)

        return "\n".join(filtered)

    def _split_by_headers(self, text: str) -> list[dict]:
        """按 Markdown 标题拆分为 section

        Returns:
            section 列表，每个元素为 {"title": str, "level": int, "content": str}
        """
        # 找到所有标题位置
        matches = list(HEADER_REGEX.finditer(text))

        if not matches:
            # 没有标题，整篇作为一个 section
            return [{"title": "", "level": 0, "content": text.strip()}]

        sections = []

        for i, match in enumerate(matches):
            level = len(match.group(1))  # # 的数量
            title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()

            sections.append({
                "title": title,
                "level": level,
                "content": section_text,
            })

        return sections

    def _merge_small_sections(self, sections: list[dict]) -> list[dict]:
        """合并过小的相邻 section

        策略：
        - 遍历 sections，维护一个当前 chunk 的缓冲区
        - 当缓冲区大小 >= target_chars 时，输出为一个 chunk
        - 如果单个 section 就超过 max_chars，在段落边界强制拆分
        """
        if not sections:
            return []

        merged = []
        current_buffer = []
        current_chars = 0

        for sec in sections:
            sec_len = len(sec["content"])

            # 如果当前 section 本身就超过 max_chars，先 flush 缓冲区，再拆分这个 section
            if sec_len > self.max_chars:
                if current_buffer:
                    merged.append(self._join_sections(current_buffer))
                    current_buffer = []
                    current_chars = 0

                # 在段落边界强制拆分这个超大 section
                splits = self._split_large_section(sec)
                merged.extend(splits)
                continue

            # 如果加入当前 section 后超过 max_chars，先 flush 缓冲区
            if current_chars + sec_len > self.max_chars and current_buffer:
                merged.append(self._join_sections(current_buffer))
                current_buffer = [sec]
                current_chars = sec_len
            else:
                current_buffer.append(sec)
                current_chars += sec_len

            # 如果缓冲区达到目标大小，输出
            if current_chars >= self.target_chars:
                merged.append(self._join_sections(current_buffer))
                current_buffer = []
                current_chars = 0

        # 处理剩余缓冲区
        if current_buffer:
            # 如果剩余很小，尝试合并回上一个 chunk
            if current_chars < self.min_chars and merged:
                last = merged[-1]
                combined_content = last["content"] + "\n\n" + self._join_sections(current_buffer)["content"]
                if len(combined_content) <= self.max_chars:
                    last["content"] = combined_content
                    last["title"] = last["title"] or current_buffer[0]["title"]
                else:
                    merged.append(self._join_sections(current_buffer))
            else:
                merged.append(self._join_sections(current_buffer))

        return merged

    @staticmethod
    def _join_sections(sections: list[dict]) -> dict:
        """将多个 section 合并为一个"""
        if len(sections) == 1:
            return sections[0]

        # 使用第一个有内容的标题作为主标题
        title = ""
        for s in sections:
            if s["title"]:
                title = s["title"]
                break

        content = "\n\n".join(s["content"] for s in sections)
        return {
            "title": title,
            "level": min(s["level"] for s in sections),
            "content": content,
        }

    def _split_large_section(self, section: dict) -> list[dict]:
        """在段落边界强制拆分超大 section"""
        paragraphs = section["content"].split("\n\n")
        result = []
        buffer = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            if current_len + para_len > self.max_chars and buffer:
                result.append({
                    "title": section["title"],
                    "level": section["level"],
                    "content": "\n\n".join(buffer),
                })
                buffer = [para]
                current_len = para_len
            else:
                buffer.append(para)
                current_len += para_len

        if buffer:
            result.append({
                "title": section["title"],
                "level": section["level"],
                "content": "\n\n".join(buffer),
            })

        return result

    def _build_chunks(
        self,
        sections: list[dict],
        source_file: str,
        category: str,
        topic: str,
        frontmatter: dict,
    ) -> list[DocumentChunk]:
        """构建带重叠的 chunks"""
        if not sections:
            return []

        chunks = []
        total = len(sections)

        for i, sec in enumerate(sections):
            content = sec["content"].strip()

            # 计算重叠文本
            overlap_prefix = ""
            overlap_suffix = ""

            if i > 0:
                # 从前一个 section 尾部取 overlap
                prev_content = sections[i - 1]["content"].strip()
                overlap_len = int(len(prev_content) * self.overlap_ratio)
                overlap_prefix = prev_content[-overlap_len:] if overlap_len > 0 else ""

            if i < total - 1:
                # 从下一个 section 头部取 overlap
                next_content = sections[i + 1]["content"].strip()
                overlap_len = int(len(next_content) * self.overlap_ratio)
                overlap_suffix = next_content[:overlap_len] if overlap_len > 0 else ""

            # 组装 chunk 内容：前缀重叠 + 主体 + 后缀重叠
            parts = []
            if overlap_prefix:
                parts.append(overlap_prefix)
            parts.append(content)
            if overlap_suffix:
                parts.append(overlap_suffix)

            full_content = "\n\n".join(parts)

            # 章节标题：优先用 frontmatter 的 title，其次用 section title
            section_title = sec["title"] or frontmatter.get("title", topic)

            chunk = DocumentChunk(
                chunk_id=f"{source_file}#{i}",
                content=full_content,
                source_file=source_file,
                category=category,
                topic=topic,
                section_title=section_title,
                chunk_index=i,
                total_chunks=total,
                frontmatter=frontmatter,
            )
            chunks.append(chunk)

        return chunks


# ------------------------------------------------------------------
# 便捷函数
# ------------------------------------------------------------------

def chunk_markdown_file(
    file_path: Path,
    category: str = "",
    **chunker_kwargs,
) -> list[DocumentChunk]:
    """对 Markdown 文件进行分块的便捷函数

    Args:
        file_path: Markdown 文件路径
        category: 分类标签
        **chunker_kwargs: 传递给 MarkdownChunker 的参数

    Returns:
        分块列表
    """
    chunker = MarkdownChunker(**chunker_kwargs)
    return chunker.chunk_file(file_path, category=category)


def chunk_markdown_text(
    text: str,
    source_file: str,
    category: str,
    topic: str,
    **chunker_kwargs,
) -> list[DocumentChunk]:
    """对 Markdown 文本进行分块的便捷函数"""
    chunker = MarkdownChunker(**chunker_kwargs)
    return chunker.chunk_text(text, source_file, category, topic)
