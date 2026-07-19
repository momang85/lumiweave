"""
AI Agent Hub — 全局 LLM 速率限制器

防止并发请求触发 API 429 限流。
使用滑动窗口 + 信号量控制并发数。
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """滑动窗口速率限制器 + 并发信号量"""

    def __init__(
        self,
        max_requests_per_minute: int = 30,   # RPM 限制
        max_concurrent: int = 3,              # 最大并发数
        min_interval: float = 0.5,            # 两次调用最小间隔（秒）
    ):
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_concurrent)
        self._window: list[float] = []
        self._max_rpm = max_requests_per_minute
        self._min_interval = min_interval
        self._last_call: float = 0.0
        self._backoff_until: float = 0.0      # 全局退避截止时间
        self._consecutive_429: int = 0

    def acquire(self, timeout: float = 120.0) -> bool:
        """
        获取调用许可。阻塞直到：
        1. RPM 窗口有空位
        2. 并发数不超限
        3. 最小间隔满足
        4. 不在全局退避期
        """
        deadline = time.time() + timeout

        # 并发控制
        if not self._semaphore.acquire(timeout=timeout):
            return False

        with self._lock:
            now = time.time()

            # 全局退避
            if now < self._backoff_until:
                wait = self._backoff_until - now
                if wait > timeout:
                    self._semaphore.release()
                    return False
                time.sleep(min(wait, 1.0))  # 分段等待
                now = time.time()

            # RPM 窗口清理
            cutoff = now - 60.0
            self._window = [t for t in self._window if t > cutoff]

            # RPM 限制
            while len(self._window) >= self._max_rpm:
                oldest = self._window[0]
                wait = oldest - cutoff
                if wait > 0:
                    if time.time() + wait > deadline:
                        self._semaphore.release()
                        return False
                    self._lock.release()
                    time.sleep(wait)
                    self._lock.acquire()
                    now = time.time()
                    cutoff = now - 60.0
                    self._window = [t for t in self._window if t > cutoff]
                else:
                    self._window.pop(0)

            # 最小间隔
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                if time.time() + wait > deadline:
                    self._semaphore.release()
                    return False
                self._lock.release()
                time.sleep(wait)
                self._lock.acquire()

            self._window.append(time.time())
            self._last_call = time.time()

        return True

    def release(self):
        """释放并发信号量"""
        self._semaphore.release()

    def report_429(self):
        """收到 429 后触发全局退避"""
        with self._lock:
            self._consecutive_429 += 1
            # 指数退避：2^count 秒，最大 60 秒
            backoff = min(2 ** self._consecutive_429, 60)
            self._backoff_until = time.time() + backoff
            # 清空窗口避免继续堆积
            self._window.clear()

    def report_success(self):
        """成功调用后重置连续 429 计数"""
        with self._lock:
            if self._consecutive_429 > 0:
                self._consecutive_429 = max(0, self._consecutive_429 - 1)


# 全局单例
_global_limiter: RateLimiter | None = None
_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _global_limiter
    if _global_limiter is None:
        with _lock:
            if _global_limiter is None:
                try:
                    from runtime_config import get as _rc_get
                    rpm = _rc_get("llm_rate_limit_rpm", 30)
                    concurrent = _rc_get("llm_rate_limit_concurrent", 3)
                    interval = _rc_get("llm_rate_limit_interval", 0.5)
                except ImportError:
                    rpm, concurrent, interval = 30, 3, 0.5
                _global_limiter = RateLimiter(
                    max_requests_per_minute=rpm,
                    max_concurrent=concurrent,
                    min_interval=interval,
                )
    return _global_limiter
