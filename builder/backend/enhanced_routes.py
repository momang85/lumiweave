"""
AI Agent Hub — Builder 后端增强路由 v0.3

新增：
- /api/agents/generate — NL → Agent 生成
- /api/agents/{id}/export/all — 多格式 ZIP 导出
- /api/providers — 列出所有 Provider
- /api/providers/{name}/models — 获取 Provider 模型列表
- /api/agents/{id}/adapt — 适配到指定 Provider
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Optional

# ── 确保 shared 模块可导入 ──
_SHARED_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "shared")
sys.path.insert(0, os.path.dirname(_SHARED_DIR))

from shared.llm_factory import list_providers, get_provider_capabilities, get_model_list
from shared.ir_models import ProviderType, ProviderConfig
from shared.agent_generator import (
    AgentGenerator, AgentDomain,
    list_available_domains, get_domain_template,
)
from shared.adapters.openai_adapter import OpenAIAdapter
from shared.adapters.anthropic_adapter import AnthropicAdapter
from shared.adapters.google_adapter import GoogleAdapter
from shared.adapters.deepseek_adapter import DeepSeekAdapter
from shared.adapters.ollama_adapter import OllamaAdapter

# ── 本地导入 ──
_BACKEND_DIR = os.path.dirname(__file__)
sys.path.insert(0, _BACKEND_DIR)

from agent_service import AgentRecord, save_agent, load_agent, list_agents
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


# ══════════════════════════════════════════════
# Pydantic 模型
# ══════════════════════════════════════════════

class GenerateRequest(BaseModel):
    """NL → Agent 生成请求 v0.5"""
    user_input: str
    domain_hint: Optional[str] = None
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""      # 前端传入的 API Key
    api_base: str = ""     # 自定义 API 地址


class AdaptRequest(BaseModel):
    """适配到指定 Provider 的请求"""
    target_provider: str
    target_model: str = ""


class ExportAllRequest(BaseModel):
    """多格式导出请求"""
    formats: list[str] = ["yaml", "openai", "anthropic", "ollama", "deepseek"]


# ══════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════

router = APIRouter(prefix="/api", tags=["enhanced"])


@router.post("/agents/generate")
def api_generate_agent(req: GenerateRequest):
    """
    自然语言 → Agent 生成

    输入用户描述和可选领域提示，返回生成的 Agent 定义 + YAML。
    有 LLM 可用时走 LLM 生成，否则使用领域模板降级。

    Returns:
        {
            "success": true,
            "agent": {...},
            "yaml": "...",
            "warnings": [...],
            "domain": "legal"
        }
    """
    domain_hint = None
    if req.domain_hint:
        try:
            domain_hint = AgentDomain(req.domain_hint)
        except ValueError:
            raise HTTPException(400, f"不支持的领域: {req.domain_hint}。"
                                      f"可用领域: {[d.value for d in AgentDomain]}")

    # 尝试创建 LLM adapter v0.5（优先使用前端传入的 Key）
    adapter = None
    try:
        provider_type = ProviderType(req.provider)
        api_key = req.api_key or os.getenv(f"{req.provider.upper()}_API_KEY", "")
        if api_key:
            config = ProviderConfig(
                provider=provider_type,
                model=req.model,
                api_key=api_key,
                base_url=req.api_base or "",
            )
            if provider_type == ProviderType.OPENAI:
                adapter = OpenAIAdapter(config)
            elif provider_type == ProviderType.ANTHROPIC:
                adapter = AnthropicAdapter(config)
            elif provider_type == ProviderType.GOOGLE:
                adapter = GoogleAdapter(config)
            elif provider_type == ProviderType.DEEPSEEK:
                adapter = DeepSeekAdapter(config)
            elif provider_type == ProviderType.OLLAMA:
                adapter = OllamaAdapter(config)
    except Exception:
        pass  # LLM 不可用时降级

    gen = AgentGenerator(llm_adapter=adapter)
    result = gen.generate(
        req.user_input,
        domain_hint=domain_hint,
        provider=ProviderType(req.provider) if req.provider else ProviderType.OPENAI,
        model=req.model,
    )

    agent_dict = result.agent_ir.to_dict() if result.agent_ir else None
    # 兼容前端：前端 AgentData 使用 model_provider 字段名
    if agent_dict and "provider" in agent_dict and "model_provider" not in agent_dict:
        agent_dict["model_provider"] = agent_dict["provider"]

    return {
        "success": result.success,
        "agent": agent_dict,
        "yaml": result.yaml_content,
        "warnings": result.warnings,
        "error": result.error,
        "domain": result.raw_skeleton.get("domain", ""),
    }


@router.get("/agents/{agent_id}/export/all")
def api_export_all(agent_id: str):
    """
    多格式 ZIP 导出

    将 Agent 导出为 YAML + 各平台适配格式，打包为 ZIP 下载。

    Returns:
        ZIP 文件流
    """
    record = load_agent(agent_id)
    if not record:
        raise HTTPException(404, "Agent 不存在")

    from fastapi.responses import StreamingResponse

    # 转换为 AgentIR
    try:
        # 使用 loader 导入再转 IR
        from shared.ir_models import AgentIR
        import yaml as yaml_lib

        # 从 record 构建 AgentIR
        agent_ir = AgentIR(
            id=f"com.aihub.{record.agent_id}",
            name=record.name,
            description=record.description,
            system_prompt=record.system_prompt,
            provider=ProviderType(record.model_provider) if record.model_provider else ProviderType.OPENAI,
            model_name=record.model_name,
            temperature=record.temperature,
            max_tokens=record.max_tokens,
            tags=record.tags,
            avatar=record.avatar,
            welcome_message=f"你好！我是 {record.name}。",
            suggested_questions=record.suggested_questions,
            tools=[
                __import__("shared.ir_models", fromlist=["ToolDefIR"]).ToolDefIR(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                )
                for t in record.tools
            ],
        )
    except Exception as e:
        raise HTTPException(500, f"Agent 转换失败: {e}")

    # 构建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. 原始 YAML
        yaml_content = record.to_yaml()
        zf.writestr(f"{agent_id}/agent.yaml", yaml_content)

        # 2. 纯文本 prompt.md
        zf.writestr(f"{agent_id}/prompt.md", agent_ir.system_prompt)

        # 3. OpenAI 格式
        openai_config = {
            "model": agent_ir.model_name,
            "messages": [{"role": "system", "content": agent_ir.system_prompt}],
            "temperature": agent_ir.temperature,
            "max_tokens": agent_ir.max_tokens,
            "tools": [t.to_openai_format() for t in agent_ir.tools],
        }
        zf.writestr(f"{agent_id}/openai_config.json",
                    json.dumps(openai_config, indent=2, ensure_ascii=False))

        # 4. Anthropic 格式
        anthropic_config = {
            "model": agent_ir.model_name,
            "system": agent_ir.system_prompt,
            "messages": [],
            "temperature": agent_ir.temperature,
            "max_tokens": agent_ir.max_tokens,
            "tools": [t.to_anthropic_format() for t in agent_ir.tools],
        }
        zf.writestr(f"{agent_id}/anthropic_config.json",
                    json.dumps(anthropic_config, indent=2, ensure_ascii=False))

        # 5. Ollama 格式
        ollama_config = {
            "model": agent_ir.model_name,
            "messages": [{"role": "system", "content": agent_ir.system_prompt}],
            "options": {"temperature": agent_ir.temperature, "num_predict": agent_ir.max_tokens},
            "tools": [t.to_openai_format() for t in agent_ir.tools],
        }
        zf.writestr(f"{agent_id}/ollama_config.json",
                    json.dumps(ollama_config, indent=2, ensure_ascii=False))

        # 6. DeepSeek 格式
        deepseek_config = {
            "model": agent_ir.model_name,
            "messages": [{"role": "system", "content": agent_ir.system_prompt}],
            "temperature": agent_ir.temperature,
            "max_tokens": agent_ir.max_tokens,
            "tools": [t.to_openai_format() for t in agent_ir.tools],
        }
        zf.writestr(f"{agent_id}/deepseek_config.json",
                    json.dumps(deepseek_config, indent=2, ensure_ascii=False))

        # 7. README
        readme = f"""# {record.name}

## 描述
{record.description}

## 适配指南

### OpenAI
1. 导入 `openai_config.json` 到你的应用
2. 或直接使用 system prompt + tools

### Anthropic (Claude)
1. 使用 `anthropic_config.json` 中的配置
2. 注意：tools 格式为 `input_schema` 而非 `parameters`

### Ollama（本地运行）
1. 确保已安装 Ollama
2. 导入 `ollama_config.json`

### DeepSeek
1. 使用 OpenAI 兼容格式
2. 详情见 `deepseek_config.json`

## System Prompt
```
{agent_ir.system_prompt}
```
"""
        zf.writestr(f"{agent_id}/README.md", readme)

    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{agent_id}_export.zip"',
        },
    )


@router.get("/providers")
def api_list_providers():
    """列出所有支持的 LLM Provider 及其能力"""
    return {"providers": list_providers()}


@router.get("/providers/{provider_name}/models")
def api_provider_models(provider_name: str):
    """获取指定 Provider 的推荐模型列表"""
    try:
        provider = ProviderType(provider_name)
    except ValueError:
        raise HTTPException(400, f"不支持的 Provider: {provider_name}")

    cap = get_provider_capabilities(provider)
    if not cap:
        raise HTTPException(404, "Provider 信息不存在")

    return {
        "provider": provider_name,
        "models": cap.models,
        "default_model": cap.models[0] if cap.models else "",
        "capabilities": {
            "supports_streaming": cap.supports_streaming,
            "supports_tools": cap.supports_tools,
            "supports_vision": cap.supports_vision,
            "max_context_tokens": cap.max_context_tokens,
            "notes": cap.notes,
        },
    }


@router.get("/domains")
def api_list_domains():
    """列出所有 Agent 领域模板"""
    return {"domains": list_available_domains()}


@router.get("/domains/{domain_name}")
def api_get_domain_template(domain_name: str):
    """获取指定领域的模板详情"""
    tmpl = get_domain_template(domain_name)
    if not tmpl:
        raise HTTPException(404, f"不支持的领域: {domain_name}")
    return {
        "domain": tmpl.domain.value,
        "name_cn": tmpl.name_cn,
        "avatar": tmpl.default_avatar,
        "system_prompt_skeleton": tmpl.system_prompt_skeleton,
        "tools": [{"name": t.name, "description": t.description} for t in tmpl.default_tools],
        "knowledge_sources": tmpl.knowledge_sources,
        "suggested_questions": tmpl.suggested_questions,
    }


# ══════════════════════════════════════════════
# v0.5: Agent 运行模式
# ══════════════════════════════════════════════

@router.get("/modes")
def api_list_modes():
    """列出所有支持的 Agent 运行模式"""
    from shared.agent_modes import list_modes
    return {"modes": list_modes()}


@router.get("/modes/{mode_name}")
def api_get_mode_info(mode_name: str):
    """获取指定模式的详细信息"""
    from shared.agent_modes import get_mode_meta, AgentMode
    try:
        mode = AgentMode(mode_name)
    except ValueError:
        raise HTTPException(404, f"不支持的模式: {mode_name}")
    return {"mode": mode_name, **get_mode_meta(mode)}
