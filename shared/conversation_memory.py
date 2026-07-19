"""
AI Agent Hub — 对话记忆库（非破坏性卸载）v0.5

将超出窗口的原始对话消息持久化到 SQLite，
Agent 可通过 search_memory 工具回溯完整历史。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).parent.parent / "builder" / "backend" / "conversation_memory.db"


class ConversationMemory:
    """
    非破坏性对话存档。

    表结构:
    - conversations(id TEXT PK, agent_id TEXT, session_id TEXT,
                    role TEXT, content TEXT, seq INTEGER, tokens INTEGER,
                    timestamp REAL, metadata TEXT)
    """

    def __init__(self, db_path: str | Path = ""):
        self._db_path = str(db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    tokens INTEGER DEFAULT 0,
                    timestamp REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_agent_session ON conversations(agent_id, session_id, seq)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON conversations(timestamp)")
            c.commit()

    # ── 写入 ──

    def archive(
        self,
        agent_id: str,
        session_id: str,
        messages: list[dict],
        base_seq: int = 0,
    ) -> int:
        """
        将裁剪掉的原始消息存入 SQLite。

        Args:
            agent_id: Agent ID
            session_id: 对话 session ID
            messages: [{"role": "user/assistant", "content": "..."}, ...]
            base_seq: 已有消息的最大序号

        Returns:
            存入的消息数量
        """
        if not messages:
            return 0

        ts = time.time()
        count = 0

        with self._conn() as c:
            for i, msg in enumerate(messages):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if not content or role == "system":
                    continue

                msg_id = f"{session_id}_{base_seq + i}"
                tokens = msg.get("tokens", 0)
                meta = json.dumps(msg.get("metadata", {}), ensure_ascii=False)

                c.execute(
                    "INSERT OR REPLACE INTO conversations VALUES (?,?,?,?,?,?,?,?,?)",
                    (msg_id, agent_id, session_id, role, str(content)[:8000],
                     base_seq + i, tokens, ts, meta),
                )
                count += 1
            c.commit()

        logger.info(f"Archived {count} messages for {agent_id}/{session_id} (seq {base_seq}+)")
        return count

    # ── 检索 ──

    def search(
        self,
        agent_id: str,
        session_id: str | None = None,
        query: str = "",
        top_k: int = 10,
        role_filter: str | None = None,
        before_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        搜索存档消息（关键词匹配）。

        Args:
            agent_id: 必须指定 Agent
            session_id: 可选 session 过滤
            query: 搜索关键词（空=返回全部）
            top_k: 返回条数
            role_filter: 可选角色过滤（"user" / "assistant"）
            before_seq: 返回序号 < 此值的消息

        Returns:
            [{"role": "user", "content": "...", "seq": 3, "timestamp": ...}, ...]
        """
        sql = "SELECT role, content, seq, timestamp FROM conversations WHERE agent_id = ?"
        params: list[Any] = [agent_id]

        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)

        if before_seq is not None:
            sql += " AND seq < ?"
            params.append(before_seq)

        if role_filter:
            sql += " AND role = ?"
            params.append(role_filter)

        if query:
            sql += " AND content LIKE ?"
            params.append(f"%{query}%")

        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(top_k)

        with self._conn() as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(sql, params).fetchall()

        return [
            {
                "role": r["role"],
                "content": r["content"],
                "seq": r["seq"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    def get_statistics(self, agent_id: str, session_id: str) -> dict:
        """获取记忆库统计"""
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as total, SUM(tokens) as total_tokens FROM conversations WHERE agent_id=? AND session_id=?",
                (agent_id, session_id),
            ).fetchone()
            return {
                "total": row[0] or 0,
                "total_tokens": row[1] or 0,
                "db_path": self._db_path,
            }

    def forget_agent(self, agent_id: str) -> int:
        """删除指定 Agent 的所有记忆"""
        with self._conn() as c:
            r = c.execute("DELETE FROM conversations WHERE agent_id=?", (agent_id,))
            c.commit()
            return r.rowcount


# ── 全局单例 ──
_global_memory: ConversationMemory | None = None


def get_memory() -> ConversationMemory:
    global _global_memory
    if _global_memory is None:
        _global_memory = ConversationMemory()
    return _global_memory


__all__ = ["ConversationMemory", "get_memory"]
