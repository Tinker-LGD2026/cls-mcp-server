"""text_to_cql 集成测试 — 真实调用 LLM API 验证 CQL 生成质量

通过 @pytest.mark.integration 标记，默认不随 `pytest` 执行。
运行方式：
    pytest tests/integration/ -m integration -v

测试策略：
- 每个用例传入自然语言 → CqlGenerator.generate() → 校验 CqlResult
- 校验维度：success=True、cql 非空、关键 SQL 片段存在、无校验错误
- LLM 输出有不确定性，因此校验以"结构合规 + 关键词存在"为主，不做精确字符串匹配
"""

from __future__ import annotations

import re

import pytest

from cls_mcp_server.tools.text_to_cql.cql_generator import CqlGenerator, CqlResult
from cls_mcp_server.tools.text_to_cql.cql_validator import clean_cql, validate_cql

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# ============================================================
# 辅助校验函数
# ============================================================

def assert_cql_success(result: CqlResult, context: str = ""):
    """断言生成成功且 CQL 非空，429 限流时跳过而非失败"""
    prefix = f"[{context}] " if context else ""
    if not result.success and result.error_message and "429" in result.error_message:
        pytest.skip(f"{prefix}跳过：API 限流 (429 TPM rate limit)")
    assert result.success, (
        f"{prefix}生成失败: error={result.error_message}, "
        f"validation_errors={result.validation_errors}, "
        f"attempts={result.attempts}"
    )
    assert result.cql.strip(), f"{prefix}CQL 为空"
    assert result.mode == "generate", f"{prefix}mode 应为 generate, 实际: {result.mode}"


def assert_cql_contains(cql: str, keywords: list[str], context: str = ""):
    """断言 CQL 包含指定关键词（不区分大小写）"""
    cql_upper = cql.upper()
    for kw in keywords:
        assert kw.upper() in cql_upper, (
            f"[{context}] CQL 缺少关键词 '{kw}'\nCQL: {cql}"
        )


def assert_cql_has_pipe(cql: str, context: str = ""):
    """断言 CQL 包含管道符（SQL 分析模式）"""
    assert "|" in cql, f"[{context}] CQL 缺少管道符 '|'\nCQL: {cql}"


def assert_cql_valid(cql: str, context: str = ""):
    """断言 CQL 通过校验器验证"""
    result = validate_cql(cql)
    assert result.is_valid, (
        f"[{context}] CQL 校验失败: {result.errors}\nCQL: {cql}"
    )


# ============================================================
# 1. 基础连通性测试
# ============================================================

class TestLlmConnectivity:
    """验证 LLM API 可达性和基本响应能力"""

    async def test_simple_query_returns_result(self, generator: CqlGenerator):
        """最简单的查询应能成功返回"""
        result = await generator.generate("查找 error 日志")
        assert_cql_success(result, "simple_query")

    async def test_response_timing(self, generator: CqlGenerator):
        """响应时间应在合理范围内（< 30s）"""
        result = await generator.generate("查看最近的错误日志")
        assert_cql_success(result, "timing")
        assert result.elapsed_ms < 30000, (
            f"响应时间过长: {result.elapsed_ms}ms"
        )

    async def test_attempts_count(self, generator: CqlGenerator):
        """简单查询应在 1-2 次尝试内成功"""
        result = await generator.generate("统计日志总数")
        assert_cql_success(result, "attempts")
        assert result.attempts <= 2, (
            f"尝试次数过多: {result.attempts}"
        )


# ============================================================
# 2. 基础检索场景
# ============================================================

class TestBasicSearch:
    """基础 CQL 检索语句生成"""

    async def test_keyword_search(self, generator: CqlGenerator):
        """关键词检索：查找包含 error 的日志"""
        result = await generator.generate("查找包含 error 的日志")
        assert_cql_success(result, "keyword_search")
        # 关键词检索可能生成纯 CQL（不含管道符）或带 SQL 的形式
        cql_lower = result.cql.lower()
        assert "error" in cql_lower, f"CQL 缺少 'error'\nCQL: {result.cql}"

    async def test_field_filter(self, generator: CqlGenerator):
        """字段过滤：查找 level 为 ERROR 的日志"""
        result = await generator.generate("查找 level 为 ERROR 的日志")
        assert_cql_success(result, "field_filter")
        cql_lower = result.cql.lower()
        assert "level" in cql_lower, f"CQL 缺少 'level'\nCQL: {result.cql}"
        assert "error" in cql_lower, f"CQL 缺少 'error'\nCQL: {result.cql}"

    async def test_multi_condition(self, generator: CqlGenerator):
        """多条件：查找 status=500 且 method=POST 的日志"""
        result = await generator.generate("查找 HTTP 状态码为 500 且请求方法为 POST 的日志")
        assert_cql_success(result, "multi_condition")
        cql_lower = result.cql.lower()
        assert "500" in cql_lower, f"CQL 缺少 '500'\nCQL: {result.cql}"
        assert "post" in cql_lower, f"CQL 缺少 'POST'\nCQL: {result.cql}"

    async def test_phrase_search(self, generator: CqlGenerator):
        """短语检索：查找包含 'connection timeout' 的日志"""
        result = await generator.generate("查找包含 connection timeout 的日志")
        assert_cql_success(result, "phrase_search")
        cql_lower = result.cql.lower()
        assert "connection" in cql_lower and "timeout" in cql_lower, (
            f"CQL 缺少 'connection timeout'\nCQL: {result.cql}"
        )


# ============================================================
# 3. 聚合分析场景
# ============================================================

class TestAggregation:
    """SQL 管道聚合分析生成"""

    async def test_count_total(self, generator: CqlGenerator):
        """统计日志总数"""
        result = await generator.generate("统计日志总数")
        assert_cql_success(result, "count_total")
        assert_cql_has_pipe(result.cql, "count_total")
        assert_cql_contains(result.cql, ["SELECT", "COUNT"], "count_total")

    async def test_group_by_status(self, generator: CqlGenerator):
        """按 status 分组统计请求数量"""
        result = await generator.generate("按 status 字段分组统计请求数量，按数量降序排列")
        assert_cql_success(result, "group_by_status")
        assert_cql_has_pipe(result.cql, "group_by_status")
        assert_cql_contains(result.cql, ["SELECT", "COUNT", "GROUP BY", "ORDER BY"], "group_by_status")

    async def test_top_n(self, generator: CqlGenerator):
        """查找请求量 Top 10 的 path"""
        result = await generator.generate("统计请求量最多的 10 个 path")
        assert_cql_success(result, "top_n")
        assert_cql_has_pipe(result.cql, "top_n")
        assert_cql_contains(result.cql, ["SELECT", "COUNT", "GROUP BY", "LIMIT"], "top_n")

    async def test_avg_response_time(self, generator: CqlGenerator):
        """计算平均响应时间"""
        result = await generator.generate("计算各服务的平均响应时间")
        assert_cql_success(result, "avg_response_time")
        assert_cql_has_pipe(result.cql, "avg_response_time")
        assert_cql_contains(result.cql, ["SELECT", "AVG"], "avg_response_time")

    async def test_percentile(self, generator: CqlGenerator):
        """计算 P99 响应时间"""
        result = await generator.generate("计算 response_time 的 P99 值")
        assert_cql_success(result, "percentile")
        assert_cql_has_pipe(result.cql, "percentile")
        cql_upper = result.cql.upper()
        assert "APPROX_PERCENTILE" in cql_upper or "PERCENTILE" in cql_upper, (
            f"CQL 缺少百分位函数\nCQL: {result.cql}"
        )


# ============================================================
# 4. 时间函数场景（CLS 扩展语法重点）
# ============================================================

class TestTimeFunction:
    """histogram / time_series 时间函数生成"""

    async def test_histogram_hourly(self, generator: CqlGenerator):
        """按小时统计日志量趋势"""
        result = await generator.generate("按小时统计日志数量的变化趋势")
        assert_cql_success(result, "histogram_hourly")
        assert_cql_has_pipe(result.cql, "histogram_hourly")
        assert_cql_contains(result.cql, ["SELECT", "HISTOGRAM", "__TIMESTAMP__"], "histogram_hourly")

    async def test_histogram_minute(self, generator: CqlGenerator):
        """按 5 分钟统计错误数趋势"""
        result = await generator.generate("按 5 分钟粒度统计 level:ERROR 日志数量趋势")
        assert_cql_success(result, "histogram_minute")
        assert_cql_has_pipe(result.cql, "histogram_minute")
        cql_upper = result.cql.upper()
        # LLM 可能用 histogram 或 time_series，两者都是合法的时间聚合函数
        has_time_func = "HISTOGRAM" in cql_upper or "TIME_SERIES" in cql_upper
        assert has_time_func, f"缺少时间聚合函数\nCQL: {result.cql}"
        assert "__TIMESTAMP__" in cql_upper, f"缺少 __TIMESTAMP__\nCQL: {result.cql}"

    async def test_histogram_validates_clean(self, generator: CqlGenerator):
        """histogram 生成的 CQL 应通过校验器"""
        result = await generator.generate("按小时统计每个 service 的请求数趋势")
        assert_cql_success(result, "histogram_validate")
        assert_cql_valid(result.cql, "histogram_validate")

    async def test_time_series_fill(self, generator: CqlGenerator):
        """time_series 时序补全"""
        result = await generator.generate("每 5 分钟统计日志数量，空缺时间点填充 0")
        assert_cql_success(result, "time_series")
        assert_cql_has_pipe(result.cql, "time_series")
        cql_upper = result.cql.upper()
        # 可能用 histogram 或 time_series，两者都算正确
        has_time_func = "HISTOGRAM" in cql_upper or "TIME_SERIES" in cql_upper
        assert has_time_func, f"缺少时间函数\nCQL: {result.cql}"


# ============================================================
# 5. compare 同环比场景
# ============================================================

class TestCompare:
    """compare 同环比函数生成"""

    async def test_day_over_day(self, generator: CqlGenerator):
        """日环比对比：今天与昨天的错误数"""
        result = await generator.generate("对比今天和昨天的错误日志数量（日环比）")
        assert_cql_success(result, "day_over_day")
        assert_cql_has_pipe(result.cql, "day_over_day")
        assert_cql_contains(result.cql, ["COMPARE"], "day_over_day")
        # compare 的 offset 参数应为 86400（1天的秒数）
        assert "86400" in result.cql, f"缺少 86400 偏移量\nCQL: {result.cql}"

    async def test_week_over_week(self, generator: CqlGenerator):
        """周同比对比"""
        result = await generator.generate("对比本周和上周的日志量（周同比）")
        assert_cql_success(result, "week_over_week")
        assert_cql_has_pipe(result.cql, "week_over_week")
        assert_cql_contains(result.cql, ["COMPARE"], "week_over_week")
        assert "604800" in result.cql, f"缺少 604800 偏移量\nCQL: {result.cql}"


# ============================================================
# 6. IP 函数场景
# ============================================================

class TestIpFunction:
    """CLS IP 地理信息函数生成"""

    async def test_ip_to_province(self, generator: CqlGenerator):
        """按省份统计请求来源"""
        result = await generator.generate("按省份统计 client_ip 的请求数量分布")
        assert_cql_success(result, "ip_province")
        assert_cql_has_pipe(result.cql, "ip_province")
        cql_upper = result.cql.upper()
        has_ip_func = any(f in cql_upper for f in [
            "IP_TO_PROVINCE", "IP_TO_CITY", "IP_TO_COUNTRY"
        ])
        assert has_ip_func, f"缺少 IP 地理函数\nCQL: {result.cql}"


# ============================================================
# 7. 带索引字段信息的增强生成
# ============================================================

class TestWithIndexInfo:
    """验证 index_info 提供字段信息后对生成质量的影响"""

    async def test_field_aware_aggregation(self, generator_with_index: CqlGenerator):
        """有索引信息时，应能正确使用字段名"""
        result = await generator_with_index.generate("按服务名统计平均响应时间")
        assert_cql_success(result, "field_aware")
        assert_cql_has_pipe(result.cql, "field_aware")
        cql_lower = result.cql.lower()
        # 应使用 index_info 中提供的字段名
        assert "service" in cql_lower, f"CQL 缺少 'service' 字段\nCQL: {result.cql}"
        assert "response_time" in cql_lower, f"CQL 缺少 'response_time' 字段\nCQL: {result.cql}"

    async def test_complex_query_with_index(self, generator_with_index: CqlGenerator):
        """复杂查询：有索引信息时，按小时统计各级别日志数量趋势"""
        result = await generator_with_index.generate(
            "按小时统计各日志级别（level）的数量变化趋势"
        )
        assert_cql_success(result, "complex_with_index")
        assert_cql_has_pipe(result.cql, "complex_with_index")
        cql_upper = result.cql.upper()
        # LLM 可能用 histogram 或 time_series，两者都合法
        has_time_func = "HISTOGRAM" in cql_upper or "TIME_SERIES" in cql_upper
        assert has_time_func, f"[complex_with_index] CQL 缺少时间聚合函数\nCQL: {result.cql}"
        assert "__TIMESTAMP__" in cql_upper, f"[complex_with_index] CQL 缺少 __TIMESTAMP__\nCQL: {result.cql}"
        assert "level" in result.cql.lower(), f"CQL 缺少 'level'\nCQL: {result.cql}"


# ============================================================
# 8. CQL 校验闭环测试
# ============================================================

class TestValidationLoop:
    """验证生成-清理-校验-重试闭环的完整性"""

    async def test_clean_cql_strips_markdown(self, generator: CqlGenerator):
        """验证 clean_cql 能正确清理 LLM 输出的 markdown 包裹"""
        result = await generator.generate("统计不同状态码的请求数量")
        assert_cql_success(result, "clean_markdown")
        # 最终 CQL 不应包含 markdown 标记
        assert "```" not in result.cql, f"CQL 含 markdown 标记\nCQL: {result.cql}"
        assert not result.cql.endswith(";"), f"CQL 以分号结尾\nCQL: {result.cql}"

    async def test_validation_passes(self, generator: CqlGenerator):
        """生成成功的 CQL 应通过校验器"""
        result = await generator.generate("按小时统计日志数量")
        assert_cql_success(result, "validation_pass")
        assert_cql_valid(result.cql, "validation_pass")
        assert result.validation_errors is None, (
            f"成功的 CQL 不应有校验错误: {result.validation_errors}"
        )

    async def test_no_dangerous_sql(self, generator: CqlGenerator):
        """生成的 CQL 不应包含危险 SQL 操作"""
        result = await generator.generate("删除所有日志")  # 故意输入危险请求
        # 不论成功或失败，CQL 都不应包含危险操作
        if result.cql:
            cql_upper = result.cql.upper()
            dangerous_patterns = [
                "DROP TABLE", "DELETE FROM", "TRUNCATE",
                "ALTER TABLE", "INSERT INTO", "UPDATE",
            ]
            for pattern in dangerous_patterns:
                assert pattern not in cql_upper, (
                    f"CQL 包含危险操作 '{pattern}'\nCQL: {result.cql}"
                )


# ============================================================
# 9. 边界场景测试
# ============================================================

class TestEdgeCases:
    """边界场景与异常输入"""

    async def test_very_short_query(self, generator: CqlGenerator):
        """极短输入"""
        result = await generator.generate("error")
        assert_cql_success(result, "short_query")
        assert "error" in result.cql.lower(), f"CQL 缺少 'error'\nCQL: {result.cql}"

    async def test_chinese_query(self, generator: CqlGenerator):
        """纯中文查询"""
        result = await generator.generate("查看最近一小时内响应时间超过两秒的慢请求")
        assert_cql_success(result, "chinese_query")
        assert result.cql.strip(), f"CQL 为空"

    async def test_mixed_language_query(self, generator: CqlGenerator):
        """中英混合查询"""
        result = await generator.generate("统计 level:ERROR 的 top 5 service")
        assert_cql_success(result, "mixed_lang")
        assert_cql_has_pipe(result.cql, "mixed_lang")

    async def test_complex_natural_language(self, generator: CqlGenerator):
        """复杂自然语言描述"""
        result = await generator.generate(
            "我想看看最近有哪些接口报错了，按接口路径分组统计错误数，"
            "只看错误数大于 10 的接口，按错误数降序排列"
        )
        assert_cql_success(result, "complex_nl")
        assert_cql_has_pipe(result.cql, "complex_nl")
        assert_cql_contains(result.cql, ["SELECT", "COUNT", "GROUP BY", "ORDER BY"], "complex_nl")
        # 应包含 HAVING 子句来过滤数量 > 10
        cql_upper = result.cql.upper()
        has_filter = "HAVING" in cql_upper or ">" in result.cql
        assert has_filter, f"CQL 缺少数量过滤条件\nCQL: {result.cql}"
