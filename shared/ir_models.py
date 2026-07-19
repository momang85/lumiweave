"""
AI Agent Hub — IR (中间表示层) 数据模型 v0.3

统一 Agent、消息、工具定义的 Pydantic 模型，
所有 Provider 适配器均以这些模型为通用接口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from .agent_modes import AgentMode, ModeConfig
except ImportError:
    from agent_modes import AgentMode, ModeConfig  # type: ignore[no-redef]


# ══════════════════════════════════════════════
# 枚举
# ══════════════════════════════════════════════

class ProviderType(str, Enum):
    """支持的 LLM Provider"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    DEEPSEEK = "deepseek"
    WENXIN = "wenxin"
    TONGYI = "tongyi"
    MOCK = "mock"


@dataclass
class AdapterCapability:
    """Provider 适配器能力描述"""
    provider: ProviderType
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    max_context_tokens: int = 128_000
    system_prompt_field: str = "messages"   # messages | system | system_instruction
    tool_result_role: str = "tool"          # tool | user
    models: list[str] = field(default_factory=list)
    notes: str = ""


# ══════════════════════════════════════════════
# 消息模型
# ══════════════════════════════════════════════

@dataclass
class ToolCallIR:
    """统一工具调用请求（IR 格式）"""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class MessageIR:
    """
    统一消息格式。

    role: system | user | assistant | tool
    content: 文本内容（可为 None，如纯 tool_call 消息）
    tool_call_id: 工具结果关联 ID
    name: 工具名称（tool 消息时）
    tool_calls: assistant 消息可能携带的工具调用列表
    """
    role: str
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCallIR] | None = None

    def to_openai_format(self) -> dict[str, Any]:
        """转换为 OpenAI API 兼容格式（用于后向兼容）"""
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": str(tc.arguments),  # adapter 会处理 JSON
                    },
                }
                for tc in self.tool_calls
            ]
        return msg

    @classmethod
    def system(cls, content: str) -> "MessageIR":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "MessageIR":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str | None = None,
                  tool_calls: list[ToolCallIR] | None = None) -> "MessageIR":
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, name: str,
                    content: str) -> "MessageIR":
        return cls(role="tool", content=content, tool_call_id=tool_call_id, name=name)


# ══════════════════════════════════════════════
# 工具定义
# ══════════════════════════════════════════════

@dataclass
class ToolDefIR:
    """
    统一工具定义。

    各 Provider 适配器负责将此格式转换为对应平台格式：
    - OpenAI: {type:"function", function:{name, description, parameters}}
    - Anthropic: {name, description, input_schema}
    - Google: {functionDeclarations:[{name, description, parameters}]}
    """
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)  # JSON Schema
    required: list[str] = field(default_factory=list)

    def to_json_schema(self) -> dict[str, Any]:
        """生成 JSON Schema 格式的参数定义"""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": self.parameters,
        }
        if self.required:
            schema["required"] = self.required
        return schema

    def to_openai_format(self) -> dict[str, Any]:
        """OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.to_json_schema(),
            },
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Anthropic Tool Use 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.to_json_schema(),
        }

    def to_google_format(self) -> dict[str, Any]:
        """Google Gemini Function Calling 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.to_json_schema(),
        }


# ══════════════════════════════════════════════
# LLM 响应
# ══════════════════════════════════════════════

@dataclass
class LLMResponseIR:
    """统一 LLM 响应"""
    content: str | None
    model: str = ""
    provider: ProviderType = ProviderType.MOCK
    tool_calls: list[ToolCallIR] | None = None
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)

    @property
    def is_tool_call(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_empty(self) -> bool:
        return not self.content and not self.tool_calls


# ══════════════════════════════════════════════
# Agent IR
# ══════════════════════════════════════════════

@dataclass
class AgentIR:
    """
    Agent 中间表示层。

    所有 Agent（无论来源是 YAML、JSON、数据库）都映射为此结构。
    各 Provider 适配器从此结构提取所需字段。
    """
    id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""

    # ── 模型配置 ──
    provider: ProviderType = ProviderType.OPENAI
    model_name: str = "gpt-4o-mini"
    fallback_model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 0.95

    # ── 行为定义 ──
    mode: AgentMode = AgentMode.SIMPLE          # v0.5: 运行模式
    mode_config: ModeConfig = field(default_factory=ModeConfig)
    system_prompt: str = ""
    tools: list[ToolDefIR] = field(default_factory=list)
    knowledge_sources: list[dict[str, str]] = field(default_factory=list)

    # ── 运行时 ──
    runtime_language: str = "python"
    runtime_packages: list[str] = field(default_factory=list)

    # ── UI ──
    avatar: str = "🤖"
    welcome_message: str = ""
    suggested_questions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "id": self.id, "name": self.name, "version": self.version,
            "author": self.author, "description": self.description,
            "mode": self.mode.value,
            "mode_config": self.mode_config.to_dict(),
            "provider": self.provider.value, "model_name": self.model_name,
            "fallback_model": self.fallback_model,
            "temperature": self.temperature, "max_tokens": self.max_tokens,
            "top_p": self.top_p, "system_prompt": self.system_prompt,
            "tools": [t.to_openai_format() for t in self.tools],
            "knowledge_sources": self.knowledge_sources,
            "runtime_language": self.runtime_language,
            "runtime_packages": self.runtime_packages,
            "avatar": self.avatar, "welcome_message": self.welcome_message,
            "suggested_questions": self.suggested_questions,
            "tags": self.tags,
        }

    # ══════════════════════════════════════════════
    # YAML 互转（向后兼容旧 loader.py）
    # ══════════════════════════════════════════════

    @classmethod
    def from_agent_config(cls, config: Any) -> "AgentIR":
        """
        从 runner/loader.py 的 AgentConfig (Pydantic) 转换为 AgentIR。

        Args:
            config: AgentConfig 实例（来自 loader.py）

        Returns:
            AgentIR 实例
        """
        provider_map = {
            "openai": ProviderType.OPENAI,
            "anthropic": ProviderType.ANTHROPIC,
            "google": ProviderType.GOOGLE,
            "ollama": ProviderType.OLLAMA,
            "deepseek": ProviderType.DEEPSEEK,
        }

        tools = []
        for t in config.tools:
            # 构建参数 schema
            if hasattr(t, "properties") and t.properties:
                parameters = dict(t.properties)
            else:
                parameters = {}
                for p in (t.parameters if hasattr(t, "parameters") else []):
                    prop_def: dict[str, Any] = {"type": p.type}
                    if p.description:
                        prop_def["description"] = p.description
                    if p.enum:
                        prop_def["enum"] = p.enum
                    parameters[p.name] = prop_def

            req = list(t.required) if hasattr(t, "required") and t.required else []

            tools.append(ToolDefIR(
                name=t.name,
                description=t.description if hasattr(t, "description") else "",
                parameters=parameters,
                required=req,
            ))

        # 读取 mode 配置
        raw_mode = getattr(config.runtime, "mode", None)
        try:
            mode = AgentMode(raw_mode) if raw_mode else AgentMode.SIMPLE
        except ValueError:
            mode = AgentMode.SIMPLE
        raw_mode_config = getattr(config.runtime, "mode_config", {}) or {}
        mode_config = ModeConfig.from_dict(raw_mode_config)
        mode_config.mode = mode

        return cls(
            id=config.meta.id,
            name=config.meta.name,
            version=config.meta.version,
            author=config.meta.author,
            description=config.meta.description,
            mode=mode,
            mode_config=mode_config,
            provider=provider_map.get(config.model.provider, ProviderType.OPENAI),
            model_name=config.model.model_name,
            fallback_model=config.model.fallback,
            temperature=config.model.parameters.temperature,
            max_tokens=config.model.parameters.max_tokens,
            top_p=getattr(config.model.parameters, "top_p", 0.95),
            system_prompt=config.system_prompt,
            tools=tools,
            knowledge_sources=[
                {"type": k.type, "source": k.source}
                for k in config.knowledge
            ],
            runtime_language=config.runtime.language,
            runtime_packages=config.runtime.packages,
            avatar=config.ui.avatar,
            welcome_message=config.ui.welcome_message,
            suggested_questions=config.ui.suggested_questions,
            tags=config.meta.tags,
        )

    def to_yaml_dict(self) -> dict[str, Any]:
        """
        导出为 YAML 字典（与原 YAML Agent DSL 格式兼容）。

        Returns:
            可直接 yaml.dump() 的字典
        """
        return {
            "meta": {
                "id": self.id,
                "name": self.name,
                "version": self.version,
                "author": self.author,
                "description": self.description,
                "tags": self.tags,
                "license": "MIT",
            },
            "model": {
                "provider": self.provider.value,
                "model_name": self.model_name,
                "fallback": self.fallback_model,
                "parameters": {
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "top_p": self.top_p,
                },
            },
            "system_prompt": self.system_prompt,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "type": "function",
                    "properties": t.parameters,
                    "required": t.required,
                }
                for t in self.tools
            ],
            "knowledge": self.knowledge_sources,
            "runtime": {
                "language": self.runtime_language,
                "min_version": ">=3.10",
                "packages": self.runtime_packages,
                "mode": self.mode.value,
                "mode_config": self.mode_config.to_dict(),
            },
            "ui": {
                "avatar": self.avatar,
                "welcome_message": self.welcome_message,
                "suggested_questions": self.suggested_questions,
            },
        }


# ══════════════════════════════════════════════
# Provider 配置
# ══════════════════════════════════════════════

@dataclass
class ProviderConfig:
    """Provider 连接配置"""
    provider: ProviderType
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    proxy: str = ""                 # HTTP/SOCKS5 代理地址
    timeout: float = 120.0
    max_retries: int = 3
    extra: dict[str, Any] = field(default_factory=dict)
