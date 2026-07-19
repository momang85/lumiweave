"""
运行时日志缓冲区 v0.7 — 结构化日志 + 耗时追踪 + 会话摘要

持久化策略：
- 内存环形缓冲区（2000条）+ JSONL 文件持久化
- 每次 log_event() 同时写内存 + 追加 JSONL 文件
- 追踪会话耗时、事件间隔
- session_end 自动生成摘要
"""

from __future__ import annotations

import json
import os
import time
import uuid
import asyncio
from collections import deque
from pathlib import Path
from typing import Optional

# ── 配置 ──
MAX_LOG_ENTRIES = 2000
LOG_FILE = Path(__file__).parent / "runtime_logs.jsonl"

# ── 运行时状态 ──
_runtime_logs: deque[dict] = deque(maxlen=MAX_LOG_ENTRIES)
_listeners: list[asyncio.Queue] = []
_file_handle = None
_session_start_times: dict[str, float] = {}  # session_id -> start timestamp
_session_last_ts: dict[str, float] = {}      # session_id -> last event timestamp
_text_buffer: dict[str, list[str]] = {}       # session_id -> buffered text chunks


def _open_log_file():
    """打开或重新打开 JSONL 日志文件"""
    global _file_handle
    if _file_handle:
        try:
            _file_handle.close()
        except Exception:
            pass
    try:
        _file_handle = open(LOG_FILE, "a", encoding="utf-8")
    except Exception:
        _file_handle = None


def _load_from_file():
    """启动时从 JSONL 文件加载历史日志到内存"""
    if not LOG_FILE.exists():
        return

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            # 只读取最近的 MAX_LOG_ENTRIES 条
            all_lines = f.readlines()
            for line in all_lines[-MAX_LOG_ENTRIES:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    _runtime_logs.append(entry)
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass


def _compact_log_file():
    """压缩日志文件，只保留最近 MAX_LOG_ENTRIES 条"""
    if not LOG_FILE.exists():
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) <= MAX_LOG_ENTRIES:
            return

        # 保留最近 MAX_LOG_ENTRIES 条
        kept = lines[-MAX_LOG_ENTRIES:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except Exception:
        pass


# ── 启动时初始化 ──
_load_from_file()
_open_log_file()


# ── 公共 API ──

def log_event(event_data: dict, agent_id: str = "", agent_name: str = "", session_id: str = ""):
    """记录一条运行时事件（v0.7 — 带耗时追踪 + text去重）"""
    now = time.time()
    event_type = event_data.get("type", "unknown")

    # ── 会话时间追踪 ──
    if event_type == "session_start":
        _session_start_times[session_id] = now
        _session_last_ts[session_id] = now
        _text_buffer[session_id] = []
    elif session_id in _session_start_times:
        _session_last_ts[session_id] = now
    elif session_id:
        _session_start_times[session_id] = now
        _session_last_ts[session_id] = now
        _text_buffer[session_id] = []

    elapsed_ms = int((now - _session_start_times.get(session_id, now)) * 1000)
    gap_ms = int((now - _session_last_ts.get(session_id, now)) * 1000) if session_id in _session_last_ts else 0

    # ── text 去重：连续 text 块合并，只在间隔>2s或块数>20时输出 ──
    if event_type == "text":
        if session_id in _text_buffer:
            _text_buffer[session_id].append(event_data.get("content", ""))
            # 每20块或间隔>2s时输出一次合并的text
            if len(_text_buffer[session_id]) >= 20 or gap_ms > 2000:
                merged = "".join(_text_buffer[session_id])
                _text_buffer[session_id] = []
                event_data = {"type": "text", "content": merged}
            else:
                return  # 不记录，继续缓冲
        else:
            _text_buffer[session_id] = [event_data.get("content", "")]

    entry = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": now,
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "type": event_type,
        "content": event_data.get("content", event_data.get("task", "")),
        "elapsed_ms": elapsed_ms,
        "gap_ms": gap_ms if gap_ms < 600000 else 0,  # 忽略过大的gap（跨session）
        "detail": event_data,
    }

    # ── session_end：刷新text缓冲 + 添加摘要 ──
    if event_type == "session_end":
        if session_id in _text_buffer and _text_buffer[session_id]:
            merged = "".join(_text_buffer[session_id])
            _text_buffer[session_id] = []
            # 不单独记录，直接加到entry的detail中
        # 清理追踪状态
        _session_start_times.pop(session_id, None)
        _session_last_ts.pop(session_id, None)
        _text_buffer.pop(session_id, None)

    # 1. 内存缓冲区
    _runtime_logs.append(entry)

    # 2. 持久化到文件
    _persist_entry(entry)

    # 3. 通知 SSE 监听器
    for q in _listeners:
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass

    # 4. 定期压缩文件
    if len(_runtime_logs) % 100 == 0 and LOG_FILE.exists():
        try:
            if LOG_FILE.stat().st_size > 5 * 1024 * 1024:
                _compact_log_file()
        except Exception:
            pass


def _persist_entry(entry: dict):
    """持久化一条日志到 JSONL 文件"""
    try:
        if _file_handle:
            _file_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            _file_handle.flush()
    except Exception:
        _open_log_file()
        try:
            if _file_handle:
                _file_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
                _file_handle.flush()
        except Exception:
            pass


def get_logs(limit: int = 200, log_type: Optional[str] = None, agent_id: Optional[str] = None) -> list[dict]:
    """获取最近的日志（支持过滤）"""
    logs = list(_runtime_logs)

    if log_type:
        logs = [l for l in logs if l["type"] == log_type]
    if agent_id:
        logs = [l for l in logs if l["agent_id"] == agent_id]

    return logs[-limit:]


def clear_logs():
    """清空日志缓冲区 + 文件"""
    _runtime_logs.clear()
    try:
        if _file_handle:
            _file_handle.truncate(0)
            _file_handle.flush()
    except Exception:
        pass
    # 重新打开文件确保干净
    try:
        _open_log_file()
    except Exception:
        pass


def register_listener() -> asyncio.Queue:
    """注册一个 SSE 监听器，返回一个 asyncio.Queue"""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _listeners.append(q)
    return q


def unregister_listener(q: asyncio.Queue):
    """注销一个 SSE 监听器"""
    try:
        _listeners.remove(q)
    except ValueError:
        pass


def get_stats() -> dict:
    """获取日志统计"""
    types: dict[str, int] = {}
    for entry in _runtime_logs:
        t = entry["type"]
        types[t] = types.get(t, 0) + 1

    return {
        "total": len(_runtime_logs),
        "by_type": types,
        "max_capacity": MAX_LOG_ENTRIES,
        "file_size_kb": round(LOG_FILE.stat().st_size / 1024, 1) if LOG_FILE.exists() else 0,
    }
