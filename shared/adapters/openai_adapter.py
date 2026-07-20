"""
AI Agent Hub — OpenAI 适配器

将 IR 格式转换为 OpenAI API 格式，调用完成后转换回 IR 响应。
支持同步对话和 SSE 流式输出。
"""

from __future__ import annotations

import json
import os as _os

# v2.3: 模块级代理注入——在 openai/httpx 首次使用前设置环境变量
_proxy_url = _os.getenv("LLM_PROXY", "")
if _proxy_url:
    _os.environ.setdefault("HTTP_PROXY", _proxy_url)
    _os.environ.setdefault("HTTPS_PROXY", _proxy_url)
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


class OpenAIAdapter(BaseAdapter):
    """OpenAI SDK 适配器（支持 GPT-4o/GPT-4o-mini 等）"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    def _ensure_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError("需要安装 openai: pip install openai>=1.0")

            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OpenAI API Key 未设置。请设置环境变量 OPENAI_API_KEY "
                    "或在 ProviderConfig 中传入 api_key"
                )

            kwargs: dict = {
                "api_key": api_key,
                "base_url": self.config.base_url or None,
                "timeout": self.config.timeout,
                "max_retries": self.config.max_retries,
            }

            # v2.4: 代理——环境变量注入（httpx自动读取，Python3.14兼容）
            proxy = self.config.proxy or os.getenv("LLM_PROXY", "")
            if proxy:
                os.environ["HTTP_PROXY"] = proxy
                os.environ["HTTPS_PROXY"] = proxy
                os.environ["NO_PROXY"] = "localhost,127.0.0.1"

            self._client = openai.OpenAI(**kwargs)

    # ── 格式转换 ──

    @staticmethod
    def _build_messages(messages: list[MessageIR]) -> list[dict]:
        """MessageIR → OpenAI messages 格式"""
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
        """ToolDefIR → OpenAI tools 格式"""
        return [t.to_openai_format() for t in tools]

    @staticmethod
    def _parse_response(response) -> LLMResponseIR:
        """OpenAI 响应 → LLMResponseIR"""
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    args = {}
                tool_calls.append(ToolCallIR(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponseIR(
            content=msg.content,
            model=response.model,
            provider=ProviderType.OPENAI,
            tool_calls=tool_calls,
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

        kwargs: dict = {
            "model": self.config.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    def _stream_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ):
        """SSE 流式输出"""
        self._ensure_client()

        kwargs: dict = {
            "model": self.config.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        stream = self._client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
