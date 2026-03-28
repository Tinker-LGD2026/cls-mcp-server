"""腾讯云认证与 CLS Client 工厂

负责创建和管理腾讯云 CLS SDK 客户端实例。
使用线程安全缓存，支持 SSE 模式下的多并发请求。
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import TYPE_CHECKING

from tencentcloud.cls.v20201016 import cls_client
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

if TYPE_CHECKING:
    from cls_mcp_server.config import ServerConfig

logger = logging.getLogger(__name__)

_cache_lock = threading.Lock()
_client_cache: dict[str, cls_client.ClsClient] = {}


def _make_cache_key(secret_id: str, secret_key: str, region: str) -> str:
    """生成缓存 key（包含 secret_key 的哈希，密钥变更时自动失效）"""
    raw = f"{secret_id}:{secret_key}:{region}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cls_client(config: ServerConfig, region: str | None = None) -> cls_client.ClsClient:
    """获取 CLS SDK 客户端实例（线程安全缓存）

    Args:
        config: 服务器配置
        region: 地域，默认使用配置中的地域

    Returns:
        CLS SDK 客户端实例
    """
    target_region = region or config.region
    cache_key = _make_cache_key(config.secret_id, config.secret_key, target_region)

    with _cache_lock:
        if cache_key in _client_cache:
            return _client_cache[cache_key]

    cred = credential.Credential(config.secret_id, config.secret_key)

    http_profile = HttpProfile()
    http_profile.endpoint = "cls.tencentcloudapi.com"
    http_profile.reqMethod = "POST"
    http_profile.reqTimeout = config.request_timeout

    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    client = cls_client.ClsClient(cred, target_region, client_profile)

    with _cache_lock:
        _client_cache[cache_key] = client

    logger.info("Created CLS client for region: %s (timeout: %ds)", target_region, config.request_timeout)
    return client


def clear_client_cache() -> None:
    """清理客户端缓存"""
    with _cache_lock:
        _client_cache.clear()
