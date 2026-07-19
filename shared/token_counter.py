"""
AI Agent Hub — Token 计数器 v0.4

支持 tiktoken 精准计数（OpenAI 模型），未安装时降级为字符估算。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── 延迟加载 ──
_tiktoken_available = False
_encoders: dict[str, object] = {}


def _ensure_tiktoken():
    global _tiktoken_available
    if not _tiktoken_available:
        try:
            import tiktoken
            _tiktoken_available = True
        except ImportError:
            _tiktoken_available = False
            logger.info("tiktoken 未安装，使用字符估算。建议: pip install tiktoken")


def _get_encoder(model: str) -> object | None:
    """获取 tiktoken encoder（带缓存）"""
    _ensure_tiktoken()
    if not _tiktoken_available:
        return None
    if model not in _encoders:
        try:
            import tiktoken
            # 尝试专用编码器，降级到 cl100k_base
            try:
                _encoders[model] = tiktoken.encoding_for_model(model)
            except KeyError:
                _encoders[model] = tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None
    return _encoders.get(model)


# ── 模型 Token 上限映射 ──
_MODEL_TOKEN_LIMITS: dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_384,
    "o1-mini": 128_000,
    "o1-preview": 128_000,
    # Anthropic
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    # Google
    "gemini-2.0-flash": 1_000_000,
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    # DeepSeek
    "deepseek-chat": 128_000,
    "deepseek-reasoner": 128_000,
    # Ollama 默认
    "llama3.2": 128_000,
    "llama3.2:3b": 128_000,
    "mistral": 32_000,
    "qwen2.5": 128_000,
}

# 默认限制
_DEFAULT_TOKEN_LIMIT = 128_000

# 预留比例（给输出留空间）
_OUTPUT_RESERVE_RATIO = 0.3


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """
    精确计数文本的 token 数。

    Args:
        text: 要计数的文本
        model: 模型名（用于选择 encoder）

    Returns:
        token 数量
    """
    if not text:
        return 0

    encoder = _get_encoder(model)
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass

    # 降级：字符级估算
    # 中文 ~1.5 字符/token, 英文 ~4 字符/token
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4.0)


def count_messages_tokens(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = "gpt-4o-mini",
) -> int:
    """
    估算消息列表的总 token 数（含 role 开销）。

    Args:
        messages: [{"role": "system/user/assistant", "content": "..."}, ...]
        tools: 工具定义列表
        model: 模型名

    Returns:
        总 token 估算
    """
    total = 0
    # 每条消息约 4 token 的 role 开销
    overhead_per_message = 4

    for msg in messages:
        total += overhead_per_message
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)

    if tools:
        for tool in tools:
            # 工具定义通常 50-200 token
            total += count_tokens(str(tool), model)

    return total


def get_model_limit(model: str) -> int:
    """获取模型的最大 token 限制"""
    return _MODEL_TOKEN_LIMITS.get(model, _DEFAULT_TOKEN_LIMIT)


def get_input_limit(model: str) -> int:
    """
    获取输入 token 预算 = 模型限制 * (1 - 输出预留比例)

    例如 gpt-4o-mini: 128000 * 0.7 = 89600 tokens 给输入
    """
    return int(get_model_limit(model) * (1 - _OUTPUT_RESERVE_RATIO))


def trim_context(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    max_input_tokens: int | None = None,
    keep_last_n: int = 20,
) -> tuple[list[dict], list[dict]]:
    """
    智能上下文裁剪（v0.5 三原则）。

    规则：
    1. **System Prompt 钉子**：System prompt 永远完整发送，绝不裁剪、截断、摘要
    2. **动态阈值 80%**：Token < 预算*0.8 时不做任何裁剪；≥0.8 时才启动窗口裁剪
    3. **非破坏性卸载**：被裁剪的消息返回给调用方，由调用方存入 ConversationMemory

    Args:
        messages: 消息列表
        model: 模型名
        max_input_tokens: 最大输入 token（None=自动计算）
        keep_last_n: 至少保留最近 N 条消息

    Returns:
        (trimmed_messages, removed_messages):
          - trimmed_messages: 裁剪后发送的消息列表（保证 system prompt 完整）
          - removed_messages: 被裁剪的消息列表（调用方应 archive）
    """
    if not messages:
        return messages, []

    budget = max_input_tokens or get_input_limit(model)
    warn_threshold = int(budget * 0.8)  # 80% 预警线

    # ── 分离 system prompt（钉子保护） ──
    system_msgs = [m for m in messages if m.get("role") == "system"]
    dialogue = [m for m in messages if m.get("role") != "system"]

    # ── 计算当前 token ──
    current = count_messages_tokens(system_msgs + dialogue, model=model)

    # ── 动态阈值：低于 80% 预警线 → 不裁剪 ──
    if current <= warn_threshold:
        logger.info(
            f"Context {current}/{budget} tokens ({current*100//budget}%) "
            f"— below 80% threshold ({warn_threshold}), no trimming needed"
        )
        return system_msgs + dialogue, []

    # ── 超过 80% 预警线 → 窗口裁剪 ──
    logger.warning(
        f"Context {current}/{budget} tokens ({current*100//budget}%) "
        f"— exceeds 80% threshold, trimming to window of {keep_last_n}"
    )

    # 保留最近 N 条对话
    if len(dialogue) > keep_last_n:
        kept = dialogue[-keep_last_n:]
        removed = dialogue[:-keep_last_n]
    else:
        kept = dialogue
        removed = []

    # 二次检查：裁剪后还超预算则继续削减窗口
    all_kept = system_msgs + kept
    keep_total = count_messages_tokens(all_kept, model=model)

    safety_count = 0
    while keep_total > warn_threshold and len(kept) > 2 and safety_count < 10:
        removed.insert(0, kept.pop(0))
        keep_total = count_messages_tokens(system_msgs + kept, model=model)
        safety_count += 1

    # 最终安全检查：如果仅 system prompt 就超过 warn_threshold
    # → 也不裁剪 system prompt（钉子原则）
    sp_tokens = count_messages_tokens(system_msgs, model=model)
    if sp_tokens > budget:
        logger.error(
            f"System prompt ALONE ({sp_tokens} tokens) exceeds budget ({budget}). "
            f"Will send anyway (Pinning rule). Consider shortening system prompt."
        )

    final_total = count_messages_tokens(system_msgs + kept, model=model)
    logger.info(
        f"Context trimmed: kept {len(kept)} dialogue + {len(system_msgs)} system, "
        f"{final_total} tokens, offloaded {len(removed)} messages"
    )

    return system_msgs + kept, removed


def estimate_cost(
    prompt_tokens: int,
    completion_tokens: int = 0,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    估算 API 调用成本（美元）。

    返回 {"prompt_cost": 0.001, "completion_cost": 0.002, "total": 0.003}
    """
    # 价格 / 1M tokens (USD)
    pricing = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o1-mini": (1.10, 4.40),
        "o1-preview": (15.00, 60.00),
        "deepseek-chat": (0.14, 0.28),
        "deepseek-reasoner": (0.55, 2.19),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
    }

    prompt_price, completion_price = pricing.get(model, (0.50, 1.50))

    prompt_cost = prompt_tokens / 1_000_000 * prompt_price
    comp_cost = completion_tokens / 1_000_000 * completion_price

    return {
        "prompt_cost": round(prompt_cost, 6),
        "completion_cost": round(comp_cost, 6),
        "total": round(prompt_cost + comp_cost, 6),
        "model": model,
    }


__all__ = [
    "count_tokens", "count_messages_tokens",
    "get_model_limit", "get_input_limit",
    "trim_context", "estimate_cost",
    "WARN_THRESHOLD_RATIO",
]

# 导出 80% 预警比例
WARN_THRESHOLD_RATIO = 0.8
