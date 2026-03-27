"""工具模块公共配置状态管理

所有工具模块通过此模块获取 ServerConfig，避免各模块重复维护 _config 全局变量。
配置在 server.py 启动时通过 set_config() 注入。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cls_mcp_server.config import ServerConfig

_lock = threading.Lock()
_config: ServerConfig | None = None


def set_config(config: ServerConfig) -> None:
    """设置全局配置（由 server.py 调用，仅在启动时执行一次）"""
    global _config
    with _lock:
        _config = config


def get_config() -> ServerConfig:
    """获取全局配置，未初始化时抛出明确异常"""
    with _lock:
        if _config is None:
            raise RuntimeError(
                "ServerConfig not initialized. "
                "Ensure server.py calls set_config() before any tool is invoked."
            )
        return _config
