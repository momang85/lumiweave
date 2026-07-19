"""
AI Agent Hub — DeepSeek 适配器

基于 OpenAI 兼容 API，但有两个关键差异：
1. reasoning_content 字段（DeepSeek-R1 的思维链）
2. 工具调用格式完全兼容 OpenAI
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


class DeepSeekAdapter(BaseAdapter):
    """DeepSeek API 适配器（基于 OpenAI 兼容格式，支持 DeepSeek-V3 / R1）"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        if not config.base_url:
            config.base_url = "https://api.deepseek.com"
        self._client = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.DEEPSEEK

    def _ensure_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError:
                raise ImportError("需要安装 openai: pip install openai>=1.0")

            api_key = self.config.api_key or os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "DeepSeek API Key 未设置。请设置环境变量 DEEPSEEK_API_KEY"
                )

            kwargs: dict = {
                "api_key": api_key,
                "base_url": self.config.base_url,
                "timeout": self.config.timeout,
                "max_retries": self.config.max_retries,
            }

            # v2.3: 代理——直接注入 httpx transport
            proxy = self.config.proxy or os.getenv("LLM_PROXY", "")
            if proxy:
                try:
                    import httpx
                    transport = httpx.HTTPTransport(proxy=proxy)
                    kwargs["http_client"] = httpx.Client(transport=transport)
                except Exception:
                    pass  # 降级

            self._client = openai.OpenAI(**kwargs)

    # ── 格式转换（OpenAI 兼容） ──

    @staticmethod
    def _build_messages(messages: list[MessageIR]) -> list[dict]:
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
        return [t.to_openai_format() for t in tools]

    @staticmethod
    def _parse_response(response) -> LLMResponseIR:
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

        # 提取 reasoning_content（DeepSeek-R1 特有）
        reasoning = ""
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            reasoning = msg.reasoning_content

        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        response_ir = LLMResponseIR(
            content=msg.content,
            model=response.model,
            provider=ProviderType.DEEPSEEK,
            tool_calls=tool_calls,
            usage=usage,
        )
        # 将 reasoning_content 存到 usage 扩展字段
        if reasoning:
            response_ir.usage["reasoning_tokens"] = 0
            response_ir.usage["reasoning_content"] = reasoning

        return response_ir

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
        """SSE 流式输出（含 reasoning_content）"""
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
            if delta:
                # DeepSeek-R1 的 reasoning_content
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    yield f"[思考] {delta.reasoning_content}"
                if delta.content:
                    yield delta.content
