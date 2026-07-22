"""
AI Agent Hub — LLM Provider 适配器基类 v0.3

定义统一的适配器接口，每个 Provider 实现各自的格式转换逻辑。

职责边界：
- 适配器只负责「格式转换」和「API 调用」，不做业务逻辑
- 统一输入：MessageIR / ToolDefIR → Provider 原生格式
- 统一输出：Provider 原生响应 → LLMResponseIR
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator

from ..ir_models import (
    LLMResponseIR,
    MessageIR,
    ProviderConfig,
    ProviderType,
    ToolCallIR,
    ToolDefIR,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 适配器基类
# ══════════════════════════════════════════════

class BaseAdapter(ABC):
    """
    LLM Provider 适配器基类。

    子类需实现：
    - _build_messages() — MessageIR → Provider 格式
    - _build_tools()     — ToolDefIR → Provider 格式
    - _parse_response()  — Provider 响应 → LLMResponseIR
    - _chat_impl()       — 实际 API 调用
    - _stream_impl()     — 流式 API 调用（可选）
    """

    def __init__(self, config: ProviderConfig):
        if not isinstance(config, ProviderConfig):
            raise TypeError(f"Expected ProviderConfig, got {type(config)}")
        self.config = config
        self._call_count = 0
        self._total_tokens = 0

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        ...

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    # ── 公共接口 ──

    def chat(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponseIR:
        """
        同步对话接口（v2.0 — 接入全局限流器）。

        Args:
            messages: 统一消息列表
            tools: 工具定义列表
            temperature: 温度
            max_tokens: 最大 token 数

        Returns:
            统一 LLM 响应
        """
        self._call_count += 1

        # ── 全局限流 ──
        try:
            from shared.rate_limiter import get_rate_limiter
            limiter = get_rate_limiter()
            if not limiter.acquire(timeout=120):
                logger.warning(f"[{self.provider_type.value}] 限流器获取许可超时，跳过限流直接调用")
        except ImportError:
            pass

        try:
            response = self._chat_impl(messages, tools, temperature, max_tokens)
            if response.usage:
                self._total_tokens += response.total_tokens
            return response
        except Exception as e:
            err = str(e).lower()
            hint = ""
            if any(k in err for k in ('connection', 'timeout', 'timed out', 'refused', 'reset', 'name or service')):
                hint = ("\n💡 连接失败，可能原因：\n"
                       "1. 需要代理：在 Settings → 运行参数 设置 llm_proxy（如 http://127.0.0.1:7897）\n"
                       "2. 网络不通：检查防火墙/VPN\n"
                       "3. 使用本地模型：安装 Ollama 后运行 'ollama pull qwen2.5:3b'")
            logger.error(f"[{self.provider_type.value}] chat error: {e}{hint}")
            raise
        finally:
            try:
                from shared.rate_limiter import get_rate_limiter
                get_rate_limiter().release()
            except ImportError:
                pass

    def stream_chat(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """
        流式对话接口（生成器）。

        Yields:
            str: 增量文本片段（delta.content）
        """
        self._call_count += 1

        try:
            yield from self._stream_impl(messages, tools, temperature, max_tokens)
        except Exception as e:
            logger.error(f"[{self.provider_type.value}] stream error: {e}")
            yield f"\n[错误: {e}]"

    # ── 子类需实现 ──

    @abstractmethod
    def _chat_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponseIR:
        ...

    def _stream_impl(
        self,
        messages: list[MessageIR],
        tools: list[ToolDefIR] | None,
        temperature: float,
        max_tokens: int,
    ):
        """默认流式实现：回退到同步 chat 并一次性 yield"""
        response = self._chat_impl(messages, tools, temperature, max_tokens)
        yield response.content or ""

    # ── 工具方法 ──

    @staticmethod
    def _parse_tool_arguments(raw_args: str | dict) -> dict:
        """安全解析工具参数"""
        if isinstance(raw_args, dict):
            return raw_args
        try:
            return json.loads(raw_args) if isinstance(raw_args, str) else {}
        except json.JSONDecodeError:
            return {"_raw": str(raw_args)}


# ══════════════════════════════════════════════
# 重试装饰器
# ══════════════════════════════════════════════

def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
):
    """
    指数退避重试装饰器（v2.0 — 支持 Retry-After + 抖动 + 限流器通知）。

    - 429 Rate Limit → 读取 Retry-After 头，通知全局限流器，指数退避
    - 5xx Server Error → 最多重试 max_retries 次
    - 401 Auth Error → 不重试，立即抛出
    - 超时 → 重试
    """
    import random

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    # 不可重试的错误
                    if any(kw in error_str for kw in ("401", "403", "auth", "api key", "unauthorized")):
                        raise

                    # 最后一次尝试
                    if attempt >= max_retries:
                        raise

                    # ── 429 特殊处理 ──
                    is_429 = "429" in error_str or "rate limit" in error_str or "too many requests" in error_str
                    if is_429:
                        # 通知全局限流器
                        try:
                            from shared.rate_limiter import get_rate_limiter
                            get_rate_limiter().report_429()
                        except ImportError:
                            pass
                        # 尝试从异常中提取 Retry-After（httpx/openai 可能包含）
                        retry_after = None
                        try:
                            if hasattr(e, 'response') and e.response is not None:
                                retry_after = e.response.headers.get('Retry-After')
                                if retry_after:
                                    retry_after = float(retry_after)
                        except Exception:
                            pass
                        if retry_after:
                            delay = retry_after
                        else:
                            # 更激进退避：5s起步
                            delay = max(5.0, base_delay * (backoff_factor ** (attempt + 1)))
                    else:
                        delay = base_delay * (backoff_factor ** attempt)

                    # 添加随机抖动（±30%）避免惊群
                    jitter = delay * 0.3 * (random.random() * 2 - 1)
                    delay = max(0.1, delay + jitter)

                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {str(e)[:100]}"
                    )
                    time.sleep(delay)

                else:
                    # 成功 — 通知限流器
                    try:
                        from shared.rate_limiter import get_rate_limiter
                        get_rate_limiter().report_success()
                    except ImportError:
                        pass

            raise last_error  # type: ignore
        return wrapper
    return decorator
