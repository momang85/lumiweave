"""
AI Agent Hub — 智能文档分块器 v0.3

支持多种分块策略，自动选择最佳断点。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class ChunkStrategy(str, Enum):
    """分块策略"""
    FIXED = "fixed"           # 固定大小 + 重叠
    SEMANTIC = "semantic"     # 按段落/标题语义边界
    RECURSIVE = "recursive"   # 递归分块：优先大分隔符
    SENTENCE = "sentence"     # 按句子边界


@dataclass
class ChunkConfig:
    """分块配置"""
    strategy: ChunkStrategy = ChunkStrategy.RECURSIVE
    chunk_size: int = 1000       # 目标块大小（字符）
    chunk_overlap: int = 150     # 块间重叠（字符）
    min_chunk_size: int = 100    # 最小块大小
    max_chunk_size: int = 2000   # 最大块大小

    # 语义分块参数
    header_pattern: str = r"^#{1,6}\s+.+$"  # Markdown 标题匹配

    # 递归分块分隔符（优先级从高到低）
    recursive_separators: list[str] = field(default_factory=lambda: [
        "\n\n",    # 段落
        "\n",      # 换行
        "。",      # 中文句号
        ". ",      # 英文句号+空格
        "！", "？", # 中文感叹/疑问
        "! ", "? ", # 英文感叹/疑问
        "；", ";",  # 分号
        "，", ",",  # 逗号
        " ",        # 空格
        "",         # 字符级兜底
    ])


@dataclass
class TextChunk:
    """单个文本块"""
    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


class SmartChunker:
    """
    智能文档分块器。

    使用示例：
        chunker = SmartChunker(ChunkConfig(strategy=ChunkStrategy.RECURSIVE))
        chunks = chunker.chunk("长文本内容...")
        for c in chunks:
            print(f"Chunk {c.chunk_index}: {c.text[:50]}...")
    """

    def __init__(self, config: ChunkConfig | None = None):
        self.config = config or ChunkConfig()

    def chunk(self, text: str, metadata: dict | None = None) -> list[TextChunk]:
        """
        将文本分块。

        Args:
            text: 原始文本
            metadata: 块级元数据

        Returns:
            TextChunk 列表
        """
        if not text.strip():
            return []

        # 清理文本：统一换行、移除多余空白
        text = self._clean_text(text)

        strategy_map: dict[ChunkStrategy, Callable] = {
            ChunkStrategy.FIXED: self._fixed_chunk,
            ChunkStrategy.SEMANTIC: self._semantic_chunk,
            ChunkStrategy.RECURSIVE: self._recursive_chunk,
            ChunkStrategy.SENTENCE: self._sentence_chunk,
        }

        chunk_func = strategy_map.get(self.config.strategy, self._recursive_chunk)
        raw_chunks = chunk_func(text)

        # 构建 TextChunk 并添加元数据
        base_meta = metadata or {}
        chunks = []
        for i, chunk_text in enumerate(raw_chunks):
            chunks.append(TextChunk(
                text=chunk_text.strip(),
                chunk_index=i,
                metadata={**base_meta, "chunk_index": i, "total_chunks": len(raw_chunks)},
            ))

        return chunks

    # ── 分块策略实现 ──

    def _fixed_chunk(self, text: str) -> list[str]:
        """固定大小分块 + 重叠"""
        chunks = []
        start = 0
        size = self.config.chunk_size
        overlap = self.config.chunk_overlap

        while start < len(text):
            end = min(start + size, len(text))
            # 尝试在自然边界断开
            if end < len(text):
                end = self._find_best_break(text, start, end)
            chunks.append(text[start:end])
            start = end - overlap if end < len(text) else len(text)

        return chunks

    def _semantic_chunk(self, text: str) -> list[str]:
        """按语义边界分块：段落 + Markdown 标题"""
        # 先按双换行分段落
        paragraphs = re.split(r"\n{2,}", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks: list[str] = []
        current = ""
        header_pattern = re.compile(self.config.header_pattern, re.MULTILINE)

        for para in paragraphs:
            # 检测 Markdown 标题
            if header_pattern.match(para):
                if current:
                    chunks.append(current)
                current = para
                continue

            if len(current) + len(para) + 2 <= self.config.max_chunk_size:
                if current:
                    current += "\n\n" + para
                else:
                    current = para
            else:
                if current:
                    chunks.append(current)
                # 如果单个段落仍然超长，递归分块
                if len(para) > self.config.max_chunk_size:
                    sub_chunks = self._recursive_chunk(para)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    def _recursive_chunk(self, text: str) -> list[str]:
        """
        递归分块：按分隔符优先级逐级拆分。

        算法：
        1. 如果文本 < max_chunk_size，直接返回
        2. 遍历递归分隔符列表，找到第一个能拆分的分隔符
        3. 对每个拆分片段递归调用
        """
        if len(text) <= self.config.max_chunk_size:
            return [text] if len(text) >= self.config.min_chunk_size or not text.strip() else []

        chunks: list[str] = []

        for separator in self.config.recursive_separators:
            if separator == "":
                # 字符级兜底：强制按大小分块
                return self._fixed_chunk(text)

            if separator not in text:
                continue

            # 按分隔符拆分
            parts = text.split(separator)
            merged_parts: list[str] = []

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                if len(part) <= self.config.max_chunk_size:
                    merged_parts.append(part)
                else:
                    # 子片段仍超大，递归
                    merged_parts.extend(self._recursive_chunk(part))

            # 将碎片合并到合理大小
            merged: list[str] = []
            current = ""

            for part in merged_parts:
                combined = current + (separator + part if current else part)
                if len(combined) <= self.config.max_chunk_size:
                    current = combined
                else:
                    if current:
                        merged.append(current)
                    current = part

            if current:
                merged.append(current)

            return merged

        return [text]

    def _sentence_chunk(self, text: str) -> list[str]:
        """按句子边界分块"""
        # 按中英文句子结束符拆分
        sentences = re.split(r"(?<=[。！？.!?\n])\s*", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        current = ""

        for sent in sentences:
            if len(current) + len(sent) + 1 <= self.config.chunk_size:
                current += (" " + sent) if current else sent
            else:
                if current:
                    chunks.append(current)
                current = sent

        if current:
            chunks.append(current)

        return chunks

    # ── 工具方法 ──

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗文本"""
        # 统一换行
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 移除多余空行（保留最多 2 个连续换行）
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 移除行首行尾多余空白
        text = text.strip()
        return text

    def _find_best_break(self, text: str, start: int, end: int) -> int:
        """在 [start, end] 范围内找到最佳断点"""
        # 搜索范围内最后一个自然断点
        search_start = max(start + self.config.chunk_size // 2, start)
        search_region = text[search_start:end]

        for sep in ["\n\n", "\n", "。", ". ", "！", "？", "；", "，", " "]:
            idx = search_region.rfind(sep)
            if idx != -1:
                return search_start + idx + len(sep)

        return end
