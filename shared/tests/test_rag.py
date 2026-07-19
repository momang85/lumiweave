"""测试 RAG 引擎 v2：分块/BM25/Re-rank/RAGAS"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_HERE = os.path.dirname(os.path.abspath(__file__))        # shared/tests
_ROOT = os.path.dirname(os.path.dirname(_HERE))            # ai-agent-hub
sys.path.insert(0, _ROOT)

from shared.rag_chunker import SmartChunker, ChunkConfig, ChunkStrategy
from shared.rag_engine_v2 import BM25Scorer, LightweightReRanker, RAGASEvaluator

# ══ 测试 1: 分块器 ══
def test_chunker():
    print("=== 分块器测试 ===")

    text = """# 第一章

人工智能正在改变软件工程的方方面面。

多智能体系统是下一阶段的关键技术。C++20 引入了 concepts、ranges、coroutines 等革命性特性。

## 1.1 背景

近年来，随着大语言模型的发展，AI 辅助编程已经从简单的代码补全进化到完整的智能体系统。

## 1.2 架构设计

系统架构需要考虑以下因素：可扩展性、性能、容错性。"""

    # 递归分块（设小 max_chunk_size 以验证多块拆分）
    chunker = SmartChunker(ChunkConfig(
        strategy=ChunkStrategy.RECURSIVE,
        chunk_size=80,
        max_chunk_size=80,
        chunk_overlap=20,
    ))
    chunks = chunker.chunk(text)

    assert len(chunks) > 1, f"递归分块失败: {len(chunks)} chunks"
    for c in chunks:
        assert len(c.text) <= 200, f"块过大: {len(c.text)}"
    print(f"  ✓ 递归分块: {len(chunks)} chunks")

    # 固定分块
    chunker2 = SmartChunker(ChunkConfig(strategy=ChunkStrategy.FIXED, chunk_size=150, chunk_overlap=20))
    chunks2 = chunker2.chunk(text)
    assert len(chunks2) > 0
    print(f"  ✓ 固定分块: {len(chunks2)} chunks")

    # 句子分块
    chunker3 = SmartChunker(ChunkConfig(strategy=ChunkStrategy.SENTENCE, chunk_size=200))
    chunks3 = chunker3.chunk(text)
    assert len(chunks3) > 0
    print(f"  ✓ 句子分块: {len(chunks3)} chunks")

    # 空文本
    assert len(chunker.chunk("")) == 0
    assert len(chunker.chunk("   ")) == 0
    print("  ✓ 空文本处理正确")

    print("  ✓ 全部分块测试通过\n")


# ══ 测试 2: BM25 ══
def test_bm25():
    print("=== BM25 测试 ===")

    docs = [
        "Python 是一种解释型编程语言，广泛用于数据科学和 Web 开发",
        "FastAPI 是一个现代高性能 Python Web 框架，支持异步编程",
        "React 是一个用于构建用户界面的 JavaScript 库",
        "ChromaDB 是一个开源向量数据库，专为 AI 应用设计",
        "BM25 是一种经典的信息检索算法，用于关键词匹配",
    ]

    bm25 = BM25Scorer()
    bm25.fit(docs)

    # 检索 Python 相关
    results = bm25.search("Python Web 框架", top_k=3)
    assert len(results) > 0, "BM25 检索无结果"
    # 应该优先返回 FastAPI 或 Python 文档
    top_text = docs[results[0][0]]
    assert "Python" in top_text or "FastAPI" in top_text, f"意外结果: {top_text}"
    print(f"  ✓ 检索 'Python Web 框架': top doc = {top_text[:50]}...")

    # 检索向量数据库
    results2 = bm25.search("向量数据库 AI", top_k=2)
    assert len(results2) > 0
    top2_text = docs[results2[0][0]]
    assert "ChromaDB" in top2_text or "向量" in top2_text
    print(f"  ✓ 检索 '向量数据库 AI': top doc = {top2_text[:50]}...")

    print("  ✓ 全部 BM25 测试通过\n")


# ══ 测试 3: Re-ranker ══
def test_reranker():
    print("=== Re-ranker 测试 ===")

    chunks = [
        {"content": "FastAPI 性能优化：使用异步编程提升 QPS", "score": 0.85, "source": "doc1"},
        {"content": "Python asyncio 最佳实践和协程使用指南", "score": 0.82, "source": "doc2"},
        {"content": "React Hooks 详解：useState 和 useEffect", "score": 0.75, "source": "doc3"},
        {"content": "Docker 容器化部署 FastAPI 应用", "score": 0.70, "source": "doc4"},
    ]

    reranker = LightweightReRanker()
    reranked = reranker.rerank("FastAPI 异步编程", chunks, top_k=2)

    assert len(reranked) == 2
    # Re-rank 后应该把最相关的放在前面
    top_content = reranked[0]["content"]
    assert "FastAPI" in top_content or "异步" in top_content or "asyncio" in top_content
    print(f"  ✓ Re-rank top-1: {top_content[:60]}")
    print(f"    _rerank_score={reranked[0]['_rerank_score']:.3f}")
    print(f"    _coverage={reranked[0]['_coverage']:.3f}")

    # 空列表
    assert len(reranker.rerank("test", [], top_k=5)) == 0
    print("  ✓ 空列表处理正确")

    print("  ✓ 全部 Re-ranker 测试通过\n")


# ══ 测试 4: RAGAS ══
def test_ragas():
    print("=== RAGAS 评估测试 ===")

    evaluator = RAGASEvaluator()

    chunks = [
        "FastAPI 是一个现代 Web 框架，性能接近 Node.js",
        "Python 异步编程使用 async/await 关键字",
        "异步兼容：FastAPI 支持 async def 路由处理器",
    ]

    answer = "FastAPI 是一个高性能的 Python Web 框架，支持异步编程，性能优秀。"

    result = evaluator.evaluate(
        query="FastAPI 异步编程性能",
        retrieved_chunks=chunks,
        generated_answer=answer,
    )

    assert "context_precision" in result
    assert "faithfulness" in result
    assert result["overall_score"] >= 0
    print(f"  Context Precision: {result['context_precision']}")
    print(f"  Faithfulness:      {result['faithfulness']}")
    print(f"  Overall Score:     {result['overall_score']}")

    # 带 ground truth 的评估
    result2 = evaluator.evaluate(
        query="FastAPI",
        retrieved_chunks=chunks,
        generated_answer=answer,
        ground_truth={"FastAPI", "Web 框架", "异步编程"},
    )
    assert result2["context_precision"] > 0
    print(f"  Ground Truth Precision: {result2['context_precision']}")

    # 空上下文
    result3 = evaluator.evaluate(
        query="test", retrieved_chunks=[], generated_answer="test answer",
    )
    assert result3["context_precision"] == 1.0  # 空上下文按全相关处理
    print("  ✓ 空上下文处理正确")

    print("  ✓ 全部 RAGAS 测试通过\n")


# ══ 执行 ══
if __name__ == "__main__":
    print("=" * 50)
    print("  AI Agent Hub — 模块2 RAG引擎 测试套件")
    print("=" * 50 + "\n")

    results = {}
    for name, func in [
        ("分块器", test_chunker),
        ("BM25 检索", test_bm25),
        ("Re-ranker", test_reranker),
        ("RAGAS 评估", test_ragas),
    ]:
        try:
            func()
            results[name] = "OK"
        except Exception as e:
            results[name] = f"FAIL: {e}"
            import traceback
            traceback.print_exc()

    print("=" * 50)
    print("          测试结果汇总")
    print("=" * 50)
    for name, status in results.items():
        s = "[PASS]" if status == "OK" else "[FAIL]"
        print(f"  {s} {name}: {status}")
    print("=" * 50)

    failed = sum(1 for s in results.values() if s != "OK")
    if failed:
        print(f"\n  {failed} 项失败!")
        sys.exit(1)
    else:
        print("\n  全部通过!")
