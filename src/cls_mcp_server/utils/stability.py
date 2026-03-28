"""稳定性增强模块：重试 + 熔断器

自主实现，零第三方依赖。
- RetryHandler: 指数退避重试，仅对可恢复错误重试
- CircuitBreaker: 按 region 独立的三状态熔断器
- CircuitBreakerManager: 全局熔断器管理器
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

logger = logging.getLogger(__name__)


# ============================================================
# 重试处理器
# ============================================================

# 可重试的腾讯云 SDK 错误码前缀
_RETRYABLE_CODE_PREFIXES = (
    "RequestLimitExceeded",
    "InternalError",
    "LimitExceeded",
)

# 可重试的 Python 异常类型
_RETRYABLE_EXCEPTION_TYPES = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def is_retryable(exc: Exception) -> bool:
    """判断异常是否可重试

    可重试错误：
    - 腾讯云 SDK：RequestLimitExceeded*、InternalError*、LimitExceeded*
    - Python 原生：ConnectionError、TimeoutError、OSError
    """
    if isinstance(exc, TencentCloudSDKException):
        code = exc.code or ""
        return any(code.startswith(prefix) for prefix in _RETRYABLE_CODE_PREFIXES)
    return isinstance(exc, _RETRYABLE_EXCEPTION_TYPES)


class RetryHandler:
    """指数退避重试处理器

    Args:
        max_attempts: 最大尝试次数（含首次调用），最小为 1
        base_delay: 基础退避延迟（秒）
        max_delay: 单次最大退避延迟（秒）
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.max_attempts = max(1, max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay

    def _calc_delay(self, attempt: int) -> float:
        """计算第 N 次重试的退避时间：base_delay * 2^(attempt-1)"""
        delay = self.base_delay * (2 ** (attempt - 1))
        return min(delay, self.max_delay)

    async def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """带指数退避的重试执行

        Args:
            func: 要执行的异步或同步函数
            *args, **kwargs: 传给 func 的参数

        Returns:
            func 的返回值

        Raises:
            最后一次尝试的异常
        """
        last_exc: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exc = e

                if attempt >= self.max_attempts:
                    break

                if not is_retryable(e):
                    raise

                delay = self._calc_delay(attempt)
                logger.warning(
                    "Retry %d/%d after %.1fs: %s (error: %s)",
                    attempt,
                    self.max_attempts,
                    delay,
                    type(e).__name__,
                    str(e)[:200],
                )
                await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]


# ============================================================
# 熔断器
# ============================================================

class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"        # 正常，请求正常通过
    OPEN = "open"            # 熔断，请求直接拒绝
    HALF_OPEN = "half_open"  # 半开，放行一个请求试探


class CircuitOpenError(Exception):
    """熔断器已开启，请求被拒绝"""

    def __init__(self, region: str, recovery_seconds: int):
        self.region = region
        self.recovery_seconds = recovery_seconds
        super().__init__(
            f"CLS API ({region}) 当前不可用，熔断器已开启，"
            f"将在 {recovery_seconds}s 后自动尝试恢复"
        )


class CircuitBreaker:
    """单个 region 的三状态熔断器

    状态转换：
      CLOSED  --连续失败 >= threshold--> OPEN
      OPEN    --等待 recovery_timeout--> HALF_OPEN
      HALF_OPEN --成功--> CLOSED
      HALF_OPEN --失败--> OPEN

    Args:
        region: 地域标识
        failure_threshold: 连续失败多少次后触发熔断
        recovery_timeout: 熔断后多少秒进入半开状态
    """

    def __init__(
        self,
        region: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        self.region = region
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def pre_check(self) -> None:
        """请求前检查熔断器状态，如果 OPEN 且超时则切换到 HALF_OPEN"""
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning(
                        "Circuit breaker [%s]: OPEN -> HALF_OPEN (recovery timeout %.0fs elapsed)",
                        self.region,
                        elapsed,
                    )
                else:
                    remaining = int(self.recovery_timeout - elapsed)
                    raise CircuitOpenError(self.region, remaining)

    async def record_success(self) -> None:
        """记录一次成功调用"""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker [%s]: HALF_OPEN -> CLOSED (probe succeeded)",
                    self.region,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    async def record_failure(self) -> None:
        """记录一次失败调用"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker [%s]: HALF_OPEN -> OPEN (probe failed)",
                    self.region,
                )
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker [%s]: CLOSED -> OPEN (failures=%d, threshold=%d)",
                    self.region,
                    self._failure_count,
                    self.failure_threshold,
                )


class CircuitBreakerManager:
    """全局熔断器管理器，按 region 维护独立的熔断器实例"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_breaker(self, region: str) -> CircuitBreaker:
        """获取指定 region 的熔断器，不存在则创建"""
        if region in self._breakers:
            return self._breakers[region]

        async with self._lock:
            # double check
            if region not in self._breakers:
                self._breakers[region] = CircuitBreaker(
                    region=region,
                    failure_threshold=self._failure_threshold,
                    recovery_timeout=self._recovery_timeout,
                )
            return self._breakers[region]

    def reset_all(self) -> None:
        """重置所有熔断器（测试用）"""
        self._breakers.clear()


# 全局单例，在 server 启动时通过 init_stability() 初始化
_retry_handler: RetryHandler | None = None
_breaker_manager: CircuitBreakerManager | None = None


def init_stability(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    failure_threshold: int = 5,
    recovery_timeout: int = 30,
) -> None:
    """初始化全局稳定性组件，由 server.py 在启动时调用"""
    global _retry_handler, _breaker_manager
    _retry_handler = RetryHandler(
        max_attempts=max_attempts,
        base_delay=base_delay,
    )
    _breaker_manager = CircuitBreakerManager(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )
    logger.info(
        "Stability initialized: retry(max=%d, delay=%.1fs), "
        "breaker(threshold=%d, recovery=%ds)",
        max_attempts,
        base_delay,
        failure_threshold,
        recovery_timeout,
    )


def get_retry_handler() -> RetryHandler | None:
    """获取全局重试处理器"""
    return _retry_handler


def get_breaker_manager() -> CircuitBreakerManager | None:
    """获取全局熔断器管理器"""
    return _breaker_manager
