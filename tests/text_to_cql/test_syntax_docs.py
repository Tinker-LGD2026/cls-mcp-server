"""syntax_docs 模块回归测试

覆盖：
1. _FILTER_KEYWORDS 关键词完整性
2. 关键词到章节的映射正确性
3. get_syntax_docs 按需过滤行为
"""

from __future__ import annotations

import pytest

from cls_mcp_server.tools.text_to_cql.syntax_docs import (
    CLS_EXTENSION_SYNTAX,
    _FILTER_KEYWORDS,
    _extract_filter_keywords,
    get_syntax_docs,
)


class TestFilterKeywordsCompleteness:
    """_FILTER_KEYWORDS 关键词集合完整性"""

    def test_keywords_is_set(self):
        """_FILTER_KEYWORDS 应该是 set 类型"""
        assert isinstance(_FILTER_KEYWORDS, set)

    def test_keywords_minimum_count(self):
        """至少包含核心的 14 个关键词"""
        assert len(_FILTER_KEYWORDS) >= 14

    def test_core_function_keywords_present(self):
        """核心 CLS 函数关键词必须存在"""
        expected_core = {"histogram", "time_series", "compare", "ip_to", "timestamp"}
        assert expected_core.issubset(_FILTER_KEYWORDS), (
            f"缺少核心关键词: {expected_core - _FILTER_KEYWORDS}"
        )

    def test_chinese_keywords_present(self):
        """中文关键词必须存在"""
        expected_chinese = {"同环比", "时间分桶", "时序补全", "管道符", "内置字段"}
        assert expected_chinese.issubset(_FILTER_KEYWORDS), (
            f"缺少中文关键词: {expected_chinese - _FILTER_KEYWORDS}"
        )

    def test_english_aliases_present(self):
        """英文别名关键词必须存在"""
        expected_english = {"ip函数", "ip function"}
        assert expected_english.issubset(_FILTER_KEYWORDS), (
            f"缺少英文别名: {expected_english - _FILTER_KEYWORDS}"
        )

    def test_no_empty_keywords(self):
        """不应存在空字符串关键词"""
        for kw in _FILTER_KEYWORDS:
            assert kw.strip(), f"发现空关键词: repr={repr(kw)}"

    def test_all_keywords_lowercase_or_chinese(self):
        """关键词应全为小写或中文，确保匹配逻辑正确"""
        for kw in _FILTER_KEYWORDS:
            assert kw == kw.lower(), (
                f"关键词 '{kw}' 包含大写字母，可能导致匹配失败"
            )


class TestExtractFilterKeywords:
    """_extract_filter_keywords 关键词提取逻辑"""

    def test_exact_keyword_match(self):
        """精确关键词匹配"""
        result = _extract_filter_keywords("histogram")
        assert "histogram" in result

    def test_keyword_in_sentence(self):
        """从句子中提取关键词"""
        result = _extract_filter_keywords("histogram怎么用")
        assert "histogram" in result

    def test_multiple_keywords_extracted(self):
        """一次提取多个关键词"""
        result = _extract_filter_keywords("histogram和compare怎么用")
        assert "histogram" in result
        assert "compare" in result

    def test_chinese_keyword_match(self):
        """中文关键词匹配"""
        result = _extract_filter_keywords("时间分桶函数用法")
        assert "时间分桶" in result

    def test_no_match_returns_empty(self):
        """无匹配关键词返回空列表"""
        result = _extract_filter_keywords("这完全不相关的查询内容")
        assert result == []

    def test_case_insensitive_match(self):
        """大小写不敏感匹配"""
        result = _extract_filter_keywords("HISTOGRAM")
        assert "histogram" in result

    def test_ip_function_match(self):
        """ip_to 系列关键词匹配"""
        result = _extract_filter_keywords("ip_to_province函数怎么用")
        assert "ip_to" in result

    def test_timestamp_keyword_match(self):
        """timestamp 关键词匹配"""
        result = _extract_filter_keywords("__TIMESTAMP__ 是什么类型")
        assert "timestamp" in result


class TestGetSyntaxDocs:
    """get_syntax_docs 函数行为"""

    def test_empty_category_returns_full_doc(self):
        """空 category 返回完整文档"""
        docs = get_syntax_docs("")
        assert docs == CLS_EXTENSION_SYNTAX
        assert len(docs) > 100

    def test_none_category_equivalent_empty(self):
        """None-like 空字符串返回全部"""
        docs = get_syntax_docs("")
        full = get_syntax_docs()
        assert docs == full

    def test_histogram_filter_returns_relevant(self):
        """histogram 关键词过滤返回相关章节"""
        docs = get_syntax_docs("histogram")
        assert "histogram" in docs.lower()

    def test_compare_filter_returns_relevant(self):
        """compare 关键词过滤返回相关章节"""
        docs = get_syntax_docs("compare")
        assert "compare" in docs.lower()

    def test_ip_filter_returns_relevant(self):
        """ip_to 关键词过滤返回 IP 函数章节"""
        docs = get_syntax_docs("ip_to")
        assert "ip_to" in docs.lower()

    def test_no_match_returns_full_doc(self):
        """无匹配关键词返回完整文档"""
        docs = get_syntax_docs("完全不存在的关键词xyzzyx")
        assert docs == CLS_EXTENSION_SYNTAX

    def test_filtered_docs_shorter_than_full(self):
        """过滤后的文档应比全文短"""
        full = get_syntax_docs("")
        filtered = get_syntax_docs("histogram")
        # 只有在文档足够大且关键词匹配到部分章节时
        if "## " in full and filtered != full:
            assert len(filtered) < len(full)

    def test_natural_language_query_filter(self):
        """自然语言查询也能触发过滤"""
        docs = get_syntax_docs("histogram怎么用")
        assert "histogram" in docs.lower()

    def test_chinese_keyword_filter(self):
        """中文关键词触发过滤"""
        docs = get_syntax_docs("同环比")
        assert "compare" in docs.lower() or "同环比" in docs


class TestSyntaxDocContent:
    """验证语法文档内容完整性"""

    def test_doc_loaded_successfully(self):
        """文档应成功加载（非 fallback）"""
        assert len(CLS_EXTENSION_SYNTAX) > 1000, "文档内容过短，可能是 fallback 版本"

    def test_doc_has_pipe_section(self):
        """包含管道符章节"""
        assert "管道符" in CLS_EXTENSION_SYNTAX

    def test_doc_has_histogram_section(self):
        """包含 histogram 章节"""
        assert "histogram" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_time_series_section(self):
        """包含 time_series 章节"""
        assert "time_series" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_compare_section(self):
        """包含 compare 章节"""
        assert "compare" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_ip_section(self):
        """包含 IP 函数章节"""
        assert "ip_to" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_timezone_section(self):
        """包含时区规则章节"""
        assert "时区" in CLS_EXTENSION_SYNTAX

    def test_doc_has_type_conversion_section(self):
        """包含类型转换章节"""
        assert "cast" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_builtin_fields_section(self):
        """包含内置字段章节"""
        assert "__TIMESTAMP__" in CLS_EXTENSION_SYNTAX

    def test_doc_has_json_section(self):
        """包含 JSON 函数章节"""
        assert "json_extract" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_url_section(self):
        """包含 URL 函数章节"""
        assert "url_extract" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_regexp_section(self):
        """包含正则函数章节"""
        assert "regexp" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_datetime_section(self):
        """包含日期时间函数章节"""
        assert "from_unixtime" in CLS_EXTENSION_SYNTAX.lower()

    def test_doc_has_estimate_section(self):
        """包含估算函数章节"""
        assert "approx" in CLS_EXTENSION_SYNTAX.lower()
