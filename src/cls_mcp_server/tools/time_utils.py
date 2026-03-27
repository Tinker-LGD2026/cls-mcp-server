"""时间转换工具模块

提供人类可读时间与 Unix 时间戳之间的双向转换能力，
避免 LLM 在心算时间戳时出错。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from cls_mcp_server.tools.registry import ToolLevel, cls_tool

logger = logging.getLogger(__name__)

# 支持的可读时间格式列表（带毫秒的格式优先匹配）
_TIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
]

# 相对时间模式：数字 + 单位 + ago
_RELATIVE_PATTERN = re.compile(
    r"^(\d+)\s*(second|seconds|sec|s|minute|minutes|min|m|hour|hours|h|day|days|d|week|weeks|w)\s*ago$",
    re.IGNORECASE,
)

# 单位到秒的映射
_UNIT_SECONDS: dict[str, int] = {
    "second": 1, "seconds": 1, "sec": 1, "s": 1,
    "minute": 60, "minutes": 60, "min": 60, "m": 60,
    "hour": 3600, "hours": 3600, "h": 3600,
    "day": 86400, "days": 86400, "d": 86400,
    "week": 604800, "weeks": 604800, "w": 604800,
}


def _get_tz(tz_name: str) -> timezone:
    """获取时区对象，支持 Asia/Shanghai 等常见时区"""
    # 常见时区偏移映射
    tz_offsets: dict[str, int] = {
        "Asia/Shanghai": 8,
        "Asia/Tokyo": 9,
        "Asia/Seoul": 9,
        "Asia/Singapore": 8,
        "Asia/Hong_Kong": 8,
        "UTC": 0,
        "GMT": 0,
        "US/Eastern": -5,
        "US/Pacific": -8,
        "Europe/London": 0,
        "Europe/Berlin": 1,
        "Europe/Paris": 1,
    }

    if tz_name in tz_offsets:
        return timezone(timedelta(hours=tz_offsets[tz_name]))

    # 尝试用 zoneinfo（Python 3.9+）
    try:
        from zoneinfo import ZoneInfo
        zi = ZoneInfo(tz_name)
        # 获取当前偏移
        offset = datetime.now(zi).utcoffset()
        if offset is not None:
            return timezone(offset)
    except (ImportError, KeyError):
        pass

    raise ValueError(f"不支持的时区: {tz_name}，请使用 Asia/Shanghai、UTC 等常见时区名")


def _parse_relative_time(expr: str, tz: timezone) -> datetime:
    """解析相对时间表达式"""
    expr_lower = expr.strip().lower()
    now = datetime.now(tz)

    if expr_lower == "now":
        return now

    if expr_lower == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    if expr_lower == "yesterday":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    if expr_lower == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # "yesterday 12:00:00" 或 "yesterday 12:00"
    for prefix, delta_days in [("yesterday", -1), ("today", 0), ("tomorrow", 1)]:
        if expr_lower.startswith(prefix + " "):
            time_part = expr_lower[len(prefix) + 1:].strip()
            base = (now + timedelta(days=delta_days)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # 解析时间部分
            for fmt in ["%H:%M:%S", "%H:%M"]:
                try:
                    t = datetime.strptime(time_part, fmt)
                    return base.replace(hour=t.hour, minute=t.minute, second=t.second)
                except ValueError:
                    continue
            raise ValueError(f"无法解析时间部分: {time_part}，请使用 HH:MM 或 HH:MM:SS 格式")

    # "3 hours ago", "1 day ago" 等
    match = _RELATIVE_PATTERN.match(expr_lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        seconds = _UNIT_SECONDS.get(unit, 0)
        return now - timedelta(seconds=amount * seconds)

    raise ValueError(
        f"无法解析相对时间: {expr}。"
        f"支持的格式: now, today, yesterday, tomorrow, "
        f"yesterday HH:MM:SS, today HH:MM, "
        f"N hours/minutes/days/weeks ago"
    )


def _parse_human_readable(expr: str, tz: timezone) -> datetime:
    """解析人类可读时间表达式（绝对或相对）"""
    expr = expr.strip()

    # 先尝试相对时间
    try:
        return _parse_relative_time(expr, tz)
    except ValueError:
        pass

    # 再尝试绝对时间格式
    for fmt in _TIME_FORMATS:
        try:
            dt = datetime.strptime(expr, fmt)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue

    raise ValueError(
        f"无法解析时间: {expr}。\n"
        f"支持的格式:\n"
        f"  - 绝对时间: YYYY-MM-DD HH:MM:SS, YYYY-MM-DD HH:MM:SS.fff, YYYY-MM-DD HH:MM, YYYY-MM-DD\n"
        f"  - 相对时间: now, today, yesterday, tomorrow\n"
        f"  - 组合格式: yesterday 12:00:00, today 09:30\n"
        f"  - 相对偏移: 3 hours ago, 1 day ago, 30 minutes ago"
    )


@cls_tool(
    name="cls_convert_time",
    level=ToolLevel.READ,
    description="""时间与时间戳转换工具。在调用需要时间戳参数的 CLS 工具前，请先使用此工具进行精确转换，避免手动计算时间戳出错。

### 功能
- **可读时间 → 时间戳**：传入 human_readable 参数，返回对应的 Unix 毫秒时间戳和秒级时间戳
- **时间戳 → 可读时间**：传入 timestamp 参数（毫秒级），返回对应的可读时间字符串
- **同时返回毫秒和秒级时间戳**，方便直接用于日志查询（毫秒）或指标查询（秒）

### 参数说明
- timestamp: Unix 毫秒时间戳（整数），与 human_readable 二选一
- human_readable: 人类可读时间表达式（字符串），与 timestamp 二选一，支持以下格式：
  - 绝对时间: `2026-03-25 14:30:00`、`2026-03-25 14:30:00.123`、`2026-03-25 14:30`、`2026-03-25`
  - 相对时间: `now`、`today`、`yesterday`、`tomorrow`
  - 组合格式: `yesterday 12:00:00`、`today 09:30`、`tomorrow 08:00`
  - 相对偏移: `3 hours ago`、`1 day ago`、`30 minutes ago`、`2 weeks ago`
- timezone: 时区名称，默认 `Asia/Shanghai`

### 使用示例
- 查询昨天12:00到13:00: 分别调用 `human_readable="yesterday 12:00:00"` 和 `human_readable="yesterday 13:00:00"`
- 查询最近1小时: 调用 `human_readable="1 hour ago"` 获取 start_time，`human_readable="now"` 获取 end_time
- 转换时间戳: 调用 `timestamp=1774396800000` 查看对应的可读时间

### 返回格式
返回包含毫秒时间戳（用于 cls_search_log 等）、秒级时间戳（用于 cls_query_metric 等）和可读时间字符串。""",
)
async def cls_convert_time(
    timestamp: int | None = None,
    human_readable: str | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> str:
    """时间与时间戳双向转换"""
    if timestamp is None and human_readable is None:
        return "❌ 请提供 timestamp（毫秒时间戳）或 human_readable（可读时间）参数，二选一。"

    if timestamp is not None and human_readable is not None:
        return "❌ 请只提供 timestamp 或 human_readable 其中一个参数。"

    try:
        tz = _get_tz(timezone_name)
    except ValueError as e:
        return f"❌ {e}"

    try:
        if timestamp is not None:
            # 时间戳 → 可读时间
            # 自动检测秒级/毫秒级
            if timestamp > 1e12:
                ts_ms = int(timestamp)
                ts_sec = ts_ms // 1000
                ms_part = ts_ms % 1000
            else:
                ts_sec = int(timestamp)
                ts_ms = ts_sec * 1000
                ms_part = 0

            dt = datetime.fromtimestamp(ts_sec, tz=tz)
            readable = dt.strftime("%Y-%m-%d %H:%M:%S") + f".{ms_part:03d}"

            return (
                f"🕐 时间戳转换结果\n"
                f"  输入时间戳: {timestamp}\n"
                f"  可读时间: {readable}\n"
                f"  时区: {timezone_name}\n"
                f"  毫秒时间戳(ms): {ts_ms}\n"
                f"  秒级时间戳(s): {ts_sec}"
            )
        else:
            # 可读时间 → 时间戳
            dt = _parse_human_readable(human_readable, tz)
            ts_ms = int(dt.timestamp() * 1000)
            ts_sec = ts_ms // 1000
            ms_part = ts_ms % 1000
            readable = dt.strftime("%Y-%m-%d %H:%M:%S") + f".{ms_part:03d}"

            return (
                f"🕐 时间转换结果\n"
                f"  输入时间: {human_readable}\n"
                f"  可读时间: {readable}\n"
                f"  时区: {timezone_name}\n"
                f"  毫秒时间戳(ms): {ts_ms}\n"
                f"  秒级时间戳(s): {ts_sec}"
            )

    except (ValueError, OSError) as e:
        return f"❌ 时间转换失败: {e}"
