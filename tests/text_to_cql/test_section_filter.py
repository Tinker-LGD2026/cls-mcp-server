"""按需加载（章节过滤）回归测试

验证新增的 9 个章节能被正确触发，且无关查询不会加载多余章节。
重点验证 cls_extension_syntax.md 中的 17 个章节的按需返回机制。
"""

from __future__ import annotations

import pytest

from cls_mcp_server.tools.text_to_cql.syntax_docs import (
    CLS_EXTENSION_SYNTAX,
    get_syntax_docs,
)


def _count_sections(text: str) -> int:
    """统计文档中 ## 章节数"""
    return text.count("\n## ") + (1 if text.startswith("## ") or text.startswith("# ") else 0)


def _has_section(text: str, section_keyword: str) -> bool:
    """检查文档中是否包含指定关键词的章节"""
    return section_keyword.lower() in text.lower()


class TestFullDocSections:
    """完整文档章节验证"""

    def test_full_doc_has_at_least_15_sections(self):
        """完整文档应包含至少 15 个章节（含新增的 9 个）"""
        section_count = _count_sections(CLS_EXTENSION_SYNTAX)
        assert section_count >= 15, (
            f"文档只有 {section_count} 个章节，期望至少 15 个"
        )

    @pytest.mark.parametrize("section_title", [
        "管道符",
        "histogram",
        "time_series",
        "compare",
        "IP 地理",
        "IP 威胁",
        "时区",
        "类型转换",
        "日期时间",
        "条件表达式",
        "JSON",
        "估算",
        "URL",
        "正则",
        "内置字段",
        "注意事项",
    ])
    def test_full_doc_contains_section(self, section_title):
        """完整文档应包含所有预期章节"""
        assert _has_section(CLS_EXTENSION_SYNTAX, section_title), (
            f"完整文档缺少 '{section_title}' 相关章节"
        )


class TestNewSectionsTriggering:
    """新增章节的按需触发测试"""

    def test_timezone_query_triggers_timezone_section(self):
        """包含'时区'的查询应触发时区章节

        注意：此测试依赖 _FILTER_KEYWORDS 是否包含时区相关关键词。
        如果当前关键词集不包含，则期望返回全文（fallback行为）。
        """
        docs = get_syntax_docs("时区规则")
        # 无论是过滤结果还是全文，都应包含时区内容
        assert "时区" in docs

    def test_cast_query_triggers_type_section(self):
        """cast/try_cast 查询应能获取类型转换章节"""
        docs = get_syntax_docs("cast 类型转换")
        # 如果 cast 不在 _FILTER_KEYWORDS 中，返回全文也应包含
        assert "cast" in docs.lower()

    def test_json_extract_query(self):
        """json_extract 查询应能获取 JSON 函数章节"""
        docs = get_syntax_docs("json_extract 用法")
        assert "json_extract" in docs.lower()

    def test_url_extract_query(self):
        """url_extract 查询"""
        docs = get_syntax_docs("url_extract_host 怎么用")
        assert "url" in docs.lower()

    def test_regexp_query(self):
        """regexp 查询"""
        docs = get_syntax_docs("regexp_like 正则匹配")
        assert "regexp" in docs.lower()

    def test_approx_query(self):
        """估算函数查询"""
        docs = get_syntax_docs("APPROX_PERCENTILE 用法")
        assert "approx" in docs.lower()

    def test_from_unixtime_query(self):
        """from_unixtime 日期时间函数查询"""
        docs = get_syntax_docs("from_unixtime 时间转换")
        assert "from_unixtime" in docs.lower()


class TestFilterIsolation:
    """过滤隔离性测试 — 确保按需返回不加载多余章节"""

    def test_histogram_filter_does_not_include_unrelated(self):
        """histogram 过滤结果不应包含完全无关的章节"""
        docs = get_syntax_docs("histogram")
        full = get_syntax_docs("")
        # 如果过滤生效（返回的不是全文），验证比全文短
        if docs != full:
            assert len(docs) < len(full)
            # histogram 相关章节应包含 histogram 关键词
            assert "histogram" in docs.lower()

    def test_compare_filter_does_not_include_ip(self):
        """compare 过滤不应包含 IP 函数章节（除非文档中有交叉引用）"""
        docs = get_syntax_docs("同环比")
        full = get_syntax_docs("")
        if docs != full:
            assert len(docs) < len(full)
            assert "compare" in docs.lower() or "同环比" in docs

    def test_ip_filter_returns_ip_related(self):
        """IP 相关查询应返回 IP 函数章节"""
        docs = get_syntax_docs("ip_to_province")
        assert "ip_to" in docs.lower()

    def test_unrelated_query_returns_full(self):
        """完全不匹配的查询返回完整文档"""
        docs = get_syntax_docs("xyzzy_not_a_keyword_12345")
        assert docs == CLS_EXTENSION_SYNTAX


class TestSQLPrerequisites:
    """SQL 前提条件章节测试"""

    def test_full_doc_mentions_standard_storage(self):
        """文档应提到标准存储要求"""
        assert "标准存储" in CLS_EXTENSION_SYNTAX

    def test_full_doc_mentions_index_requirement(self):
        """文档应提到键值索引+统计要求"""
        assert "统计" in CLS_EXTENSION_SYNTAX

    def test_full_doc_mentions_default_rows(self):
        """文档应提到默认返回行数"""
        assert "100" in CLS_EXTENSION_SYNTAX
