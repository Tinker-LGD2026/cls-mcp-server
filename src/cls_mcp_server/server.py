"""MCP Server 实例创建与启动

负责创建 FastMCP 实例、注册工具、启动 SSE / Streamable HTTP / stdio 传输。
"""

from __future__ import annotations

import logging

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from cls_mcp_server.config import ServerConfig
from cls_mcp_server.middleware import BearerTokenAuthMiddleware
from cls_mcp_server.tools.registry import register_all_tools

logger = logging.getLogger(__name__)

# 服务版本号，健康检查和运维使用
SERVER_VERSION = "0.1.0"


def _inject_config(config: ServerConfig) -> None:
    """将配置注入到公共状态模块，所有工具模块共享"""
    from cls_mcp_server.tools._state import set_config

    set_config(config)


def _check_credentials(config: ServerConfig) -> bool:
    """检查密钥配置是否完整"""
    return bool(config.secret_id and config.secret_key)


def _register_health_routes(mcp: FastMCP, config: ServerConfig) -> None:
    """注册健康检查端点

    /health  - 存活检查 (liveness)，进程运行即返回 200
    /readiness - 就绪检查 (readiness)，检查配置和密钥完整性
    """

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "version": SERVER_VERSION,
            "transport": config.transport,
        })

    @mcp.custom_route("/readiness", methods=["GET"])
    async def readiness_check(request: Request) -> JSONResponse:
        checks = {
            "config_valid": len(config.validate()) == 0,
            "credentials": _check_credentials(config),
            "region": config.region,
        }
        all_ready = all([checks["config_valid"], checks["credentials"]])
        return JSONResponse(
            {
                "status": "ready" if all_ready else "not_ready",
                "checks": checks,
            },
            status_code=200 if all_ready else 503,
        )


def create_server(config: ServerConfig) -> FastMCP:
    """创建并配置 MCP Server 实例

    Args:
        config: 服务器配置

    Returns:
        配置完成的 FastMCP 实例
    """
    kwargs: dict = {
        "name": "cls-mcp-server",
        "instructions": (
            "腾讯云 CLS（Cloud Log Service）日志服务 MCP Server。"
            "提供日志查询分析、指标查询、告警管理、资源管理等可观测性能力。"
            "所有工具以 cls_ 前缀命名。"
            "日志查询类工具的时间参数使用毫秒级 Unix 时间戳；"
            "指标查询类工具（cls_query_metric、cls_query_range_metric）的时间参数使用秒级 Unix 时间戳。"
            "重要：需要传入时间戳时，请先调用 cls_convert_time 工具将人类可读时间转换为精确时间戳，"
            "不要手动计算时间戳，以避免计算错误。"
        ),
        "host": config.host,
        "port": config.port,
    }

    # Streamable HTTP 模式下启用无状态 HTTP
    if config.transport == "streamable-http":
        kwargs["stateless_http"] = config.stateless_http

    mcp = FastMCP(**kwargs)

    # 注册健康检查端点（仅 HTTP 传输模式）
    if config.transport in ("sse", "streamable-http"):
        _register_health_routes(mcp, config)

    # 将 config 注入到所有工具模块
    _inject_config(config)

    # 注册工具
    registered = register_all_tools(mcp, config)
    logger.info("Server initialized with %d tools", len(registered))

    return mcp


def run_server(config: ServerConfig) -> None:
    """启动 MCP Server

    Args:
        config: 服务器配置
    """
    mcp = create_server(config)

    if config.transport == "stdio":
        logger.info("Starting stdio transport")
        mcp.run(transport="stdio")
    elif config.transport in ("sse", "streamable-http"):
        # HTTP 模式：手动获取 Starlette app，以便挂载认证中间件
        if config.transport == "sse":
            logger.info("Starting SSE transport on %s:%d", config.host, config.port)
            starlette_app = mcp.sse_app()
        else:
            logger.info(
                "Starting Streamable HTTP transport on %s:%d (stateless=%s)",
                config.host, config.port, config.stateless_http,
            )
            starlette_app = mcp.streamable_http_app()

        # 条件性挂载 Bearer Token 认证中间件
        if config.auth_token:
            starlette_app.add_middleware(
                BearerTokenAuthMiddleware,
                token=config.auth_token,
            )
            logger.info("Bearer Token authentication ENABLED")
        else:
            logger.warning(
                "No auth token configured (MCP_AUTH_TOKEN / --auth-token). "
                "HTTP endpoint is UNPROTECTED!"
            )

        # 使用 uvicorn 启动
        uv_config = uvicorn.Config(
            starlette_app,
            host=config.host,
            port=config.port,
            log_level=config.log_level.lower(),
        )
        server = uvicorn.Server(uv_config)
        anyio.run(server.serve)
