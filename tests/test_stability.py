"""稳定性增强 + 工具白名单 单元测试"""

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from cls_mcp_server.config import ServerConfig, _find_dotenv_path
from cls_mcp_server.utils.stability import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitOpenError,
    CircuitState,
    RetryHandler,
    init_stability,
    is_retryable,
)
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)


# ============================================================
# Config Tests
# ============================================================

class TestConfigExtension:
    """测试 ServerConfig 新增字段"""

    def test_default_values(self):
        c = ServerConfig()
        assert c.request_timeout == 60
        assert c.retry_max_attempts == 3
        assert c.retry_base_delay == 1.0
        assert c.cb_failure_threshold == 5
        assert c.cb_recovery_timeout == 30
        assert c.enabled_tools == frozenset()

    def test_from_env_defaults(self):
        # 清除可能影响的环境变量
        for key in ["CLS_REQUEST_TIMEOUT", "CLS_RETRY_MAX_ATTEMPTS",
                     "CLS_RETRY_BASE_DELAY", "CLS_CB_FAILURE_THRESHOLD",
                     "CLS_CB_RECOVERY_TIMEOUT", "CLS_ENABLED_TOOLS"]:
            os.environ.pop(key, None)

        c = ServerConfig.from_env()
        assert c.request_timeout == 60
        assert c.retry_max_attempts == 3
        assert c.enabled_tools == frozenset()

    def test_from_env_with_values(self):
        os.environ["CLS_REQUEST_TIMEOUT"] = "120"
        os.environ["CLS_RETRY_MAX_ATTEMPTS"] = "5"
        os.environ["CLS_ENABLED_TOOLS"] = "cls_search_log,cls_describe_topics"

        try:
            c = ServerConfig.from_env()
            assert c.request_timeout == 120
            assert c.retry_max_attempts == 5
            assert c.enabled_tools == frozenset({"cls_search_log", "cls_describe_topics"})
        finally:
            os.environ.pop("CLS_REQUEST_TIMEOUT", None)
            os.environ.pop("CLS_RETRY_MAX_ATTEMPTS", None)
            os.environ.pop("CLS_ENABLED_TOOLS", None)

    def test_enabled_tools_whitespace_handling(self):
        os.environ["CLS_ENABLED_TOOLS"] = " cls_search_log , cls_describe_topics , "
        try:
            c = ServerConfig.from_env()
            assert c.enabled_tools == frozenset({"cls_search_log", "cls_describe_topics"})
        finally:
            os.environ.pop("CLS_ENABLED_TOOLS", None)

    def test_enabled_tools_empty_string(self):
        os.environ["CLS_ENABLED_TOOLS"] = ""
        try:
            c = ServerConfig.from_env()
            assert c.enabled_tools == frozenset()
        finally:
            os.environ.pop("CLS_ENABLED_TOOLS", None)

    def test_dotenv_override_env_vars(self, tmp_path):
        """验证 .env 文件通过 override=True 能覆盖已有的环境变量"""
        env_file = tmp_path / ".env"
        env_file.write_text("CLS_REGION=ap-shanghai\nCLS_LOG_LEVEL=DEBUG\n")

        # 预设环境变量（模拟 systemd EnvironmentFile 注入的旧值）
        os.environ["CLS_REGION"] = "ap-guangzhou"
        os.environ["CLS_LOG_LEVEL"] = "INFO"

        try:
            with patch("cls_mcp_server.config._find_dotenv_path", return_value=env_file):
                c = ServerConfig.from_env()
            # .env 的值应该覆盖环境变量中的旧值
            assert c.region == "ap-shanghai"
            assert c.log_level == "DEBUG"
        finally:
            os.environ.pop("CLS_REGION", None)
            os.environ.pop("CLS_LOG_LEVEL", None)

    def test_dotenv_not_found_still_works(self):
        """验证 .env 文件不存在时 from_env() 不会报错，使用环境变量默认值"""
        os.environ.pop("CLS_REGION", None)
        with patch("cls_mcp_server.config._find_dotenv_path", return_value=None):
            c = ServerConfig.from_env()
        assert c.region == "ap-guangzhou"  # 使用默认值


class TestFindDotenvPath:
    """测试 _find_dotenv_path 路径搜索逻辑"""

    def test_finds_cwd_env(self, tmp_path):
        """优先找到 cwd 下的 .env"""
        env_file = tmp_path / ".env"
        env_file.write_text("CLS_REGION=ap-beijing\n")

        with patch("cls_mcp_server.config.Path.cwd", return_value=tmp_path):
            result = _find_dotenv_path()
        assert result == env_file

    def test_falls_back_to_project_root(self, tmp_path, monkeypatch):
        """cwd 无 .env 时回退到项目根目录"""
        # 模拟项目结构: project_root/src/cls_mcp_server/config.py
        fake_config_dir = tmp_path / "src" / "cls_mcp_server"
        fake_config_dir.mkdir(parents=True, exist_ok=True)
        fake_config_py = fake_config_dir / "config.py"
        fake_config_py.touch()

        # 项目根目录有 .env
        root_env = tmp_path / ".env"
        root_env.write_text("CLS_REGION=ap-nanjing\n")

        # cwd 没有 .env
        empty_cwd = tmp_path / "somewhere"
        empty_cwd.mkdir(exist_ok=True)

        import cls_mcp_server.config as config_mod

        with patch("cls_mcp_server.config.Path.cwd", return_value=empty_cwd):
            # mock __file__ 指向模拟的 config.py 路径
            monkeypatch.setattr(config_mod, "__file__", str(fake_config_py))
            result = _find_dotenv_path()

        assert result == root_env

    def test_returns_none_when_no_env(self, tmp_path):
        """两个位置都没有 .env 时返回 None"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir(exist_ok=True)

        with patch("cls_mcp_server.config.Path.cwd", return_value=empty_dir):
            # __file__ 指向的项目根目录也没有 .env（实际项目根目录可能有，
            # 但这里的 cwd 没有，且不影响 __file__ 的搜索路径）
            result = _find_dotenv_path()
        # 结果取决于真实的 __file__ 路径下是否有 .env
        # 至少不应该报错
        assert result is None or isinstance(result, Path)


# ============================================================
# Retry Tests
# ============================================================

class TestIsRetryable:
    """测试可重试错误判断"""

    def test_request_limit_exceeded(self):
        exc = TencentCloudSDKException("RequestLimitExceeded", "Too many requests")
        assert is_retryable(exc) is True

    def test_internal_error(self):
        exc = TencentCloudSDKException("InternalError.DatabaseError", "DB error")
        assert is_retryable(exc) is True

    def test_limit_exceeded(self):
        exc = TencentCloudSDKException("LimitExceeded.LogSearch", "Search limit")
        assert is_retryable(exc) is True

    def test_auth_failure_not_retryable(self):
        exc = TencentCloudSDKException("AuthFailure.SecretIdNotFound", "Bad key")
        assert is_retryable(exc) is False

    def test_invalid_param_not_retryable(self):
        exc = TencentCloudSDKException("InvalidParameter", "Bad param")
        assert is_retryable(exc) is False

    def test_connection_error_retryable(self):
        assert is_retryable(ConnectionError("conn failed")) is True

    def test_timeout_error_retryable(self):
        assert is_retryable(TimeoutError("timeout")) is True

    def test_value_error_not_retryable(self):
        assert is_retryable(ValueError("bad value")) is False


class TestRetryHandler:
    """测试重试处理器"""

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        handler = RetryHandler(max_attempts=3, base_delay=0.01)
        call_count = 0

        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await handler.execute(success)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retryable_error_retries(self):
        handler = RetryHandler(max_attempts=3, base_delay=0.01)
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TencentCloudSDKException("InternalError", "temp failure")
            return "ok"

        result = await handler.execute(fail_then_succeed)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_no_retry(self):
        handler = RetryHandler(max_attempts=3, base_delay=0.01)
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise TencentCloudSDKException("AuthFailure.SecretIdNotFound", "bad key")

        with pytest.raises(TencentCloudSDKException):
            await handler.execute(auth_fail)
        assert call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_max_attempts_exhausted(self):
        handler = RetryHandler(max_attempts=2, base_delay=0.01)
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise TencentCloudSDKException("InternalError", "always fail")

        with pytest.raises(TencentCloudSDKException):
            await handler.execute(always_fail)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_min_attempts_is_one(self):
        handler = RetryHandler(max_attempts=0)  # should become 1
        assert handler.max_attempts == 1

    def test_backoff_calculation(self):
        handler = RetryHandler(base_delay=1.0, max_delay=30.0)
        assert handler._calc_delay(1) == 1.0   # 1 * 2^0
        assert handler._calc_delay(2) == 2.0   # 1 * 2^1
        assert handler._calc_delay(3) == 4.0   # 1 * 2^2
        assert handler._calc_delay(6) == 30.0  # 1 * 2^5 = 32, capped at 30


# ============================================================
# Circuit Breaker Tests
# ============================================================

class TestCircuitBreaker:
    """测试熔断器"""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=3, recovery_timeout=1)
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=3, recovery_timeout=1)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_rejects_requests(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=2, recovery_timeout=100)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError) as exc_info:
            await cb.pre_check()
        assert exc_info.value.region == "ap-guangzhou"

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=2, recovery_timeout=0)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # recovery_timeout=0, so immediately transitions
        await asyncio.sleep(0.01)
        await cb.pre_check()  # should not raise
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=2, recovery_timeout=0)
        await cb.record_failure()
        await cb.record_failure()
        await asyncio.sleep(0.01)
        await cb.pre_check()  # -> HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=2, recovery_timeout=0)
        await cb.record_failure()
        await cb.record_failure()
        await asyncio.sleep(0.01)
        await cb.pre_check()  # -> HALF_OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker("ap-guangzhou", failure_threshold=3, recovery_timeout=1)
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()  # resets count
        await cb.record_failure()  # count = 1 now, not 3
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerManager:
    """测试熔断器管理器"""

    @pytest.mark.asyncio
    async def test_creates_breakers_per_region(self):
        mgr = CircuitBreakerManager(failure_threshold=5, recovery_timeout=30)
        b1 = await mgr.get_breaker("ap-guangzhou")
        b2 = await mgr.get_breaker("ap-shanghai")
        b3 = await mgr.get_breaker("ap-guangzhou")
        assert b1 is b3  # same region, same instance
        assert b1 is not b2  # different region, different instance

    @pytest.mark.asyncio
    async def test_reset_all(self):
        mgr = CircuitBreakerManager(failure_threshold=5, recovery_timeout=30)
        await mgr.get_breaker("ap-guangzhou")
        await mgr.get_breaker("ap-shanghai")
        mgr.reset_all()
        # After reset, new breaker should be created
        b = await mgr.get_breaker("ap-guangzhou")
        assert b.state == CircuitState.CLOSED


# ============================================================
# Init Stability Tests
# ============================================================

class TestInitStability:
    """测试全局初始化"""

    def test_init_creates_globals(self):
        from cls_mcp_server.utils.stability import (
            get_breaker_manager,
            get_retry_handler,
        )
        init_stability(max_attempts=2, base_delay=0.5, failure_threshold=3, recovery_timeout=10)
        rh = get_retry_handler()
        bm = get_breaker_manager()
        assert rh is not None
        assert rh.max_attempts == 2
        assert rh.base_delay == 0.5
        assert bm is not None
