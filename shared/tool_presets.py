"""
AI Agent Hub v0.6 — 工具预设系统

用户可预配置常用工具的 API Key / 参数。
创建 Agent 时，LLM 看到可用工具清单（不含 Key）来设计工具定义，
本地系统在最后一步自动将秘密（API Key）填入 LLM 留空的位置。

两种参数：
- public_params:  传给 LLM，帮助生成工具定义（如工具名、描述、示例 URL）
- secret_params:  本地注入，不在 HTTP 或 LLM 中传输（如 API Key、Token）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ── 预设工具定义 ──

@dataclass
class ToolPreset:
    """一个可预配的工具模板"""
    name: str                          # 工具名称（LLM 引用用）
    handler: str                       # 处理函数名
    description: str                   # 工具说明（公开）
    public_params: dict[str, Any] = field(default_factory=dict)   # 公开参数（传给 LLM）
    secret_params: dict[str, str] = field(default_factory=dict)   # 秘密参数（本地注入，key=env_var_name）
    category: str = "general"          # 分类


# ── 内置工具预设清单 ──

BUILTIN_TOOL_PRESETS: dict[str, ToolPreset] = {
    "web_search": ToolPreset(
        name="web_search",
        handler="web_search",
        description="搜索互联网获取最新信息",
        public_params={
            "name": "web_search",
            "description": "搜索互联网获取最新信息，返回标题、URL、摘要。使用 DuckDuckGo 免费 API，无需配置密钥",
            "parameters": [
                {"name": "query", "type": "string", "description": "搜索关键词", "required": True},
            ],
        },
        secret_params={},  # v0.6.1: DuckDuckGo 免费，无需 Key
        category="search",
    ),
    "read_file": ToolPreset(
        name="read_file",
        handler="read_file",
        description="读取本地文件内容",
        public_params={
            "name": "read_file",
            "description": "读取项目内文件内容",
            "parameters": [
                {"name": "path", "type": "string", "description": "文件路径", "required": True},
            ],
        },
        secret_params={},
        category="file",
    ),
    "write_file": ToolPreset(
        name="write_file",
        handler="write_file",
        description="写入或创建文件",
        public_params={
            "name": "write_file",
            "description": "创建或覆盖写入文件内容",
            "parameters": [
                {"name": "path", "type": "string", "description": "文件路径", "required": True},
                {"name": "content", "type": "string", "description": "文件内容", "required": True},
                {"name": "overwrite", "type": "boolean", "description": "是否覆盖", "required": False},
            ],
        },
        secret_params={},
        category="file",
    ),
    "list_dir": ToolPreset(
        name="list_dir",
        handler="list_dir",
        description="列出目录内容",
        public_params={
            "name": "list_dir",
            "description": "列出目录中的文件和子目录",
            "parameters": [
                {"name": "path", "type": "string", "description": "目录路径", "required": False},
            ],
        },
        secret_params={},
        category="file",
    ),
    "run_command": ToolPreset(
        name="run_command",
        handler="run_command",
        description="执行 shell 命令",
        public_params={
            "name": "run_command",
            "description": "在本地执行 shell 命令并获取输出",
            "parameters": [
                {"name": "command", "type": "string", "description": "要执行的命令", "required": True},
                {"name": "timeout", "type": "integer", "description": "超时秒数", "required": False},
            ],
        },
        secret_params={},
        category="system",
    ),
    "code_executor": ToolPreset(
        name="code_executor",
        handler="code_executor",
        description="执行 Python 代码",
        public_params={
            "name": "code_executor",
            "description": "在沙箱中执行 Python 代码并返回输出",
            "parameters": [
                {"name": "code", "type": "string", "description": "Python 代码", "required": True},
                {"name": "timeout", "type": "integer", "description": "超时秒数，默认10", "required": False},
            ],
        },
        secret_params={},
        category="system",
    ),
    "github_api": ToolPreset(
        name="github_api",
        handler="github_api",
        description="调用 GitHub API（需 Token）",
        public_params={
            "name": "github_api",
            "description": "调用 GitHub REST API，需要设置 GITHUB_TOKEN 环境变量",
            "parameters": [
                {"name": "endpoint", "type": "string", "description": "API 路径，如 /repos/{owner}/{repo}", "required": True},
                {"name": "method", "type": "string", "description": "GET/POST/PATCH，默认GET", "required": False},
            ],
        },
        secret_params={"api_token": "GITHUB_TOKEN"},
        category="api",
    ),
}


def get_enabled_presets(env: dict[str, str] | None = None) -> list[dict]:
    """返回当前已启用（有 Key 或无需 Key）的工具预设清单（仅公开参数）。

    此函数返回的数据可直接传给 LLM 的 system_prompt。
    """
    if env is None:
        env = dict(os.environ)

    enabled = []
    for name, preset in BUILTIN_TOOL_PRESETS.items():
        # 检查是否需要秘密参数
        has_secrets = True
        for secret_key, env_var in preset.secret_params.items():
            if not env.get(env_var, "").strip():
                has_secrets = False
                break

        if has_secrets:
            enabled.append({
                "name": preset.name,
                "handler": preset.handler,
                "description": preset.description,
                "definition": preset.public_params,
                "category": preset.category,
            })

    return enabled


def inject_secrets(tool_def: dict, presets: dict[str, ToolPreset], env: dict[str, str] | None = None) -> dict:
    """将本地秘密参数注入到 LLM 生成的工具定义中。

    LLM 生成的工具定义中，需要用 {{SECRET:key}} 占位符标记秘密参数位置。
    此函数将占位符替换为实际值。

    也支持直接匹配工具名称对应的预设，自动补充参数。
    """
    if env is None:
        env = dict(os.environ)

    tool_name = tool_def.get("name", "")

    # 匹配预设
    preset = presets.get(tool_name)
    if not preset:
        return tool_def  # 无匹配预设，原样返回

    # 补充缺失的参数定义
    if "parameters" in tool_def and preset.public_params.get("parameters"):
        existing_params = {p.get("name", ""): p for p in tool_def["parameters"]}
        for pdef in preset.public_params.get("parameters", []):
            pname = pdef.get("name", "")
            if pname not in existing_params:
                tool_def["parameters"].append(pdef)

    # 注入秘密值：替换模板中的占位符
    for secret_key, env_var in preset.secret_params.items():
        secret_value = env.get(env_var, "").strip()
        placeholder = f"{{{{SECRET:{secret_key}}}}}"

        # 在所有参数字段中替换
        for param in tool_def.get("parameters", []):
            if "description" in param:
                param["description"] = param["description"].replace(placeholder, "***")  # 不暴露在描述中

        # 在工具描述中替换
        if "description" in tool_def:
            tool_def["description"] = tool_def["description"].replace(placeholder, "***")

    return tool_def
