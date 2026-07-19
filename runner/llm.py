"""
AI Agent Hub — LLM 客户端 v0.2

新增：
- Tool Calling 支持（OpenAI Function Calling 格式）
- ToolCall 数据结构
- BaseLLM.chat() 接受 tools 参数
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class ToolCall:
    """单个工具调用请求"""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    role: str          # system | user | assistant | tool
    content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None   # v0.2: assistant 消息可能携带 tool_calls


@dataclass
class LLMResponse:
    content: str | None
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCall] | None = None    # v0.2: LLM 可能返回 tool_calls 而非 content

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)

    @property
    def is_tool_call(self) -> bool:
        """是否需要执行工具调用"""
        return bool(self.tool_calls)


# ──────────────────────────────────────────────
# 抽象基类
# ──────────────────────────────────────────────

class BaseLLM(ABC):
    """LLM 客户端基类"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,           # v0.2: OpenAI 格式的工具定义
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        ...


# ──────────────────────────────────────────────
# OpenAI Provider（增强 Function Calling）
# ──────────────────────────────────────────────

class OpenAILLM(BaseLLM):
    """基于 OpenAI SDK 的云端推理客户端"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        try:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=base_url,
            )
        except ImportError:
            raise ImportError("需要安装 openai 包: pip install openai")

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_mock(self) -> bool:
        return False

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        if not self.api_key:
            raise RuntimeError(
                "未设置 OPENAI_API_KEY 环境变量。"
                "请在终端运行: set OPENAI_API_KEY=sk-xxx (Windows)"
            )

        # 构建 API 消息
        api_messages = []
        for m in messages:
            msg = {"role": m.role}
            if m.content is not None:
                msg["content"] = m.content
            if m.tool_call_id is not None:
                msg["tool_call_id"] = m.tool_call_id
            if m.name is not None:
                msg["name"] = m.name
            if m.tool_calls is not None:
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
            api_messages.append(msg)

        # 构建 API 请求参数
        kwargs = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        msg = choice.message

        # 解析 tool_calls
        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return LLMResponse(
            content=msg.content,
            model=response.model,
            usage=usage,
            tool_calls=tool_calls,
        )


# ──────────────────────────────────────────────
# Mock Provider
# ──────────────────────────────────────────────

_MOCK_RESPONSES: dict[str, list[str]] = {
    "python": [
        "这是一个 Python 相关的 Mock 回复。配置 OPENAI_API_KEY 获得真实回复。",
    ],
    "javascript": [
        "这是一个前端相关的 Mock 回复。配置 API Key 后获得真实 AI 回复。",
    ],
    "default": [
        "🤖 [Mock 模式] 当前运行在无 API 的演示模式。设置 OPENAI_API_KEY 启用真实 AI。",
    ],
}


class MockLLM(BaseLLM):
    """Mock 客户端"""

    def __init__(self, model: str = "mock", agent_tags: list[str] | None = None):
        self.model = model
        self._tags = agent_tags or []
        self._call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_mock(self) -> bool:
        return True

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self._call_count += 1
        time.sleep(0.3)

        # 如果传入了 tools，模拟偶尔返回 tool_call
        if tools and self._call_count % 4 == 1:
            # 模拟一次 tool call
            first_tool = tools[0]["function"]
            return LLMResponse(
                content=None,
                model=f"mock/{self.model}",
                tool_calls=[
                    ToolCall(
                        id=f"mock_call_{self._call_count}",
                        name=first_tool["name"],
                        arguments={"query": "mock search query"},
                    )
                ],
            )

        for tag in self._tags:
            for key, responses in _MOCK_RESPONSES.items():
                if key in tag.lower():
                    content = responses[self._call_count % len(responses)]
                    break
            else:
                continue
            break
        else:
            content = _MOCK_RESPONSES["default"][
                self._call_count % len(_MOCK_RESPONSES["default"])
            ]

        user_msg = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        if user_msg:
            content = (
                f"🤖 [Mock] 收到: {user_msg[:60]}...\n\n{content}"
            )

        return LLMResponse(
            content=content,
            model=f"mock/{self.model}",
        )


# ──────────────────────────────────────────────
# v0.3: 多 Provider 支持（基于 shared/adapters）
# ──────────────────────────────────────────────

class _SharedAdapterWrapper(BaseLLM):
    """
    将 shared/adapters 的 BaseAdapter 包装为 BaseLLM 接口。

    用于 Anthropic / Google / Ollama / DeepSeek 等 Provider。
    """

    def __init__(self, adapter, provider_name: str, model: str = ""):
        self._adapter = adapter
        self._provider = provider_name
        self._model = model or adapter.config.model

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def is_mock(self) -> bool:
        return False

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        from shared.ir_models import MessageIR, ToolDefIR, ToolCallIR

        # 转换为 IR 消息
        ir_messages = []
        for m in messages:
            ir_messages.append(MessageIR(
                role=m.role,
                content=m.content,
                tool_call_id=m.tool_call_id,
                name=m.name,
                tool_calls=[
                    ToolCallIR(id=tc.id, name=tc.name, arguments=tc.arguments)
                    for tc in m.tool_calls
                ] if m.tool_calls else None,
            ))

        # 转换为 IR 工具
        ir_tools = None
        if tools:
            ir_tools = []
            for t in tools:
                func = t.get("function", t)
                params = func.get("parameters", func.get("input_schema", {}))
                ir_tools.append(ToolDefIR(
                    name=func.get("name", t.get("name", "")),
                    description=func.get("description", t.get("description", "")),
                    parameters=params.get("properties", {}),
                    required=params.get("required", []),
                ))

        # 调用适配器
        ir_resp = self._adapter.chat(ir_messages, ir_tools, temperature, max_tokens)

        # 转换回 LLMResponse
        return LLMResponse(
            content=ir_resp.content,
            model=self._model,
            usage=ir_resp.usage,
            tool_calls=[
                ToolCall(id=tc.id, name=tc.name, arguments=tc.arguments)
                for tc in ir_tool_calls
            ] if (ir_tool_calls := ir_resp.tool_calls) else None,
        )


class AnthropicLLM(BaseLLM):
    """Anthropic Claude 客户端"""
    def __init__(self, model: str = "claude-3-5-sonnet-20241022", api_key: str | None = None):
        from shared.adapters.anthropic_adapter import AnthropicAdapter
        from shared.ir_models import ProviderConfig, ProviderType

        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("未设置 ANTHROPIC_API_KEY 环境变量")
        config = ProviderConfig(provider=ProviderType.ANTHROPIC, model=model, api_key=api_key)
        self._wrapped = _SharedAdapterWrapper(AnthropicAdapter(config), "anthropic", model)

    @property
    def provider_name(self) -> str: return "anthropic"
    @property
    def is_mock(self) -> bool: return False
    def chat(self, **kwargs) -> LLMResponse: return self._wrapped.chat(**kwargs)


class GoogleLLM(BaseLLM):
    """Google Gemini 客户端"""
    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None):
        from shared.adapters.google_adapter import GoogleAdapter
        from shared.ir_models import ProviderConfig, ProviderType

        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("未设置 GOOGLE_API_KEY 环境变量")
        config = ProviderConfig(provider=ProviderType.GOOGLE, model=model, api_key=api_key)
        self._wrapped = _SharedAdapterWrapper(GoogleAdapter(config), "google", model)

    @property
    def provider_name(self) -> str: return "google"
    @property
    def is_mock(self) -> bool: return False
    def chat(self, **kwargs) -> LLMResponse: return self._wrapped.chat(**kwargs)


class OllamaLLM(BaseLLM):
    """Ollama 本地模型客户端"""
    def __init__(self, model: str = "llama3.2", base_url: str = ""):
        from shared.adapters.ollama_adapter import OllamaAdapter
        from shared.ir_models import ProviderConfig, ProviderType

        config = ProviderConfig(
            provider=ProviderType.OLLAMA,
            model=model,
            base_url=base_url or os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )
        adapter = OllamaAdapter(config)
        self._wrapped = _SharedAdapterWrapper(adapter, "ollama", model)
        self._adapter = adapter

    @property
    def provider_name(self) -> str: return "ollama"
    @property
    def is_mock(self) -> bool: return False
    def chat(self, **kwargs) -> LLMResponse: return self._wrapped.chat(**kwargs)
    def list_models(self) -> list: return self._adapter.list_local_models()


class DeepSeekLLM(BaseLLM):
    """DeepSeek 客户端"""
    def __init__(self, model: str = "deepseek-chat", api_key: str | None = None):
        from shared.adapters.deepseek_adapter import DeepSeekAdapter
        from shared.ir_models import ProviderConfig, ProviderType

        api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量")
        config = ProviderConfig(provider=ProviderType.DEEPSEEK, model=model, api_key=api_key)
        self._wrapped = _SharedAdapterWrapper(DeepSeekAdapter(config), "deepseek", model)

    @property
    def provider_name(self) -> str: return "deepseek"
    @property
    def is_mock(self) -> bool: return False
    def chat(self, **kwargs) -> LLMResponse: return self._wrapped.chat(**kwargs)


# ──────────────────────────────────────────────
# 工厂函数 v0.3
# ──────────────────────────────────────────────

def create_llm(
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    agent_tags: list[str] | None = None,
) -> BaseLLM:
    """
    统一 LLM 工厂（v0.3 多 Provider）。

    支持: openai | anthropic | google | ollama | deepseek | mock

    API Key 环境变量：
    - OPENAI_API_KEY
    - ANTHROPIC_API_KEY
    - GOOGLE_API_KEY
    - DEEPSEEK_API_KEY
    - OLLAMA_HOST (默认 http://localhost:11434)
    """

    provider_lower = provider.lower().strip()

    if provider_lower == "anthropic":
        return AnthropicLLM(model=model, api_key=api_key)
    elif provider_lower == "google":
        return GoogleLLM(model=model, api_key=api_key)
    elif provider_lower == "ollama":
        return OllamaLLM(model=model, base_url=base_url or "")
    elif provider_lower == "deepseek":
        return DeepSeekLLM(model=model, api_key=api_key)

    # OpenAI 及降级
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[!] 未检测到 OPENAI_API_KEY，将使用 Mock 模式运行。")
        print("    设置方法: set OPENAI_API_KEY=sk-xxx  (Windows PowerShell)")
        print()
        return MockLLM(model=model, agent_tags=agent_tags)

    if provider_lower in ("openai", ""):
        return OpenAILLM(model=model, api_key=api_key, base_url=base_url)
    else:
        print(f"[!] Provider '{provider}' 暂未原生支持，使用 OpenAI 兼容模式。")
        return OpenAILLM(model=model, api_key=api_key, base_url=base_url)
