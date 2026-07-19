"""
AI Agent Hub — LLM 工厂 v0.3

统一的多 Provider LLM 创建入口。
根据 ProviderConfig 自动选择对应适配器。
内置适配能力表，供前端展示 Provider 对比。
"""

from __future__ import annotations

import logging
from typing import Type

from .adapters.base_adapter import BaseAdapter
from .adapters.openai_adapter import OpenAIAdapter
from .adapters.anthropic_adapter import AnthropicAdapter
from .adapters.google_adapter import GoogleAdapter
from .adapters.ollama_adapter import OllamaAdapter
from .adapters.deepseek_adapter import DeepSeekAdapter
from .ir_models import AdapterCapability, ProviderConfig, ProviderType

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 适配器注册表
# ══════════════════════════════════════════════

_ADAPTER_MAP: dict[ProviderType, Type[BaseAdapter]] = {
    ProviderType.OPENAI: OpenAIAdapter,
    ProviderType.ANTHROPIC: AnthropicAdapter,
    ProviderType.GOOGLE: GoogleAdapter,
    ProviderType.OLLAMA: OllamaAdapter,
    ProviderType.DEEPSEEK: DeepSeekAdapter,
}

# ══════════════════════════════════════════════
# 适配能力表（供前端/Buildder 展示）
# ══════════════════════════════════════════════

_PROVIDER_CAPABILITIES: dict[ProviderType, AdapterCapability] = {
    ProviderType.OPENAI: AdapterCapability(
        provider=ProviderType.OPENAI,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
        max_context_tokens=128_000,
        system_prompt_field="messages",
        tool_result_role="tool",
        models=[
            "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
            "gpt-3.5-turbo", "o1-mini", "o1-preview",
        ],
        notes="最广泛兼容的 Provider，Function Calling 完善，支持视觉。API Key 需海外支付。",
    ),
    ProviderType.ANTHROPIC: AdapterCapability(
        provider=ProviderType.ANTHROPIC,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
        max_context_tokens=200_000,
        system_prompt_field="system",
        tool_result_role="user",
        models=[
            "claude-3-5-sonnet-20241022", "claude-3-opus-20240229",
            "claude-3-sonnet-20240229", "claude-3-haiku-20240307",
        ],
        notes="200K 最大上下文，Tool Use 设计优雅但格式与 OpenAI 不同。system 是独立顶层字段。",
    ),
    ProviderType.GOOGLE: AdapterCapability(
        provider=ProviderType.GOOGLE,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=True,
        max_context_tokens=1_000_000,
        system_prompt_field="system_instruction",
        tool_result_role="tool",
        models=[
            "gemini-2.0-flash", "gemini-1.5-pro",
            "gemini-1.5-flash", "gemini-1.0-pro",
        ],
        notes="1M 最大上下文（业界最高），免费额度慷慨。role 用 'model' 而非 'assistant'。",
    ),
    ProviderType.OLLAMA: AdapterCapability(
        provider=ProviderType.OLLAMA,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=False,
        max_context_tokens=128_000,
        system_prompt_field="messages",
        tool_result_role="tool",
        models=[
            "llama3.2", "llama3.2:3b", "mistral", "mixtral:8x7b",
            "gemma2", "qwen2.5", "deepseek-r1",
        ],
        notes="本地运行，无需 API Key。工具调用依赖模型支持（需工具专用模型）。性能取决于本地硬件。",
    ),
    ProviderType.DEEPSEEK: AdapterCapability(
        provider=ProviderType.DEEPSEEK,
        supports_streaming=True,
        supports_tools=True,
        supports_vision=False,
        max_context_tokens=128_000,
        system_prompt_field="messages",
        tool_result_role="tool",
        models=[
            "deepseek-chat", "deepseek-reasoner",
        ],
        notes="国产性价比之王，API 完全兼容 OpenAI 格式。R1 模型有 reasoning_content 思维链。国内支付方便。",
    ),
}


# ══════════════════════════════════════════════
# LLM 工厂
# ══════════════════════════════════════════════

class LLMFactory:
    """
    统一 LLM 工厂。

    使用方式：
        factory = LLMFactory()
        adapter = factory.create(ProviderConfig(
            provider=ProviderType.OPENAI,
            model="gpt-4o-mini",
        ))
        response = adapter.chat(messages, tools)
    """

    def __init__(self):
        self._adapters: dict[ProviderType, BaseAdapter] = {}

    def create(self, config: ProviderConfig) -> BaseAdapter:
        """
        创建或获取缓存的适配器实例。

        Args:
            config: Provider 连接配置

        Returns:
            对应的适配器实例

        Raises:
            ValueError: 不支持的 Provider
        """
        adapter_cls = _ADAPTER_MAP.get(config.provider)
        if adapter_cls is None:
            raise ValueError(
                f"不支持的 Provider: {config.provider.value}。"
                f"支持的 Provider: {[p.value for p in _ADAPTER_MAP]}"
            )

        # 缓存键：provider + model + api_key hash
        cache_key = (
            config.provider,
            config.model,
            hash(config.api_key),
        )

        if cache_key not in self._adapters:
            self._adapters[cache_key] = adapter_cls(config)
            logger.info(f"Created adapter: {config.provider.value}/{config.model}")

        return self._adapters[cache_key]

    def get_or_create(
        self,
        provider: ProviderType,
        model: str = "",
        api_key: str = "",
        base_url: str = "",
    ) -> BaseAdapter:
        """便捷方法：按参数创建适配器"""
        config = ProviderConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        return self.create(config)

    def clear(self):
        """清除所有缓存的适配器"""
        self._adapters.clear()

    @property
    def cached_count(self) -> int:
        return len(self._adapters)


# ══════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════

# 全局单例工厂
_global_factory = LLMFactory()


def create_llm(config: ProviderConfig) -> BaseAdapter:
    """全局工厂：创建 LLM 适配器"""
    return _global_factory.create(config)


def list_providers() -> list[dict]:
    """
    列出所有支持的 Provider 及其能力。

    Returns:
        [
            {"provider": "openai", "supports_streaming": true, "models": [...], ...},
            ...
        ]
    """
    result = []
    for provider, cap in _PROVIDER_CAPABILITIES.items():
        result.append({
            "provider": cap.provider.value,
            "supports_streaming": cap.supports_streaming,
            "supports_tools": cap.supports_tools,
            "supports_vision": cap.supports_vision,
            "max_context_tokens": cap.max_context_tokens,
            "models": cap.models,
            "notes": cap.notes,
        })
    return result


def get_provider_capabilities(provider: ProviderType | str) -> AdapterCapability | None:
    """
    获取指定 Provider 的能力详情。

    Args:
        provider: Provider 类型或字符串

    Returns:
        AdapterCapability 或 None（不支持的 Provider）
    """
    if isinstance(provider, str):
        try:
            provider = ProviderType(provider)
        except ValueError:
            return None
    return _PROVIDER_CAPABILITIES.get(provider)


def get_model_list(provider: ProviderType | str) -> list[str]:
    """获取指定 Provider 的推荐模型列表"""
    cap = get_provider_capabilities(provider)
    return cap.models if cap else []


def guess_model_for_provider(provider: ProviderType) -> str:
    """
    为 Provider 返回推荐默认模型。

    Args:
        provider: Provider 类型

    Returns:
        推荐的模型名称
    """
    defaults = {
        ProviderType.OPENAI: "gpt-4o-mini",
        ProviderType.ANTHROPIC: "claude-3-5-sonnet-20241022",
        ProviderType.GOOGLE: "gemini-2.0-flash",
        ProviderType.OLLAMA: "llama3.2",
        ProviderType.DEEPSEEK: "deepseek-chat",
    }
    return defaults.get(provider, "unknown")
