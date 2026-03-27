"""参数校验模块

为 MCP 工具提供统一的入口层参数校验，校验失败时返回结构化错误信息，
使大模型能精确理解错误原因（参数名、错误原因、期望格式）并自我纠正。
"""

from __future__ import annotations

from typing import Any

from cls_mcp_server.utils.errors import ParamValidationError, ValidationError


# ============================================================
# 模式判断
# ============================================================

def is_analytics_mode(query: str) -> bool:
    """判断查询是否为分析模式（query 包含 SQL 管道符 |）。

    分析模式下，CLS API 的 Limit 和 Sort 参数不生效，
    需通过 SQL 中的 LIMIT / ORDER BY 控制。
    """
    return isinstance(query, str) and "|" in query


# ============================================================
# 通用原子校验函数
# ============================================================

def check_required_string(param_name: str, value: Any, description: str = "") -> ValidationError | None:
    """校验必填字符串参数非空"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ValidationError(
            param=param_name,
            value=value,
            reason="必填参数，不能为空或空字符串",
            expected=description or f"非空字符串",
        )
    return None


def check_positive_int(
    param_name: str,
    value: Any,
    min_val: int = 1,
    max_val: int | None = None,
) -> ValidationError | None:
    """校验正整数参数范围"""
    if not isinstance(value, int):
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"必须为整数，实际类型为 {type(value).__name__}",
            expected=f"整数" + (f"，范围 [{min_val}, {max_val}]" if max_val else f"，最小值 {min_val}"),
        )
    if value < min_val:
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"值 {value} 小于最小值 {min_val}",
            expected=f"整数，范围 [{min_val}, {max_val}]" if max_val else f"整数，最小值 {min_val}",
        )
    if max_val is not None and value > max_val:
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"值 {value} 超过最大值 {max_val}",
            expected=f"整数，范围 [{min_val}, {max_val}]",
        )
    return None


def check_enum(param_name: str, value: Any, allowed: list[str]) -> ValidationError | None:
    """校验枚举值是否在白名单中"""
    if value is not None and str(value).lower() not in [a.lower() for a in allowed]:
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"值 '{value}' 不在允许范围内",
            expected=f"允许的值: {allowed}",
        )
    return None


def check_time_range(start_time: int, end_time: int) -> ValidationError | None:
    """校验时间范围逻辑：start_time 必须小于等于 end_time"""
    if isinstance(start_time, int) and isinstance(end_time, int) and start_time > end_time:
        return ValidationError(
            param="start_time / end_time",
            value=f"start_time={start_time}, end_time={end_time}",
            reason=f"start_time ({start_time}) 大于 end_time ({end_time})，时间范围逆序",
            expected="start_time 必须小于等于 end_time（均为毫秒级 Unix 时间戳），请用 cls_convert_time 工具获取正确的时间戳",
        )
    return None


def check_non_negative_int(
    param_name: str,
    value: Any,
    max_val: int | None = None,
) -> ValidationError | None:
    """校验非负整数参数（允许 0）"""
    if not isinstance(value, int):
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"必须为整数，实际类型为 {type(value).__name__}",
            expected=f"非负整数" + (f"，范围 [0, {max_val}]" if max_val else ""),
        )
    if value < 0:
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"值 {value} 不能为负数",
            expected=f"非负整数" + (f"，范围 [0, {max_val}]" if max_val else ""),
        )
    if max_val is not None and value > max_val:
        return ValidationError(
            param=param_name,
            value=value,
            reason=f"值 {value} 超过最大值 {max_val}",
            expected=f"非负整数，范围 [0, {max_val}]",
        )
    return None


def _collect_errors(checks: list[ValidationError | None]) -> None:
    """收集校验错误，如有则抛出 ParamValidationError"""
    errors = [e for e in checks if e is not None]
    if errors:
        raise ParamValidationError(errors)


# ============================================================
# 各工具的组合校验入口
# ============================================================

def validate_search_log_params(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    limit: int,
    sort: str,
) -> None:
    """校验 cls_search_log 参数，失败抛出 ParamValidationError。

    检索模式（query 不含 |）：校验 limit (0, 1000] 和 sort 白名单。
    分析模式（query 含 |）：跳过 limit 和 sort 校验，因为 CLS API 在分析模式下忽略这两个参数，
    返回条数和排序由 SQL 中的 LIMIT / ORDER BY 控制。
    """
    checks: list[ValidationError | None] = [
        check_required_string("topic_id", topic_id, "日志主题 ID，格式如 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"),
        check_required_string("query", query, "CQL 检索语句，如 '*' 或 'level:ERROR'；分析语句如 '* | SELECT COUNT(*) AS cnt'"),
        check_time_range(start_time, end_time),
    ]
    # 仅检索模式校验 limit 和 sort（分析模式下 API 忽略这两个参数）
    if not is_analytics_mode(query):
        checks.append(check_positive_int("limit", limit, min_val=1, max_val=1000))
        checks.append(check_enum("sort", sort, ["asc", "desc"]))
    _collect_errors(checks)


def validate_log_context_params(
    topic_id: str,
    btime: str,
    pkg_id: str,
    pkg_log_id: int,
    prev_logs: int,
    next_logs: int,
) -> None:
    """校验 cls_get_log_context 参数，失败抛出 ParamValidationError"""
    _collect_errors([
        check_required_string("topic_id", topic_id, "日志主题 ID，格式如 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"),
        check_required_string("btime", btime, "日志时间，支持毫秒时间戳（如 '1774537847429'）或 'YYYY-mm-dd HH:MM:SS.FFF' 格式字符串"),
        check_required_string("pkg_id", pkg_id, "日志包序号，从 cls_search_log 返回的 PkgId 字段获取"),
        check_non_negative_int("prev_logs", prev_logs, max_val=100),
        check_non_negative_int("next_logs", next_logs, max_val=100),
    ])


def validate_log_histogram_params(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    interval: int | None,
) -> None:
    """校验 cls_get_log_histogram 参数，失败抛出 ParamValidationError"""
    checks = [
        check_required_string("topic_id", topic_id, "日志主题 ID，格式如 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"),
        check_required_string("query", query, "CQL 检索语句，如 '*' 或 'level:ERROR'"),
        check_time_range(start_time, end_time),
    ]
    if interval is not None:
        checks.append(check_positive_int("interval", interval, min_val=1))
    _collect_errors(checks)


def validate_log_count_params(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
) -> None:
    """校验 cls_get_log_count 参数，失败抛出 ParamValidationError"""
    _collect_errors([
        check_required_string("topic_id", topic_id, "日志主题 ID，格式如 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"),
        check_required_string("query", query, "CQL 检索语句，如 '*' 或 'level:ERROR'"),
        check_time_range(start_time, end_time),
    ])


def check_metric_time_range(start_time: int, end_time: int) -> ValidationError | None:
    """校验指标查询的时间范围逻辑：start_time 必须小于等于 end_time（秒级时间戳）"""
    if isinstance(start_time, int) and isinstance(end_time, int) and start_time > end_time:
        return ValidationError(
            param="start_time / end_time",
            value=f"start_time={start_time}, end_time={end_time}",
            reason=f"start_time ({start_time}) 大于 end_time ({end_time})，时间范围逆序",
            expected="start_time 必须小于等于 end_time（均为秒级 Unix 时间戳），请用 cls_convert_time 工具获取正确的时间戳",
        )
    return None


def validate_query_metric_params(
    topic_id: str,
    query: str,
) -> None:
    """校验 cls_query_metric 参数，失败抛出 ParamValidationError"""
    _collect_errors([
        check_required_string("topic_id", topic_id, "指标主题 ID（时序主题），非普通日志主题 ID"),
        check_required_string("query", query, "PromQL 兼容查询语句，如 'openclaw_active_sessions' 或 'rate(metric_name[5m])'"),
    ])


def validate_query_range_metric_params(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    step: int,
) -> None:
    """校验 cls_query_range_metric 参数，失败抛出 ParamValidationError"""
    _collect_errors([
        check_required_string("topic_id", topic_id, "指标主题 ID（时序主题），非普通日志主题 ID"),
        check_required_string("query", query, "PromQL 兼容查询语句，如 'openclaw_active_sessions' 或 'rate(metric_name[5m])'"),
        check_metric_time_range(start_time, end_time),
        check_positive_int("step", step, min_val=1),
    ])


def validate_list_metrics_params(
    topic_id: str,
    start_time: int,
    end_time: int,
) -> None:
    """校验 cls_list_metrics 参数，失败抛出 ParamValidationError"""
    _collect_errors([
        check_required_string("topic_id", topic_id, "指标主题 ID（时序主题），非普通日志主题 ID"),
        check_metric_time_range(start_time, end_time),
    ])
