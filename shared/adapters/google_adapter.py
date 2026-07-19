"""
AI Agent Hub — Google Gemini 适配器

关键差异：
- system_instruction 是独立 config 字段
- role 用 "model" 而非 "assistant"
- 工具定义格式：tools: [{functionDeclarations: []}]
"""

from __future__ import annotations

import json
import logging
import os

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


class GoogleAdapter(BaseAdapter):
    """Google Generative AI 适配器（支持 Gemini 2.0 Flash / Gemini 1.5 Pro 等）"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None
        self._model_instance = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GOOGLE

    def _ensure_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai
            except ImportError:
                raise ImportError(
                    "需要安装 google-generativeai: pip install google-generativeai>=0.7"
                )

            api_key = self.config.api_key or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Google API Key 未设置。请设置环境变量 GOOGLE_API_KEY"
                )

            genai.configure(api_key=api_key)
            self._client = genai
            self._model_instance = genai.GenerativeModel(self.config.model)

    # ── 格式转换 ──

    @staticmethod
    def _build_messages(messages: list[MessageIR]) -> tuple[str | None, list[dict]]:
        """
        MessageIR → (system_instruction, contents)

        Google 格式：
        - system_instruction 单独抽出
        - role "assistant" → "model"
        - tool 消息作为 function_response
        """
        system_instruction = None
        contents = []

        for m in messages:
            if m.role == "system":
                system_instruction = m.content
                continue

            role = "model" if m.role == "assistant" else m.role

            if m.role == "tool":
                # Google: 工具结果作为 function_response
                contents.append({
                    "role": "tool",
                    "parts": [{
                        "functionResponse": {
                            "name": m.name or "",
                            "response": {"result": m.content or ""},
                        }
                    }],
                })
                continue

            if m.role == "assistant" and m.tool_calls:
                # Google: 工具调用作为 functionCall
                parts = []
                if m.content:
                    parts.append({"text": m.content})
                for tc in m.tool_calls:
                    parts.append({
                        "functionCall": {
                            "name": tc.name,
                            "args": tc.arguments,
                        },
                    })
                contents.append({"role": "model", "parts": parts})
                continue

            contents.append({
                "role": role,
                "parts": [{"text": m.content or ""}],
            })

        return system_instruction, contents

    @staticmethod
    def _build_tools(tools: list[ToolDefIR]) -> dict | None:
        """ToolDefIR → Google tools 格式"""
        if not tools:
            return None
        declarations = [t.to_google_format() for t in tools]
        return {"function_declarations": declarations}

    @staticmethod
    def _parse_response(response) -> LLMResponseIR:
        """Google 响应 → LLMResponseIR"""
        if not response.candidates:
            return LLMResponseIR(
                content="",
                provider=ProviderType.GOOGLE,
            )

        candidate = response.candidates[0]
        tool_calls = []
        text_parts = []

        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                args = dict(fc.args) if fc.args else {}
                tool_calls.append(ToolCallIR(
                    id=fc.name,  # Google 没有独立 tool_call_id
                    name=fc.name,
                    arguments=args,
                ))

        usage = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                "completion_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
            }

        return LLMResponseIR(
            content="".join(text_parts) or None,
            model=response.model_name if hasattr(response, "model_name") else "",
            provider=ProviderType.GOOGLE,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
        )

    # ── 核心调用 ──

    @retry_on_failure(max_retries=3, base_delay=1.0)
    def _chat_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponseIR:
        self._ensure_client()

        system_instruction, contents = self._build_messages(messages)

        kwargs: dict = {
            "contents": contents,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        }
        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        tool_config = self._build_tools(tools or [])
        if tool_config:
            kwargs["tools"] = [tool_config]

        response = self._model_instance.generate_content(**kwargs)
        return self._parse_response(response)

    def _stream_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ):
        """流式输出"""
        self._ensure_client()

        system_instruction, contents = self._build_messages(messages)

        kwargs: dict = {
            "contents": contents,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
            "stream": True,
        }
        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        tool_config = self._build_tools(tools or [])
        if tool_config:
            kwargs["tools"] = [tool_config]

        response = self._model_instance.generate_content(**kwargs)
        for chunk in response:
            if chunk.candidates:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        yield part.text
