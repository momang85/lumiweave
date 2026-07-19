"""
运行时配置 — 所有可调参数集中管理，持久化到 runtime_config.json。
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from copy import deepcopy

_CONFIG_FILE = Path(__file__).parent / "runtime_config.json"

_DEFAULTS: dict = {
    # ── Agent 调度 ──
    "max_tool_iterations": 60,
    "max_delegate_calls": 10,
    "max_sub_iterations": 5,
    "history_window": 10,
    "agent_session_ttl": 3600,             # session 过期秒数

    # ── 子Agent ──
    "sub_agent_max_tokens": 8192,
    "sub_agent_temperature": 0.3,
    "sub_agent_system_prompt_limit": 8000,
    "sub_agent_timeout": 120,               # 子Agent整体执行超时（秒）
    # ── 缓存 ──
    "delegate_cache_max": 50,

    # ── 命令/代码执行 ──
    "run_command_timeout": 10,
    "code_executor_timeout": 10,            # handle_code_run 默认超时
    "max_list_dir_per_session": 5,
    "max_run_command_per_session": 5,

    # ── 搜索 ──
    "web_search_timeout": 8,                # DuckDuckGo HTTP 超时
    "web_search_proxy": "",                 # HTTP 代理地址（如 http://127.0.0.1:7897）
    "llm_proxy": "",                        # LLM API 代理（优先级高于 web_search_proxy）
    "search_result_limit": 5,               # 搜索返回结果数量
    "serpapi_timeout": 10,                  # Google SerpAPI 超时

    # ── 文件操作 ──
    "file_read_default_lines": 500,
    "search_file_max_results": 50,
    "output_truncate_limit": 8000,          # stdout/stderr 截断长度

    # ── LLM 参数 ──
    "orchestrator_temperature": 0.3,
    "orchestrator_max_tokens": 8192,

    # ── 速率限制 ──
    "llm_rate_limit_rpm": 30,               # 每分钟最大请求数
    "llm_rate_limit_concurrent": 3,          # 最大并发 LLM 调用
    "llm_rate_limit_interval": 0.5,          # 调用最小间隔（秒）

    # ── 功能开关 ──
    "enable_rag": True,
    "enable_web_search": True,
    "enable_tool_fallback": True,
}

_config: dict = {}

def _load():
    global _config
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        else:
            loaded = {}
    except Exception:
        loaded = {}
    _config = deepcopy(_DEFAULTS)
    for k, v in loaded.items():
        if k in _config:
            _config[k] = v

def _save():
    try:
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load()

def get(key: str, default=None):
    return _config.get(key, default)

def get_all() -> dict:
    return deepcopy(_config)

def get_defaults() -> dict:
    return deepcopy(_DEFAULTS)

def update(data: dict) -> dict:
    for k, v in data.items():
        if k in _config:
            orig = _config[k]
            if isinstance(orig, int) and isinstance(v, str) and v.isdigit():
                v = int(v)
            elif isinstance(orig, float) and isinstance(v, str):
                try: v = float(v)
                except ValueError: pass
            elif isinstance(orig, bool) and isinstance(v, str):
                v = v.lower() in ("true", "1", "yes", "on")
            _config[k] = v
    _save()
    return get_all()

def reset():
    global _config
    _config = deepcopy(_DEFAULTS)
    _save()
    return _config
