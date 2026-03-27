"""日志检索 MCP 工具端到端测试

通过直接调用工具 handler 函数，测试 5 个检索工具的完整调用链路：
参数校验 → CLS API 调用 → 结果格式化 → 错误处理

测试分类：
1. Bad Case：非法参数拦截 + 错误返回格式验证
2. Good Case：正常调用 + 返回结果结构验证
3. 边界值：极值参数 + 模式兼容性
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cls_mcp_server.tools.search import (
    cls_describe_search_syntax,
    cls_get_log_context,
    cls_get_log_count,
    cls_get_log_histogram,
    cls_search_log,
)

from conftest import (
    TEST_END_TIME,
    TEST_START_TIME,
    TEST_TOPIC_ID,
    assert_success_result,
    assert_validation_error,
)


def _run(coro):
    """同步执行异步函数"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ============================================================
# 一、Bad Case 测试：参数校验拦截
# ============================================================

class TestSearchLogBadCase:
    """cls_search_log 异常参数测试"""

    def test_empty_topic_id(self):
        result = _run(cls_search_log(
            topic_id="", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["topic_id"])

    def test_empty_query(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["query"])

    def test_negative_limit(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=-1,
        ))
        assert_validation_error(result, ["limit"])

    def test_zero_limit(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=0,
        ))
        assert_validation_error(result, ["limit"])

    def test_limit_exceeds_max(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=1001,
        ))
        assert_validation_error(result, ["limit"])

    def test_invalid_sort(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            sort="random",
        ))
        assert_validation_error(result, ["sort"])

    def test_time_reversed(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
        ))
        assert_validation_error(result, ["start_time"])

    def test_multiple_errors(self):
        """多个参数同时错误"""
        result = _run(cls_search_log(
            topic_id="", query="",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
            limit=-1, sort="bad",
        ))
        data = assert_validation_error(result)
        assert data["error_count"] >= 3

    def test_whitespace_topic_id(self):
        result = _run(cls_search_log(
            topic_id="   ", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["topic_id"])


class TestGetLogContextBadCase:
    """cls_get_log_context 异常参数测试"""

    def test_empty_topic_id(self):
        result = _run(cls_get_log_context(
            topic_id="", btime="1774537847429",
            pkg_id="pkg1", pkg_log_id=1,
        ))
        assert_validation_error(result, ["topic_id"])

    def test_empty_btime(self):
        result = _run(cls_get_log_context(
            topic_id=TEST_TOPIC_ID, btime="",
            pkg_id="pkg1", pkg_log_id=1,
        ))
        assert_validation_error(result, ["btime"])

    def test_empty_pkg_id(self):
        result = _run(cls_get_log_context(
            topic_id=TEST_TOPIC_ID, btime="1774537847429",
            pkg_id="", pkg_log_id=1,
        ))
        assert_validation_error(result, ["pkg_id"])

    def test_negative_prev_logs(self):
        result = _run(cls_get_log_context(
            topic_id=TEST_TOPIC_ID, btime="1774537847429",
            pkg_id="pkg1", pkg_log_id=1, prev_logs=-5,
        ))
        assert_validation_error(result, ["prev_logs"])

    def test_negative_next_logs(self):
        result = _run(cls_get_log_context(
            topic_id=TEST_TOPIC_ID, btime="1774537847429",
            pkg_id="pkg1", pkg_log_id=1, next_logs=-1,
        ))
        assert_validation_error(result, ["next_logs"])

    def test_prev_logs_exceeds_max(self):
        result = _run(cls_get_log_context(
            topic_id=TEST_TOPIC_ID, btime="1774537847429",
            pkg_id="pkg1", pkg_log_id=1, prev_logs=101,
        ))
        assert_validation_error(result, ["prev_logs"])


class TestGetLogHistogramBadCase:
    """cls_get_log_histogram 异常参数测试"""

    def test_empty_topic_id(self):
        result = _run(cls_get_log_histogram(
            topic_id="", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["topic_id"])

    def test_empty_query(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["query"])

    def test_time_reversed(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
        ))
        assert_validation_error(result, ["start_time"])

    def test_negative_interval(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            interval=-1000,
        ))
        assert_validation_error(result, ["interval"])

    def test_zero_interval(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            interval=0,
        ))
        assert_validation_error(result, ["interval"])


class TestGetLogCountBadCase:
    """cls_get_log_count 异常参数测试"""

    def test_empty_topic_id(self):
        result = _run(cls_get_log_count(
            topic_id="", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["topic_id"])

    def test_empty_query(self):
        result = _run(cls_get_log_count(
            topic_id=TEST_TOPIC_ID, query="",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["query"])

    def test_time_reversed(self):
        result = _run(cls_get_log_count(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
        ))
        assert_validation_error(result, ["start_time"])


# ============================================================
# 二、Good Case 测试：正常调用（需要真实凭证）
# ============================================================

SKIP_NO_CREDS = pytest.mark.skipif(
    not (os.getenv("CLS_SECRET_ID") and os.getenv("CLS_SECRET_KEY")),
    reason="需要 CLS_SECRET_ID 和 CLS_SECRET_KEY 环境变量"
)


@SKIP_NO_CREDS
class TestSearchLogGoodCase:
    """cls_search_log 正常调用测试"""

    def test_simple_search(self):
        """基本检索：* 查询"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=5, sort="desc",
        ))
        assert_success_result(result)
        # 结果应包含日志内容或空结果提示
        assert "📊" in result or "📭" in result

    def test_search_with_condition(self):
        """条件检索（使用全文关键词，避免未索引字段报错）"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="error",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=5,
        ))
        assert_success_result(result)

    def test_sql_analysis(self):
        """SQL 分析模式"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS total",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)

    def test_sql_analysis_group_by(self):
        """SQL 分析 GROUP BY"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS cnt GROUP BY __SOURCE__ ORDER BY cnt DESC LIMIT 5",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)

    def test_search_with_limit_1(self):
        """limit=1 最小值"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=1,
        ))
        assert_success_result(result)

    def test_search_with_limit_1000(self):
        """limit=1000 最大值"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=1000,
        ))
        assert_success_result(result)

    def test_search_sort_asc(self):
        """升序排序"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=5, sort="asc",
        ))
        assert_success_result(result)

    def test_invalid_topic_id_api_error(self):
        """无效 topic_id 应返回 API 错误"""
        result = _run(cls_search_log(
            topic_id="00000000-0000-0000-0000-000000000000",
            query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=5,
        ))
        # 应返回 API_ERROR（非 VALIDATION_ERROR）
        data = json.loads(result)
        assert data["success"] is False
        assert data["error_type"] == "API_ERROR"


@SKIP_NO_CREDS
class TestGetLogHistogramGoodCase:
    """cls_get_log_histogram 正常调用测试"""

    def test_basic_histogram(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)
        assert "📊" in result or "📭" in result

    def test_histogram_with_condition(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="error",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)

    def test_histogram_with_interval(self):
        result = _run(cls_get_log_histogram(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            interval=600000,  # 10 分钟
        ))
        assert_success_result(result)


@SKIP_NO_CREDS
class TestGetLogCountGoodCase:
    """cls_get_log_count 正常调用测试"""

    def test_basic_count(self):
        result = _run(cls_get_log_count(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)
        assert "📊" in result

    def test_count_with_condition(self):
        result = _run(cls_get_log_count(
            topic_id=TEST_TOPIC_ID, query="error",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)

    def test_count_with_pipe_query(self):
        """query 中已包含管道符，应只取检索部分"""
        result = _run(cls_get_log_count(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS total",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_success_result(result)


@SKIP_NO_CREDS
class TestDescribeSearchSyntaxGoodCase:
    """cls_describe_search_syntax 正常调用测试"""

    def test_returns_syntax_guide(self):
        result = _run(cls_describe_search_syntax())
        assert_success_result(result)
        assert "CQL" in result
        assert "SELECT" in result
        assert "SQL" in result


# ============================================================
# 三、边界值 + 检索/分析模式兼容性测试
# ============================================================

class TestSearchLogAnalyticsModeBoundary:
    """分析模式下参数校验兼容性（不需要真实凭证，校验在 API 调用前）"""

    def test_analytics_negative_limit_passes_validation(self):
        """分析模式 limit=-1 通过校验（校验层不拦截）"""
        # 校验通过后会走到 API 调用，无凭证会被 handle_api_error 捕获
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS cnt",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=-1, sort="random",
        ))
        # 不应是 VALIDATION_ERROR
        try:
            data = json.loads(result)
            if data.get("success") is False:
                assert data["error_type"] != "VALIDATION_ERROR", \
                    f"分析模式不应返回 VALIDATION_ERROR: {data}"
        except json.JSONDecodeError:
            pass  # 非 JSON 说明是正常结果

    def test_analytics_zero_limit_passes_validation(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT status GROUP BY status",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=0,
        ))
        try:
            data = json.loads(result)
            if data.get("success") is False:
                assert data["error_type"] != "VALIDATION_ERROR"
        except json.JSONDecodeError:
            pass

    def test_analytics_huge_limit_passes_validation(self):
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS cnt",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=99999,
        ))
        try:
            data = json.loads(result)
            if data.get("success") is False:
                assert data["error_type"] != "VALIDATION_ERROR"
        except json.JSONDecodeError:
            pass

    def test_analytics_still_validates_topic_id(self):
        """分析模式下 topic_id 为空仍然拦截"""
        result = _run(cls_search_log(
            topic_id="",
            query="* | SELECT COUNT(*) AS cnt",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        assert_validation_error(result, ["topic_id"])

    def test_analytics_still_validates_time_range(self):
        """分析模式下时间逆序仍然拦截"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID,
            query="* | SELECT COUNT(*) AS cnt",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
        ))
        assert_validation_error(result, ["start_time"])

    def test_search_mode_validates_limit(self):
        """检索模式下 limit 超范围仍然拦截"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            limit=1001,
        ))
        assert_validation_error(result, ["limit"])

    def test_search_mode_validates_sort(self):
        """检索模式下非法 sort 仍然拦截"""
        result = _run(cls_search_log(
            topic_id=TEST_TOPIC_ID, query="level:ERROR",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
            sort="invalid",
        ))
        assert_validation_error(result, ["sort"])


class TestDescribeSearchSyntaxBoundary:
    """cls_describe_search_syntax 无参数工具"""

    def test_no_params_returns_content(self):
        """无参数调用直接返回语法文档"""
        result = _run(cls_describe_search_syntax())
        assert isinstance(result, str)
        assert len(result) > 100
        assert "CQL" in result


class TestErrorResponseFormat:
    """统一验证错误响应格式"""

    def test_validation_error_has_all_fields(self):
        """VALIDATION_ERROR 包含完整字段"""
        result = _run(cls_search_log(
            topic_id="", query="",
            start_time=TEST_END_TIME, end_time=TEST_START_TIME,
            limit=-1, sort="bad",
        ))
        data = json.loads(result)
        assert data["success"] is False
        assert data["error_type"] == "VALIDATION_ERROR"
        assert isinstance(data["error_count"], int)
        assert data["error_count"] > 0
        assert isinstance(data["errors"], list)
        assert "hint" in data

        for err in data["errors"]:
            assert set(err.keys()) == {"param", "value", "reason", "expected"}, \
                f"Error fields mismatch: {err.keys()}"

    def test_validation_error_hint_useful(self):
        """hint 提供有用的修正指引"""
        result = _run(cls_search_log(
            topic_id="", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        data = json.loads(result)
        assert "修正" in data["hint"] or "重试" in data["hint"]

    def test_error_expected_field_actionable(self):
        """每个 error 的 expected 字段应包含可操作的信息"""
        result = _run(cls_search_log(
            topic_id="", query="*",
            start_time=TEST_START_TIME, end_time=TEST_END_TIME,
        ))
        data = json.loads(result)
        for err in data["errors"]:
            assert len(err["expected"]) > 5, \
                f"Expected field too short: '{err['expected']}'"
