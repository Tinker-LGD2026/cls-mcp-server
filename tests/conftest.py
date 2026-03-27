"""公共 pytest fixtures 和辅助函数

为日志检索工具测试提供统一的测试配置、Mock 对象和断言辅助函数。
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cls_mcp_server.config import ServerConfig
from cls_mcp_server.tools._state import set_config


# ============================================================
# 测试常量
# ============================================================

TEST_TOPIC_ID = "a47d3903-2e14-4637-aead-6bacbc97fb1b"

# 使用固定的毫秒时间戳（2026-03-25 08:00:00 ~ 09:00:00 CST）
TEST_START_TIME = 1774396800000
TEST_END_TIME = 1774400400000


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def setup_config():
    """自动注入测试用 ServerConfig"""
    config = ServerConfig(
        secret_id=os.getenv("CLS_SECRET_ID", "test_secret_id"),
        secret_key=os.getenv("CLS_SECRET_KEY", "test_secret_key"),
        region=os.getenv("CLS_REGION", "ap-guangzhou"),
    )
    set_config(config)
    return config


@pytest.fixture
def has_credentials():
    """检查是否配置了真实的 CLS 凭证"""
    return bool(os.getenv("CLS_SECRET_ID")) and bool(os.getenv("CLS_SECRET_KEY"))


# ============================================================
# 断言辅助函数
# ============================================================

def assert_validation_error(result: str, expected_params: list[str] | None = None):
    """断言返回结果为结构化的参数校验错误

    Args:
        result: 工具返回的字符串
        expected_params: 期望报错的参数名列表（可选）
    """
    data = json.loads(result)
    assert data["success"] is False, f"Expected success=False, got {data}"
    assert data["error_type"] == "VALIDATION_ERROR", f"Expected VALIDATION_ERROR, got {data['error_type']}"
    assert data["error_count"] > 0
    assert len(data["errors"]) > 0

    for err in data["errors"]:
        assert "param" in err, f"Missing 'param' in error: {err}"
        assert "value" in err, f"Missing 'value' in error: {err}"
        assert "reason" in err, f"Missing 'reason' in error: {err}"
        assert "expected" in err, f"Missing 'expected' in error: {err}"

    if expected_params:
        actual_params = [err["param"] for err in data["errors"]]
        for param in expected_params:
            assert any(param in p for p in actual_params), \
                f"Expected param '{param}' in errors, got {actual_params}"

    return data


def assert_api_error(result: str, expected_code: str | None = None):
    """断言返回结果为结构化的 API 错误"""
    data = json.loads(result)
    assert data["success"] is False
    assert data["error_type"] == "API_ERROR"
    assert "error_code" in data
    assert "message" in data
    if expected_code:
        assert data["error_code"] == expected_code
    return data


def assert_success_result(result: str):
    """断言返回结果为成功（非 JSON 错误格式）"""
    # 成功结果不是 JSON 错误格式
    try:
        data = json.loads(result)
        # 如果能解析为 JSON，检查不是错误
        if isinstance(data, dict) and "success" in data:
            assert data["success"] is not False, f"Expected success but got error: {data}"
    except json.JSONDecodeError:
        # 非 JSON 格式说明是正常的文本返回
        pass
    return result
