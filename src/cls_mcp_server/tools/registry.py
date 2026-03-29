"""Tool 注册器模块

根据权限配置动态注册 MCP Tool，实现三级权限控制：
- read:   只读操作（查询、列表），默认开启
- write:  写操作（创建、修改），需 CLS_ENABLE_WRITE=true
- danger: 高危操作（删除），需 CLS_ENABLE_DANGEROUS=true
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from cls_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)


class ToolLevel(str, Enum):
    """工具权限等级"""

    READ = "read"
    WRITE = "write"
    DANGER = "danger"


# 全局工具注册表：收集所有通过 @cls_tool 装饰的函数
_tool_definitions: list[dict[str, Any]] = []


def cls_tool(
    name: str,
    level: ToolLevel = ToolLevel.READ,
    description: str = "",
) -> Callable:
    """装饰器：声明一个 CLS MCP Tool 及其权限等级

    Args:
        name: 工具名称，建议使用 cls_ 前缀
        level: 权限等级
        description: 工具描述，给 LLM 看的
    """

    def decorator(func: Callable) -> Callable:
        # 为写操作在描述中追加警告
        desc = description
        if level == ToolLevel.WRITE:
            desc += "\n\n⚠️ 此为写操作，执行前请确认参数正确。"
        elif level == ToolLevel.DANGER:
            desc += "\n\n🚨 此为高危删除操作，不可逆！请务必在执行前向用户确认。"

        func._cls_tool_name = name
        func._cls_tool_level = level
        func._cls_tool_description = desc

        # 防止重复注册（虽然 Python import 机制保证模块只加载一次）
        if not any(t["name"] == name for t in _tool_definitions):
            _tool_definitions.append(
                {
                    "name": name,
                    "level": level,
                    "description": desc,
                    "func": func,
                }
            )
        return func

    return decorator


def should_register(level: ToolLevel, config: ServerConfig) -> bool:
    """判断指定权限等级的工具是否应该注册"""
    if level == ToolLevel.READ:
        return True
    if level == ToolLevel.WRITE:
        return config.enable_write
    if level == ToolLevel.DANGER:
        return config.enable_write and config.enable_dangerous
    return False


def register_all_tools(mcp: FastMCP, config: ServerConfig) -> list[str]:
    """将符合权限要求的工具注册到 MCP Server

    过滤逻辑（AND 关系）：
    1. 权限检查：READ 默认通过，WRITE/DANGER 需要配置开启
    2. 白名单检查：enabled_tools 非空时，工具名必须在白名单中

    Args:
        mcp: FastMCP server 实例
        config: 服务器配置

    Returns:
        已注册的工具名称列表
    """
    # 先导入所有工具模块，触发 @cls_tool 装饰器执行
    _import_tool_modules()

    # 校验白名单中是否有无效的工具名
    if config.enabled_tools:
        all_tool_names = {t["name"] for t in _tool_definitions}
        invalid_names = config.enabled_tools - all_tool_names
        if invalid_names:
            logger.warning(
                "⚠️  Unknown tool names in CLS_ENABLED_TOOLS (ignored): %s",
                ", ".join(sorted(invalid_names)),
            )

    registered: list[str] = []
    skipped: list[str] = []

    for tool_def in _tool_definitions:
        name = tool_def["name"]
        level = tool_def["level"]
        desc = tool_def["description"]
        func = tool_def["func"]

        # 条件 1：权限检查
        if not should_register(level, config):
            skipped.append(f"{name} [{level.value}] (permission)")
            continue

        # 条件 2：白名单检查（空白名单 = 全部通过）
        if config.enabled_tools and name not in config.enabled_tools:
            skipped.append(f"{name} [{level.value}] (whitelist)")
            continue

        # 注册到 FastMCP
        mcp.tool(name=name, description=desc)(func)
        registered.append(f"{name} [{level.value}]")

    logger.info("✅ Registered %d tools: %s", len(registered), ", ".join(registered))
    if skipped:
        logger.info("⏭️  Skipped %d tools: %s", len(skipped), ", ".join(skipped))

    return registered


def _import_tool_modules() -> None:
    """导入所有工具子模块，确保 @cls_tool 装饰器被执行"""
    import cls_mcp_server.tools.time_utils  # noqa: F401
    import cls_mcp_server.tools.search  # noqa: F401
    import cls_mcp_server.tools.metrics  # noqa: F401
    import cls_mcp_server.tools.alarm  # noqa: F401
    import cls_mcp_server.tools.resource  # noqa: F401
    import cls_mcp_server.tools.data_transform  # noqa: F401
    import cls_mcp_server.tools.scheduled_sql  # noqa: F401
    import cls_mcp_server.tools.text_to_cql.tool_definition  # noqa: F401
