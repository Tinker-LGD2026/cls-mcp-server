"""参数校验单元测试（pytest 风格）

覆盖 validators.py 中所有校验函数，包括：
- 原子校验函数
- 组合校验入口（检索模式 + 分析模式）
- 批量错误收集
"""

from __future__ import annotations

import json

import pytest

from cls_mcp_server.utils.errors import ParamValidationError, format_validation_errors
from cls_mcp_server.utils.validators import (
    check_enum,
    check_non_negative_int,
    check_positive_int,
    check_required_string,
    check_time_range,
    is_analytics_mode,
    validate_log_context_params,
    validate_log_count_params,
    validate_log_histogram_params,
    validate_search_log_params,
)


# ============================================================
# is_analytics_mode 测试
# ============================================================

class TestIsAnalyticsMode:
    def test_sql_pipe_is_analytics(self):
        assert is_analytics_mode("* | SELECT COUNT(*) AS cnt") is True

    def test_complex_pipe_is_analytics(self):
        assert is_analytics_mode("level:ERROR | SELECT service, COUNT(*) AS cnt GROUP BY service") is True

    def test_simple_query_is_search(self):
        assert is_analytics_mode("level:ERROR") is False

    def test_wildcard_is_search(self):
        assert is_analytics_mode("*") is False

    def test_empty_is_search(self):
        assert is_analytics_mode("") is False

    def test_none_is_search(self):
        assert is_analytics_mode(None) is False  # type: ignore[arg-type]

    def test_pipe_in_value_is_analytics(self):
        """含 | 字符的 query 视为分析模式"""
        assert is_analytics_mode("a|b") is True


# ============================================================
# 原子校验函数测试
# ============================================================

class TestCheckRequiredString:
    def test_valid_string(self):
        assert check_required_string("param", "hello") is None

    def test_empty_string(self):
        err = check_required_string("param", "")
        assert err is not None
        assert err.param == "param"

    def test_whitespace_only(self):
        err = check_required_string("param", "   ")
        assert err is not None

    def test_none_value(self):
        err = check_required_string("param", None)
        assert err is not None


class TestCheckPositiveInt:
    def test_valid_value(self):
        assert check_positive_int("limit", 10, min_val=1, max_val=1000) is None

    def test_min_boundary(self):
        assert check_positive_int("limit", 1, min_val=1, max_val=1000) is None

    def test_max_boundary(self):
        assert check_positive_int("limit", 1000, min_val=1, max_val=1000) is None

    def test_below_min(self):
        err = check_positive_int("limit", 0, min_val=1, max_val=1000)
        assert err is not None
        assert "limit" == err.param

    def test_above_max(self):
        err = check_positive_int("limit", 1001, min_val=1, max_val=1000)
        assert err is not None

    def test_negative_value(self):
        err = check_positive_int("limit", -1, min_val=1)
        assert err is not None

    def test_non_int_type(self):
        err = check_positive_int("limit", "10")  # type: ignore[arg-type]
        assert err is not None
        assert "类型" in err.reason


class TestCheckEnum:
    def test_valid_value(self):
        assert check_enum("sort", "asc", ["asc", "desc"]) is None

    def test_valid_case_insensitive(self):
        assert check_enum("sort", "ASC", ["asc", "desc"]) is None

    def test_invalid_value(self):
        err = check_enum("sort", "random", ["asc", "desc"])
        assert err is not None
        assert "random" in err.reason

    def test_none_skipped(self):
        """None 值跳过校验"""
        assert check_enum("sort", None, ["asc", "desc"]) is None


class TestCheckTimeRange:
    def test_valid_range(self):
        assert check_time_range(100, 200) is None

    def test_equal_range(self):
        assert check_time_range(100, 100) is None

    def test_reversed_range(self):
        err = check_time_range(200, 100)
        assert err is not None
        assert "逆序" in err.reason


class TestCheckNonNegativeInt:
    def test_zero_allowed(self):
        assert check_non_negative_int("prev_logs", 0, max_val=100) is None

    def test_valid_value(self):
        assert check_non_negative_int("prev_logs", 50, max_val=100) is None

    def test_negative_fails(self):
        err = check_non_negative_int("prev_logs", -1, max_val=100)
        assert err is not None

    def test_above_max(self):
        err = check_non_negative_int("prev_logs", 101, max_val=100)
        assert err is not None


# ============================================================
# validate_search_log_params 组合校验测试
# ============================================================

class TestValidateSearchLogParams:
    """检索模式参数校验"""

    def test_valid_params(self):
        """正常参数不抛异常"""
        validate_search_log_params("abc-123", "*", 100, 200, 10, "desc")

    def test_valid_params_max_limit(self):
        validate_search_log_params("abc-123", "level:ERROR", 100, 200, 1000, "asc")

    def test_empty_topic_id(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("", "*", 100, 200, 10, "desc")
        assert any(e.param == "topic_id" for e in exc_info.value.errors)

    def test_empty_query(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "", 100, 200, 10, "desc")
        assert any(e.param == "query" for e in exc_info.value.errors)

    def test_negative_limit(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "*", 100, 200, -1, "desc")
        assert any(e.param == "limit" for e in exc_info.value.errors)

    def test_zero_limit(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "*", 100, 200, 0, "desc")
        assert any(e.param == "limit" for e in exc_info.value.errors)

    def test_limit_exceeds_max(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "*", 100, 200, 1001, "desc")
        assert any(e.param == "limit" for e in exc_info.value.errors)

    def test_invalid_sort(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "*", 100, 200, 10, "random")
        assert any(e.param == "sort" for e in exc_info.value.errors)

    def test_time_reversed(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc", "*", 200, 100, 10, "desc")
        assert any("time" in e.param for e in exc_info.value.errors)

    def test_multiple_errors_batch(self):
        """多个参数同时错误时批量返回"""
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("", "", 200, 100, -1, "random")
        errors = exc_info.value.errors
        assert len(errors) >= 4, f"Expected >= 4 errors, got {len(errors)}: {[e.param for e in errors]}"

    def test_error_format_json(self):
        """错误信息可序列化为标准 JSON 格式"""
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("", "*", 100, 200, 10, "desc")
        result = json.loads(format_validation_errors(exc_info.value.errors))
        assert result["success"] is False
        assert result["error_type"] == "VALIDATION_ERROR"
        assert "hint" in result


class TestValidateSearchLogParamsAnalyticsMode:
    """分析模式参数校验"""

    def test_analytics_skip_limit_sort(self):
        """分析模式下 limit=-1 sort=random 不报错"""
        validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 100, 200, -1, "random")

    def test_analytics_limit_zero(self):
        validate_search_log_params("abc-123", "* | SELECT status, COUNT(*) GROUP BY status", 100, 200, 0, "desc")

    def test_analytics_limit_huge(self):
        validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 100, 200, 99999, "xyz")

    def test_analytics_still_checks_topic_id(self):
        """分析模式下 topic_id 仍然必填"""
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("", "* | SELECT COUNT(*) AS cnt", 100, 200, 10, "desc")
        assert any(e.param == "topic_id" for e in exc_info.value.errors)

    def test_analytics_still_checks_time_range(self):
        """分析模式下时间逆序仍然校验"""
        with pytest.raises(ParamValidationError) as exc_info:
            validate_search_log_params("abc-123", "* | SELECT COUNT(*) AS cnt", 200, 100, 10, "desc")
        assert any("time" in e.param for e in exc_info.value.errors)

    def test_search_mode_still_validates_limit(self):
        """检索模式下 limit 仍然校验"""
        with pytest.raises(ParamValidationError):
            validate_search_log_params("abc-123", "level:ERROR", 100, 200, -1, "desc")

    def test_search_mode_still_validates_sort(self):
        """检索模式下 sort 仍然校验"""
        with pytest.raises(ParamValidationError):
            validate_search_log_params("abc-123", "*", 100, 200, 10, "random")


# ============================================================
# validate_log_context_params 测试
# ============================================================

class TestValidateLogContextParams:
    def test_valid_params(self):
        validate_log_context_params("abc-123", "1774537847429", "pkg1", 1, 10, 10)

    def test_valid_with_string_btime(self):
        validate_log_context_params("abc-123", "2026-03-25 14:25:00.000", "pkg1", 1, 5, 5)

    def test_empty_topic_id(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("", "1774537847429", "pkg1", 1, 10, 10)
        assert any(e.param == "topic_id" for e in exc_info.value.errors)

    def test_empty_btime(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("abc", "", "pkg1", 1, 10, 10)
        assert any(e.param == "btime" for e in exc_info.value.errors)

    def test_empty_pkg_id(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("abc", "1774537847429", "", 1, 10, 10)
        assert any(e.param == "pkg_id" for e in exc_info.value.errors)

    def test_negative_prev_logs(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("abc", "1774537847429", "pkg1", 1, -5, 10)
        assert any(e.param == "prev_logs" for e in exc_info.value.errors)

    def test_prev_logs_exceeds_max(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("abc", "1774537847429", "pkg1", 1, 101, 10)
        assert any(e.param == "prev_logs" for e in exc_info.value.errors)

    def test_negative_next_logs(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_context_params("abc", "1774537847429", "pkg1", 1, 10, -5)
        assert any(e.param == "next_logs" for e in exc_info.value.errors)

    def test_zero_prev_next_allowed(self):
        """prev_logs=0 和 next_logs=0 应该允许"""
        validate_log_context_params("abc-123", "1774537847429", "pkg1", 1, 0, 0)


# ============================================================
# validate_log_histogram_params 测试
# ============================================================

class TestValidateLogHistogramParams:
    def test_valid_params(self):
        validate_log_histogram_params("abc-123", "*", 100, 200, None)

    def test_valid_with_interval(self):
        validate_log_histogram_params("abc-123", "*", 100, 200, 60000)

    def test_empty_topic_id(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_histogram_params("", "*", 100, 200, None)
        assert any(e.param == "topic_id" for e in exc_info.value.errors)

    def test_empty_query(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_histogram_params("abc", "", 100, 200, None)
        assert any(e.param == "query" for e in exc_info.value.errors)

    def test_negative_interval(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_histogram_params("abc", "*", 100, 200, -1000)
        assert any(e.param == "interval" for e in exc_info.value.errors)

    def test_zero_interval(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_histogram_params("abc", "*", 100, 200, 0)
        assert any(e.param == "interval" for e in exc_info.value.errors)

    def test_time_reversed(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_histogram_params("abc", "*", 200, 100, None)
        assert any("time" in e.param for e in exc_info.value.errors)


# ============================================================
# validate_log_count_params 测试
# ============================================================

class TestValidateLogCountParams:
    def test_valid_params(self):
        validate_log_count_params("abc-123", "*", 100, 200)

    def test_valid_with_condition(self):
        validate_log_count_params("abc-123", "level:ERROR", 100, 200)

    def test_empty_topic_id(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_count_params("", "*", 100, 200)
        assert any(e.param == "topic_id" for e in exc_info.value.errors)

    def test_empty_query(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_count_params("abc", "", 100, 200)
        assert any(e.param == "query" for e in exc_info.value.errors)

    def test_time_reversed(self):
        with pytest.raises(ParamValidationError) as exc_info:
            validate_log_count_params("abc", "*", 200, 100)
        assert any("time" in e.param for e in exc_info.value.errors)
