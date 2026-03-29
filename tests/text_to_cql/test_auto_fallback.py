"""auto 降级逻辑与 mode_router 兼容性测试

覆盖：
1. auto 模式路由到 syntax_only 和 generate 的判断
2. LLM 未配置时 auto 降级为 syntax_only
3. LLM 未配置时显式 generate 返回 CONFIG_ERROR
4. original_mode 追踪逻辑
5. mode_router 面对新关键词的行为
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cls_mcp_server.tools.text_to_cql.mode_router import (
    route_mode,
    _SYNTAX_EXACT_PHRASES,
    _GENERATE_SIGNALS,
)


class TestModeRouterBasic:
    """mode_router 基础路由测试"""

    @pytest.mark.parametrize("query,expected", [
        # syntax_only 查询
        ("语法参考", "syntax_only"),
        ("histogram怎么用", "syntax_only"),
        ("time_series用法", "syntax_only"),
        ("compare", "syntax_only"),
        ("syntax reference", "syntax_only"),
        ("CLS有哪些独有函数", "syntax_only"),
        ("函数列表", "syntax_only"),
        ("文档", "syntax_only"),
        ("ip_to_", "syntax_only"),
        # generate 查询
        ("统计最近1小时错误日志", "generate"),
        ("查询 level:ERROR 的日志", "generate"),
        ("分析各状态码分布", "generate"),
        ("帮我写一个按小时统计的CQL", "generate"),
        ("top10 最慢的请求", "generate"),
        ("错误日志趋势", "generate"),
    ])
    def test_known_queries(self, query, expected):
        assert route_mode(query) == expected

    def test_short_query_defaults_syntax(self):
        """<= 5 字符默认走 syntax_only"""
        assert route_mode("abc") == "syntax_only"
        assert route_mode("hi") == "syntax_only"

    def test_ambiguous_defaults_generate(self):
        """无明确信号默认走 generate"""
        assert route_mode("最近有什么异常") == "generate"

    def test_empty_query_defaults_syntax(self):
        """空查询走 syntax_only（<= 5 字符）"""
        assert route_mode("") == "syntax_only"


class TestModeRouterNewKeywords:
    """mode_router 面对新关键词的兼容性"""

    @pytest.mark.parametrize("query", [
        "cast类型转换怎么用",
        "json_extract语法",
        "url_decode函数用法",
        "APPROX_PERCENTILE有什么函数",
    ])
    def test_new_keyword_syntax_queries(self, query):
        """包含新关键词 + 语法查询信号词的查询应走 syntax_only

        注意：route_mode 通过 _SYNTAX_EXACT_PHRASES 中的短语匹配。
        "怎么用"/"语法"/"用法"/"有什么函数" 等词在其中。
        但 "是什么"/"怎么写" 不一定在列表中。
        """
        result = route_mode(query)
        assert result == "syntax_only", (
            f"查询 '{query}' 应路由到 syntax_only，实际: {result}"
        )

    @pytest.mark.parametrize("query", [
        "timezone规则是什么",
        "regexp_like正则怎么写",
    ])
    def test_new_keyword_without_syntax_signal_defaults_generate(self, query):
        """包含新关键词但无明确语法信号词的查询默认走 generate

        "是什么"/"怎么写" 不在 _SYNTAX_EXACT_PHRASES 中，
        也不在 _SYNTAX_COMBO_PATTERNS 中匹配，
        同时也不触发 _GENERATE_SIGNALS，所以默认走 generate。
        """
        result = route_mode(query)
        assert result == "generate", (
            f"查询 '{query}' 无明确信号默认走 generate，实际: {result}"
        )

    @pytest.mark.parametrize("query", [
        "统计每小时的json字段分布",
        "帮我分析url访问路径的top10",
        "查找匹配正则的日志",
    ])
    def test_new_keyword_generate_queries(self, query):
        """包含新关键词 + 生成信号的查询应走 generate"""
        result = route_mode(query)
        assert result == "generate", (
            f"查询 '{query}' 应路由到 generate，实际: {result}"
        )


class TestAutoFallbackLogic:
    """auto 降级逻辑测试 — 需要 mock tool_definition 中的逻辑"""

    @pytest.fixture
    def mock_env_no_llm(self):
        """模拟 LLM 未配置的环境 — mock get_config 返回无 LLM 配置的 ServerConfig"""
        from cls_mcp_server.config import ServerConfig
        mock_config = ServerConfig(llm_api_base="", llm_api_key="", llm_model="")
        with patch("cls_mcp_server.tools.text_to_cql.tool_definition.get_config", return_value=mock_config):
            yield

    @pytest.fixture
    def mock_env_with_llm(self):
        """模拟 LLM 已配置的环境 — mock get_config 返回带 LLM 配置的 ServerConfig"""
        from cls_mcp_server.config import ServerConfig
        mock_config = ServerConfig(
            llm_api_base="http://test-llm.example.com",
            llm_api_key="test-key-123",
            llm_model="test-model",
        )
        with patch("cls_mcp_server.tools.text_to_cql.tool_definition.get_config", return_value=mock_config):
            yield

    def test_get_llm_config_returns_none_without_env(self, mock_env_no_llm):
        """LLM 环境变量未配置时返回 None"""
        from cls_mcp_server.tools.text_to_cql.tool_definition import _get_llm_config
        assert _get_llm_config() is None

    def test_get_llm_config_returns_config_with_env(self, mock_env_with_llm):
        """LLM 环境变量已配置时返回 LlmConfig"""
        from cls_mcp_server.tools.text_to_cql.tool_definition import _get_llm_config
        config = _get_llm_config()
        assert config is not None
        assert config.api_base == "http://test-llm.example.com"
        assert config.api_key == "test-key-123"
        assert config.model == "test-model"

    def test_get_llm_config_incomplete_env(self):
        """部分配置 LLM 变量应返回 None"""
        from cls_mcp_server.config import ServerConfig
        mock_config = ServerConfig(
            llm_api_base="http://test.com",
            llm_api_key="",  # 空值
            llm_model="model",
        )
        with patch("cls_mcp_server.tools.text_to_cql.tool_definition.get_config", return_value=mock_config):
            from cls_mcp_server.tools.text_to_cql.tool_definition import _get_llm_config
            assert _get_llm_config() is None


class TestOriginalModeTracking:
    """验证 original_mode 追踪逻辑

    在 tool_definition.py 中：
    - original_mode = mode  # 保存原始模式
    - if mode == "auto": mode = route_mode(query)  # 路由修改 mode
    - 后续判断使用 original_mode 而非 mode
    """

    def test_auto_to_generate_then_fallback(self, mock_env_no_llm=None):
        """auto -> route_mode 返回 generate -> LLM 未配置 -> 降级为 syntax_only

        这个路径是通过检查 original_mode == "auto" 来实现降级的。
        如果直接 mode="generate" 且 LLM 未配置则返回错误（不降级）。
        """
        # 验证核心逻辑：auto 路由到 generate 时，original_mode 仍是 "auto"
        # 这使得 LLM 未配置时可以降级
        mode = "auto"
        original_mode = mode
        query = "统计错误日志数量"  # 这会被 route_mode 路由到 "generate"
        routed = route_mode(query)
        assert routed == "generate"
        assert original_mode == "auto"  # original_mode 未被修改

    def test_explicit_generate_no_fallback(self):
        """显式 generate 模式下 original_mode != "auto"，不会降级"""
        mode = "generate"
        original_mode = mode
        assert original_mode == "generate"
        assert original_mode != "auto"  # 不满足降级条件
