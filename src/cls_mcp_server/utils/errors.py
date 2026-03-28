"""统一错误处理模块

捕获腾讯云 SDK 异常，转换为 LLM 可读的结构化错误信息。
错误返回采用 JSON 格式，便于大模型精确解析错误原因并自我纠正。

集成稳定性增强：
- 熔断器：按 region 粒度，连续失败达阈值后熔断
- 重试：对可恢复错误（网络超时、限流、5xx）自动指数退避重试
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Callable

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

from cls_mcp_server.utils.stability import (
    CircuitOpenError,
    get_breaker_manager,
    get_retry_handler,
    is_retryable,
)

logger = logging.getLogger(__name__)


# ============================================================
# 结构化错误模型
# ============================================================

@dataclass
class ValidationError:
    """单个参数的校验错误，包含大模型自我纠正所需的全部信息"""
    param: str       # 错误参数名，如 "topic_id"
    value: Any       # 实际传入的值
    reason: str      # 错误原因，如 "不能为空字符串"
    expected: str    # 期望的正确格式/范围，如 "非空字符串，格式如 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"


class ParamValidationError(Exception):
    """参数校验异常，携带结构化错误列表"""
    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        super().__init__(f"{len(errors)} 个参数校验失败")


def format_validation_errors(errors: list[ValidationError]) -> str:
    """将校验错误列表格式化为结构化 JSON 响应，便于大模型解析和自我纠正"""
    return json.dumps({
        "success": False,
        "error_type": "VALIDATION_ERROR",
        "error_count": len(errors),
        "errors": [asdict(e) for e in errors],
        "hint": "请根据每个错误的 expected 字段修正对应参数后重试"
    }, ensure_ascii=False, indent=2)


# ============================================================
# 常见 SDK 错误码映射
# ============================================================

ERROR_HINTS: dict[str, str] = {
    "AuthFailure.SecretIdNotFound": "SecretId 不存在，请检查 CLS_SECRET_ID 配置",
    "AuthFailure.SignatureFailure": "签名验证失败，请检查 CLS_SECRET_KEY 配置",
    "AuthFailure.UnauthorizedOperation": "无权限执行此操作，请检查 CAM 策略配置",
    "ResourceNotFound.TopicNotExist": "主题不存在，请检查 topic_id 是否正确",
    "ResourceNotFound.LogsetNotExist": "日志集不存在，请检查 logset_id 是否正确",
    "LimitExceeded.LogSearch": "日志检索并发超限（单 Topic 最大并发 15），请稍后重试",
    "FailedOperation.QueryError": "查询语句执行失败，请检查 CQL/SQL 语法",
    "FailedOperation.InvalidContext": "检索翻页游标已失效，请重新发起查询（不传 context 参数）",
    "InvalidParameterValue": "参数值不合法，请检查输入参数",
}


def format_api_error(exc: TencentCloudSDKException) -> str:
    """将腾讯云 SDK 异常格式化为结构化 JSON 错误信息"""
    code = exc.code or "UnknownError"
    message = exc.message or "未知错误"
    request_id = exc.requestId or "N/A"
    hint = ERROR_HINTS.get(code, "")

    error_obj: dict[str, Any] = {
        "success": False,
        "error_type": "API_ERROR",
        "error_code": code,
        "message": message,
        "request_id": request_id,
    }
    if hint:
        error_obj["suggestion"] = hint

    return json.dumps(error_obj, ensure_ascii=False, indent=2)


def parse_json_param(value: str, param_name: str) -> Any:
    """安全解析 JSON 格式的输入参数，失败时返回明确的用户提示

    Args:
        value: JSON 字符串
        param_name: 参数名称，用于错误提示

    Raises:
        ValueError: JSON 格式不合法
    """
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(f"参数 '{param_name}' 不是合法的 JSON 格式: {e}") from e


def _extract_region(func: Callable, args: tuple, kwargs: dict) -> str:
    """从工具函数参数中提取 region 值

    工具函数签名约定：region 参数名固定为 'region'，默认值为 ""。
    如果提取不到，返回空字符串（使用默认 region）。
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    if "region" in kwargs:
        return kwargs["region"] or ""

    if "region" in params:
        idx = params.index("region")
        if idx < len(args):
            return args[idx] or ""

    return ""


def handle_api_error(func: Callable) -> Callable:
    """装饰器：统一捕获异常并返回结构化错误信息

    集成稳定性增强：
    - 熔断器检查（按 region，OPEN 时直接拒绝）
    - 自动重试（对可恢复错误进行指数退避重试）

    异常处理优先级：
    1. ParamValidationError -> 结构化参数校验错误（含每个参数的错误详情和期望格式）
    2. CircuitOpenError -> 熔断器已开启（该 region 暂不可用）
    3. TencentCloudSDKException -> 结构化 API 错误（含错误码、消息、修复建议）
    4. ValueError -> 结构化参数错误
    5. json.JSONDecodeError -> 结构化响应解析错误
    6. Exception -> 结构化内部错误
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            # 参数校验类错误不走重试/熔断
            return await _execute_with_stability(func, args, kwargs)
        except ParamValidationError as e:
            logger.warning("Validation error in %s: %d error(s)", func.__name__, len(e.errors))
            return format_validation_errors(e.errors)
        except CircuitOpenError as e:
            logger.warning("Circuit open for %s: %s", func.__name__, e)
            return json.dumps({
                "success": False,
                "error_type": "CIRCUIT_OPEN",
                "message": str(e),
                "region": e.region,
                "suggestion": f"该区域 ({e.region}) API 连续失败触发熔断保护，"
                              f"将在 {e.recovery_seconds}s 后自动恢复，请稍后重试"
            }, ensure_ascii=False, indent=2)
        except TencentCloudSDKException as e:
            logger.error("CLS API error in %s: [%s] %s (RequestId: %s)", func.__name__, e.code, e.message, e.requestId)
            return format_api_error(e)
        except ValueError as e:
            logger.error("Parameter error in %s: %s", func.__name__, e)
            return json.dumps({
                "success": False,
                "error_type": "PARAM_ERROR",
                "message": str(e),
                "suggestion": "请检查参数格式是否正确"
            }, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as e:
            logger.error("JSON decode error in %s: %s", func.__name__, e)
            return json.dumps({
                "success": False,
                "error_type": "PARSE_ERROR",
                "message": f"响应数据解析失败: {e}",
                "suggestion": "这是服务端返回数据格式异常，请稍后重试"
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.exception("Unexpected error in %s", func.__name__)
            return json.dumps({
                "success": False,
                "error_type": "INTERNAL_ERROR",
                "message": f"{type(e).__name__}: {e}",
                "suggestion": "内部错误，请稍后重试或联系管理员"
            }, ensure_ascii=False, indent=2)

    return wrapper


async def _execute_with_stability(
    func: Callable, args: tuple, kwargs: dict
) -> Any:
    """带熔断和重试保护的执行逻辑

    调用链：熔断器检查 → 重试包装 → 实际调用
    重试全部耗尽后才算一次"真正的失败"，不会因重试中的瞬时失败触发熔断。
    """
    breaker_mgr = get_breaker_manager()
    retry_handler = get_retry_handler()

    region = _extract_region(func, args, kwargs)

    # 获取该 region 的熔断器
    breaker = None
    if breaker_mgr and region:
        breaker = await breaker_mgr.get_breaker(region)
        await breaker.pre_check()  # OPEN 时抛 CircuitOpenError

    # 定义实际调用
    async def _call() -> Any:
        return await func(*args, **kwargs)

    try:
        # 有重试器则走重试逻辑，否则直接调用
        if retry_handler:
            result = await retry_handler.execute(_call)
        else:
            result = await _call()

        # 成功：通知熔断器
        if breaker:
            await breaker.record_success()

        return result
    except Exception as e:
        # 失败：通知熔断器（仅可重试错误计入熔断统计）
        if breaker and is_retryable(e):
            await breaker.record_failure()
        raise
