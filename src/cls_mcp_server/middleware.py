"""HTTP Bearer Token 认证中间件

为 SSE / Streamable HTTP 传输模式提供静态 Bearer Token 认证。
通过环境变量 MCP_AUTH_TOKEN 或 CLI 参数 --auth-token 配置。
"""

from __future__ import annotations

import hmac
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# 不需要认证的路径（健康检查、就绪检查等运维端点）
DEFAULT_EXEMPT_PATHS: set[str] = {"/health", "/readiness"}


class BearerTokenAuthMiddleware(BaseHTTPMiddleware):
    """Bearer Token 认证中间件

    校验 HTTP 请求的 Authorization: Bearer <token> 头。
    使用 hmac.compare_digest 进行常量时间比较，防止时序攻击。

    Args:
        app: ASGI 应用
        token: 预期的 Bearer Token
        exempt_paths: 跳过认证的路径集合
    """

    def __init__(
        self,
        app,  # type: ignore[override]
        token: str,
        exempt_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._token = token
        self._exempt_paths = exempt_paths if exempt_paths is not None else DEFAULT_EXEMPT_PATHS

    async def dispatch(self, request: Request, call_next) -> Response:
        # 豁免路径直接放行
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # 提取客户端信息用于日志
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # 检查 Authorization header
        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            logger.warning(
                "Auth failed: missing Authorization header | path=%s client=%s",
                path,
                client_ip,
            )
            return JSONResponse(
                {"error": "Missing Authorization header. Expected: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_header.startswith("Bearer "):
            logger.warning(
                "Auth failed: malformed Authorization header | path=%s client=%s",
                path,
                client_ip,
            )
            return JSONResponse(
                {"error": "Malformed Authorization header. Expected: Bearer <token>"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        provided_token = auth_header[7:]  # len("Bearer ") == 7

        # 常量时间比较，防止时序侧信道攻击
        if not hmac.compare_digest(provided_token, self._token):
            logger.warning(
                "Auth failed: invalid token | path=%s client=%s",
                path,
                client_ip,
            )
            return JSONResponse(
                {"error": "Invalid token"},
                status_code=403,
            )

        return await call_next(request)
