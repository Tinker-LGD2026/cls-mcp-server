"""配置管理模块

从环境变量读取服务器配置，支持 .env 文件。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# 支持的传输方式
TransportType = Literal["stdio", "sse", "streamable-http"]


@dataclass(frozen=True)
class ServerConfig:
    """CLS MCP Server 全局配置"""

    # 腾讯云认证
    secret_id: str = ""
    secret_key: str = ""
    region: str = "ap-guangzhou"

    # 传输方式
    transport: TransportType = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000

    # Streamable HTTP 无状态模式（推荐 K8s 部署时开启）
    stateless_http: bool = True

    # 权限控制
    enable_write: bool = False
    enable_dangerous: bool = False

    # HTTP 认证
    auth_token: str | None = None

    # 日志
    log_level: str = "INFO"

    # SDK 请求超时（秒），部分大模型相关接口较慢，建议适当调大
    request_timeout: int = 60

    # 重试配置
    retry_max_attempts: int = 3       # 最大尝试次数（含首次调用）
    retry_base_delay: float = 1.0     # 基础退避延迟（秒）

    # 熔断器配置
    cb_failure_threshold: int = 5     # 连续失败多少次后触发熔断
    cb_recovery_timeout: int = 30     # 熔断后多少秒进入半开状态尝试恢复

    # 工具白名单（为空则注册全部工具）
    enabled_tools: frozenset[str] = field(default_factory=frozenset)

    # === 向后兼容属性 ===
    @property
    def sse_host(self) -> str:
        """向后兼容旧配置名"""
        return self.host

    @property
    def sse_port(self) -> int:
        """向后兼容旧配置名"""
        return self.port

    @classmethod
    def from_env(cls) -> ServerConfig:
        """从环境变量加载配置

        向后兼容：CLS_SSE_HOST/CLS_SSE_PORT 作为 CLS_HOST/CLS_PORT 的回退
        """
        host = os.getenv("CLS_HOST") or os.getenv("CLS_SSE_HOST", "0.0.0.0")
        port_str = os.getenv("CLS_PORT") or os.getenv("CLS_SSE_PORT", "8000")

        # 解析工具白名单
        enabled_tools_raw = os.getenv("CLS_ENABLED_TOOLS", "").strip()
        enabled_tools = (
            frozenset(t.strip() for t in enabled_tools_raw.split(",") if t.strip())
            if enabled_tools_raw
            else frozenset()
        )

        return cls(
            secret_id=os.getenv("CLS_SECRET_ID", ""),
            secret_key=os.getenv("CLS_SECRET_KEY", ""),
            region=os.getenv("CLS_REGION", "ap-guangzhou"),
            transport=os.getenv("CLS_TRANSPORT", "stdio"),  # type: ignore[arg-type]
            host=host,
            port=cls._safe_int(port_str, 8000),
            stateless_http=os.getenv("CLS_STATELESS_HTTP", "true").lower() == "true",
            enable_write=os.getenv("CLS_ENABLE_WRITE", "false").lower() == "true",
            enable_dangerous=os.getenv("CLS_ENABLE_DANGEROUS", "false").lower() == "true",
            auth_token=os.getenv("MCP_AUTH_TOKEN") or None,
            log_level=os.getenv("CLS_LOG_LEVEL", "INFO"),
            request_timeout=cls._safe_int(os.getenv("CLS_REQUEST_TIMEOUT", "60"), 60),
            retry_max_attempts=cls._safe_int(os.getenv("CLS_RETRY_MAX_ATTEMPTS", "3"), 3),
            retry_base_delay=cls._safe_float(os.getenv("CLS_RETRY_BASE_DELAY", "1.0"), 1.0),
            cb_failure_threshold=cls._safe_int(os.getenv("CLS_CB_FAILURE_THRESHOLD", "5"), 5),
            cb_recovery_timeout=cls._safe_int(os.getenv("CLS_CB_RECOVERY_TIMEOUT", "30"), 30),
            enabled_tools=enabled_tools,
        )

    @staticmethod
    def _safe_int(value: str, default: int) -> int:
        """安全的整数转换，失败时返回默认值"""
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning("Invalid integer value '%s', using default %d", value, default)
            return default

    @staticmethod
    def _safe_float(value: str, default: float) -> float:
        """安全的浮点数转换，失败时返回默认值"""
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning("Invalid float value '%s', using default %s", value, default)
            return default

    def validate(self) -> list[str]:
        """校验配置，返回错误列表"""
        errors: list[str] = []
        if not self.secret_id:
            errors.append("CLS_SECRET_ID is required")
        if not self.secret_key:
            errors.append("CLS_SECRET_KEY is required")
        if self.transport not in ("stdio", "sse", "streamable-http"):
            errors.append(
                f"CLS_TRANSPORT must be 'stdio', 'sse' or 'streamable-http', got '{self.transport}'"
            )
        if self.enable_dangerous and not self.enable_write:
            errors.append("CLS_ENABLE_DANGEROUS requires CLS_ENABLE_WRITE=true")
        return errors

    def print_summary(self) -> None:
        """打印配置摘要（脱敏）"""
        masked_id = f"{self.secret_id[:4]}****{self.secret_id[-4:]}" if len(self.secret_id) > 8 else "****"
        logger.info("=== CLS MCP Server Configuration ===")
        logger.info("  Region:     %s", self.region)
        logger.info("  Transport:  %s", self.transport)
        logger.info("  SecretId:   %s", masked_id)
        logger.info("  Write mode: %s", "ENABLED" if self.enable_write else "DISABLED (read-only)")
        logger.info("  Danger mode:%s", "ENABLED" if self.enable_dangerous else "DISABLED")
        logger.info("  Timeout:    %ds", self.request_timeout)
        logger.info("  Retry:      max %d attempts, base delay %.1fs", self.retry_max_attempts, self.retry_base_delay)
        logger.info("  Breaker:    threshold %d failures, recovery %ds", self.cb_failure_threshold, self.cb_recovery_timeout)
        if self.enabled_tools:
            logger.info("  Whitelist:  %s", ", ".join(sorted(self.enabled_tools)))
        else:
            logger.info("  Whitelist:  ALL (no filter)")
        if self.transport in ("sse", "streamable-http"):
            logger.info("  Listen:     %s:%d", self.host, self.port)
            if self.transport == "streamable-http":
                logger.info("  Stateless:  %s", "YES" if self.stateless_http else "NO")
            logger.info("  Auth:       %s", "ENABLED (Bearer Token)" if self.auth_token else "DISABLED (no token set)")
