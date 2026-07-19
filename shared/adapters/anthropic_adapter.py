"""
AI Agent Hub — Anthropic (Claude) 适配器

关键差异：
- system 是独立字段，不在 messages 中
- tool 结果用 role:"user" + content[{type:"tool_result"}]
- 工具定义格式：{name, description, input_schema}
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


class AnthropicAdapter(BaseAdapter):
    """Anthropic SDK 适配器（支持 Claude 3.5 Sonnet / Claude 3 Opus 等）"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError("需要安装 anthropic: pip install anthropic>=0.30")

            api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Anthropic API Key 未设置。请设置环境变量 ANTHROPIC_API_KEY"
                )
            self._client = anthropic.Anthropic(
                api_key=api_key,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )

    # ── 格式转换 ──

    @staticmethod
    def _build_messages(messages: list[MessageIR]) -> tuple[str | None, list[dict]]:
        """
        MessageIR → (system_prompt, anthropic_messages)

        Anthropic 特殊处理：
        - system prompt 从 messages 中提取，作为单独参数
        - tool 结果用 role:"user" 包装
        """
        system_prompt = None
        result = []

        for m in messages:
            if m.role == "system":
                system_prompt = m.content
                continue

            if m.role == "tool":
                # Anthropic: tool 结果作为 user 消息
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "",
                        "content": m.content or "",
                    }],
                })
                continue

            if m.role == "assistant" and m.tool_calls:
                # Anthropic: 构造 tool_use content block
                content_blocks = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                result.append({"role": "assistant", "content": content_blocks})
                continue

            # 普通 user/assistant 消息
            if m.content is not None:
                result.append({"role": m.role, "content": m.content})
            else:
                result.append({"role": m.role, "content": ""})

        return system_prompt, result

    @staticmethod
    def _build_tools(tools: list[ToolDefIR]) -> list[dict]:
        """ToolDefIR → Anthropic tools 格式"""
        return [t.to_anthropic_format() for t in tools]

    @staticmethod
    def _parse_response(response) -> LLMResponseIR:
        """Anthropic 响应 → LLMResponseIR"""
        tool_calls = []
        text_content = ""

        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCallIR(
                    id=block.id,
                    name=block.name,
                    arguments=dict(block.input) if block.input else {},
                ))

        usage = {
            "input_tokens": response.usage.input_tokens if response.usage else 0,
            "output_tokens": response.usage.output_tokens if response.usage else 0,
            "total_tokens": (
                response.usage.input_tokens + response.usage.output_tokens
            ) if response.usage else 0,
        }

        return LLMResponseIR(
            content=text_content or None,
            model=response.model,
            provider=ProviderType.ANTHROPIC,
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

        system_prompt, anthropic_msgs = self._build_messages(messages)

        kwargs: dict = {
            "model": self.config.model,
            "messages": anthropic_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._build_tools(tools)

        response = self._client.messages.create(**kwargs)
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

        system_prompt, anthropic_msgs = self._build_messages(messages)

        kwargs: dict = {
            "model": self.config.model,
            "messages": anthropic_msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = self._build_tools(tools)

        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text
