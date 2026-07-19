"""
子Agent记忆持久化 v0.6.1 — ChromaDB 存储子Agent“经验”

每次子Agent完成任务后，将 (agent_id, task_signature, result_summary) 存储。
下次类似任务时检索相关经验，注入到子Agent context 中。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

_MEMORY_DIR = Path(__file__).resolve().parent.parent / "builder" / "backend" / "agent_memory"


def _ensure_db():
    """延迟加载 ChromaDB，避免启动时依赖"""
    try:
        import chromadb
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        client = chromadb.PersistentClient(path=str(_MEMORY_DIR))
        collection = client.get_or_create_collection("agent_experiences")
        return collection
    except ImportError:
        return None


def store_experience(
    agent_id: str,
    agent_name: str,
    task: str,
    result: str,
    tags: list[str] | None = None,
):
    """存储一次子Agent的执行经验"""
    collection = _ensure_db()
    if collection is None:
        return

    task_hash = hashlib.md5((agent_id + task).encode()).hexdigest()[:16]
    timestamp = time.time()

    metadata = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "task_preview": task[:500],
        "result_preview": result[:500],
        "timestamp": timestamp,
        "tags": ",".join(tags or []),
    }

    try:
        collection.upsert(
            ids=[task_hash],
            documents=[f"{task[:200]} | {result[:200]}"],
            metadatas=[metadata],
        )
    except Exception:
        pass


def retrieve_experience(agent_id: str, task: str, top_k: int = 3) -> list[dict]:
    """检索与当前任务最相关的子Agent历史经验"""
    collection = _ensure_db()
    if collection is None:
        return []

    try:
        results = collection.query(
            query_texts=[task[:500]],
            n_results=min(top_k, 5),
            where={"agent_id": agent_id},
        )
        if not results or not results.get("metadatas") or not results["metadatas"][0]:
            return []

        experiences = []
        for i, meta in enumerate(results["metadatas"][0]):
            if meta:
                experiences.append({
                    "agent_name": meta.get("agent_name", ""),
                    "task": meta.get("task_preview", "")[:200],
                    "result": meta.get("result_preview", "")[:200],
                    "tags": meta.get("tags", ""),
                })
        return experiences
    except Exception:
        return []


def forget_agent(agent_id: str):
    """删除某个Agent的所有记忆"""
    collection = _ensure_db()
    if collection is None:
        return
    try:
        collection.delete(where={"agent_id": agent_id})
    except Exception:
        pass


# ══════════════════════════════════════════════
# v0.7: Agent 表现评分（JSON 文件存储）
# ══════════════════════════════════════════════

_STATS_FILE = _MEMORY_DIR.parent / "agent_stats.json"


def _load_stats() -> dict:
    try:
        if _STATS_FILE.exists():
            with open(_STATS_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_stats(stats: dict):
    try:
        with open(_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record_agent_result(agent_id: str, agent_name: str, success: bool, duration_ms: float = 0):
    """记录一次 Agent 执行结果"""
    stats = _load_stats()
    entry = stats.get(agent_id, {
        "agent_name": agent_name,
        "success_count": 0,
        "fail_count": 0,
        "total_duration_ms": 0.0,
        "call_count": 0,
    })
    entry["agent_name"] = agent_name
    entry["call_count"] += 1
    if success:
        entry["success_count"] += 1
    else:
        entry["fail_count"] += 1
    entry["total_duration_ms"] += duration_ms
    stats[agent_id] = entry
    _save_stats(stats)


def get_agent_score(agent_id: str) -> dict:
    """获取单个 Agent 的评分"""
    entry = _load_stats().get(agent_id)
    if not entry:
        return {"agent_id": agent_id, "score": 0, "call_count": 0, "message": "无记录"}
    total = entry["call_count"]
    if total == 0:
        return {"agent_id": agent_id, "score": 0, "call_count": 0}
    success_rate = entry["success_count"] / total
    avg_duration = entry["total_duration_ms"] / total / 1000
    # 综合评分：成功率权重 70% + 速度权重 30%（越快越高）
    speed_score = max(0, 1.0 - avg_duration / 60.0)  # 60秒以上为0分
    score = round(success_rate * 0.7 + speed_score * 0.3, 2)
    return {
        "agent_id": agent_id,
        "agent_name": entry["agent_name"],
        "score": score,
        "success_rate": round(success_rate, 2),
        "avg_duration_s": round(avg_duration, 1),
        "call_count": total,
        "success_count": entry["success_count"],
        "fail_count": entry["fail_count"],
    }


def get_all_agent_scores() -> list[dict]:
    """获取所有 Agent 的评分，按评分降序"""
    stats = _load_stats()
    result = [get_agent_score(aid) for aid in stats]
    result.sort(key=lambda x: x["score"], reverse=True)
    return result
