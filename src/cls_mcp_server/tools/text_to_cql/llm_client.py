"""OpenAI 兼容 API LLM 客户端

通过 httpx 调用 OpenAI 兼容的 chat/completions API。
使用模块级连接池复用 TCP/TLS 连接，减少重试场景下的连接开销。
包含错误分类和指数退避重试机制。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random

import httpx

logger = logging.getLogger(__name__)

# ---------- 错误分类 ----------
# 可重试的 HTTP 状态码（服务端临时错误、限流）
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
# 不可重试的 HTTP 状态码（客户端错误、认证失败）
NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404})

# 模块级连接池单例，惰性初始化
_shared_client: httpx.AsyncClient | None = None


def _get_shared_client() -> httpx.AsyncClient:
    """获取共享的 httpx AsyncClient（惰性初始化）

    使用连接池复用 TCP/TLS 连接，避免每次请求都做握手。
    超时由调用方按需传入，此处设置较大的默认超时。
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
            ),
        )
    return _shared_client


async def close_shared_client() -> None:
    """关闭共享的 httpx 客户端，释放连接池资源

    应在服务关闭时调用（SIGTERM 处理器或 uvicorn shutdown hook）。
    """
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
        logger.info("Shared httpx client closed")


class LlmClientError(Exception):
    """LLM 调用异常"""

    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


async def call_llm(
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float = 15.0,
    temperature: float = 0.0,
) -> str:
    """调用 OpenAI 兼容 API，返回 assistant 回复内容

    使用模块级共享连接池，同一 api_base 的多次调用复用 TCP/TLS 连接。

    Args:
        api_base: API 地址，如 https://api.openai.com/v1
        api_key: API Key
        model: 模型名称
        messages: 对话消息列表
        timeout: 请求超时（秒）
        temperature: 生成温度，默认 0.0（确定性输出）

    Returns:
        assistant 回复的文本内容

    Raises:
        LlmClientError: 调用失败，retryable 标记是否可重试
    """
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048,
    }

    try:
        client = _get_shared_client()
        resp = await client.post(
            url, headers=headers, json=payload,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        if resp.status_code != 200:
            error_text = resp.text[:500]
            retryable = resp.status_code in RETRYABLE_STATUS_CODES
            logger.error(
                "LLM API error: status=%d, retryable=%s, body=%s",
                resp.status_code, retryable, error_text,
            )
            raise LlmClientError(
                f"LLM API 返回错误 (HTTP {resp.status_code}): {error_text}",
                status_code=resp.status_code,
                retryable=retryable,
            )

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise LlmClientError("LLM API 返回空的 choices")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise LlmClientError("LLM API 返回空的 content")

        return content.strip()

    except httpx.TimeoutException as e:
        logger.error("LLM API timeout after %.1fs: %s", timeout, e)
        raise LlmClientError(
            f"LLM API 请求超时 ({timeout}s)", retryable=True,
        ) from e
    except httpx.ConnectError as e:
        logger.error("LLM API connect error: %s", e)
        raise LlmClientError(
            f"LLM API 连接失败: {e}", retryable=True,
        ) from e
    except httpx.HTTPError as e:
        logger.error("LLM API HTTP error: %s", e)
        raise LlmClientError(f"LLM API 网络错误: {e}", retryable=True) from e
    except json.JSONDecodeError as e:
        logger.error("LLM API response not JSON: %s", e)
        raise LlmClientError("LLM API 响应格式错误（非 JSON）") from e


async def call_llm_with_retry(
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float = 15.0,
    temperature: float = 0.0,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> str:
    """带指数退避重试的 LLM 调用

    对可重试错误（网络超时、429 限流、5xx 服务端错误）自动重试，
    不可重试错误（401/403 认证失败、400 参数错误）直接抛出。
    退避策略：base_delay * 2^attempt + 随机抖动（避免惊群效应）。

    Args:
        api_base: API 地址
        api_key: API Key
        model: 模型名称
        messages: 对话消息列表
        timeout: 单次请求超时（秒）
        temperature: 生成温度
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 基础退避延迟（秒）

    Returns:
        assistant 回复的文本内容

    Raises:
        LlmClientError: 所有重试耗尽或遇到不可重试错误
    """
    last_error: LlmClientError | None = None

    for attempt in range(max_retries + 1):  # 0 = 首次调用, 1..max_retries = 重试
        try:
            return await call_llm(
                api_base=api_base,
                api_key=api_key,
                model=model,
                messages=messages,
                timeout=timeout,
                temperature=temperature,
            )
        except LlmClientError as e:
            last_error = e

            # 不可重试错误：直接抛出
            if not e.retryable:
                logger.error(
                    "LLM call failed (non-retryable, attempt %d/%d): %s",
                    attempt + 1, max_retries + 1, e,
                )
                raise

            # 已到最后一次重试：抛出
            if attempt >= max_retries:
                logger.error(
                    "LLM call failed after %d attempts: %s",
                    max_retries + 1, e,
                )
                raise

            # 计算退避延迟：base_delay * 2^attempt + 随机抖动
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                "LLM call failed (retryable, attempt %d/%d): %s. Retrying in %.1fs...",
                attempt + 1, max_retries + 1, e, delay,
            )
            await asyncio.sleep(delay)

    # 理论上不会走到这里，但兜底处理
    raise last_error or LlmClientError("LLM 调用失败：未知错误")
