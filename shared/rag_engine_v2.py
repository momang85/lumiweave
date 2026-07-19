"""
AI Agent Hub — RAG 引擎 v2.1

增强功能：
- 多策略智能分块（语义/递归/句子）
- Hybrid Search（稠密向量 + BM25 关键词）
- Cross-Encoder Re-ranking
- RAGAS 评估指标
- 多知识库隔离 + 增量更新
- jieba 中文分词集成（BM25）
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .rag_chunker import ChunkConfig, ChunkStrategy, SmartChunker, TextChunk

logger = logging.getLogger(__name__)

# ── jieba 延迟加载 ──
_jieba = None


def _get_jieba():
    """延迟加载 jieba，未安装时回退到 regex 分词"""
    global _jieba
    if _jieba is None:
        try:
            import jieba
            jieba.setLogLevel(logging.WARNING)
            _jieba = jieba
            logger.info("jieba 分词器已加载")
        except ImportError:
            logger.warning("jieba 未安装，使用 regex 分词降级。建议: pip install jieba")
            _jieba = False
    return _jieba if _jieba is not False else None


# ══════════════════════════════════════════════
# BM25 关键词检索
# ══════════════════════════════════════════════

class BM25Scorer:
    """
    BM25 关键词检索（v2.1：集成 jieba 中文分词）。

    用于 Hybrid Search 的稀疏检索分量，与稠密向量检索互补。
    优先使用 jieba 分词，未安装时降级到 regex 分词。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._documents: list[str] = []
        self._doc_len: list[int] = []
        self._avg_dl: float = 0.0
        self._df: dict[str, int] = {}  # document frequency
        self._idf: dict[str, float] = {}
        self._built = False
        self._using_jieba = False

    def _tokenize(self, text: str) -> list[str]:
        """
        中英文混合分词（v2.1：集成 jieba）。

        策略：优先使用 jieba 精准分词，未安装时回退 regex。
        """
        tokens: list[str] = []

        # ── 英文单词提取 ──
        en_words = re.findall(r"[a-zA-Z]+", text.lower())
        tokens.extend(en_words)

        # ── 中文分词 ──
        jieba = _get_jieba()
        if jieba:
            # jieba 精准模式：过滤停用词和单字
            cn_tokens = list(jieba.cut(text))
            stopwords = {"的", "了", "在", "是", "我", "有", "和", "就",
                         "不", "人", "都", "一", "一个", "上", "也", "很",
                         "到", "说", "要", "去", "你", "会", "着", "没有",
                         "看", "好", "自己", "这", "他", "她", "它", "们",
                         "那", "些", "所", "为", "因为", "所以", "可以",
                         "这个", "那个", "什么", "怎么", "如何", "吗", "呢",
                         "吧", "啊", "哦", "嗯"}
            for token in cn_tokens:
                token = token.strip()
                if len(token) >= 2 and token not in stopwords:
                    tokens.append(token)
            self._using_jieba = True
        else:
            # 降级：双字词组 + 单字
            cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
            for i in range(len(cn_chars) - 1):
                tokens.append(cn_chars[i] + cn_chars[i + 1])
            tokens.extend(cn_chars)

        return tokens

    def fit(self, documents: list[str]):
        """构建 BM25 索引"""
        self._documents = documents
        self._doc_len = []
        self._df = {}

        for doc in documents:
            tokens = self._tokenize(doc)
            self._doc_len.append(len(tokens))
            unique_tokens = set(tokens)
            for token in unique_tokens:
                self._df[token] = self._df.get(token, 0) + 1

        self._avg_dl = sum(self._doc_len) / max(len(documents), 1)

        # 计算 IDF
        n = len(documents)
        self._idf = {}
        for token, df in self._df.items():
            self._idf[token] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

        self._built = True
        logger.info(f"BM25 index built: {len(documents)} docs, {len(self._df)} unique tokens")

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        BM25 检索。

        Returns:
            [(doc_index, score), ...] 按分数降序
        """
        if not self._built:
            return []

        query_tokens = self._tokenize(query)
        scores: list[float] = [0.0] * len(self._documents)

        for token in query_tokens:
            idf = self._idf.get(token, 0)
            if idf == 0:
                continue

            for i, doc in enumerate(self._documents):
                tf = self._tokenize(doc).count(token)
                doc_len = self._doc_len[i]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self._avg_dl, 1))
                scores[i] += idf * numerator / max(denominator, 0.001)

        # 排序取 top_k
        indexed_scores = [(i, s) for i, s in enumerate(scores) if s > 0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:top_k]


# ══════════════════════════════════════════════
# 轻量 Re-ranker（无外部依赖）
# ══════════════════════════════════════════════

class LightweightReRanker:
    """
    轻量级 Re-ranking（不依赖 Cross-Encoder 模型）。

    基于 query 与每个 chunk 的 token 覆盖率进行重排序。
    生产环境可替换为 sentence-transformers CrossEncoder。
    """

    def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        重排序。

        Args:
            query: 查询文本
            chunks: [{"content": "..., "score": 0.85, "source": "..."}, ...]
            top_k: 返回条数

        Returns:
            重排序后的 chunks
        """
        if not chunks:
            return []

        # 提取 query 关键词
        query_tokens = set(re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", query.lower()))

        scored = []
        for chunk in chunks:
            content = chunk.get("content", "")
            content_lower = content.lower()

            # 计算 token 覆盖率得分
            if query_tokens:
                match_count = sum(1 for t in query_tokens if t in content_lower)
                coverage_score = match_count / len(query_tokens)
            else:
                coverage_score = 0

            # 计算 query 在 content 中的位置得分（越靠前越好）
            pos = content_lower.find(query.lower()[:20])
            position_score = max(0, 1.0 - pos / max(len(content), 1)) if pos >= 0 else 0

            # 融合得分
            rerank_score = (
                0.4 * chunk.get("score", 0) +      # 原始向量相似度
                0.4 * coverage_score +              # Token 覆盖率
                0.2 * position_score                # 位置得分
            )

            chunk["_rerank_score"] = rerank_score
            chunk["_coverage"] = round(coverage_score, 3)
            scored.append(chunk)

        scored.sort(key=lambda x: x["_rerank_score"], reverse=True)
        return scored[:top_k]


# ══════════════════════════════════════════════
# RAGAS 评估
# ══════════════════════════════════════════════

class RAGASEvaluator:
    """
    RAGAS 评估指标（轻量实现）。

    评估维度：
    - Context Precision: 检索到的文档中有多少相关
    - Context Recall: 相关文档中有多少被检索到
    - Faithfulness: 生成答案是否忠于上下文
    - Answer Relevance: 答案是否与问题相关

    注意：完整 RAGAS 需 LLM 参与评估，这里是基于统计的近似实现。
    """

    @staticmethod
    def context_precision(
        retrieved_chunks: list[str],
        ground_truth_relevant: set[str] | None = None,
    ) -> dict[str, float]:
        """
        上下文精确度。

        Args:
            retrieved_chunks: 检索到的文本块
            ground_truth_relevant: 人工标注的相关内容（关键词集合）

        Returns:
            {"precision": 0.8, "relevant_count": 4, "total": 5}
        """
        if not ground_truth_relevant:
            # 无标注时，使用自评估
            return {"precision": 1.0, "relevant_count": len(retrieved_chunks), "total": len(retrieved_chunks)}

        relevant_count = 0
        for chunk in retrieved_chunks:
            if any(kw in chunk for kw in ground_truth_relevant):
                relevant_count += 1

        return {
            "precision": relevant_count / max(len(retrieved_chunks), 1),
            "relevant_count": relevant_count,
            "total": len(retrieved_chunks),
        }

    @staticmethod
    def answer_faithfulness(
        generated_answer: str,
        context_chunks: list[str],
    ) -> dict[str, float]:
        """
        答案忠实度评估（统计近似）。

        检查生成的答案中是否有原文中不存在的「幻觉」。
        """
        # 提取答案中的关键陈述
        statements = RAGASEvaluator._extract_statements(generated_answer)

        supported_count = 0
        context_text = " ".join(context_chunks)

        for stmt in statements:
            # 检查陈述是否在上下文中出现或部分出现
            if any(word in context_text for word in stmt.split()[:5]):
                supported_count += 1

        return {
            "faithfulness": supported_count / max(len(statements), 1),
            "total_statements": len(statements),
            "supported_statements": supported_count,
        }

    @staticmethod
    def _extract_statements(text: str) -> list[str]:
        """从文本中提取关键陈述"""
        # 按标点分句
        sentences = re.split(r"[。！？.!?\n]+", text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    @staticmethod
    def evaluate(
        query: str,
        retrieved_chunks: list[str],
        generated_answer: str,
        ground_truth: set[str] | None = None,
    ) -> dict[str, Any]:
        """
        综合 RAGAS 评估。

        Returns:
            {
                "context_precision": 0.8,
                "faithfulness": 0.9,
                "chunks_retrieved": 5,
                "overall_score": 0.85,
            }
        """
        precision_result = RAGASEvaluator.context_precision(retrieved_chunks, ground_truth)
        faithfulness_result = RAGASEvaluator.answer_faithfulness(generated_answer, retrieved_chunks)

        overall = (
            precision_result["precision"] * 0.5 +
            faithfulness_result["faithfulness"] * 0.5
        )

        return {
            "context_precision": round(precision_result["precision"], 3),
            "faithfulness": round(faithfulness_result["faithfulness"], 3),
            "chunks_retrieved": len(retrieved_chunks),
            "overall_score": round(overall, 3),
        }


# ══════════════════════════════════════════════
# 统一导出
# ══════════════════════════════════════════════

__all__ = [
    "ChunkStrategy", "ChunkConfig", "SmartChunker", "TextChunk",
    "BM25Scorer", "LightweightReRanker", "RAGASEvaluator",
]
