"""
AI Agent Hub — Builder Backend (FastAPI)

提供:
- Agent CRUD API
- 实时聊天（SSE 流式输出）
- 知识库上传 & RAG 检索
- 模板市场
- Agent YAML 导入/导出
"""

from __future__ import annotations

# v2.3: 最早期代理注入——在任何 adapter/openai 导入前设置
import os as _os
_PROXY = _os.getenv("LLM_PROXY", "")
if _PROXY:
    _os.environ["HTTP_PROXY"] = _PROXY
    _os.environ["HTTPS_PROXY"] = _PROXY
del _os, _PROXY

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# ── 确保能找到 runner 模块 ──
RUNNER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "runner")
sys.path.insert(0, RUNNER_DIR)

from agent_service import (
    AgentRecord,
    save_agent,
    load_agent,
    list_agents,
    delete_agent,
    import_from_yaml,
)
from rag_engine import (
    add_knowledge,
    search_knowledge,
    delete_knowledge,
    get_knowledge_stats,
)
from templates_data import BUILTIN_TEMPLATES

# ── 增强路由（v0.3） ──
try:
    from enhanced_routes import router as enhanced_router
    _HAS_ENHANCED = True
except ImportError:
    enhanced_router = None
    _HAS_ENHANCED = False

# ── 应用初始化 ──

app = FastAPI(title="AI Agent Hub Builder API", version="0.5.1")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 确保上传目录存在 ──
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════
# Pydantic 模型
# ══════════════════════════════════════════════

class AgentCreate(BaseModel):
    name: str = "我的 Agent"
    description: str = ""
    mode: str = "simple"               # v0.5
    mode_config: dict | None = None    # v0.5
    system_prompt: str = "你是一个有用的助手。"
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    tools: list[dict] = []
    tags: list[str] = []
    avatar: str = "🤖"
    suggested_questions: list[str] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    mode: Optional[str] = None               # v0.5
    mode_config: Optional[dict] | None = None  # v0.5
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[list[dict]] = None
    tags: Optional[list[str]] = None
    avatar: Optional[str] = None
    suggested_questions: Optional[list[str]] = None


class ChatRequest(BaseModel):
    agent_id: str
    message: str
    enable_rag: bool = True
    provider: str = "openai"           # v0.5: 已废弃
    api_key: str = ""                  # v0.5: 前端 sessionStorage Key（dev 环境，生产用 env var）
    api_base: str = ""                 # v0.5: 自定义 API 地址
    history: list[dict] = []           # v0.4: 前端对话历史
    history_window: int = 10           # v0.4: 保留最近 N 轮对话
    session_id: str = ""               # v0.6: 前端会话 ID，用于日志关联


class ProviderCheckRequest(BaseModel):
    """检查 Provider 是否可用（是否有 API Key）"""
    provider: str


class TemplateCreate(BaseModel):
    template_id: str


class YAMLImport(BaseModel):
    yaml_content: str


# ══════════════════════════════════════════════
# Agent CRUD
# ══════════════════════════════════════════════

@app.get("/api/agents")
def api_list_agents():
    """列出所有已创建的 Agent"""
    agents = list_agents()
    return {"agents": [a.to_dict() for a in agents], "count": len(agents)}


@app.post("/api/agents")
def api_create_agent(data: AgentCreate):
    """创建新 Agent"""
    record = AgentRecord(
        agent_id=str(uuid.uuid4())[:12],
        **data.model_dump(),
    )
    save_agent(record)
    return {"agent": record.to_dict(), "message": "创建成功"}


@app.get("/api/agents/{agent_id}")
def api_get_agent(agent_id: str):
    """获取 Agent 详情"""
    record = load_agent(agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")
    return {"agent": record.to_dict()}


@app.put("/api/agents/{agent_id}")
def api_update_agent(agent_id: str, data: AgentUpdate):
    """更新 Agent"""
    record = load_agent(agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")

    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(record, key, value)

    save_agent(record)
    return {"agent": record.to_dict(), "message": "更新成功"}


@app.delete("/api/agents/{agent_id}")
def api_delete_agent(agent_id: str):
    """删除 Agent"""
    delete_knowledge(agent_id)
    if delete_agent(agent_id):
        return {"message": "删除成功"}
    raise HTTPException(404, "Agent 不存在")


@app.get("/api/agents/{agent_id}/export")
def api_export_agent(agent_id: str):
    """导出 Agent 为 YAML"""
    record = load_agent(agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")
    yaml_str = record.to_yaml()
    return {"yaml": yaml_str}


@app.post("/api/agents/import")
def api_import_agent(data: YAMLImport):
    """从 YAML 导入 Agent"""
    try:
        record = import_from_yaml(data.yaml_content)
        return {"agent": record.to_dict(), "message": "导入成功"}
    except Exception as e:
        raise HTTPException(400, f"YAML 解析失败: {e}")


# ══════════════════════════════════════════════
# 多 Provider 聊天（SSE 流式输出）v0.4
# ══════════════════════════════════════════════

# ── 确保 shared 模块可导入 ──
_SHARED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "shared")
sys.path.insert(0, os.path.dirname(_SHARED_DIR))

# Provider → 环境变量映射
_PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}
_PROVIDER_DEFAULT_BASE = {
    "openai": "",
    "anthropic": "",
    "google": "",
    "deepseek": "https://api.deepseek.com",
    "ollama": "http://localhost:11434",
}


async def _chat_generator_v4(
    record: "AgentRecord",
    user_msg: str,
    enable_rag: bool,
    api_key: str,
    api_base: str,
    history: list[dict],
    history_window: int = 10,
):
    """
    多 Provider SSE 聊天生成器 v0.4

    将选中的 Agent 定义（system_prompt + tools）+ 裁剪后的对话历史 + 知识库 RAG
    发送到指定 Provider API，流式返回结果。
    """
    from shared.ir_models import (
        ProviderType, ProviderConfig, MessageIR, ToolDefIR, ToolCallIR,
    )

    # ── 强制使用 Agent 配置的 Provider + Model ──
    # v0.5: 运行时忽略 req.provider，强制使用 Agent 自身配置
    provider_lower = (record.model_provider or "openai").lower().strip()
    try:
        provider_type = ProviderType(provider_lower)
    except ValueError:
        provider_type = ProviderType.OPENAI
        provider_lower = "openai"

    model = record.model_name or "gpt-4o-mini"

    # ── 获取 API Key（优先级：前端 sessionStorage > 环境变量） ──
    effective_key = api_key
    if not effective_key and provider_lower in _PROVIDER_ENV_KEYS:
        effective_key = os.getenv(_PROVIDER_ENV_KEYS[provider_lower], "")
    if not effective_key and provider_lower == "ollama":
        effective_key = "ollama-local"

    if not effective_key:
        env_key = _PROVIDER_ENV_KEYS.get(provider_lower, "API_KEY")
        yield f"data: {json.dumps({'type': 'no_api_key', 'content': f'请配置 {provider_lower.upper()} API Key（Agent 绑定的 Provider: {record.model_provider}）', 'provider': provider_lower, 'env_key': env_key, 'agent_provider': record.model_provider, 'agent_model': record.model_name}, ensure_ascii=False)}\n\n"
        return

    base_url = api_base or _PROVIDER_DEFAULT_BASE.get(provider_lower, "")

    # ── 构建工具定义 ──
    ir_tools = []
    for tool in record.tools:
        tool_name = (tool.get("name") or "").strip()
        if not tool_name:
            continue  # 跳过空名称工具
            
        props = tool.get("properties", {})
        if not props:
            params = tool.get("parameters", [])
            if isinstance(params, list):
                props = {}
                for p in params:
                    if isinstance(p, dict):
                        props[p.get("name", "param")] = {
                            "type": p.get("type", "string"),
                            "description": p.get("description", ""),
                        }
        ir_tools.append(ToolDefIR(
            name=tool_name,
            description=tool.get("description", ""),
            parameters=props,
            required=tool.get("required", []),
        ))

    # ── v0.5: 注入 search_memory 工具（如尚未定义） ──
    if not any(t.name == "search_memory" for t in ir_tools):
        ir_tools.append(ToolDefIR(
            name="search_memory",
            description="搜索对话记忆库——当推理卡壳、需要回溯之前被裁剪的对话记录时使用。返回原始历史消息。",
            parameters={
                "query": {"type": "string", "description": "搜索关键词（如'用户之前提到的API版本'），留空返回最近记录"},
                "top_k": {"type": "integer", "description": "返回条数，默认10"},
            },
            required=[],
        ))

    # ── v0.5: system_prompt(钉子) + 动态80%裁剪 + 非破坏性卸载 + RAG ──
    from shared.token_counter import count_tokens, get_input_limit, trim_context, WARN_THRESHOLD_RATIO
    from shared.conversation_memory import get_memory

    messages = [MessageIR.system(record.system_prompt)]  # 钉子：始终完整保留

    # 注入对话历史
    if history:
        for h in history:
            role = h.get("role", "user")
            content = h.get("content", "")
            if role in ("user", "assistant"):
                messages.append(MessageIR(role=role, content=str(content)))

    # RAG 上下文注入
    if enable_rag and record.agent_id:
        try:
            from rag_engine import get_knowledge_stats as _kb_stats
            _stats = _kb_stats(record.agent_id)
            if _stats.get("exists") and _stats.get("chunks", 0) > 0:
                knowledge_results = search_knowledge(record.agent_id, user_msg, top_k=2)
                if knowledge_results:
                    kb_parts = []
                    kb_tokens = 0
                    for r in knowledge_results:
                        part = f"[{r['source']}] {r['content'][:800]}"
                        kb_tokens += count_tokens(part, model)
                        if kb_tokens > 3000:
                            break
                        kb_parts.append(part)
                    if kb_parts:
                        messages.append(MessageIR.system(f"参考知识：\n" + "\n\n".join(kb_parts)))
                        yield f"data: {json.dumps({'type': 'info', 'content': f'已注入 {len(kb_parts)} 条知识库上下文'}, ensure_ascii=False)}\n\n"
                    else:
                        _n = _stats['chunks']
                        yield f"data: {json.dumps({'type': 'info', 'content': f'知识库存在（{_n}块），但未匹配到相关内容'}, ensure_ascii=False)}\n\n"
                else:
                    _n = _stats['chunks']
                    yield f"data: {json.dumps({'type': 'info', 'content': f'知识库存在（{_n}块），检索返回空'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'info', 'content': '知识库为空或无匹配，跳过RAG注入'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'info', 'content': f'RAG注入跳过（{str(e)[:100]}）'}, ensure_ascii=False)}\n\n"

    messages.append(MessageIR.user(user_msg))

    # ── v0.5 裁剪：80% 动态阈值 + 非破坏性卸载 ──
    raw_messages_for_count = [{"role": m.role, "content": m.content or ""} for m in messages]
    estimated_tokens = count_tokens(str(raw_messages_for_count), model)
    input_limit = get_input_limit(model)
    warn_threshold = int(input_limit * WARN_THRESHOLD_RATIO)

    trimmed_raw, offloaded = trim_context(
        raw_messages_for_count, model=model, keep_last_n=history_window,
    )

    # 非破坏性卸载：保存被裁剪的消息到 SQLite
    if offloaded:
        session_id = f"{record.agent_id}_{int(time.time())}"
        get_memory().archive(record.agent_id, session_id, offloaded)
        yield f"data: {json.dumps({'type': 'info', 'content': f'已存档 {len(offloaded)} 条旧消息（可用 search_memory 回溯）', 'offloaded': len(offloaded)}, ensure_ascii=False)}\n\n"

    messages = [MessageIR(role=m["role"], content=m.get("content", "")) for m in trimmed_raw]
    estimated_tokens = count_tokens(str(trimmed_raw), model)

    usage_pct = estimated_tokens * 100 // input_limit if input_limit else 0
    yield f"data: {json.dumps({'type': 'info', 'content': f'上下文: ~{estimated_tokens}/{input_limit:,} tokens ({usage_pct}%, 预警线 80%)', 'tokens': estimated_tokens, 'usage_pct': usage_pct}, ensure_ascii=False)}\n\n"

    # ── 创建适配器并流式调用 ──
    try:
        from shared.adapter_registry import get_adapter_map

        from runtime_config import get as _cfg_get
        llm_proxy = os.getenv("LLM_PROXY", "") or _cfg_get("llm_proxy", "") or _cfg_get("web_search_proxy", "")

        config = ProviderConfig(
            provider=provider_type,
            model=model,
            api_key=effective_key,
            base_url=base_url,
            proxy=llm_proxy,
            timeout=120,
        )

        adapter_cls = get_adapter_map().get(provider_type)
        if not adapter_cls:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Provider {provider} 适配器未实现'}, ensure_ascii=False)}\n\n"
            return

        adapter = adapter_cls(config)

        # ══════════════════════════════════════════════
        # v0.5: 工具调用循环（非流式检测 + 执行 → 流式输出最终文本）
        # ══════════════════════════════════════════════
        from runtime_config import get as _cfg_get
        MAX_TOOL_ITERATIONS = _cfg_get("max_tool_iterations", 60)
        tool_call_count = 0

        # 导入工具处理器
        try:
            from runner.tool_handlers import get_handler as _get_tool_handler
        except ImportError:
            try:
                import sys, os as _os
                _root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
                sys.path.insert(0, _root)
                from runner.tool_handlers import get_handler as _get_tool_handler
            except ImportError:
                _get_tool_handler = None

        def _parse_xml_tool_calls(content: str) -> list[dict]:
            """从文本中解析 XML 格式的工具调用（第三方 API fallback）"""
            if not content:
                return []
            import re
            # 匹配 <||DSML||invoke name="xxx">... 格式
            pattern = r'<\|\|DSML\|\|invoke\s+name="([^"]+)">(.*?)</\|\|DSML\|\|invoke>'
            matches = re.findall(pattern, content, re.DOTALL)
            if not matches:
                # 尝试匹配更简单的 <tool name="xxx"> 格式
                pattern2 = r'<tool\s+name="([^"]+)">(.*?)</tool>'
                matches = re.findall(pattern2, content, re.DOTALL)
            if not matches:
                # 尝试匹配 <action>...{"tool":"xxx"}...</action> 格式
                pattern3 = r'<ACTION>\s*(\{.*?\})\s*</ACTION>'
                matches3 = re.findall(pattern3, content, re.DOTALL)
                if matches3:
                    result = []
                    for m in matches3:
                        try:
                            obj = json.loads(m)
                            tool_name = obj.get("tool") or obj.get("name")
                            if tool_name:
                                result.append({"name": tool_name, "arguments": obj.get("params", obj)})
                        except json.JSONDecodeError:
                            pass
                    return result

            result = []
            for name, inner in matches:
                # 解析参数
                args = {}
                param_pattern = r'<\|\|DSML\|\|parameter\s+name="([^"]+)"[^>]*>(.*?)</\|\|DSML\|\|parameter>'
                params = re.findall(param_pattern, inner, re.DOTALL)
                for pname, pval in params:
                    args[pname] = pval.strip()
                if not args:
                    # 尝试简单键值对
                    param_pattern2 = r'<param\s+name="([^"]+)">(.*?)</param>'
                    params2 = re.findall(param_pattern2, inner, re.DOTALL)
                    for pname, pval in params2:
                        args[pname] = pval.strip()
                result.append({"name": name, "arguments": args})
            return result

        # v0.5.1: 有工具时通知前端切换到编排面板
        if ir_tools:
            yield f"data: {json.dumps({'type': 'orchestration_start'}, ensure_ascii=False)}\n\n"

        while ir_tools and tool_call_count < MAX_TOOL_ITERATIONS:
            try:
                # v0.5.1: 发送进度事件（避免前端卡死）
                if tool_call_count == 0:
                    yield f"data: {json.dumps({'type': 'info', 'content': '正在分析任务...'}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'info', 'content': f'正在处理工具调用结果（第 {tool_call_count} 轮）...'}, ensure_ascii=False)}\n\n"

                # 非流式调用检测工具调用（asyncio.to_thread 避免阻塞事件循环）
                response = await asyncio.to_thread(
                    adapter.chat,
                    messages=messages,
                    tools=ir_tools,
                    temperature=record.temperature,
                    max_tokens=record.max_tokens,
                )
            except Exception:
                break  # 非流式调用失败，直接走流式输出

            # 标准 Function Calling 检测
            has_tool_calls = bool(response.tool_calls)

            # XML 文本格式 fallback（第三方 API 可能返回此格式）
            xml_tool_calls = []
            if not has_tool_calls and response.content:
                xml_tool_calls = _parse_xml_tool_calls(response.content)
                if xml_tool_calls:
                    has_tool_calls = True

            if has_tool_calls:
                tool_call_count += 1

                # 发送工具调用提示
                if response.tool_calls:
                    for tc in response.tool_calls:
                        yield f"data: {json.dumps({'type': 'info', 'content': f'[工具调用] {tc.name}'}, ensure_ascii=False)}\n\n"
                elif xml_tool_calls:
                    for tc in xml_tool_calls:
                        yield f"data: {json.dumps({'type': 'info', 'content': f'[工具调用] {tc.get("name", "")}'}, ensure_ascii=False)}\n\n"

                # 将 assistant 的 tool_call 消息加入历史
                from shared.ir_models import ToolCallIR as _TCI
                if response.tool_calls:
                    tool_calls_ir = [
                        _TCI(id=tc.id, name=tc.name, arguments=tc.arguments)
                        for tc in response.tool_calls
                    ]
                    messages.append(MessageIR.assistant(
                        content=response.content,
                        tool_calls=tool_calls_ir,
                    ))
                elif xml_tool_calls:
                    # 为 XML 工具调用生成伪 tool_calls
                    tool_calls_ir = [
                        _TCI(id=f"xml-{i}", name=tc["name"], arguments=tc.get("arguments", {}))
                        for i, tc in enumerate(xml_tool_calls)
                    ]
                    messages.append(MessageIR.assistant(
                        content=response.content,
                        tool_calls=tool_calls_ir,
                    ))

                # 并行执行多个工具（尤其多个 delegate_task 可并发）
                tools_to_execute = response.tool_calls if response.tool_calls else xml_tool_calls
                # 发送 agent_dispatch 事件（同步信息）
                for tc in tools_to_execute:
                    tool_name = tc.name if hasattr(tc, 'name') else tc.get("name", "")
                    tool_args = (tc.arguments if hasattr(tc, 'arguments') else tc.get("arguments", {})) or {}
                    if tool_name == "delegate_task":
                        yield f"data: {json.dumps({'type': 'agent_dispatch', 'agent_id': tool_args.get('agent_id', ''), 'task': (tool_args.get('task', '') or '')[:120], 'agent_name': tool_args.get('agent_id', '')}, ensure_ascii=False)}\n\n"

                async def _execute_one_tool(tc):
                    tool_name = tc.name if hasattr(tc, 'name') else tc.get("name", "")
                    tool_args = (tc.arguments if hasattr(tc, 'arguments') else tc.get("arguments", {})) or {}
                    handler = _get_tool_handler(tool_name) if _get_tool_handler else None
                    if handler:
                        try:
                            # v0.6.1: 子Agent委托任务增加整体超时，防止单个Agent卡住10分钟
                            from runtime_config import get as _rc_get
                            if tool_name == "delegate_task":
                                sub_timeout = _rc_get("sub_agent_timeout", 120)
                                tool_result = await asyncio.wait_for(
                                    asyncio.to_thread(handler, **tool_args, _api_key=api_key, _provider=provider_lower, _model=model, _base_url=base_url),
                                    timeout=sub_timeout,
                                )
                            else:
                                tool_result = await asyncio.to_thread(
                                    handler,
                                    **tool_args,
                                    _api_key=api_key,
                                    _provider=provider_lower,
                                    _model=model,
                                    _base_url=base_url,
                                )
                        except asyncio.TimeoutError:
                            tool_result = json.dumps({
                                "error": f"工具 {tool_name} 执行超时（>{_rc_get('sub_agent_timeout', 120)}s），已强制终止",
                                "retryable": True,
                                "timeout": True,
                            }, ensure_ascii=False)
                        except Exception as e:
                            tool_result = json.dumps({"error": str(e), "retryable": False}, ensure_ascii=False)
                    else:
                        tool_result = json.dumps({"error": f"未找到工具处理器: {tool_name}", "retryable": False}, ensure_ascii=False)
                    return tc, tool_name, tool_args, tool_result

                # 发送开始执行提示
                for tc in tools_to_execute:
                    tool_name = tc.name if hasattr(tc, 'name') else tc.get("name", "")
                    yield f"data: {json.dumps({'type': 'info', 'content': f'[执行工具] {tool_name}...'}, ensure_ascii=False)}\n\n"

                results = await asyncio.gather(*[_execute_one_tool(tc) for tc in tools_to_execute])

                for tc, tool_name, tool_args, tool_result in results:
                    # v0.5.1: delegate_task 结果发送 agent_result 事件
                    if tool_name == "delegate_task":
                        try:
                            obj = json.loads(tool_result) if isinstance(tool_result, str) else (tool_result if isinstance(tool_result, dict) else {})
                            agent_event = {
                                'type': 'agent_result',
                                'agent_id': tool_args.get('agent_id', ''),
                                'agent_name': obj.get('agent_name', tool_args.get('agent_id', '')),
                                'success': obj.get('success', False),
                                'tool_calls': obj.get('tool_calls', 0),
                                'output_snippet': (obj.get('output', '') or '')[:150],
                                'error': (obj.get('error', '') or '')[:200],
                                'needs_key': obj.get('needs_key', False),
                                'needed_provider': obj.get('needed_provider', ''),
                            }
                            yield f"data: {json.dumps(agent_event, ensure_ascii=False)}\n\n"
                        except Exception as e:
                            logger = logging.getLogger(__name__)
                            logger.warning(f"解析 delegate_task 结果失败: {type(e).__name__}: {e}")
                            yield f"data: {json.dumps({'type': 'agent_result', 'agent_id': tool_args.get('agent_id', ''), 'success': False, 'error': f'结果解析失败: {str(e)[:100]}'}, ensure_ascii=False)}\n\n"

                        # v0.5.1: 检测 needs_key 信号（子 Agent 需要 API Key）
                        try:
                            result_obj = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
                            if isinstance(result_obj, dict) and result_obj.get("needs_key"):
                                needed_prov = result_obj.get("needed_provider", "openai")
                                yield f"data: {json.dumps({'type': 'no_api_key', 'content': result_obj.get('error', f'请配置 {needed_prov.upper()} API Key'), 'provider': needed_prov, 'env_key': result_obj.get('env_key', ''), 'needed_model': result_obj.get('needed_model', '')}, ensure_ascii=False)}\n\n"
                                yield f"data: {json.dumps({'type': 'done', 'total_tokens': adapter.total_tokens if hasattr(adapter, 'total_tokens') else 0}, ensure_ascii=False)}\n\n"
                                return
                        except Exception as e:
                            logger = logging.getLogger(__name__)
                            logger.warning(f"needs_key 检测失败: {type(e).__name__}: {e}")

                    tc_id = tc.id if hasattr(tc, 'id') else f"xml-{tool_name}"
                    messages.append(MessageIR.tool_result(
                        tool_call_id=tc_id or "",
                        name=tool_name,
                        content=tool_result,
                    ))
            else:
                break  # 没有工具调用，进入流式输出

        # 流式输出最终文本（此时已处理完所有工具调用）
        full_response = ""

        # 发送流式开始提示
        yield f"data: {json.dumps({'type': 'info', 'content': '正在生成回答...'}, ensure_ascii=False)}\n\n"
        try:
            for chunk in adapter.stream_chat(
                messages=messages,
                temperature=record.temperature,
                max_tokens=record.max_tokens,
            ):
                if chunk.startswith("[思考]"):
                    # DeepSeek R1 reasoning
                    yield f"data: {json.dumps({'type': 'reasoning', 'content': chunk[4:]}, ensure_ascii=False)}\n\n"
                else:
                    full_response += chunk
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

        except Exception as stream_err:
            error_msg = str(stream_err)
            if "api_key" in error_msg.lower() or "key" in error_msg.lower() or "auth" in error_msg.lower():
                yield f"data: {json.dumps({'type': 'no_api_key', 'content': f'{provider.upper()} API Key 无效或未配置', 'provider': provider, 'detail': error_msg[:200]}, ensure_ascii=False)}\n\n"
                return
            # 流式失败 → 回退到同步 chat（一次性输出）
            yield f"data: {json.dumps({'type': 'info', 'content': '流式输出失败，尝试回退...'}, ensure_ascii=False)}\n\n"
            try:
                fallback = await asyncio.to_thread(
                    adapter.chat,
                    messages=messages,
                    temperature=record.temperature,
                    max_tokens=record.max_tokens,
                )
                if fallback.content:
                    yield f"data: {json.dumps({'type': 'text', 'content': fallback.content}, ensure_ascii=False)}\n\n"
            except Exception as fallback_err:
                yield f"data: {json.dumps({'type': 'error', 'content': f'生成失败: {str(fallback_err)[:500]}'}, ensure_ascii=False)}\n\n"
                return

        # v0.6: 流式文本中检测 DSML 工具调用 —— 模型在文本输出中嵌入了未执行的工具请求
        if full_response.strip() and tool_call_count < MAX_TOOL_ITERATIONS:
            dsml_leftover = _parse_xml_tool_calls(full_response)
            if dsml_leftover:
                yield f"data: {json.dumps({'type': 'info', 'content': f'检测到 {len(dsml_leftover)} 个未执行的工具调用，继续处理...'}, ensure_ascii=False)}\n\n"
                # 将 DSML 工具调用作为 assistant 消息追加
                tc_ir = [
                    _TCI(id=f"dsml-post-{i}", name=tc["name"], arguments=tc.get("arguments", {}))
                    for i, tc in enumerate(dsml_leftover)
                ]
                messages.append(MessageIR.assistant(content="", tool_calls=tc_ir))
                # 执行这些工具
                for i, tc in enumerate(dsml_leftover):
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {}) or {}
                    handler = _get_tool_handler(tool_name) if _get_tool_handler else None
                    if handler:
                        try:
                            yield f"data: {json.dumps({'type': 'info', 'content': f'[执行工具] {tool_name}...'}, ensure_ascii=False)}\n\n"
                            tool_result = await asyncio.to_thread(handler, **tool_args, _api_key=api_key, _provider=provider_lower, _model=model, _base_url=base_url)
                        except Exception as e:
                            tool_result = json.dumps({"error": str(e), "retryable": False}, ensure_ascii=False)
                    else:
                        tool_result = json.dumps({"error": f"未找到工具处理器: {tool_name}"}, ensure_ascii=False)
                    messages.append(MessageIR.tool_result(tool_call_id=f"dsml-post-{i}", name=tool_name, content=tool_result))
                    tool_call_count += 1
                # 追加完毕后再做最后一轮流式输出
                yield f"data: {json.dumps({'type': 'info', 'content': '正在生成最终回答...'}, ensure_ascii=False)}\n\n"
                final_text = ""
                try:
                    for chunk in adapter.stream_chat(messages=messages, temperature=record.temperature, max_tokens=record.max_tokens):
                        if not chunk.startswith("[思考]"):
                            final_text += chunk
                            yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass  # 最终流式失败，前面已有部分输出

        yield f"data: {json.dumps({'type': 'done', 'total_tokens': adapter.total_tokens}, ensure_ascii=False)}\n\n"

    except ImportError as e:
        pkg = str(e).split("'")[1] if "'" in str(e) else provider_lower
        yield f"data: {json.dumps({'type': 'error', 'content': f'缺少 {provider_lower} SDK: pip install {pkg}', 'provider': provider}, ensure_ascii=False)}\n\n"
    except Exception as e:
        error_str = str(e)
        # 检测 401/403 认证错误
        if any(kw in error_str.lower() for kw in ("401", "403", "unauthorized", "api key", "invalid")):
            yield f"data: {json.dumps({'type': 'no_api_key', 'content': f'{provider.upper()} 认证失败，请检查 API Key', 'provider': provider, 'detail': error_str[:200]}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'error', 'content': error_str[:500], 'provider': provider}, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def api_chat(req: ChatRequest):
    """多 Provider 聊天接口（SSE 流式）v0.6 — 含上下文裁剪 + 工具调用 + 运行时日志"""
    record = load_agent(req.agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")

    from runtime_logger import log_event

    session_id = req.session_id or uuid.uuid4().hex[:12]
    agent_name = record.name
    gen = _chat_generator_v4(
        record=record,
        user_msg=req.message,
        enable_rag=req.enable_rag,
        api_key=req.api_key,
        api_base=req.api_base,
        history=req.history,
        history_window=req.history_window,
    )

    async def logged_gen():
        log_event(
            {"type": "session_start", "content": f"Agent: {record.name} | 消息: {req.message[:100]}", "message": req.message[:200]},
            agent_id=req.agent_id, agent_name=agent_name, session_id=session_id,
        )
        # 收集事件用于会话保存
        collected: list[dict] = []
        dispatch_n = success_n = 0
        final_text = ""
        try:
            async for event_str in gen:
                if isinstance(event_str, str) and event_str.startswith("data: "):
                    try:
                        data = json.loads(event_str[6:])
                        log_event(data, agent_id=req.agent_id, agent_name=agent_name, session_id=session_id)
                        t = data.get("type", "")
                        if t == "agent_dispatch": dispatch_n += 1
                        elif t == "agent_result" and data.get("success"): success_n += 1
                        elif t == "text": final_text += data.get("content", "")
                        collected.append({"type": t, "content": str(data.get("content", ""))[:200]})
                    except json.JSONDecodeError:
                        pass
                yield event_str
        except Exception as e:
            log_event(
                {"type": "error", "content": f"会话异常: {str(e)[:200]}"},
                agent_id=req.agent_id, agent_name=agent_name, session_id=session_id,
            )
            raise
        finally:
            try:
                from shared.session_manager import save_session
                msgs = [{"role": "user", "content": req.message}]
                if final_text.strip():
                    msgs.append({"role": "assistant", "content": final_text[:5000]})
                save_session(session_id, req.agent_id, agent_name, msgs,
                             {"dispatch_count": dispatch_n, "success_count": success_n})
            except Exception: pass
            log_event(
                {"type": "session_end", "content": "会话结束"},
                agent_id=req.agent_id, agent_name=agent_name, session_id=session_id,
            )

    return StreamingResponse(
        logged_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-Id": session_id,
        },
    )


# ══════════════════════════════════════════════
# v0.6: 统一 Settings API — 后端设置管理
# ══════════════════════════════════════════════

# 内存字典：记录前端 POST 过来的 Key（会话级）
_frontend_provider_keys: dict[str, str] = {}
_frontend_tool_keys: dict[str, str] = {}

_SETTINGS_PROVIDER_LIST = [
    {"id":"openai","name":"OpenAI","env_key":"OPENAI_API_KEY","base_env":"OPENAI_BASE_URL","signup":"https://platform.openai.com/api-keys","hint":"sk-..."},
    {"id":"deepseek","name":"DeepSeek","env_key":"DEEPSEEK_API_KEY","base_env":"DEEPSEEK_BASE_URL","signup":"https://platform.deepseek.com/api_keys","hint":"sk-..."},
    {"id":"anthropic","name":"Anthropic Claude","env_key":"ANTHROPIC_API_KEY","base_env":"ANTHROPIC_BASE_URL","signup":"https://console.anthropic.com/keys","hint":"sk-ant-..."},
    {"id":"google","name":"Google Gemini","env_key":"GOOGLE_API_KEY","base_env":"GOOGLE_BASE_URL","signup":"https://aistudio.google.com/apikey","hint":"AIza..."},
    {"id":"ollama","name":"Ollama (本地)","env_key":"","base_env":"","signup":"","hint":"http://localhost:11434"},
]


@app.get("/api/settings")
def api_settings_get():
    """获取完整设置状态：Provider + 工具预设"""
    from shared.tool_presets import BUILTIN_TOOL_PRESETS

    providers = []
    for prov in _SETTINGS_PROVIDER_LIST:
        env_key_val = os.getenv(prov["env_key"], "").strip() if prov["env_key"] else ""
        front_key = _frontend_provider_keys.get(prov["id"], "").strip()
        base_env = os.getenv(prov["base_env"], "").strip() if prov["base_env"] else ""
        models: list[str] = []
        try:
            from shared.llm_factory import get_model_list
            models = get_model_list(prov["id"])
        except Exception:
            pass
        providers.append({
            "id": prov["id"], "name": prov["name"],
            "env_key": prov["env_key"], "base_env": prov["base_env"],
            "signup": prov["signup"], "hint": prov["hint"],
            "has_env_key": bool(env_key_val),
            "has_frontend_key": bool(front_key),
            "has_key": bool(env_key_val or front_key or prov["id"] == "ollama"),
            "models": models, "needs_key": prov["id"] != "ollama",
            "base_url": base_env,
        })

    tool_presets = []
    for name, preset in BUILTIN_TOOL_PRESETS.items():
        has_key = True
        for _sk, env_var in preset.secret_params.items():
            if not (os.getenv(env_var, "").strip() or _frontend_tool_keys.get(env_var, "").strip()):
                has_key = False
                break
        tool_presets.append({
            "name": preset.name, "id": name,
            "description": preset.description,
            "handler": preset.handler, "category": preset.category,
            "needs_key": len(preset.secret_params) > 0, "has_key": has_key,
            "secret_env_keys": list(preset.secret_params.values()),
            "params": [
                {"name": p["name"], "type": p["type"],
                 "description": p["description"],
                 "required": p.get("required", False)}
                for p in preset.public_params.get("parameters", [])
            ],
        })

    any_cfg = any(p["has_key"] for p in providers if p["needs_key"])
    return {
        "providers": providers,
        "tool_presets": tool_presets,
        "any_configured": any_cfg,
        "frontend_count": sum(1 for p in providers if p["has_frontend_key"]),
        "env_count": sum(1 for p in providers if p["has_env_key"]),
    }


@app.post("/api/settings")
def api_settings_save(data: dict):
    """前端同步配置给后端会话"""
    saved = 0
    if "providers" in data:
        for pid, cfg in data["providers"].items():
            if isinstance(cfg, dict):
                k = cfg.get("key", "").strip()
                if k:
                    _frontend_provider_keys[pid] = k; saved += 1
                else:
                    _frontend_provider_keys.pop(pid, None)
    if "tools" in data:
        for ek, v in data["tools"].items():
            if isinstance(v, str) and v.strip():
                os.environ[ek] = v.strip()
                _frontend_tool_keys[ek] = v.strip()
                saved += 1
    return {"message": "已同步", "saved": saved}


@app.delete("/api/settings")
def api_settings_clear():
    """清除前端所有配置"""
    c = len(_frontend_provider_keys) + len(_frontend_tool_keys)
    _frontend_provider_keys.clear(); _frontend_tool_keys.clear()
    return {"message": f"已清除 {c} 项", "cleared": c}


# ══════════════════════════════════════════════
# 旧版 API — 保留向后兼容
# ══════════════════════════════════════════════

@app.post("/api/auth/check")
def api_auth_check(req: ProviderCheckRequest):
    provider_lower = req.provider.lower().strip()
    env_key = _PROVIDER_ENV_KEYS.get(provider_lower, "")
    has_env = bool(os.getenv(env_key, "").strip()) if env_key else False
    has_fe = bool(_frontend_provider_keys.get(provider_lower, "").strip())
    has_key = has_env or has_fe or provider_lower == "ollama"
    models: list = []
    try:
        from shared.llm_factory import get_model_list
        models = get_model_list(provider_lower)
    except Exception: pass
    return {"provider": provider_lower, "has_key": has_key, "has_env_key": has_env,
            "has_frontend_key": has_fe, "env_key": env_key, "models": models}


@app.get("/api/auth/status")
def api_auth_status():
    result = []
    for p in ["openai","anthropic","google","deepseek","ollama"]:
        result.append(api_auth_check(ProviderCheckRequest(provider=p)))
    return {"providers": result, "any_configured": any(r["has_key"] for r in result)}


@app.post("/api/tool-presets")
def api_save_tool_presets(presets: dict):
    for k, v in presets.items():
        if v and isinstance(v, str) and v.strip():
            os.environ[k] = v.strip(); _frontend_tool_keys[k] = v.strip()
    return {"message": "已保存", "count": len(presets)}


@app.get("/api/tool-presets")
def api_get_tool_presets():
    from shared.tool_presets import BUILTIN_TOOL_PRESETS
    items = []
    for name, preset in BUILTIN_TOOL_PRESETS.items():
        hk = True
        for _sk, ev in preset.secret_params.items():
            if not (os.getenv(ev,"").strip() or _frontend_tool_keys.get(ev,"").strip()):
                hk = False; break
        items.append({
            "name": preset.name, "description": preset.description,
            "handler": preset.handler, "category": preset.category,
            "needs_key": len(preset.secret_params) > 0, "has_key": hk,
            "params": [{"name": p["name"], "type": p["type"],
                        "description": p.get("description",""),
                        "required": p.get("required", False)}
                       for p in preset.public_params.get("parameters", [])],
        })
    return {"presets": items, "count": len(items),
            "enabled_count": sum(1 for i in items if i["has_key"] or not i["needs_key"])}

@app.post("/api/agents/{agent_id}/knowledge")
async def api_upload_knowledge(agent_id: str, file: UploadFile = File(...)):
    """上传知识库文件"""
    record = load_agent(agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")

    # 保存文件
    ext = Path(file.filename or "upload.txt").suffix
    if ext.lower() not in (".txt", ".md", ".pdf"):
        raise HTTPException(400, "仅支持 .txt .md .pdf 文件")

    # 确保上传目录存在
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    file_path = os.path.join(UPLOAD_DIR, f"{agent_id}_{uuid.uuid4().hex[:8]}{ext}")
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise HTTPException(400, "上传的文件为空（0 字节）")

    # 向量化
    try:
        result = add_knowledge(agent_id, file_path)
        if result.get("error"):
            import logging
            logging.getLogger('main').warning(f"知识库上传失败: {file_path} -> {result['error']}")
        return {"message": result.get("error") or f"向量化成功", "file_size": file_size, **result}
    except Exception as e:
        import logging
        logging.getLogger('main').error(f"知识库上传异常: {e}")
        raise HTTPException(500, f"向量化失败: {e}")


@app.get("/api/agents/{agent_id}/knowledge")
def api_get_knowledge(agent_id: str):
    """获取知识库状态"""
    return get_knowledge_stats(agent_id)


@app.delete("/api/agents/{agent_id}/knowledge")
def api_delete_knowledge(agent_id: str):
    """删除知识库"""
    if delete_knowledge(agent_id):
        return {"message": "知识库已删除"}
    return {"message": "知识库不存在或已删除"}


@app.post("/api/agents/{agent_id}/knowledge/search")
def api_search_knowledge(agent_id: str, query: str = "", top_k: int = 5):
    """搜索知识库"""
    if not query:
        raise HTTPException(400, "缺少查询参数 query")
    results = search_knowledge(agent_id, query, top_k)
    return {"results": results, "count": len(results)}


# ══════════════════════════════════════════════
# v0.6.1: 运行时配置
# ══════════════════════════════════════════════

@app.get("/api/runtime-config")
def api_runtime_config_get():
    """获取运行时配置（含默认值说明）"""
    from runtime_config import get_all, get_defaults
    return {"config": get_all(), "defaults": get_defaults()}


@app.post("/api/runtime-config")
def api_runtime_config_save(data: dict):
    """更新运行时配置（部分更新）"""
    from runtime_config import update
    return {"config": update(data), "message": "配置已更新，下次请求生效"}


# ══════════════════════════════════════════════
# v0.6: 运行时日志查看
# ══════════════════════════════════════════════

@app.get("/api/logs")
def api_logs(limit: int = 200, type: str = "", agent_id: str = ""):
    """获取最近运行日志（支持按类型和 Agent 过滤）"""
    from runtime_logger import get_logs, get_stats
    logs = get_logs(
        limit=min(limit, 500),
        log_type=type if type else None,
        agent_id=agent_id if agent_id else None,
    )
    return {
        "logs": logs,
        "count": len(logs),
        "stats": get_stats(),
    }


@app.get("/api/logs/stream")
async def api_logs_stream():
    """SSE 实时日志推送"""
    from runtime_logger import register_listener, unregister_listener
    q = register_listener()

    async def event_stream():
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_listener(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.delete("/api/logs")
def api_logs_clear():
    """清空日志缓冲区"""
    from runtime_logger import clear_logs
    clear_logs()
    return {"message": "日志已清空"}


# ══════════════════════════════════════════════
# v1.0: 会话历史管理
# ══════════════════════════════════════════════

@app.get("/api/sessions")
def api_sessions_list(agent_id: str = "", limit: int = 50):
    """列出历史会话"""
    from shared.session_manager import list_sessions
    return {"sessions": list_sessions(agent_id=agent_id, limit=limit)}


@app.get("/api/sessions/{session_id}")
def api_sessions_get(session_id: str):
    """获取会话详情（含消息历史）"""
    from shared.session_manager import load_session
    data = load_session(session_id)
    if not data:
        raise HTTPException(404, "会话不存在")
    return data


@app.delete("/api/sessions/{session_id}")
def api_sessions_delete(session_id: str):
    """删除会话"""
    from shared.session_manager import delete_session
    if delete_session(session_id):
        return {"message": "已删除"}
    raise HTTPException(404, "会话不存在")


# ══════════════════════════════════════════════
# v0.7: Agent 表现评分
# ══════════════════════════════════════════════

@app.get("/api/agent-scores")
def api_agent_scores():
    """获取所有 Agent 的表现评分（成功率、平均耗时、综合评分）"""
    from shared.agent_memory import get_all_agent_scores
    return {"scores": get_all_agent_scores()}


# ══════════════════════════════════════════════
# v0.6: 项目文件浏览
# ══════════════════════════════════════════════

@app.get("/api/projects/list")
def api_project_list(dir: str = "."):
    """列出项目目录结构"""
    from pathlib import Path
    project_root = Path.cwd().resolve()
    target = (project_root / dir).resolve()

    # 安全检查
    if not str(target).startswith(str(project_root)):
        raise HTTPException(403, "仅允许访问项目目录内文件")

    if not target.exists():
        raise HTTPException(404, f"目录不存在: {dir}")
    if not target.is_dir():
        raise HTTPException(400, f"路径不是目录: {dir}")

    def _build_tree(path: Path, depth: int = 0, max_depth: int = 3) -> list[dict]:
        if depth > max_depth:
            return []
        items = []
        try:
            for p in sorted(path.iterdir()):
                if p.name.startswith('.') and p.name not in ('.gitignore',):
                    continue
                if p.name in ('node_modules', '__pycache__', '.git', 'chroma_data', 'uploads'):
                    continue
                item: dict = {
                    "name": p.name,
                    "type": "dir" if p.is_dir() else "file",
                    "path": str(p.relative_to(project_root)).replace("\\", "/"),
                }
                if p.is_file():
                    item["size"] = p.stat().st_size
                if p.is_dir() and depth < max_depth:
                    sub = _build_tree(p, depth + 1, max_depth)
                    if sub:
                        item["children"] = sub
                        item["count"] = len(sub)
                items.append(item)
        except PermissionError:
            pass
        return items

    tree = _build_tree(target)
    return {
        "root": str(target.relative_to(project_root)).replace("\\", "/") if target != project_root else "",
        "path": str(target),
        "items": tree,
        "count": len(tree),
    }


@app.get("/api/projects/read")
def api_project_read(path: str = "", limit: int = 500, offset: int = 0):
    """读取项目文件内容"""
    from pathlib import Path
    project_root = Path.cwd().resolve()
    target = (project_root / path).resolve()

    if not str(target).startswith(str(project_root)):
        raise HTTPException(403, "仅允许访问项目目录内文件")
    if not target.exists():
        raise HTTPException(404, f"文件不存在: {path}")
    if target.is_dir():
        raise HTTPException(400, "请指定文件路径，而非目录")

    if target.suffix.lower() in ('.pyc', '.exe', '.dll', '.so', '.pyd', '.pyo'):
        raise HTTPException(400, "不支持二进制文件")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(500, f"无法读取文件: {e}")

    lines = content.split("\n")
    total = len(lines)
    preview = "\n".join(lines[offset:offset + limit])

    return {
        "path": str(target.relative_to(project_root)).replace("\\", "/"),
        "content": preview,
        "lines": len(preview.split("\n")),
        "total_lines": total,
        "size": target.stat().st_size,
        "truncated": len(preview) < len(content),
    }


# ══════════════════════════════════════════════
# 中间问题（Middle）: 工具预设配置
# ══════════════════════════════════════════════

@app.post("/api/tool-presets")
def api_save_tool_presets(presets: dict):
    """保存工具预设（前端 Settings 面板配置的 API Key 等）"""
    # 将前端传入的 Key 写入临时环境变量（此会话中有效）
    for key, value in presets.items():
        if value and isinstance(value, str) and value.strip():
            os.environ[key] = value.strip()
    return {"message": "预设已保存", "count": len(presets)}


@app.get("/api/tool-presets")
def api_get_tool_presets():
    """获取工具预设状态"""
    from shared.tool_presets import BUILTIN_TOOL_PRESETS

    items = []
    for name, preset in BUILTIN_TOOL_PRESETS.items():
        has_secrets = True
        for secret_key, env_var in preset.secret_params.items():
            if not os.getenv(env_var, "").strip():
                has_secrets = False
                break
        items.append({
            "name": preset.name,
            "description": preset.description,
            "handler": preset.handler,
            "category": preset.category,
            "needs_key": len(preset.secret_params) > 0,
            "has_key": has_secrets,
            "params": [{"name": p["name"], "type": p["type"], "description": p["description"], "required": p.get("required", False)}
                        for p in preset.public_params.get("parameters", [])],
        })

    return {
        "presets": items,
        "count": len(items),
        "enabled_count": sum(1 for i in items if i["has_key"] or not i["needs_key"]),
    }


# ══════════════════════════════════════════════
# 模板市场
# ══════════════════════════════════════════════

@app.get("/api/templates")
def api_list_templates():
    """列出所有内置模板"""
    return {"templates": BUILTIN_TEMPLATES, "count": len(BUILTIN_TEMPLATES)}


@app.post("/api/templates/{template_id}/use")
def api_use_template(template_id: str):
    """基于模板创建 Agent"""
    template = next((t for t in BUILTIN_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(404, "模板不存在")

    model = template.get("model", {})
    params = model.get("parameters", {})

    record = AgentRecord(
        agent_id=str(uuid.uuid4())[:12],
        name=template["name"],
        description=template["description"],
        system_prompt=template["system_prompt"],
        model_provider=model.get("provider", "openai"),
        model_name=model.get("model_name", "gpt-4o-mini"),
        temperature=params.get("temperature", 0.7),
        max_tokens=params.get("max_tokens", 4096),
        tools=template.get("tools", []),
        tags=template.get("tags", []),
        avatar=template.get("icon", "🤖"),
        suggested_questions=template.get("suggested_questions", []),
    )
    save_agent(record)
    return {"agent": record.to_dict(), "message": f"已从模板 '{template['name']}' 创建"}


# ══════════════════════════════════════════════
# 健康检查
# ══════════════════════════════════════════════

@app.get("/api/health")
def api_health():
    return {
        "status": "ok",
        "version": "0.3.0",
        "agents_count": len(list_agents()),
        "templates_count": len(BUILTIN_TEMPLATES),
        "enhanced_routes": _HAS_ENHANCED,
    }


# ── 注册增强路由 ──
if enhanced_router is not None:
    app.include_router(enhanced_router)


# ══════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("AI Agent Hub Builder API v0.3 启动中...")
    print(f"  API 文档: http://localhost:8000/docs")
    print(f"  Agent 存储: {os.path.abspath(os.path.join(os.path.dirname(__file__), 'agent_store'))}")
    print(f"  增强路由: {'已加载' if _HAS_ENHANCED else '未加载'}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
