"""Text2CQL 模块单元测试

覆盖优化修复的所有关键点：
1. CQL 校验器 — FROM 检查兼容 EXTRACT/TRIM/SUBSTRING
2. CQL 校验器 — 基础校验功能
3. 重试对话历史保留
4. 模式路由
5. 语法文档过滤
6. httpx 连接池复用
"""

from __future__ import annotations

import pytest

from cls_mcp_server.tools.text_to_cql.cql_validator import (
    ValidationResult,
    clean_cql,
    validate_cql,
    _has_invalid_from_clause,
)
from cls_mcp_server.tools.text_to_cql.mode_router import route_mode
from cls_mcp_server.tools.text_to_cql.prompts import (
    build_retry_user_prompt,
    build_system_prompt,
    build_user_prompt,
)
from cls_mcp_server.tools.text_to_cql.syntax_docs import get_syntax_docs


# ============================================================
# 1. CQL 校验器 — FROM 检查兼容性（核心修复点）
# ============================================================

class TestFromClauseDetection:
    """FROM 子句检测：确保合法函数内 FROM 不被误报"""

    def test_extract_hour_from_not_flagged(self):
        """EXTRACT(HOUR FROM __TIMESTAMP__) 不应被误报"""
        sql = "SELECT EXTRACT(HOUR FROM CAST(__TIMESTAMP__ AS TIMESTAMP)) AS h, COUNT(*) AS cnt GROUP BY h"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_extract_day_from_not_flagged(self):
        """EXTRACT(DAY FROM ...) 不应被误报"""
        sql = "SELECT EXTRACT(DAY FROM CAST(__TIMESTAMP__ AS TIMESTAMP)) AS d"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_trim_from_not_flagged(self):
        """TRIM(LEADING 'x' FROM col) 不应被误报"""
        sql = "SELECT TRIM(LEADING '/' FROM path) AS clean_path"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_substring_from_not_flagged(self):
        """SUBSTRING(col FROM 1 FOR 3) 不应被误报"""
        sql = "SELECT SUBSTRING(message FROM 1 FOR 100) AS msg"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_from_unnest_not_flagged(self):
        """FROM UNNEST(...) 是 CLS 合法用法"""
        sql = "SELECT * FROM UNNEST(SPLIT(tags, ','))"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_from_json_extract_not_flagged(self):
        """FROM JSON_EXTRACT(...) 是 CLS 合法用法"""
        sql = "SELECT * FROM JSON_EXTRACT(data, '$')"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_real_from_table_flagged(self):
        """真正的 FROM table_name 应该被检测到"""
        sql = "SELECT * FROM logs WHERE level = 'ERROR'"
        assert _has_invalid_from_clause(sql.upper()) is True

    def test_from_with_schema_table_flagged(self):
        """FROM some_table 应该被检测到"""
        sql = "SELECT COUNT(*) FROM access_log"
        assert _has_invalid_from_clause(sql.upper()) is True

    def test_no_from_at_all(self):
        """没有 FROM 的 SQL 不应被误报"""
        sql = "SELECT COUNT(*) AS total, AVG(latency) AS avg_latency GROUP BY status"
        assert _has_invalid_from_clause(sql.upper()) is False

    def test_extract_and_no_table_from(self):
        """EXTRACT + 普通聚合，无 FROM 表名"""
        sql = "SELECT EXTRACT(HOUR FROM CAST(__TIMESTAMP__ AS TIMESTAMP)) AS h, COUNT(*) GROUP BY h ORDER BY h"
        assert _has_invalid_from_clause(sql.upper()) is False


# ============================================================
# 2. CQL 校验器 — 基础功能
# ============================================================

class TestCqlValidator:
    """CQL 校验器基础功能测试"""

    def test_empty_cql(self):
        result = validate_cql("")
        assert not result.is_valid
        assert "CQL 查询为空" in result.errors[0]

    def test_valid_simple_cql(self):
        result = validate_cql("level:ERROR")
        assert result.is_valid

    def test_valid_sql_pipe(self):
        result = validate_cql("* | SELECT COUNT(*) AS total")
        assert result.is_valid

    def test_unmatched_brackets(self):
        result = validate_cql("* | SELECT COUNT(*")
        assert not result.is_valid
        assert any("括号" in e or "右括号" in e for e in result.errors)

    def test_unmatched_quotes(self):
        result = validate_cql("level:'ERROR")
        assert not result.is_valid
        assert any("引号" in e for e in result.errors)

    def test_sql_must_start_with_select(self):
        result = validate_cql("* | COUNT(*) AS total")
        assert not result.is_valid
        assert any("SELECT" in e for e in result.errors)

    def test_histogram_without_cast(self):
        result = validate_cql("* | SELECT histogram(some_field, interval 1 hour) AS t")
        assert not result.is_valid
        assert any("histogram" in e for e in result.errors)

    def test_histogram_with_cast(self):
        result = validate_cql(
            "* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 hour) AS t, "
            "COUNT(*) AS cnt GROUP BY t ORDER BY t"
        )
        assert result.is_valid

    def test_dangerous_drop_table(self):
        result = validate_cql("* | SELECT 1; DROP TABLE users")
        assert not result.is_valid
        assert any("危险" in e for e in result.errors)

    def test_clean_cql_strips_markdown(self):
        raw = "```sql\nSELECT COUNT(*) AS total\n```"
        assert clean_cql(raw) == "SELECT COUNT(*) AS total"

    def test_clean_cql_strips_semicolon(self):
        assert clean_cql("level:ERROR;") == "level:ERROR"


# ============================================================
# 3. 重试 Prompt — 对话历史和索引信息保留
# ============================================================

class TestRetryPrompts:
    """重试 Prompt 构建测试"""

    def test_retry_prompt_without_index(self):
        """无索引信息时的重试 Prompt"""
        prompt = build_retry_user_prompt(
            query="统计错误日志",
            error_feedback="CLS SQL 不需要 FROM 子句",
        )
        assert "统计错误日志" in prompt
        assert "FROM 子句" in prompt
        assert "索引" not in prompt

    def test_retry_prompt_with_index(self):
        """有索引信息时的重试 Prompt 应包含索引字段"""
        index_info = "可用字段：\n  - level (keyword)\n  - latency (long, 统计)"
        prompt = build_retry_user_prompt(
            query="统计错误日志",
            error_feedback="CLS SQL 不需要 FROM 子句",
            index_info=index_info,
        )
        assert "统计错误日志" in prompt
        assert "FROM 子句" in prompt
        assert "level" in prompt
        assert "latency" in prompt
        assert "索引字段" in prompt

    def test_user_prompt_with_index(self):
        """首次 User Prompt 带索引信息"""
        index_info = "可用字段：\n  - status (long)"
        prompt = build_user_prompt("统计各状态码分布", index_info)
        assert "status" in prompt
        assert "统计各状态码分布" in prompt

    def test_user_prompt_without_index(self):
        """首次 User Prompt 不带索引信息"""
        prompt = build_user_prompt("统计错误日志")
        assert prompt == "统计错误日志"

    def test_system_prompt_includes_syntax(self):
        """System Prompt 包含语法文档"""
        prompt = build_system_prompt("## histogram\n时间分桶函数")
        assert "histogram" in prompt
        assert "CQL" in prompt


# ============================================================
# 4. 模式路由
# ============================================================

class TestModeRouter:
    """Auto 模式路由判断测试"""

    @pytest.mark.parametrize("query", [
        "语法参考",
        "CLS有哪些独有函数",
        "histogram怎么用",
        "syntax reference",
        "time_series用法",
        "CLS支持哪些函数",
        "函数列表",
    ])
    def test_syntax_only_queries(self, query):
        assert route_mode(query) == "syntax_only"

    @pytest.mark.parametrize("query", [
        "统计最近1小时错误日志",
        "查询 level:ERROR 的日志",
        "分析各状态码分布",
        "帮我写一个按小时统计的CQL",
        "top10 最慢的请求",
        "错误日志趋势",
    ])
    def test_generate_queries(self, query):
        assert route_mode(query) == "generate"

    def test_short_query_defaults_syntax(self):
        """非常短的查询默认走 syntax_only"""
        assert route_mode("abc") == "syntax_only"

    def test_ambiguous_defaults_generate(self):
        """无明确信号的查询默认走 generate"""
        assert route_mode("最近有什么异常") == "generate"


# ============================================================
# 5. 语法文档过滤
# ============================================================

class TestSyntaxDocsFilter:
    """语法文档 category 过滤测试"""

    def test_empty_category_returns_all(self):
        """空 category 返回全部文档"""
        docs = get_syntax_docs("")
        assert len(docs) > 100

    def test_histogram_filter(self):
        """过滤 histogram 相关章节"""
        docs = get_syntax_docs("histogram")
        assert "histogram" in docs.lower()

    def test_compare_filter(self):
        """过滤 compare 相关章节"""
        docs = get_syntax_docs("compare")
        assert "compare" in docs.lower()

    def test_ip_filter(self):
        """过滤 IP 函数相关章节"""
        docs = get_syntax_docs("ip_to")
        assert "ip_to" in docs.lower()

    def test_no_match_returns_all(self):
        """无匹配关键词时返回全部"""
        docs = get_syntax_docs("这是一个完全不匹配的查询")
        full_docs = get_syntax_docs("")
        assert docs == full_docs

    def test_natural_language_with_keyword(self):
        """自然语言查询中提取函数名关键词"""
        docs = get_syntax_docs("histogram怎么用")
        assert "histogram" in docs.lower()


# ============================================================
# 6. httpx 连接池
# ============================================================

class TestLlmClientPool:
    """LLM 客户端连接池测试"""

    def test_shared_client_singleton(self):
        """共享客户端是单例"""
        from cls_mcp_server.tools.text_to_cql.llm_client import _get_shared_client
        client1 = _get_shared_client()
        client2 = _get_shared_client()
        assert client1 is client2

    def test_shared_client_not_closed(self):
        """共享客户端创建后未关闭"""
        from cls_mcp_server.tools.text_to_cql.llm_client import _get_shared_client
        client = _get_shared_client()
        assert not client.is_closed

    @pytest.mark.asyncio
    async def test_close_shared_client(self):
        """关闭共享客户端后重新获取是新实例"""
        from cls_mcp_server.tools.text_to_cql.llm_client import (
            _get_shared_client,
            close_shared_client,
        )
        client1 = _get_shared_client()
        await close_shared_client()
        assert client1.is_closed
        client2 = _get_shared_client()
        assert client2 is not client1
        assert not client2.is_closed
        # 清理
        await close_shared_client()


# ============================================================
# 7. CqlGenerator — 重试对话历史累积
# ============================================================

class TestCqlGeneratorMessages:
    """CqlGenerator 消息构建测试"""

    def test_initial_messages_structure(self):
        """首次消息包含 system + user"""
        from cls_mcp_server.tools.text_to_cql.cql_generator import CqlGenerator, LlmConfig
        gen = CqlGenerator(
            llm_config=LlmConfig(api_base="http://test", api_key="k", model="m"),
            syntax_docs="test docs",
            index_info="可用字段：\n  - level (keyword)",
        )
        msgs = gen._build_initial_messages("统计错误日志")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "test docs" in msgs[0]["content"]
        assert "level" in msgs[1]["content"]
        assert "统计错误日志" in msgs[1]["content"]

    def test_initial_messages_without_index(self):
        """无索引信息时 user prompt 只包含查询"""
        from cls_mcp_server.tools.text_to_cql.cql_generator import CqlGenerator, LlmConfig
        gen = CqlGenerator(
            llm_config=LlmConfig(api_base="http://test", api_key="k", model="m"),
            syntax_docs="docs",
        )
        msgs = gen._build_initial_messages("查询日志")
        assert len(msgs) == 2
        assert msgs[1]["content"] == "查询日志"
