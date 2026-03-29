"""CQL 生成器 — 核心模块

实现自然语言到 CQL 的转换，包含完整的生成-校验-重试闭环。
每次 tool 调用创建独立实例，所有状态为实例局部变量，天然支持并发隔离。
重试时保留完整对话历史（含上一轮生成结果和校验错误），使 LLM 能基于上下文修正。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from cls_mcp_server.tools.text_to_cql.cql_validator import (
    ValidationResult,
    clean_cql,
    validate_cql,
)
from cls_mcp_server.tools.text_to_cql.llm_client import LlmClientError, call_llm_with_retry
from cls_mcp_server.tools.text_to_cql.prompts import (
    build_retry_user_prompt,
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


@dataclass
class LlmConfig:
    """LLM 调用配置"""

    api_base: str
    api_key: str
    model: str


@dataclass
class CqlResult:
    """CQL 生成结果"""

    success: bool
    cql: str = ""
    mode: str = ""  # "syntax_only" | "generate"
    attempts: int = 0
    elapsed_ms: int = 0
    validation_errors: list[str] | None = None
    error_message: str = ""


class CqlGenerator:
    """CQL 生成器

    每次 tool 调用创建一个新实例，封装完整的生成-校验-重试循环。
    所有状态为实例局部变量，天然支持协程级并发隔离。
    重试时保留完整对话历史，让 LLM 能看到之前的错误并修正。
    """

    def __init__(
        self,
        llm_config: LlmConfig,
        syntax_docs: str,
        index_info: str = "",
        max_retries: int = 3,
        total_timeout: float = 30.0,
        per_call_timeout: float = 15.0,
    ):
        self._llm_config = llm_config
        self._syntax_docs = syntax_docs
        self._index_info = index_info
        self._max_retries = max_retries
        self._total_timeout = total_timeout
        self._per_call_timeout = per_call_timeout

    async def generate(self, user_query: str) -> CqlResult:
        """生成-校验-重试闭环

        重试时保留完整对话历史：system → user → assistant(错误CQL) → user(重试指令)，
        使 LLM 能看到之前生成的错误结果和校验反馈，避免重复犯错。
        LLM 网络调用本身带有指数退避重试（可重试错误自动重试，不可重试错误直接失败）。

        Args:
            user_query: 用户自然语言描述

        Returns:
            CqlResult 包含生成结果和元信息
        """
        start_time = time.monotonic()
        best_cql = ""
        best_errors: list[str] = []
        last_attempt = 0

        # 对话历史：在重试循环中持续累积
        messages: list[dict[str, str]] = self._build_initial_messages(user_query)

        for attempt in range(1, self._max_retries + 1):
            last_attempt = attempt

            # 检查总超时
            elapsed = time.monotonic() - start_time
            if elapsed > self._total_timeout:
                logger.warning(
                    "Total timeout reached after %d attempts (%.1fs)",
                    attempt - 1,
                    elapsed,
                )
                break

            # 剩余时间不足以完成一次调用
            remaining = self._total_timeout - elapsed
            if remaining < 3.0:
                break

            try:
                # 调用 LLM（内置指数退避重试：超时/429/5xx 自动重试，401/403 直接失败）
                call_timeout = min(self._per_call_timeout, remaining)
                raw_response = await call_llm_with_retry(
                    api_base=self._llm_config.api_base,
                    api_key=self._llm_config.api_key,
                    model=self._llm_config.model,
                    messages=messages,
                    timeout=call_timeout,
                    max_retries=2,
                    base_delay=1.0,
                )

                # 清理和校验
                cql = clean_cql(raw_response)
                validation = validate_cql(cql)

                if validation.is_valid:
                    elapsed_ms = int((time.monotonic() - start_time) * 1000)
                    logger.info(
                        "CQL generated successfully in %d attempts (%.1fs)",
                        attempt,
                        elapsed_ms / 1000,
                    )
                    return CqlResult(
                        success=True,
                        cql=cql,
                        mode="generate",
                        attempts=attempt,
                        elapsed_ms=elapsed_ms,
                    )

                # 校验失败，记录最佳结果并追加对话历史用于重试
                best_cql = cql
                best_errors = validation.errors
                error_feedback = "; ".join(validation.errors)
                logger.info(
                    "Attempt %d validation failed: %s. CQL: %s",
                    attempt,
                    error_feedback,
                    cql[:200],
                )

                # 追加 assistant 的错误回复和用户的重试指令到对话历史
                messages.append({"role": "assistant", "content": cql})
                messages.append({
                    "role": "user",
                    "content": build_retry_user_prompt(
                        query=user_query,
                        error_feedback=error_feedback,
                        index_info=self._index_info,
                    ),
                })

            except LlmClientError as e:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                logger.error("LLM call failed on attempt %d: %s", attempt, e)
                return CqlResult(
                    success=False,
                    mode="generate",
                    attempts=attempt,
                    elapsed_ms=elapsed_ms,
                    error_message=str(e),
                )

        # 所有重试都失败，返回最佳结果（使用实际 attempt 值）
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        if best_cql:
            return CqlResult(
                success=False,
                cql=best_cql,
                mode="generate",
                attempts=last_attempt,
                elapsed_ms=elapsed_ms,
                validation_errors=best_errors,
                error_message=f"校验未通过: {'; '.join(best_errors)}",
            )

        return CqlResult(
            success=False,
            mode="generate",
            attempts=last_attempt,
            elapsed_ms=elapsed_ms,
            error_message="生成失败：未能获得有效的 CQL 查询",
        )

    def _build_initial_messages(self, user_query: str) -> list[dict[str, str]]:
        """构建首次调用的 LLM 对话消息

        Args:
            user_query: 用户自然语言描述

        Returns:
            OpenAI 格式的消息列表（system + user）
        """
        return [
            {
                "role": "system",
                "content": build_system_prompt(self._syntax_docs),
            },
            {
                "role": "user",
                "content": build_user_prompt(user_query, self._index_info),
            },
        ]
