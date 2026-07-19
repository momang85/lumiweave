"""
AI Agent Hub — Agent 管理服务

处理 Agent 的 CRUD、YAML 导入导出、存储管理。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ── 存储路径 ──
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "agent_store")
Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)


# ── Agent 数据模型（简化版，用于前端交互） ──

class AgentRecord:
    """Agent 存储记录"""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        system_prompt: str = "",
        model_provider: str = "openai",
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        tags: list[str] | None = None,
        avatar: str = "",
        suggested_questions: list[str] | None = None,
        mode: str = "simple",                       # v0.5
        mode_config: dict | None = None,            # v0.5
        created_at: str = "",
        updated_at: str = "",
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.model_provider = model_provider
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools or []
        self.tags = tags or []
        self.avatar = avatar or "🤖"
        self.suggested_questions = suggested_questions or []
        self.mode = mode
        self.mode_config = mode_config or {}
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.updated_at = updated_at or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": self.tools,
            "tags": self.tags,
            "avatar": self.avatar,
            "suggested_questions": self.suggested_questions,
            "mode": self.mode,
            "mode_config": self.mode_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_yaml(self) -> str:
        """导出为符合 DSL 规范的 YAML"""
        record = {
            "meta": {
                "id": f"com.aihub.{self.agent_id}",
                "name": self.name,
                "version": "1.0.0",
                "author": "AI Hub Builder",
                "description": self.description,
                "tags": self.tags,
                "license": "MIT",
            },
            "model": {
                "provider": self.model_provider,
                "model_name": self.model_name,
                "fallback": "",
                "parameters": {
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
            },
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "knowledge": [],
            "runtime": {"language": "python", "min_version": ">=3.10", "packages": []},
            "ui": {
                "avatar": self.avatar,
                "welcome_message": f"你好！我是 {self.name}。",
                "suggested_questions": self.suggested_questions,
            },
        }
        return yaml.dump(record, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _record_path(agent_id: str) -> str:
    return os.path.join(STORAGE_DIR, f"{agent_id}.json")


def save_agent(record: AgentRecord) -> AgentRecord:
    record.updated_at = datetime.now(timezone.utc).isoformat()
    with open(_record_path(record.agent_id), "w", encoding="utf-8") as f:
        json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
    return record


def load_agent(agent_id: str) -> Optional[AgentRecord]:
    path = _record_path(agent_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return AgentRecord(**data)


def list_agents() -> list[AgentRecord]:
    records = []
    for fname in sorted(os.listdir(STORAGE_DIR)):
        if fname.endswith(".json"):
            agent_id = fname[:-5]
            rec = load_agent(agent_id)
            if rec:
                records.append(rec)
    return records


def delete_agent(agent_id: str) -> bool:
    path = _record_path(agent_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def import_from_yaml(yaml_content: str) -> AgentRecord:
    """从 YAML 内容导入 Agent"""
    data = yaml.safe_load(yaml_content)
    if not data or "meta" not in data:
        raise ValueError("无效的 Agent YAML 格式")

    meta = data.get("meta", {})
    model = data.get("model", {})
    params = model.get("parameters", {})

    runtime = data.get("runtime", {})
    record = AgentRecord(
        agent_id=str(uuid.uuid4())[:12],
        name=meta.get("name", "导入的 Agent"),
        description=meta.get("description", ""),
        system_prompt=data.get("system_prompt", ""),
        model_provider=model.get("provider", "openai"),
        model_name=model.get("model_name", "gpt-4o-mini"),
        temperature=params.get("temperature", 0.7),
        max_tokens=params.get("max_tokens", 4096),
        tools=data.get("tools", []),
        tags=meta.get("tags", []),
        avatar=data.get("ui", {}).get("avatar", "🤖"),
        suggested_questions=data.get("ui", {}).get("suggested_questions", []),
        mode=runtime.get("mode", "simple"),
        mode_config=runtime.get("mode_config", {}),
    )
    return save_agent(record)
