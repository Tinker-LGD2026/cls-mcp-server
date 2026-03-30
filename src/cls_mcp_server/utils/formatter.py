"""响应格式化工具

将 CLS API 响应转换为 LLM 可读的结构化文本。
"""

from __future__ import annotations

import json
import time
from typing import Any


def format_timestamp(ts: int | float) -> str:
    """将时间戳转换为可读时间字符串（自动检测秒级/毫秒级）

    大于 1e12 视为毫秒级时间戳，否则视为秒级。
    """
    try:
        ts_sec = ts / 1000 if ts > 1e12 else ts
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_sec))
    except (ValueError, OSError):
        return str(ts)


def format_timestamp_ms(ts: int | float) -> str:
    """将毫秒时间戳转换为 YYYY-mm-dd HH:MM:SS.FFF 格式（UTC+8）

    """
    try:
        ts_ms = int(ts)
        ts_sec = ts_ms // 1000
        ms = ts_ms % 1000
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_sec)) + f".{ms:03d}"
    except (ValueError, OSError):
        return str(ts)


def truncate_text(text: str, max_length: int = 4000) -> str:
    """截断过长文本，防止 context window 溢出"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n... (已截断，原始长度 {len(text)} 字符)"


def format_log_results(results: list[Any], total: int | None = None, list_over: bool = True) -> str:
    """格式化日志检索结果"""
    if not results:
        return "📭 未查询到匹配的日志记录"

    lines: list[str] = []
    if total is not None:
        lines.append(f"📊 共匹配 {total} 条日志，本次返回 {len(results)} 条")
    else:
        lines.append(f"📊 本次返回 {len(results)} 条日志")

    if not list_over:
        lines.append("📌 还有更多日志，可通过 context 参数翻页获取")

    lines.append("")

    for i, log_item in enumerate(results, 1):
        lines.append(f"--- 日志 #{i} ---")
        if hasattr(log_item, "Time") and log_item.Time:
            lines.append(f"时间: {format_timestamp_ms(log_item.Time)} ({int(log_item.Time)})")
        if hasattr(log_item, "Source") and log_item.Source:
            lines.append(f"来源: {log_item.Source}")
        if hasattr(log_item, "FileName") and log_item.FileName:
            lines.append(f"文件: {log_item.FileName}")

        # 上下文定位字段（供 cls_get_log_context 使用）
        if hasattr(log_item, "PkgId") and log_item.PkgId:
            lines.append(f"PkgId: {log_item.PkgId}")
        if hasattr(log_item, "PkgLogId") and log_item.PkgLogId is not None:
            lines.append(f"PkgLogId: {log_item.PkgLogId}")

        # 解析日志内容
        if hasattr(log_item, "LogJson") and log_item.LogJson:
            try:
                log_dict = json.loads(log_item.LogJson)
                for k, v in log_dict.items():
                    lines.append(f"  {k}: {v}")
            except json.JSONDecodeError:
                lines.append(f"  内容: {log_item.LogJson}")
        lines.append("")

    result = "\n".join(lines)
    return truncate_text(result, max_length=8000)


def format_list_result(
    items: list[dict[str, Any]],
    title: str,
    total: int | None = None,
    fields: list[str] | None = None,
) -> str:
    """格式化列表类型的 API 响应"""
    if not items:
        return f"📭 {title}: 无数据"

    lines: list[str] = []
    count_info = f"（共 {total} 条）" if total is not None else f"（{len(items)} 条）"
    lines.append(f"📋 {title} {count_info}")
    lines.append("")

    for i, item in enumerate(items, 1):
        lines.append(f"--- #{i} ---")
        display_fields = fields or list(item.keys())
        for field in display_fields:
            if field in item and item[field] is not None:
                value = item[field]
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                lines.append(f"  {field}: {value}")
        lines.append("")

    return truncate_text("\n".join(lines))
