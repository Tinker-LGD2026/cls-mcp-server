"""Text2CQL 工具模块

将自然语言转换为 CLS CQL 查询语句，支持语法查询和 LLM 生成两种模式。
"""

__all__ = [
    "CqlGenerator",
    "CqlResult",
    "LlmConfig",
    "call_llm",
    "close_shared_client",
    "LlmClientError",
    "validate_cql",
    "clean_cql",
    "ValidationResult",
    "route_mode",
    "get_syntax_docs",
]
