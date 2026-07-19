"""
AI Agent Hub — Adapter 注册表 v0.5.1

统一的 Provider→Adapter 映射，避免 main.py 和 agent_dispatcher.py 中的重复定义。
"""
from __future__ import annotations

from .ir_models import ProviderType


# Provider → (AdapterClass, default_model) 映射
def get_adapter_map():
    """延迟导入避免循环依赖"""
    from .adapters.openai_adapter import OpenAIAdapter
    from .adapters.deepseek_adapter import DeepSeekAdapter
    from .adapters.anthropic_adapter import AnthropicAdapter
    from .adapters.google_adapter import GoogleAdapter
    from .adapters.ollama_adapter import OllamaAdapter

    return {
        ProviderType.OPENAI:    OpenAIAdapter,
        ProviderType.DEEPSEEK:  DeepSeekAdapter,
        ProviderType.ANTHROPIC: AnthropicAdapter,
        ProviderType.GOOGLE:    GoogleAdapter,
        ProviderType.OLLAMA:    OllamaAdapter,
    }


# Provider → 默认模型
DEFAULT_MODELS: dict[str, str] = {
    "openai":    "gpt-4o-mini",
    "deepseek":  "deepseek-chat",
    "anthropic": "claude-3-5-sonnet-20241022",
    "google":    "gemini-2.0-flash",
    "ollama":    "llama3.2",
}


# Provider → 环境变量名
PROVIDER_ENV_KEYS: dict[str, str] = {
    "openai":    "OPENAI_API_KEY",
    "deepseek":  "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google":    "GOOGLE_API_KEY",
}
