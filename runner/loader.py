"""
AI Agent Hub — Agent 定义加载器 v0.2

在 v0.1 基础上增加：
- Tool properties（JSON Schema 格式参数）
- Tool handler / timeout / requires_approval
- Model tool_choice / parallel_tool_calls
- Agent examples（few-shot）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# 数据模型 v0.2
# ──────────────────────────────────────────────

class MetaConfig(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    author: str = "Unknown"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    license: str = "MIT"
    created_at: str = ""


class ToolParam(BaseModel):
    """单个参数定义（扁平格式）"""
    name: str
    type: str = "string"          # string | number | integer | boolean | array | object
    description: str = ""         # v0.2 新增
    required: bool = False
    default: Any = None
    enum: list[str] | None = None


class ToolConfig(BaseModel):
    """工具定义"""
    name: str
    description: str = ""
    type: str = "function"        # function | api | mcp
    handler: str = ""             # v0.2 新增：处理函数名
    endpoint: str = ""
    method: str = "GET"
    # 参数定义（二选一或共存）
    parameters: list[ToolParam] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)   # v0.2: JSON Schema 格式
    required: list[str] = Field(default_factory=list)          # v0.2: 必填参数
    # 安全控制
    timeout: int = 30
    requires_approval: bool = False
    sandbox: bool = True


class ModelParameters(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float = 1.0
    tool_choice: str = "auto"              # v0.2: auto | none | required
    parallel_tool_calls: bool = True       # v0.2


class ModelConfig(BaseModel):
    provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    fallback: str = ""
    parameters: ModelParameters = Field(default_factory=ModelParameters)


class KnowledgeItem(BaseModel):
    type: str = "url"
    source: str = ""


class RuntimeConfig(BaseModel):
    language: str = "python"
    min_version: str = ">=3.10"
    packages: list[str] = Field(default_factory=list)
    mode: str = "simple"                          # v0.5: 运行模式
    mode_config: dict[str, Any] = Field(default_factory=dict)


class UIConfig(BaseModel):
    avatar: str = "🤖"
    welcome_message: str = "你好！有什么可以帮你的？"
    suggested_questions: list[str] = Field(default_factory=list)


class ExamplePair(BaseModel):
    """Few-shot 示例对话对"""
    user: str
    assistant: str


class AgentConfig(BaseModel):
    """完整的 Agent 定义 v0.2"""
    meta: MetaConfig
    model: ModelConfig
    system_prompt: str = ""
    examples: list[ExamplePair] = Field(default_factory=list)   # v0.2 新增
    tools: list[ToolConfig] = Field(default_factory=list)
    knowledge: list[KnowledgeItem] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def strip_system_prompt(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    # ── 辅助方法 ──

    def to_openai_tools(self) -> list[dict]:
        """
        将 Agent 定义的 tools 转换为 OpenAI Function Calling 格式。

        type='function' 和 type='api' 均视为可调用的函数工具。
        type='mcp' 暂不转换。
        """
        openai_tools = []
        for tool in self.tools:
            if tool.type not in ("function", "api"):
                continue

            # 构建 parameters JSON Schema
            if tool.properties:
                # v0.2 格式：直接使用 properties
                param_schema = {
                    "type": "object",
                    "properties": tool.properties,
                }
                if tool.required:
                    param_schema["required"] = tool.required
            else:
                # v0.1 兼容格式：从扁平参数列表构建
                props = {}
                required_list = []
                for p in tool.parameters:
                    prop_def = {"type": _map_type(p.type)}
                    if p.description:
                        prop_def["description"] = p.description
                    if p.enum:
                        prop_def["enum"] = p.enum
                    if p.default is not None:
                        prop_def["default"] = p.default
                    props[p.name] = prop_def
                    if p.required:
                        required_list.append(p.name)

                param_schema = {
                    "type": "object",
                    "properties": props,
                }
                if required_list:
                    param_schema["required"] = required_list

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": param_schema,
                },
            })

        return openai_tools


def _map_type(t: str) -> str:
    """将简化的类型名映射为 JSON Schema 类型"""
    mapping = {
        "string": "string",
        "number": "number",
        "integer": "integer",
        "int": "integer",
        "bool": "boolean",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "list": "array",
    }
    return mapping.get(t.lower(), "string")


# ──────────────────────────────────────────────
# 加载器（同 v0.1）
# ──────────────────────────────────────────────

class LoadError(Exception):
    """加载或校验失败"""


def load_agent(path: str | Path) -> AgentConfig:
    path = Path(path)
    if not path.exists():
        raise LoadError(f"文件不存在: {path}")
    if path.suffix not in (".yaml", ".yml"):
        raise LoadError(f"不是 YAML 文件: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise LoadError(f"YAML 解析失败: {e}") from e

    if raw is None:
        raise LoadError("文件内容为空")
    if "fields" in raw:
        raise LoadError(
            f"这不是 Agent 定义文件，而是规范文档 ({path.name})。"
        )

    try:
        config = AgentConfig.model_validate(raw)
    except Exception as e:
        raise LoadError(f"Agent 定义校验失败:\n{e}") from e

    return config


def list_available_agents(agents_dir: str | Path = "agents") -> list[Path]:
    agents_dir = Path(agents_dir)
    if not agents_dir.is_dir():
        return []
    files = sorted(agents_dir.glob("*.yaml")) + sorted(agents_dir.glob("*.yml"))
    return [
        f for f in files
        if "spec" not in f.name.lower() and "readme" not in f.name.lower()
    ]
