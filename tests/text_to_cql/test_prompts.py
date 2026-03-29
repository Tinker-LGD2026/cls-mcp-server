"""prompts 模块回归测试

覆盖：
1. 占位符替换完整性
2. 新增的时区/引号/类型规则格式正确
3. 模板内容一致性
"""

from __future__ import annotations

import pytest

from cls_mcp_server.tools.text_to_cql.prompts import (
    SYSTEM_PROMPT_TEMPLATE,
    USER_PROMPT_TEMPLATE,
    USER_PROMPT_WITH_INDEX_TEMPLATE,
    RETRY_PROMPT_TEMPLATE,
    RETRY_PROMPT_WITH_INDEX_TEMPLATE,
    build_system_prompt,
    build_user_prompt,
    build_retry_user_prompt,
)


class TestSystemPromptTemplate:
    """System Prompt 模板内容验证"""

    def test_has_syntax_docs_placeholder(self):
        """模板包含 {syntax_docs} 占位符"""
        assert "{syntax_docs}" in SYSTEM_PROMPT_TEMPLATE

    def test_no_other_unresolved_placeholders(self):
        """模板中除 {syntax_docs} 外不应有其他占位符"""
        # 替换已知占位符后检查
        resolved = SYSTEM_PROMPT_TEMPLATE.replace("{syntax_docs}", "DOCS")
        # 检查没有残留的 {xxx} 模式（排除 SQL 代码中的花括号）
        import re
        remaining = re.findall(r"\{[a-z_]+\}", resolved)
        assert not remaining, f"发现未解析的占位符: {remaining}"

    def test_has_timezone_rules(self):
        """System Prompt 包含时区规则"""
        assert "时区" in SYSTEM_PROMPT_TEMPLATE
        assert "UTC+8" in SYSTEM_PROMPT_TEMPLATE
        assert "UTC+0" in SYSTEM_PROMPT_TEMPLATE

    def test_has_quote_rules(self):
        """System Prompt 包含引号规则"""
        assert "单引号" in SYSTEM_PROMPT_TEMPLATE
        assert "双引号" in SYSTEM_PROMPT_TEMPLATE

    def test_has_type_rules(self):
        """System Prompt 包含类型注意事项"""
        assert "bigint" in SYSTEM_PROMPT_TEMPLATE
        assert "毫秒" in SYSTEM_PROMPT_TEMPLATE
        assert "from_unixtime" in SYSTEM_PROMPT_TEMPLATE

    def test_has_time_series_limitations(self):
        """System Prompt 包含 time_series 限制说明"""
        assert "GROUP BY" in SYSTEM_PROMPT_TEMPLATE
        assert "ORDER BY" in SYSTEM_PROMPT_TEMPLATE
        assert "DESC" in SYSTEM_PROMPT_TEMPLATE
        assert "%i" in SYSTEM_PROMPT_TEMPLATE

    def test_has_pipe_syntax(self):
        """System Prompt 包含管道符语法说明"""
        assert "|" in SYSTEM_PROMPT_TEMPLATE
        assert "管道符" in SYSTEM_PROMPT_TEMPLATE

    def test_has_no_from_clause_rule(self):
        """System Prompt 提到不需要 FROM 子句"""
        assert "FROM" in SYSTEM_PROMPT_TEMPLATE

    def test_has_output_format_section(self):
        """System Prompt 包含输出格式说明"""
        assert "输出格式" in SYSTEM_PROMPT_TEMPLATE or "输出" in SYSTEM_PROMPT_TEMPLATE

    def test_has_histogram_long_example(self):
        """System Prompt 包含 histogram LONG 型示例"""
        assert "histogram(__TIMESTAMP__" in SYSTEM_PROMPT_TEMPLATE

    def test_has_histogram_cast_example(self):
        """System Prompt 包含 histogram CAST 型示例"""
        assert "histogram(cast(__TIMESTAMP__" in SYSTEM_PROMPT_TEMPLATE

    def test_has_compare_example(self):
        """System Prompt 包含 compare 示例"""
        assert "compare(" in SYSTEM_PROMPT_TEMPLATE

    def test_has_beijing_time_example(self):
        """System Prompt 包含北京时间转换示例"""
        assert "Asia/Shanghai" in SYSTEM_PROMPT_TEMPLATE


class TestBuildSystemPrompt:
    """build_system_prompt 函数"""

    def test_substitutes_syntax_docs(self):
        """正确替换 {syntax_docs} 占位符"""
        test_docs = "## test section\ntest content here"
        result = build_system_prompt(test_docs)
        assert "test section" in result
        assert "test content here" in result
        assert "{syntax_docs}" not in result

    def test_preserves_other_content(self):
        """替换后保留其他模板内容"""
        result = build_system_prompt("test docs")
        assert "CQL" in result
        assert "时区" in result

    def test_empty_docs(self):
        """空文档也能正常替换"""
        result = build_system_prompt("")
        assert "{syntax_docs}" not in result
        assert "CQL" in result


class TestBuildUserPrompt:
    """build_user_prompt 函数"""

    def test_without_index(self):
        """无索引信息时只返回查询内容"""
        result = build_user_prompt("统计错误日志")
        assert result == "统计错误日志"

    def test_with_index(self):
        """有索引信息时包含索引和查询"""
        index = "可用字段：\n  - level (keyword)"
        result = build_user_prompt("统计错误日志", index)
        assert "统计错误日志" in result
        assert "level" in result
        assert "索引" in result

    def test_no_residual_placeholders(self):
        """替换后无残留占位符"""
        result = build_user_prompt("test query", "test index")
        assert "{query}" not in result
        assert "{index_info}" not in result


class TestBuildRetryUserPrompt:
    """build_retry_user_prompt 函数"""

    def test_without_index(self):
        """无索引信息的重试 Prompt"""
        result = build_retry_user_prompt(
            query="统计错误",
            error_feedback="FROM 子句不合法",
        )
        assert "统计错误" in result
        assert "FROM 子句不合法" in result
        assert "索引" not in result

    def test_with_index(self):
        """有索引信息的重试 Prompt"""
        result = build_retry_user_prompt(
            query="统计错误",
            error_feedback="FROM 子句不合法",
            index_info="可用字段：\n  - status (long)",
        )
        assert "统计错误" in result
        assert "FROM 子句不合法" in result
        assert "status" in result
        assert "索引字段" in result

    def test_no_residual_placeholders(self):
        """替换后无残留占位符"""
        result = build_retry_user_prompt("q", "err", "idx")
        assert "{query}" not in result
        assert "{error_feedback}" not in result
        assert "{index_info}" not in result


class TestTemplateConsistency:
    """模板内部一致性"""

    def test_user_template_has_query_placeholder(self):
        assert "{query}" in USER_PROMPT_TEMPLATE

    def test_user_with_index_has_both_placeholders(self):
        assert "{query}" in USER_PROMPT_WITH_INDEX_TEMPLATE
        assert "{index_info}" in USER_PROMPT_WITH_INDEX_TEMPLATE

    def test_retry_template_has_required_placeholders(self):
        assert "{query}" in RETRY_PROMPT_TEMPLATE
        assert "{error_feedback}" in RETRY_PROMPT_TEMPLATE

    def test_retry_with_index_has_all_placeholders(self):
        assert "{query}" in RETRY_PROMPT_WITH_INDEX_TEMPLATE
        assert "{error_feedback}" in RETRY_PROMPT_WITH_INDEX_TEMPLATE
        assert "{index_info}" in RETRY_PROMPT_WITH_INDEX_TEMPLATE
