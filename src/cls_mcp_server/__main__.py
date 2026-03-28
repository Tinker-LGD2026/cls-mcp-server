"""CLS MCP Server 入口模块

支持通过命令行参数或环境变量配置启动方式。
"""

from __future__ import annotations

import argparse
import logging
import sys

from cls_mcp_server.config import ServerConfig
from cls_mcp_server.server import run_server


def setup_logging(level: str) -> None:
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,  # MCP stdio 模式下，日志必须输出到 stderr
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        prog="cls-mcp-server",
        description="腾讯云 CLS 日志服务 MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="传输方式: stdio | sse | streamable-http，覆盖环境变量 CLS_TRANSPORT",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP 监听端口（SSE/Streamable HTTP 模式），覆盖环境变量 CLS_PORT",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="HTTP 监听地址（SSE/Streamable HTTP 模式），覆盖环境变量 CLS_HOST",
    )
    parser.add_argument(
        "--enable-write",
        action="store_true",
        default=None,
        help="启用写操作工具",
    )
    parser.add_argument(
        "--enable-dangerous",
        action="store_true",
        default=None,
        help="启用高危操作工具（需同时启用写操作）",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="日志级别",
    )
    parser.add_argument(
        "--auth-token",
        default=None,
        help="HTTP Bearer Token 认证令牌（SSE/Streamable HTTP 模式），覆盖环境变量 MCP_AUTH_TOKEN",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=None,
        help="SDK 请求超时时间（秒），覆盖环境变量 CLS_REQUEST_TIMEOUT，默认 60",
    )
    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=None,
        help="最大重试次数（含首次），覆盖环境变量 CLS_RETRY_MAX_ATTEMPTS，默认 3",
    )
    parser.add_argument(
        "--enabled-tools",
        default=None,
        help="工具白名单（逗号分隔），覆盖环境变量 CLS_ENABLED_TOOLS，未设置则注册全部",
    )
    return parser.parse_args()


def main() -> None:
    """主入口"""
    args = parse_args()

    # 从环境变量加载基础配置
    config = ServerConfig.from_env()

    # 命令行参数覆盖
    overrides: dict = {}
    if args.transport is not None:
        overrides["transport"] = args.transport
    if args.port is not None:
        overrides["port"] = args.port
    if args.host is not None:
        overrides["host"] = args.host
    if args.enable_write is True:
        overrides["enable_write"] = True
    if args.enable_dangerous is True:
        overrides["enable_dangerous"] = True
    if args.log_level is not None:
        overrides["log_level"] = args.log_level
    if args.auth_token is not None:
        overrides["auth_token"] = args.auth_token
    if args.request_timeout is not None:
        overrides["request_timeout"] = args.request_timeout
    if args.retry_max_attempts is not None:
        overrides["retry_max_attempts"] = args.retry_max_attempts
    if args.enabled_tools is not None:
        overrides["enabled_tools"] = frozenset(
            t.strip() for t in args.enabled_tools.split(",") if t.strip()
        )

    if overrides:
        # frozen dataclass，需要重建
        config_dict = {
            "secret_id": config.secret_id,
            "secret_key": config.secret_key,
            "region": config.region,
            "transport": config.transport,
            "host": config.host,
            "port": config.port,
            "stateless_http": config.stateless_http,
            "enable_write": config.enable_write,
            "enable_dangerous": config.enable_dangerous,
            "auth_token": config.auth_token,
            "log_level": config.log_level,
            "request_timeout": config.request_timeout,
            "retry_max_attempts": config.retry_max_attempts,
            "retry_base_delay": config.retry_base_delay,
            "cb_failure_threshold": config.cb_failure_threshold,
            "cb_recovery_timeout": config.cb_recovery_timeout,
            "enabled_tools": config.enabled_tools,
        }
        config_dict.update(overrides)
        config = ServerConfig(**config_dict)

    # 设置日志
    setup_logging(config.log_level)

    # 校验配置
    errors = config.validate()
    if errors:
        for err in errors:
            logging.error("Configuration error: %s", err)
        sys.exit(1)

    # 打印配置摘要
    config.print_summary()

    # 启动
    run_server(config)


if __name__ == "__main__":
    main()
