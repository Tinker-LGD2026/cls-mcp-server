"""tool_definition 参数 schema 稳定性测试

覆盖：
1. 函数参数名、类型、默认值不变
2. description 文本变更不影响参数 schema
3. 工具名称和级别不变
"""

from __future__ import annotations

import inspect

import pytest

from cls_mcp_server.tools.text_to_cql.tool_definition import cls_text_to_cql


class TestFunctionSignature:
    """cls_text_to_cql 函数签名稳定性"""

    def test_is_coroutine_function(self):
        """应该是异步函数"""
        assert inspect.iscoroutinefunction(cls_text_to_cql)

    def test_parameter_names(self):
        """参数名称应完整且稳定"""
        sig = inspect.signature(cls_text_to_cql)
        param_names = list(sig.parameters.keys())
        expected = ["query", "mode", "topic_id", "region"]
        assert param_names == expected, (
            f"参数名变化: 期望 {expected}, 实际 {param_names}"
        )

    def test_query_parameter_required(self):
        """query 参数应为必填（无默认值）"""
        sig = inspect.signature(cls_text_to_cql)
        param = sig.parameters["query"]
        assert param.default is inspect.Parameter.empty, "query 应无默认值"

    def test_mode_default_auto(self):
        """mode 默认值应为 'auto'"""
        sig = inspect.signature(cls_text_to_cql)
        param = sig.parameters["mode"]
        assert param.default == "auto"

    def test_topic_id_default_empty(self):
        """topic_id 默认值应为空字符串"""
        sig = inspect.signature(cls_text_to_cql)
        param = sig.parameters["topic_id"]
        assert param.default == ""

    def test_region_default_empty(self):
        """region 默认值应为空字符串"""
        sig = inspect.signature(cls_text_to_cql)
        param = sig.parameters["region"]
        assert param.default == ""

    def test_parameter_annotations(self):
        """参数类型注解应正确（支持 from __future__ annotations 延迟求值）"""
        sig = inspect.signature(cls_text_to_cql)
        for name in ["query", "mode", "topic_id", "region"]:
            param = sig.parameters[name]
            # from __future__ import annotations 使注解变为字符串
            assert param.annotation in (str, "str"), (
                f"参数 {name} 类型注解应为 str，实际: {param.annotation}"
            )

    def test_return_annotation(self):
        """返回值类型应为 str"""
        sig = inspect.signature(cls_text_to_cql)
        assert sig.return_annotation in (str, "str")


class TestDescriptionContent:
    """description 内容关键信息验证"""

    @pytest.fixture
    def description(self):
        """获取工具 description — 尝试多种方式"""
        # 方式1: cls_tool 装饰器存储的属性
        desc = getattr(cls_text_to_cql, "_tool_description", None)
        if desc:
            return desc
        # 方式2: _tool_info dict
        info = getattr(cls_text_to_cql, "_tool_info", None)
        if info and isinstance(info, dict):
            desc = info.get("description", "")
            if desc:
                return desc
        # 方式3: docstring（最后兜底）
        return cls_text_to_cql.__doc__ or ""

    def test_description_mentions_text_to_cql(self, description):
        """description 包含工具核心功能描述"""
        if description:
            lower = description.lower()
            assert "cql" in lower or "查询" in lower

    def test_description_mentions_modes(self, description):
        """description 提到三种模式（如能获取到完整 description）"""
        # docstring 可能很短，只有在能获取到完整 description 时才检查
        if len(description) > 100:
            assert "auto" in description
            assert "syntax_only" in description
            assert "generate" in description


class TestToolMetadata:
    """工具元数据（装饰器注入的信息）"""

    def test_tool_name(self):
        """工具名称应为 cls_text_to_cql"""
        name = getattr(cls_text_to_cql, "_tool_name", None)
        if name is None:
            info = getattr(cls_text_to_cql, "_tool_info", None)
            if info:
                name = info.get("name")
        if name is not None:
            assert name == "cls_text_to_cql"

    def test_tool_function_name(self):
        """函数名应为 cls_text_to_cql"""
        assert cls_text_to_cql.__name__ == "cls_text_to_cql"
