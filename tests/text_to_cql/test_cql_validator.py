"""cql_validator 校验器兼容性测试

覆盖：
1. 传统 CAST 写法通过校验
2. LONG 型直传写法兼容性（新推荐写法）
3. 非法语法正确拦截
4. 边界条件与安全检查
"""

from __future__ import annotations

import pytest

from cls_mcp_server.tools.text_to_cql.cql_validator import (
    ValidationResult,
    clean_cql,
    validate_cql,
    _has_invalid_from_clause,
    _check_sql_part,
)


class TestHistogramValidation:
    """histogram 函数校验兼容性"""

    def test_traditional_cast_timestamp_pass(self):
        """传统 CAST 写法应通过"""
        result = validate_cql(
            "* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 hour) as t, "
            "COUNT(*) as cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid, f"传统 CAST 写法不应报错: {result.errors}"

    def test_long_type_direct_pass(self):
        """LONG 型直传写法应通过（新推荐写法）

        这是新文档推荐的最简写法：
        histogram(__TIMESTAMP__, interval 1 hour)
        自动按 UTC+8 处理，无需 CAST
        """
        result = validate_cql(
            "* | SELECT histogram(__TIMESTAMP__, interval 1 hour) as t, "
            "COUNT(*) as cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid, (
            f"LONG 型直传写法不应报错（这是新推荐写法）: {result.errors}"
        )

    def test_histogram_without_timestamp_field_fail(self):
        """histogram 使用非 __TIMESTAMP__ 字段应报错"""
        result = validate_cql(
            "* | SELECT histogram(some_field, interval 1 hour) as t"
        )
        assert not result.is_valid
        assert any("histogram" in e for e in result.errors)

    def test_histogram_5_minute_bucket(self):
        """5 分钟分桶 — LONG 型"""
        result = validate_cql(
            "level:ERROR | SELECT histogram(__TIMESTAMP__, interval 5 minute) as t, "
            "COUNT(*) as cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid, f"5分钟分桶不应报错: {result.errors}"

    def test_histogram_1_day_cast(self):
        """1 天分桶 — CAST 型"""
        result = validate_cql(
            "* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 day) as t, "
            "COUNT(*) as cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid


class TestTimeSeriesValidation:
    """time_series 函数校验兼容性"""

    def test_traditional_cast_pass(self):
        """传统 CAST 写法应通过"""
        result = validate_cql(
            "* | SELECT time_series(cast(__TIMESTAMP__ as timestamp), '1h', '%Y-%m-%d %H:%i:%s', '0') as t, "
            "COUNT(*) as cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid, f"time_series CAST 写法不应报错: {result.errors}"

    def test_long_type_direct_pass(self):
        """LONG 型直传写法应通过（新推荐写法）"""
        result = validate_cql(
            "* | SELECT time_series(__TIMESTAMP__, '5m', '%Y-%m-%d %H:%i:%s', '0') as time, "
            "COUNT(*) as cnt GROUP BY time ORDER BY time"
        )
        assert result.is_valid, (
            f"time_series LONG 型直传写法不应报错: {result.errors}"
        )

    def test_time_series_without_timestamp_field_fail(self):
        """time_series 使用非 __TIMESTAMP__ 字段应报错"""
        result = validate_cql(
            "* | SELECT time_series(some_field, '1h', '%H:%i', '0') as t"
        )
        assert not result.is_valid
        assert any("time_series" in e for e in result.errors)


class TestCompareValidation:
    """compare 函数相关语法校验"""

    def test_basic_compare_pass(self):
        """基础 compare 用法应通过"""
        result = validate_cql("* | SELECT compare(count(*), 86400) as result")
        assert result.is_valid

    def test_multi_period_compare_pass(self):
        """多周期 compare 应通过"""
        result = validate_cql("* | SELECT compare(count(*), 86400, 604800) as result")
        assert result.is_valid


class TestIpFunctionValidation:
    """IP 函数校验"""

    def test_ip_to_province_pass(self):
        result = validate_cql(
            "* | SELECT ip_to_province(client_ip) as province, COUNT(*) as cnt "
            "GROUP BY province ORDER BY cnt DESC LIMIT 10"
        )
        assert result.is_valid

    def test_ip_to_threat_level_pass(self):
        result = validate_cql(
            "* | SELECT client_ip, ip_to_threat_level(client_ip) as level, COUNT(*) as cnt "
            "GROUP BY client_ip, level HAVING level > 0 ORDER BY level DESC"
        )
        assert result.is_valid

    def test_is_subnet_of_pass(self):
        result = validate_cql(
            "* | SELECT client_ip, COUNT(*) as cnt "
            "WHERE is_subnet_of(client_ip, '192.168.0.0/16') "
            "GROUP BY client_ip"
        )
        assert result.is_valid


class TestJsonFunctionValidation:
    """JSON 函数校验"""

    def test_json_extract_scalar_pass(self):
        result = validate_cql(
            "* | SELECT json_extract_scalar(body, '$.action') as action, "
            "COUNT(*) as cnt GROUP BY action ORDER BY cnt DESC"
        )
        assert result.is_valid


class TestFromClauseDetectionExtended:
    """FROM 子句检测扩展测试"""

    def test_from_unnest_allowed(self):
        assert _has_invalid_from_clause("SELECT * FROM UNNEST(SPLIT(TAGS, ','))") is False

    def test_from_json_extract_allowed(self):
        assert _has_invalid_from_clause("SELECT * FROM JSON_EXTRACT(DATA, '$')") is False

    def test_from_table_blocked(self):
        assert _has_invalid_from_clause("SELECT * FROM LOGS WHERE LEVEL = 'ERROR'") is True

    def test_extract_from_not_blocked(self):
        assert _has_invalid_from_clause(
            "SELECT EXTRACT(HOUR FROM CAST(__TIMESTAMP__ AS TIMESTAMP)) AS H"
        ) is False

    def test_no_from_at_all(self):
        assert _has_invalid_from_clause("SELECT COUNT(*) AS TOTAL") is False


class TestSafetyChecks:
    """安全检查"""

    @pytest.mark.parametrize("dangerous_cql", [
        "* | SELECT 1; DROP TABLE users",
        "* | DELETE FROM logs WHERE 1=1",
        "* | UPDATE users SET admin = true",
        "* | INSERT INTO logs VALUES (1)",
        "* | TRUNCATE logs",
        "* | ALTER TABLE logs ADD COLUMN x int",
        "* | CREATE TABLE evil (id int)",
    ])
    def test_dangerous_sql_blocked(self, dangerous_cql):
        result = validate_cql(dangerous_cql)
        assert not result.is_valid
        assert any("危险" in e for e in result.errors)


class TestEdgeCases:
    """边界条件"""

    def test_empty_cql(self):
        result = validate_cql("")
        assert not result.is_valid
        assert "CQL 查询为空" in result.errors[0]

    def test_whitespace_only_cql(self):
        result = validate_cql("   ")
        assert not result.is_valid

    def test_simple_search_cql(self):
        """纯检索 CQL 无 SQL 部分"""
        result = validate_cql("level:ERROR AND status:500")
        assert result.is_valid

    def test_clean_cql_markdown(self):
        raw = "```sql\nSELECT COUNT(*) AS total\n```"
        assert clean_cql(raw) == "SELECT COUNT(*) AS total"

    def test_clean_cql_semicolon(self):
        assert clean_cql("level:ERROR;") == "level:ERROR"

    def test_unmatched_brackets(self):
        result = validate_cql("* | SELECT COUNT(*")
        assert not result.is_valid
        assert any("括号" in e for e in result.errors)

    def test_unmatched_quotes(self):
        result = validate_cql("level:'ERROR")
        assert not result.is_valid
        assert any("引号" in e for e in result.errors)

    def test_sql_without_select(self):
        result = validate_cql("* | COUNT(*) AS total")
        assert not result.is_valid
        assert any("SELECT" in e for e in result.errors)
