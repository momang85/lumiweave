"""
AI Agent Hub — RAG 引擎

基于 ChromaDB + sentence-transformers 实现：
- 文档上传自动分块 + 向量化
- 语义搜索 & 上下文召回
- 多知识库隔离
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings


# ── 配置 ──

CHROMA_DIR = os.path.join(os.path.dirname(__file__), "chroma_data")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

CHUNK_SIZE = 1000       # 每块字符数
CHUNK_OVERLAP = 150     # 块间重叠字符数
TOP_K_RESULTS = 5       # 检索返回条数

# ── 全局单例 ──

_chroma_client: Optional[chromadb.PersistentClient] = None
_embedding_model = None


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_embedding_model():
    """延迟加载 embedding 模型"""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


# ── 核心 API ──

def _make_collection_name(agent_id: str) -> str:
    """基于 agent_id 生成 ChromaDB collection 名称"""
    safe_id = hashlib.md5(agent_id.encode()).hexdigest()[:16]
    return f"kb_{safe_id}"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将文本切分为重叠块"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # 尽量在句号/换行处断开
        if end < len(text):
            for sep in ["\n\n", "\n", "。", ". ", " "]:
                pos = text.rfind(sep, start, end)
                if pos > start + chunk_size // 2:
                    end = pos + len(sep)
                    break
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def _parse_file(file_path: str) -> str:
    """解析上传的文件，返回纯文本"""
    import logging
    _log = logging.getLogger('rag_engine')
    ext = Path(file_path).suffix.lower()
    file_size = os.path.getsize(file_path)

    if ext == ".txt":
        return Path(file_path).read_text(encoding="utf-8", errors="replace")

    elif ext == ".md":
        return Path(file_path).read_text(encoding="utf-8", errors="replace")

    elif ext == ".pdf":
        if file_size == 0:
            return ""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages = len(reader.pages)
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
            _log.info(f"PDF 解析: {file_size} bytes, {pages} 页, 提取 {len(text)} 字符")
            if not text.strip():
                _log.warning(f"PDF 无可提取文本（可能是扫描件/图片PDF）: {file_path}")
            return text
        except ImportError:
            raise RuntimeError("PDF 解析需要 PyPDF2: pip install PyPDF2")

    else:
        raise ValueError(f"不支持的文件类型: {ext}，仅支持 .txt .md .pdf")


def add_knowledge(agent_id: str, file_path: str) -> dict:
    """
    将知识文件向量化并存入 ChromaDB。

    Returns:
        {"chunks": int, "total_chunks": int, "collection": str, "source": str}
    """
    import logging
    _log = logging.getLogger('rag_engine')

    # 1. 解析文件
    file_exists = os.path.exists(file_path)
    file_size = os.path.getsize(file_path) if file_exists else 0
    ext = Path(file_path).suffix.lower()

    if not file_exists:
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"文件未找到: {file_path}", "text_length": 0}

    try:
        text = _parse_file(file_path)
    except Exception as e:
        _log.error(f"文件解析失败: {file_path} - {e}")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"文件解析失败: {str(e)[:100]}", "text_length": 0}

    text_length = len(text.strip()) if text else 0

    if text_length == 0:
        if ext == ".pdf":
            hint = f"PDF 无可提取文本（{file_size} bytes）—— 可能是扫描件/图片PDF"
        else:
            hint = f"文件内容为空（{file_size} bytes）—— 检查编码是否为 UTF-8"
        _log.warning(f"文件内容为空: {file_path} ({file_size} bytes, {ext})")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": hint, "text_length": text_length, "file_size": file_size}

    _log.info(f"文件解析: {file_path} -> {text_length} 字符, {file_size} bytes")
    chunks = _chunk_text(text)

    if not chunks:
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": "文本切分后无有效块", "text_length": text_length}

    _log.info(f"文本分块: {text_length} 字符 -> {len(chunks)} 块")

    # 3. 向量化
    try:
        model = _get_embedding_model()
    except Exception as e:
        _log.error(f"Embedding 模型加载失败: {e}")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"向量模型加载失败: {str(e)[:100]}"}

    try:
        embeddings = model.encode(chunks, show_progress_bar=False).tolist()
    except Exception as e:
        _log.error(f"向量化编码失败: {e}")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"向量化编码失败: {str(e)[:100]}"}

    # 4. 存入 ChromaDB（追加模式，不清空已有内容）
    try:
        client = _get_client()
    except Exception as e:
        _log.error(f"ChromaDB 客户端初始化失败: {e}")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"ChromaDB初始化失败: {str(e)[:100]}"}

    collection_name = _make_collection_name(agent_id)

    # 获取或创建 collection
    try:
        collection = client.get_collection(collection_name)
        existing_count = collection.count()
        _log.info(f"使用已有 collection: {collection_name} ({existing_count} 块)")
    except Exception:
        collection = client.create_collection(name=collection_name)
        existing_count = 0
        _log.info(f"新建 collection: {collection_name}")

    ids = [f"chunk_{existing_count + i}" for i in range(len(chunks))]
    metadatas = [{"source": os.path.basename(file_path), "index": existing_count + i} for i in range(len(chunks))]

    try:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
    except Exception as e:
        _log.error(f"ChromaDB 写入失败: {e}")
        return {"chunks": 0, "total_chunks": 0, "collection": "", "error": f"向量写入失败: {str(e)[:100]}"}

    total = existing_count + len(chunks)
    _log.info(f"知识写入成功: {len(chunks)} 块 -> collection {collection_name} (共 {total} 块)")
    return {
        "chunks": len(chunks),
        "total_chunks": total,
        "collection": collection_name,
        "source": os.path.basename(file_path),
    }


def search_knowledge(agent_id: str, query: str, top_k: int = TOP_K_RESULTS) -> list[dict]:
    """
    搜索知识库，返回最相关的文本块。

    Returns:
        [{"content": "...", "score": 0.85, "source": "..."}, ...]
    """
    collection_name = _make_collection_name(agent_id)
    client = _get_client()

    try:
        collection = client.get_collection(collection_name)
    except Exception:
        return []  # 知识库不存在

    model = _get_embedding_model()
    query_embedding = model.encode([query], show_progress_bar=False).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
    )

    items = []
    if results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 0
            score = 1.0 - min(distance, 1.0) if distance else 1.0
            source = (
                results["metadatas"][0][i].get("source", "")
                if results.get("metadatas") and results["metadatas"][0]
                else ""
            )
            items.append({
                "content": doc,
                "score": round(score, 4),
                "source": source,
            })

    return items


def delete_knowledge(agent_id: str) -> bool:
    """删除指定 Agent 的知识库"""
    collection_name = _make_collection_name(agent_id)
    client = _get_client()
    try:
        client.delete_collection(collection_name)
        return True
    except Exception:
        return False


def get_knowledge_stats(agent_id: str) -> dict:
    """获取知识库统计"""
    collection_name = _make_collection_name(agent_id)
    client = _get_client()
    try:
        collection = client.get_collection(collection_name)
        return {
            "exists": True,
            "chunks": collection.count(),
            "collection": collection_name,
        }
    except Exception:
        return {"exists": False, "chunks": 0}
