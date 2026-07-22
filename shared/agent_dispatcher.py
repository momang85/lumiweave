"""
AI Agent Hub — Agent 调度器 v0.5

中央调度 Agent 的工具引擎：
- list_agents(): 列出所有可用子 Agent 的能力清单
- delegate_task(): 调用子 Agent 执行任务并返回结果
- 计划追踪与重规划
"""

from __future__ import annotations

import os as _os
# v2.3: 模块级代理——所有子Agent LLM调用通过代理
if not _os.getenv("HTTPS_PROXY"):
    _proxy = _os.getenv("LLM_PROXY", "")
    if _proxy:
        _os.environ["HTTP_PROXY"] = _proxy
        _os.environ["HTTPS_PROXY"] = _proxy

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from shared.constants import PROVIDER_ENV_MAP, PROVIDER_DEFAULT_MODELS
from typing import Any

logger = logging.getLogger(__name__)

# ─── 常量 ───
_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
_MAX_DELEGATE_CALLS = 10


def _resolve_llm_proxy() -> str:
    """从 runtime_config 或环境变量解析 LLM 代理地址。"""
    try:
        from runtime_config import get as _rc_get
        return _rc_get("llm_proxy", "") or _rc_get("web_search_proxy", "")
    except ImportError:
        return ""


# ══════════════════════════════════════════════
# Agent 注册表
# ══════════════════════════════════════════════

@dataclass
class AgentInfo:
    """子 Agent 的简要信息（供 Hub Agent 查阅）"""
    agent_id: str
    name: str
    description: str
    domain: str
    tags: list[str] = field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    avatar: str = "🤖"


@dataclass
class DelegateResult:
    """单次调派结果"""
    agent_id: str
    agent_name: str
    success: bool
    output: str
    error: str = ""
    tool_calls: int = 0
    duration_ms: float = 0.0


@dataclass
class DispatchSession:
    """调度会话状态"""
    session_id: str
    plan: list[dict[str, Any]] = field(default_factory=list)
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    delegate_results: list[DelegateResult] = field(default_factory=list)
    current_step_index: int = 0
    replan_count: int = 0
    total_delegate_calls: int = 0
    started_at: float = 0.0


class AgentRegistry:
    """Agent 注册表：从 agents/ 目录加载所有 Agent 并提取关键信息（线程安全）"""

    _cache: dict[str, AgentInfo] = {}
    _loaded: bool = False
    _lock: "threading.Lock | None" = None

    @classmethod
    def _ensure_lock(cls):
        if cls._lock is None:
            import threading
            cls._lock = threading.Lock()

    @classmethod
    def load(cls) -> dict[str, AgentInfo]:
        """加载所有 Agent 信息（带缓存 + 线程安全）"""
        cls._ensure_lock()
        with cls._lock:
            if cls._loaded:
                return cls._cache

        cls._cache = {}
        if not _AGENTS_DIR.exists():
            logger.warning(f"Agent 目录不存在: {_AGENTS_DIR}")
            return cls._cache

        import yaml

        for yaml_file in sorted(_AGENTS_DIR.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not data:
                    continue

                meta = data.get("meta", {})
                agent_id = meta.get("id", yaml_file.stem)
                model = data.get("model", {})

                info = AgentInfo(
                    agent_id=agent_id,
                    name=meta.get("name", yaml_file.stem),
                    description=meta.get("description", ""),
                    domain=meta.get("domain", "general"),
                    tags=meta.get("tags", []),
                    model_provider=model.get("provider", ""),
                    model_name=model.get("model_name", ""),
                    avatar=data.get("ui", {}).get("avatar", "🤖"),
                )
                cls._cache[agent_id] = info
            except Exception as e:
                logger.debug(f"跳过 {yaml_file.name}: {e}")

        cls._loaded = True
        logger.info(f"加载 {len(cls._cache)} 个 Agent 到注册表")
        return cls._cache

    @classmethod
    def list_agents(cls, filter_tag: str = "") -> list[AgentInfo]:
        """列出所有 Agent，可选标签过滤"""
        agents = list(cls.load().values())
        if filter_tag:
            tag_lower = filter_tag.lower()
            agents = [a for a in agents if tag_lower in [t.lower() for t in a.tags]]
        return agents

    @classmethod
    def get_agent(cls, agent_id: str) -> AgentInfo | None:
        """按 ID 查找 Agent"""
        return cls.load().get(agent_id)

    @classmethod
    def find_by_tags(cls, tags: list[str]) -> list[AgentInfo]:
        """按标签匹配 Agent（返回排序后的匹配结果）"""
        agents = list(cls.load().values())
        scored = []
        for a in agents:
            a_tags_lower = [t.lower() for t in a.tags]
            score = sum(1 for t in tags if t.lower() in a_tags_lower)
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored]

    @classmethod
    def to_summary_text(cls) -> str:
        """返回所有 Agent 的摘要文本（供 Hub Agent 的 system prompt 补充）"""
        agents = list(cls.load().values())
        if not agents:
            return "(暂无可用子 Agent)"

        lines = ["可用子 Agent 列表：", ""]
        for a in agents:
            tags_str = ", ".join(a.tags[:5]) if a.tags else "通用"
            lines.append(f"  [{a.agent_id}] {a.avatar} {a.name}")
            lines.append(f"      描述: {a.description[:80]}")
            lines.append(f"      领域: {a.domain} | 标签: {tags_str}")
            lines.append("")
        return "\n".join(lines)


# ══════════════════════════════════════════════
# 任务调派引擎
# ══════════════════════════════════════════════

class AgentDispatcher:
    """
    Agent 调派引擎。

    被中央调度 Agent 调用，负责：
    1. 查找目标 Agent 的 YAML 文件
    2. 使用 Runner 执行子任务
    3. 返回结构化结果
    4. 追踪调用次数和计划状态
    """

    def __init__(self):
        self._sessions: dict[str, DispatchSession] = {}
        self._current_session_id: str = ""
        self._session_ttl: int = 3600  # 1 小时自动清理
        self._event_queue: list = []   # v2.6: SSE事件队列（线程安全）

    def _cleanup_expired_sessions(self):
        """清理过期 session 防止内存泄漏"""
        import time
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if hasattr(s, 'started_at') and (now - s.started_at) > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug(f"清理 {len(expired)} 个过期 session")

    # ── 公共 API ──

    def list_agents(self, filter_tag: str = "") -> list[dict]:
        """列出可用 Agent（供 list_agents 工具处理器调用）"""
        agents = AgentRegistry.list_agents(filter_tag)
        result = []
        for a in agents:
            result.append({
                "agent_id": a.agent_id,
                "name": a.name,
                "description": a.description,
                "tags": a.tags,
                "domain": a.domain,
                "avatar": a.avatar,
            })
        return result

    def _emit(self, event_type: str, data: dict):
        """向SSE事件队列推送子Agent事件"""
        self._event_queue.append((event_type, data))

    def delegate_task(
        self,
        agent_id: str,
        task: str,
        context: str = "",
        api_key: str = "",
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        base_url: str = "",
    ) -> dict:
        """
        将任务指派给子 Agent 执行。

        Args:
            agent_id: 目标 Agent ID
            task: 任务描述
            context: 附加上下文
            api_key: LLM API Key（用于执行子 Agent）
            provider: LLM Provider
            model: LLM 模型

        Returns:
            {"success": bool, "output": str, "tool_calls": int, "error": str}
        """
        import time

        # 防无限循环
        sess = self._get_or_create_session()
        if sess.total_delegate_calls >= _MAX_DELEGATE_CALLS:
            return {
                "success": False,
                "output": "",
                "tool_calls": 0,
                "error": f"已达到最大调派次数 ({_MAX_DELEGATE_CALLS})",
            }

        # v2.0: 候选列表（失败时自动换人）
        _fallback_candidates: list = []

        # 查找 Agent（支持精确匹配 + 模糊匹配）
        agent_info = AgentRegistry.get_agent(agent_id)
        if not agent_info:
            # 模糊匹配：尝试部分匹配 ID 或名称
            all_agents = AgentRegistry.list_agents()
            candidates = []
            query_lower = agent_id.lower().replace(" ", "-").replace("_", "-")
            for a in all_agents:
                aid_lower = a.agent_id.lower()
                name_lower = a.name.lower().replace(" ", "-").replace("_", "-")
                if query_lower in aid_lower or aid_lower in query_lower:
                    candidates.append((3, a))  # ID 匹配权重高
                elif query_lower in name_lower or name_lower in query_lower:
                    candidates.append((2, a))  # 名称匹配
                elif any(query_lower in t.lower() for t in a.tags):
                    candidates.append((1, a))  # 标签匹配
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                agent_info = candidates[0][1]
                logger.info(f"模糊匹配: '{agent_id}' -> '{agent_info.agent_id}' ({agent_info.name})")

            # v2.0: 保存候选列表用于失败时自动换人
            _fallback_candidates = candidates[1:] if candidates else []

        if not agent_info:
            return {
                "success": False,
                "output": "",
                "tool_calls": 0,
                "error": f"未找到 Agent: {agent_id}。请先用 list_agents 查看可用 Agent。",
            }

        # 使用实际匹配的 agent_id
        actual_agent_id = agent_info.agent_id
        yaml_path = _AGENTS_DIR / f"{actual_agent_id}.yaml"
        if not yaml_path.exists():
            # 尝试用文件名匹配
            candidates = list(_AGENTS_DIR.glob("*.yaml"))
            found = None
            for c in candidates:
                try:
                    import yaml
                    with open(c, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data and data.get("meta", {}).get("id") == actual_agent_id:
                        found = c
                        break
                except Exception:
                    continue
            yaml_path = found if found else None

        if not yaml_path:
            # v2.5: Agent不存在 → 自动生成
            logger.info(f"Agent '{agent_id}' 未找到，尝试自动生成...")
            try:
                from shared.agent_generator import AgentGenerator
                desc = f"{agent_id} 开发专家。接收开发任务创建代码文件。"
                gen = AgentGenerator()  # 模板模式，无需LLM调用
                new_agent = gen.generate(user_input=desc)
                if new_agent and new_agent.yaml_content:
                    logger.info(f"自动生成Agent成功: {new_agent.agent_id}")
                    # 重新搜索
                    yaml_path = AgentFileStore._find_agent_file(agent_id)
                    if not yaml_path:
                        yaml_path = AgentFileStore._find_agent_file(new_agent.agent_id)
            except Exception as e:
                logger.warning(f"自动生成Agent失败，继续执行: {e}")
            
            if not yaml_path:
                return {
                    "success": False,
                    "output": "",
                    "tool_calls": 0,
                    "error": f"Agent {agent_id} 的 YAML 文件未找到，自动创建也失败",
                }

        # 执行子 Agent — v0.5.1: 复用 orchestrator 的 LLM 配置
        start = time.time()
        try:
            # 读取子 Agent 的 YAML 获取 system_prompt + tools
            sub_system_prompt = ""
            sub_tools: list[dict] = []
            try:
                import yaml
                with open(yaml_path, "r", encoding="utf-8") as f:
                    sub_data = yaml.safe_load(f) or {}
                sub_system_prompt = sub_data.get("system_prompt", "")
                sub_tools = sub_data.get("tools", [])
                sub_model_provider = (sub_data.get("model") or {}).get("provider", "openai")
                sub_model_name = (sub_data.get("model") or {}).get("model_name", "gpt-4o-mini")
            except Exception:
                sub_model_provider = "openai"
                sub_model_name = "gpt-4o-mini"

            # ═══ v0.6.1: 预检 — 子Agent 独立模型选择 ═══
            sub_model_provider = (sub_data.get("model") or {}).get("provider", "openai") if sub_data else "openai"
            sub_model_name = (sub_data.get("model") or {}).get("model_name", "gpt-4o-mini") if sub_data else "gpt-4o-mini"

            preferred_provider = (provider or "").strip()
            preferred_key = (api_key or "").strip()

            # v0.6.1: 优先级改为：子Agent原生Provider(有Key) > orchestrator Provider > 其他降级
            providers_to_try: list[tuple[str, str, str]] = []

            # 1. 子 Agent 原生 provider 优先（如果环境有 Key）
            if sub_model_provider != preferred_provider:
                sub_env_key = {
                    "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY",
                }.get(sub_model_provider, f"{sub_model_provider.upper()}_API_KEY")
                sub_key = os.getenv(sub_env_key, "").strip()
                if sub_key or sub_model_provider == "ollama":
                    providers_to_try.append((sub_model_provider, sub_env_key, sub_model_provider))

            # 2. orchestrator 的 provider（作为备选，或子Agent无独立Key时使用）
            if preferred_provider and preferred_key:
                providers_to_try.append((preferred_provider, "", preferred_provider))

            # 3. 如果子Agent原生provider没装上且和orchestrator不同，补上
            if sub_model_provider not in [p for p, _, _ in providers_to_try]:
                providers_to_try.append((sub_model_provider, "", sub_model_provider))

            # 4. 扫描环境变量中的其他 Provider 作为最后降级
            for prov, env_key in [
                ("deepseek", "DEEPSEEK_API_KEY"),
                ("openai", "OPENAI_API_KEY"),
                ("anthropic", "ANTHROPIC_API_KEY"),
                ("google", "GOOGLE_API_KEY"),
            ]:
                if prov not in [p for p, _, _ in providers_to_try]:
                    providers_to_try.append((prov, env_key, prov))

            # 5. 如果调用方传入 api_key + provider，确保它同时存在
            if api_key and provider and not any(p == provider for p, _, _ in providers_to_try):
                providers_to_try.insert(0, (provider, "", provider))

            # v0.6.1: 子Agent原生Provider找不到Key时，回退到orchestrator Key
            native_prov = sub_model_provider
            native_key = None
            for prov, env_key_str, _ in providers_to_try:
                env_map = {"openai":"OPENAI_API_KEY","deepseek":"DEEPSEEK_API_KEY","anthropic":"ANTHROPIC_API_KEY","google":"GOOGLE_API_KEY"}
                actual_env_key = env_key_str or env_map.get(prov, f"{prov.upper()}_API_KEY")
                key = os.getenv(actual_env_key, "").strip()
                if prov == "ollama": key = "ollama-local"
                if prov == preferred_provider and preferred_key: key = preferred_key
                if key:
                    native_key = key
                    break
            if not native_key:
                # 子Agent原生Provider无Key，使用orchestrator的Key和Provider
                providers_to_try = [(preferred_provider, "", preferred_provider)] if preferred_provider else []
                providers_to_try.append((sub_model_provider, "", sub_model_provider))

            # 尝试每个 Provider 直到找到可用 Key
            effective_provider = ""
            effective_model = ""
            available_key = ""
            last_error = ""

            for prov, env_key_str, _ in providers_to_try:
                env_map = {
                    "openai": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY",
                }
                actual_env_key = env_key_str or env_map.get(prov, f"{prov.upper()}_API_KEY")
                key = os.getenv(actual_env_key, "").strip() if not (preferred_provider == prov and preferred_key) else preferred_key

                if prov == "ollama":
                    key = "ollama-local"

                if key:
                    effective_provider = prov
                    available_key = key
                    # v2.2: 子Agent快模型覆盖——运行时配置可指定 sub_agent_model
                    _sub_fast_model = ""
                    try:
                        from runtime_config import get as _rc_get
                        _sub_fast_model = _rc_get("sub_agent_model", "")
                    except ImportError:
                        pass
                    if _sub_fast_model:
                        effective_model = _sub_fast_model
                    elif preferred_provider == prov and model:
                        effective_model = model
                    elif prov == sub_model_provider:
                        effective_model = sub_model_name
                    else:
                        effective_model = {
                            "deepseek": "deepseek-chat", "openai": "gpt-4o-mini",
                            "anthropic": "claude-3-5-sonnet-20241022", "google": "gemini-2.0-flash",
                        }.get(prov, "gpt-4o-mini")
                    break
                else:
                    last_error = prov

            if not available_key:
                elapsed = (time.time() - start) * 1000
                return {
                    "success": False, "output": "", "tool_calls": 0,
                    "agent_name": agent_info.name,
                    "needs_key": True,
                    "needed_provider": sub_model_provider,
                    "needed_model": sub_model_name,
                    "env_key": env_map.get(sub_model_provider, f"{sub_model_provider.upper()}_API_KEY"),
                    "error": (
                        f"子 Agent「{agent_info.name}」需要 API Key，"
                        f"但所有 Provider 均未配置。请在前端 API 设置中配置任一 Provider 的 Key。"
                    ),
                }

            # v0.6.1: 检索子Agent历史经验
            experience_context = ""
            try:
                from shared.agent_memory import retrieve_experience
                experiences = retrieve_experience(actual_agent_id, task, top_k=2)
                if experiences:
                    exp_lines = []
                    for e in experiences:
                        exp_lines.append(f"- 上次: {e['task'][:80]}; 结果: {e['result'][:80]}")
                    experience_context = f"【历史经验】\n" + "\n".join(exp_lines) + "\n\n"
            except ImportError:
                pass

            # 构建子 Agent 调用的消息：system_prompt + 经验 + 上下文 + task
            sub_messages: list[dict] = []
            if sub_system_prompt:
                sub_messages.append({"role": "system", "content": sub_system_prompt[:8000]})
            full_prompt = experience_context + task
            if context:
                full_prompt = f"【上下文信息】\n{context}\n\n【需要完成的任务】\n{full_prompt}"

            # 构建子 Agent 的工具（转换为 OpenAI 格式）
            # v0.6: 自动注入文件工具，让子 Agent 可以直接写项目文件到 projects/ 目录
            _injected_file_tools = [
                {
                    "name": "write_file",
                    "description": "将内容写入指定文件路径（如 projects/项目名/backend/main.py）。路径相对于项目根目录。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "文件相对路径"},
                        {"name": "content", "type": "string", "required": True, "description": "文件内容"},
                        {"name": "overwrite", "type": "boolean", "required": False, "description": "是否覆盖"},
                    ],
                },
                {
                    "name": "read_file",
                    "description": "读取文件内容。可读自己或其他Agent写的文件，查看接口格式、字段定义。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "文件相对路径"},
                    ],
                },
                {
                    "name": "list_dir",
                    "description": "列出目录内容。查看其他Agent创建了哪些文件。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "目录相对路径"},
                    ],
                },
                {
                    "name": "search_file",
                    "description": "搜索文件。查找其他Agent的生成文件（如 pattern='*.py' 找后端代码）。",
                    "type": "function",
                    "parameters": [
                        {"name": "pattern", "type": "string", "required": True, "description": "文件名通配符，如 *.py"},
                        {"name": "directory", "type": "string", "required": False, "description": "搜索目录"},
                    ],
                },
                {
                    "name": "send_to_agent",
                    "description": "给另一个Agent发消息并获取回复。用于确认接口格式、询问字段含义。",
                    "type": "function",
                    "parameters": [
                        {"name": "target_agent_id", "type": "string", "required": True, "description": "目标Agent的ID"},
                        {"name": "message", "type": "string", "required": True, "description": "要发送的消息/问题"},
                    ],
                },
                {
                    "name": "write_context",
                    "description": "写入共享上下文让其他Agent读取。声明接口约定如字段名、数据格式。",
                    "type": "function",
                    "parameters": [
                        {"name": "project", "type": "string", "required": True, "description": "项目目录名"},
                        {"name": "section", "type": "string", "required": False, "description": "分区名（api_fields等）"},
                        {"name": "content", "type": "string", "required": True, "description": "内容"},
                    ],
                },
            ]
            # 合并去重：YAML 中已定义的工具优先保留
            existing_names = {t.get("name") for t in sub_tools if isinstance(t, dict)}
            for inj in _injected_file_tools:
                if inj["name"] not in existing_names:
                    sub_tools.append(inj)

            sub_tool_defs: list[dict] = []
            for t in sub_tools:
                if isinstance(t, dict) and t.get("name"):
                    params_props = {}
                    param_required = []
                    for p in t.get("parameters", []):
                        if isinstance(p, dict):
                            params_props[p.get("name", "p")] = {
                                "type": p.get("type", "string"),
                                "description": p.get("description", ""),
                            }
                            if p.get("required"):
                                param_required.append(p.get("name", "p"))
                    sub_tool_defs.append({
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": {
                                "type": "object",
                                "properties": params_props if params_props else {},
                                "required": param_required,
                            },
                        },
                    })

            # v2.6: 发送子Agent派发事件
            self._emit('agent_dispatch', {
                'agent_id': actual_agent_id,
                'agent_name': agent_info.name,
                'task': full_prompt[:200],
                'layer': 3
            })
            # 使用 orchestrator 的 LLM（同一 API Key）执行子任务
            # effective_provider / effective_model 已在预检阶段定义

            # 构建 LLM 配置
            from shared.ir_models import ProviderConfig, ProviderType, MessageIR, ToolDefIR, ToolCallIR
            try:
                pt = ProviderType(effective_provider)
            except ValueError:
                pt = ProviderType.OPENAI

            llm_config = ProviderConfig(
                provider=pt,
                model=effective_model,
                api_key=available_key,
                base_url=base_url or os.getenv(f"{effective_provider.upper()}_BASE_URL", ""),
                proxy=os.getenv("LLM_PROXY", _resolve_llm_proxy()),
                timeout=20,      # v0.6.1: 子Agent HTTP 超时 20s（orchestrator 会重试）
                max_retries=1,   # v0.6.1: 最多重试1次，orchestrator 层会兜底
            )

            # 创建适配器直接调用（不经过 AgentRunner）
            from shared.adapter_registry import get_adapter_map
            adapter_map = get_adapter_map()
            adapter_cls = adapter_map.get(pt, adapter_map[ProviderType.OPENAI])
            adapter = adapter_cls(llm_config)

            # 构建 IR messages 和 tools
            # v2.1: 注入子Agent模式指令——优先创建文件，不要浪费迭代在探索上
            _sub_agent_mode = (
                "【子Agent模式】你正在被AI调度中心调用完成一个具体任务。\n"
                "关键规则：\n"
                "1. 第一步就用 write_file 创建要求的文件，不要先 list_dir/read_file 探索\n"
                "2. 你只有有限的工具调用次数，优先用于创建文件而非探索\n"
                "3. 创建完文件后，用 write_context 声明你的接口约定（字段名、数据格式），方便其他Agent对接\n"
                "4. 完成后用 read_file 确认文件存在且内容完整\n\n"
            )
            sub_prompt = _sub_agent_mode + sub_system_prompt[:8000]
            ir_messages = [MessageIR(role="system", content=sub_prompt)]
            ir_messages.append(MessageIR(role="user", content=full_prompt))

            ir_tools: list[ToolDefIR] = []
            for td in sub_tool_defs:
                fn = td["function"]
                ir_tools.append(ToolDefIR(
                    name=fn["name"],
                    description=fn["description"],
                    parameters=fn["parameters"].get("properties", {}),
                    required=fn["parameters"].get("required", []),
                ))

            # 执行子任务（从运行时配置读取迭代次数）
            # v0.5.2: 部分模型不支持 tools，失败时自动回退到无 tools 调用
            result_parts: list[str] = []
            tool_call_count = 0
            try:
                from runtime_config import get as _rc_get
                MAX_SUB_ITERATIONS = _rc_get("max_sub_iterations", 5)
                sub_max_tokens = _rc_get("sub_agent_max_tokens", 8192)
                sub_timeout = _rc_get("sub_agent_timeout", 120)
            except ImportError:
                MAX_SUB_ITERATIONS = 5
                sub_max_tokens = 8192
                sub_timeout = 120
            use_tools = bool(ir_tools)
            sub_start_time = time.time()
            for _sub_iter in range(MAX_SUB_ITERATIONS):
                # v0.6.1: 内部超时检查，防止单轮卡住
                if time.time() - sub_start_time > sub_timeout:
                    result_parts.append(f"[警告] 子Agent执行超过 {sub_timeout} 秒，已强制终止。当前已执行 {_sub_iter} 轮，{tool_call_count} 次工具调用。")
                    break
                try:
                    resp = adapter.chat(
                        messages=ir_messages,
                        tools=ir_tools if use_tools else None,
                        temperature=0.3,
                        max_tokens=sub_max_tokens,
                    )
                except Exception as e:
                    error_str = str(e)
                    # 如果模型不支持 tools，自动回退到无 tools 调用
                    if use_tools and any(kw in error_str.lower() for kw in ("tool", "tool_choice", "function", "unsupported")):
                        use_tools = False
                        try:
                            resp = adapter.chat(
                                messages=ir_messages,
                                tools=None,
                                temperature=0.3,
                                max_tokens=sub_max_tokens,
                            )
                        except Exception as fallback_err:
                            if result_parts:
                                break
                            raise fallback_err
                    else:
                        if result_parts:
                            break
                        raise


                if resp.tool_calls:
                    tool_call_count += 1
                    for tc in resp.tool_calls:
                        # v0.6: 子 Agent 直接调用真实工具处理器，而不是模拟占位
                        # 这样 frontend 子 Agent 可以直接 write_file 到 projects/ 目录
                        from runner.tool_handlers import get_handler as _sub_get_handler
                        handler = _sub_get_handler(tc.name)
                        real_tool_result: str | None = None
                        if handler and tc.name != "delegate_task":  # 防止子 Agent 无限递归委托
                            try:
                                real_tool_result = handler(
                                    **tc.arguments,
                                    _api_key=available_key,
                                    _provider=effective_provider,
                                    _model=effective_model,
                                    _base_url=base_url,
                                )
                                # 对于写文件工具，记录摘要
                                if tc.name in ("write_file", "read_file"):
                                    result_parts.append(f"[工具: {tc.name}] 路径: {tc.arguments.get('filePath', tc.arguments.get('path', 'unknown'))}")
                                else:
                                    result_parts.append(f"[工具: {tc.name}] 参数: {json.dumps(tc.arguments, ensure_ascii=False)}")
                            except Exception as e:
                                result_parts.append(f"[工具: {tc.name}] 执行失败: {str(e)}")
                        else:
                            result_parts.append(f"[工具: {tc.name}] 参数: {json.dumps(tc.arguments, ensure_ascii=False)}")

                        tool_result = real_tool_result if real_tool_result is not None else json.dumps(
                            {"info": f"工具 {tc.name} 已调用，参数: {json.dumps(tc.arguments, ensure_ascii=False)}",
                             "note": "子Agent工具在实际运行时会由Runner处理"},
                            ensure_ascii=False,
                        )
                        ir_messages.append(MessageIR.assistant(
                            content=resp.content,
                            tool_calls=[ToolCallIR(id=tc.id, name=tc.name, arguments=tc.arguments)],
                        ))
                        ir_messages.append(MessageIR.tool_result(
                            tool_call_id=tc.id or f"sub-{_sub_iter}",
                            name=tc.name,
                            content=tool_result,
                        ))
                elif resp.content:
                    result_parts.append(resp.content)
                    ir_messages.append(MessageIR.assistant(content=resp.content))
                    break
                else:
                    break

            final_output = "\n\n".join(result_parts) if result_parts else "(子 Agent 未返回内容)"

            if not api_key and not llm_config.api_key:
                # 无 API Key：返回子 Agent 的配置文件信息，让 orchestrator 自行推理
                final_output = (
                    f"[子 Agent 信息] 名称: {agent_info.name}\n"
                    f"描述: {agent_info.description}\n"
                    f"领域: {agent_info.domain}\n"
                    f"模型: {sub_model_provider}/{sub_model_name}\n"
                    f"能力: {sub_system_prompt[:500] if sub_system_prompt else '(无系统提示)'}\n\n"
                    f"[提示] 由于缺少 {effective_provider.upper()}_API_KEY，无法实际运行子 Agent。"
                    f"请在 ApiKeyModal 中配置后重试。\n\n"
                    f"[任务] {task}\n\n"
                    f"[建议处理方式] 基于以上 Agent 信息，由你（调度中心）代为回答。"
                )

            elapsed = (time.time() - start) * 1000

            # v2.1: 检测 Agent 是否只探索未创建——如果 task 要求写文件但 Agent 没用 write_file，标记警告
            _task_lower = task.lower()
            _expects_creation = any(kw in _task_lower for kw in ("创建", "写", "create", "write", "生成"))
            _has_write = any("write_file" in p for p in result_parts)
            if _expects_creation and not _has_write:
                final_output = (
                    f"⚠️ [调度中心警告] 本次委托要求创建文件，但Agent未使用 write_file。\n"
                    f"Agent只做了以下操作：\n" + final_output + "\n\n"
                    f"[调度中心建议] 请重新委托，并在task中明确要求'第一步就用write_file创建文件'。"
                )
                # 标记为失败以触发重试/换人
                sess.delegate_results.append(DelegateResult(
                    agent_id=actual_agent_id, agent_name=agent_info.name,
                    success=False, output=final_output, tool_calls=tool_call_count, duration_ms=elapsed,
                ))
                sess.total_delegate_calls += 1
                return {"success": False, "output": final_output, "tool_calls": tool_call_count,
                        "agent_name": agent_info.name,
                        "error": "Agent未创建要求的文件（未使用write_file）"}

            # v2.6: 发送子Agent结果事件
            self._emit('agent_result', {
                'agent_id': actual_agent_id,
                'agent_name': agent_info.name,
                'success': True,
                'tool_calls': tool_call_count,
                'output_snippet': final_output[:200],
                'layer': 3
            })
            delegate_result = DelegateResult(
                agent_id=actual_agent_id,
                agent_name=agent_info.name,
                success=True,
                output=final_output,  # v0.6: 不再截断，sub-agent 完整输出传给 orchestrator
                tool_calls=tool_call_count,
                duration_ms=elapsed,
            )
            sess.delegate_results.append(delegate_result)
            sess.total_delegate_calls += 1

            # v0.6.1: 存储子Agent经验
            try:
                from shared.agent_memory import store_experience
                store_experience(
                    agent_id=actual_agent_id,
                    agent_name=agent_info.name,
                    task=task[:500],
                    result=final_output[:500],
                    tags=agent_info.tags,
                )
            except ImportError:
                pass

            logger.info(
                f"委托 {agent_info.name}({actual_agent_id}) 完成: "
                f"{elapsed:.0f}ms, {tool_call_count} tool calls, "
                f"输出长度: {len(final_output)} 字符"
            )

            # v0.7: 记录评分
            try:
                from shared.agent_memory import record_agent_result
                record_agent_result(actual_agent_id, agent_info.name, True, elapsed)
            except ImportError:
                pass

            return {
                "success": True,
                "output": final_output,  # v0.6: 完整输出
                "tool_calls": tool_call_count,
                "agent_name": agent_info.name,
                "error": "",
            }

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            error_str = str(e)

            # 检测 401/认证错误 -> 返回 needs_key 信号
            is_auth_error = any(kw in error_str.lower() for kw in
                ("401", "unauthorized", "api key", "incorrect api key", "invalid api key"))

            if is_auth_error:
                delegate_result = DelegateResult(
                    agent_id=actual_agent_id,
                    agent_name=agent_info.name,
                    success=False,
                    output="",
                    error=error_str,
                    duration_ms=elapsed,
                )
                sess.delegate_results.append(delegate_result)
                sess.total_delegate_calls += 1

                env_key_map = {
                    "openai": "OPENAI_API_KEY",
                    "deepseek": "DEEPSEEK_API_KEY",
                    "anthropic": "ANTHROPIC_API_KEY",
                    "google": "GOOGLE_API_KEY",
                }
                needed_env_key = env_key_map.get(effective_provider, f"{effective_provider.upper()}_API_KEY")

                return {
                    "success": False,
                    "output": "",
                    "tool_calls": 0,
                    "agent_name": agent_info.name,
                    "needs_key": True,
                    "needed_provider": effective_provider,
                    "needed_model": effective_model,
                    "env_key": needed_env_key,
                    "error": f"{effective_provider.upper()} API Key 无效或已过期。请在前端 API 设置中重新配置 {effective_provider.upper()} Key，或将此 Agent 的 model_provider 改为有可用 Key 的厂商。{error_str[:200]}",
                }

            delegate_result = DelegateResult(
                agent_id=actual_agent_id,
                agent_name=agent_info.name,
                success=False,
                output="",
                error=error_str,
                duration_ms=elapsed,
            )
            sess.delegate_results.append(delegate_result)
            sess.total_delegate_calls += 1

            logger.error(f"委托 {agent_info.name} 失败: {e}")

            # v0.7: 记录失败评分
            try:
                from shared.agent_memory import record_agent_result
                record_agent_result(actual_agent_id, agent_info.name, False, elapsed)
            except ImportError:
                pass

            # 增强错误提示
            hint = ""
            lower_err = error_str.lower()
            if not error_str and tool_call_count == 0:
                # 连接失败且无错误信息 = 大概率网络/代理问题
                error_str = "无法连接到LLM服务（请求超时或网络不通）。请检查：1) Settings中是否配置了LLM代理 2) API Key是否有效 3) 网络是否正常"
                lower_err = error_str.lower()
            if any(kw in lower_err for kw in ("connection", "timeout", "timed out", "refused", "reset", "无法连接")):
                hint = (
                    f"（网络不通：请在 Settings → 运行参数 中设置 llm_proxy，"
                    f"例如 http://127.0.0.1:7897）"
                )

            # v2.6: 发送子Agent失败事件
            self._emit('agent_result', {
                'agent_id': actual_agent_id,
                'agent_name': agent_info.name,
                'success': False,
                'tool_calls': tool_call_count,
                'error': error_str[:200],
                'layer': 3
            })
            # v2.0: 失败自动换人 — 尝试候选列表中下一个 Agent
            if _fallback_candidates:
                next_agent = _fallback_candidates.pop(0)[1]
                logger.info(f"自动换人: '{agent_id}' 失败 → 尝试 '{next_agent.agent_id}' ({next_agent.name})")
                return self.delegate_task(
                    agent_id=next_agent.agent_id,
                    task=task,
                    context=context,
                    api_key=api_key,
                    provider=provider,
                    model=model,
                    base_url=base_url,
                )

            return {
                "success": False,
                "output": "",
                "tool_calls": 0,
                "agent_name": agent_info.name,
                "error": f"{error_str}{hint}",
            }

    def get_session_status(self) -> dict:
        """获取当前调度会话状态"""
        sess = self._get_or_create_session()
        return {
            "session_id": sess.session_id,
            "total_delegate_calls": sess.total_delegate_calls,
            "replan_count": sess.replan_count,
            "results": [
                {
                    "agent": r.agent_name,
                    "success": r.success,
                    "output_preview": r.output[:200] if r.success else r.error,
                    "tool_calls": r.tool_calls,
                }
                for r in sess.delegate_results
            ],
        }

    def reset(self):
        """重置当前会话"""
        self._current_session_id = ""
        self._sessions.clear()

    # ── 内部 ──

    def _get_or_create_session(self) -> DispatchSession:
        import time
        # 定期清理过期 session
        self._cleanup_expired_sessions()

        if self._current_session_id and self._current_session_id in self._sessions:
            return self._sessions[self._current_session_id]

        sid = str(uuid.uuid4())[:12]
        self._current_session_id = sid
        self._sessions[sid] = DispatchSession(session_id=sid, started_at=time.time())
        return self._sessions[sid]


# ══════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════

_dispatcher: AgentDispatcher | None = None


def get_dispatcher() -> AgentDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AgentDispatcher()
    return _dispatcher


def reset_dispatcher():
    global _dispatcher
    if _dispatcher:
        _dispatcher.reset()
    _dispatcher = AgentDispatcher()


__all__ = [
    "AgentInfo", "DelegateResult", "DispatchSession",
    "AgentRegistry", "AgentDispatcher",
    "get_dispatcher", "reset_dispatcher",
]
