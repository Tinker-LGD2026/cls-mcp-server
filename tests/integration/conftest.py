"""集成测试 conftest — 管理 LLM API 配置和共享 fixtures

需要设置以下环境变量才能运行集成测试：
  LKEAP_API_KEY  — LLM API 密钥（必填）
  LKEAP_API_BASE — API 地址（可选，默认 https://api.lkeap.cloud.tencent.com/v3）
  LKEAP_MODEL    — 模型名称（可选，默认 glm-5）
"""

from __future__ import annotations

import os
import time

import pytest

from cls_mcp_server.tools.text_to_cql.cql_generator import CqlGenerator, LlmConfig
from cls_mcp_server.tools.text_to_cql.syntax_docs import get_syntax_docs
from cls_mcp_server.tools.text_to_cql import llm_client


# ============================================================
# 配置
# ============================================================

DEFAULT_API_BASE = "https://api.lkeap.cloud.tencent.com/v3"
DEFAULT_MODEL = "glm-5"


def _get_api_key() -> str:
    key = os.environ.get("LKEAP_API_KEY", "")
    if not key:
        pytest.skip("LKEAP_API_KEY not set, skipping integration test")
    return key


def _get_api_base() -> str:
    return os.environ.get("LKEAP_API_BASE", DEFAULT_API_BASE)


def _get_model() -> str:
    return os.environ.get("LKEAP_MODEL", DEFAULT_MODEL)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _reset_shared_client_and_rate_limit():
    """每个测试前重置共享 httpx client + 测试间限流

    1. pytest-asyncio 默认 function scope，每个测试用新事件循环，
       但模块级 _shared_client 绑定到旧循环会导致 'Event loop is closed'。
    2. LKEAP 免费额度 TPM 较低，测试间需等待避免 429。
    """
    llm_client._shared_client = None
    yield
    llm_client._shared_client = None
    delay = float(os.environ.get("LKEAP_RATE_LIMIT_DELAY", "3"))
    time.sleep(delay)


@pytest.fixture(scope="session")
def llm_config() -> LlmConfig:
    """Session 级别的 LLM 配置，所有集成测试共享"""
    return LlmConfig(
        api_base=_get_api_base(),
        api_key=_get_api_key(),
        model=_get_model(),
    )


@pytest.fixture(scope="session")
def syntax_docs() -> str:
    """Session 级别的语法文档，所有集成测试共享"""
    return get_syntax_docs()


@pytest.fixture
def generator(llm_config: LlmConfig, syntax_docs: str) -> CqlGenerator:
    """每个测试用例创建独立的 CqlGenerator 实例

    使用较宽松的超时：
    - total_timeout=60s（LLM 首次调用可能较慢）
    - per_call_timeout=30s
    """
    return CqlGenerator(
        llm_config=llm_config,
        syntax_docs=syntax_docs,
        max_retries=3,
        total_timeout=90.0,
        per_call_timeout=45.0,
    )


@pytest.fixture
def generator_with_index(llm_config: LlmConfig, syntax_docs: str) -> CqlGenerator:
    """带索引字段信息的 Generator，用于测试 index_info 对生成质量的影响"""
    sample_index_info = (
        "字段列表：\n"
        "- status (long) - HTTP 状态码\n"
        "- method (text) - 请求方法\n"
        "- path (text) - 请求路径\n"
        "- response_time (long) - 响应时间(ms)\n"
        "- client_ip (text) - 客户端 IP\n"
        "- level (text) - 日志级别\n"
        "- service (text) - 服务名称\n"
        "- message (text) - 日志内容\n"
        "- __TIMESTAMP__ (long) - 日志时间戳(毫秒)\n"
        "- __SOURCE__ (text) - 日志来源\n"
    )
    return CqlGenerator(
        llm_config=llm_config,
        syntax_docs=syntax_docs,
        index_info=sample_index_info,
        max_retries=3,
        total_timeout=90.0,
        per_call_timeout=45.0,
    )
