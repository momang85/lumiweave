"""
AI Agent Hub — Ollama 适配器

基于 HTTP REST API，OpenAI 兼容格式但有细节差异。
本地运行，无需 API Key。
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from .base_adapter import BaseAdapter, retry_on_failure
from ..ir_models import (
    LLMResponseIR,
    MessageIR,
    ProviderConfig,
    ProviderType,
    ToolCallIR,
    ToolDefIR,
)

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """Ollama HTTP REST API 适配器（支持 Llama 3 / Mistral / Gemma 等本地模型）"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    # ── 格式转换 ──

    @staticmethod
    def _build_messages(messages: list[MessageIR]) -> list[dict]:
        """MessageIR → Ollama API 格式（OpenAI 兼容）"""
        result = []
        for m in messages:
            msg: dict = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.name is not None:
                msg["name"] = m.name
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in m.tool_calls
                ]
            result.append(msg)
        return result

    @staticmethod
    def _build_tools(tools: list[ToolDefIR]) -> list[dict]:
        """ToolDefIR → Ollama tools 格式（OpenAI 兼容）"""
        return [t.to_openai_format() for t in tools]

    @staticmethod
    def _parse_response(data: dict) -> LLMResponseIR:
        """Ollama 响应 → LLMResponseIR"""
        message = data.get("message", data)

        content = message.get("content", "")
        tool_calls = None

        if "tool_calls" in message and message["tool_calls"]:
            tool_calls = []
            for tc in message["tool_calls"]:
                func = tc.get("function", tc)
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"_raw": args}

                tool_calls.append(ToolCallIR(
                    id=tc.get("id", "unknown"),
                    name=func.get("name", "unknown"),
                    arguments=args,
                ))

        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        }

        return LLMResponseIR(
            content=content or None,
            model=data.get("model", ""),
            provider=ProviderType.OLLAMA,
            tool_calls=tool_calls,
            usage=usage,
        )

    # ── 核心调用 ──

    @retry_on_failure(max_retries=2, base_delay=0.5)
    def _chat_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponseIR:
        payload: dict = {
            "model": self.config.model,
            "messages": self._build_messages(messages),
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }
        if tools:
            payload["tools"] = self._build_tools(tools)

        response = self._http.post("/api/chat", json=payload)
        response.raise_for_status()
        return self._parse_response(response.json())

    def _stream_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ):
        """流式输出"""
        payload: dict = {
            "model": self.config.model,
            "messages": self._build_messages(messages),
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": True,
        }
        if tools:
            payload["tools"] = self._build_tools(tools)

        with self._http.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    def list_local_models(self) -> list[dict]:
        """列出本地已安装的模型"""
        try:
            response = self._http.get("/api/tags")
            response.raise_for_status()
            return response.json().get("models", [])
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    def pull_model(self, model_name: str) -> bool:
        """拉取模型"""
        try:
            response = self._http.post("/api/pull", json={"name": model_name},
                                       timeout=300)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False
