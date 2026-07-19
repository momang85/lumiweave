"""
AI Agent Hub — 会话管理器 v1.0

持久化完整会话上下文，支持：
- 保存/加载会话（消息历史 + 元数据）
- 列出历史会话
- 恢复上下文继续对话
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# 存储路径
_SESSIONS_DIR = Path(__file__).parent.parent / "builder" / "backend" / "sessions"
_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def save_session(
    session_id: str,
    agent_id: str,
    agent_name: str,
    messages: list[dict],
    metadata: dict | None = None,
) -> str:
    """
    保存完整会话上下文。

    Args:
        session_id: 会话 ID
        agent_id: Agent ID
        agent_name: Agent 名称
        messages: 完整消息列表 [{"role":"system"|"user"|"assistant"|"tool", "content":"..."}]
        metadata: 额外元数据（user_query, dispatch_count, success_count 等）

    Returns:
        session_id
    """
    record = {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
        "messages": messages[-200:],  # 保留最近 200 条消息
        "metadata": metadata or {},
    }

    # 更新已存在的会话
    existing = load_session(session_id)
    if existing:
        record["created_at"] = existing.get("created_at", record["created_at"])
        # 合并消息（去重）
        existing_ids = {m.get("_id", "") for m in existing.get("messages", [])}
        for m in record["messages"]:
            if m.get("_id", "") not in existing_ids:
                existing["messages"].append(m)
        record["messages"] = existing["messages"][-200:]
        record["message_count"] = len(record["messages"])

    with open(_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return session_id


def load_session(session_id: str) -> dict | None:
    """加载会话完整数据。"""
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_sessions(agent_id: str = "", limit: int = 50) -> list[dict]:
    """
    列出历史会话（按更新时间倒序）。

    Args:
        agent_id: 可选，筛选特定 Agent 的会话
        limit: 最大返回数量

    Returns:
        会话摘要列表（不含 messages）
    """
    sessions = []
    for f in sorted(_SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            continue

        if agent_id and data.get("agent_id") != agent_id:
            continue

        # 生成摘要（取第一条用户消息的前 80 字符）
        user_msgs = [m["content"] for m in data.get("messages", []) if m.get("role") == "user"]
        summary = user_msgs[0][:80] if user_msgs else "(空会话)"

        sessions.append({
            "session_id": data["session_id"],
            "agent_id": data.get("agent_id", ""),
            "agent_name": data.get("agent_name", ""),
            "summary": summary,
            "message_count": data.get("message_count", 0),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "metadata": data.get("metadata", {}),
        })

        if len(sessions) >= limit:
            break

    return sessions


def delete_session(session_id: str) -> bool:
    """删除会话。"""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False
