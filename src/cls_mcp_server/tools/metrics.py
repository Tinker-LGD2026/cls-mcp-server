"""指标查询工具模块

提供 CLS 指标查询能力，支持 PromQL 兼容的指标查询。
"""

from __future__ import annotations

import asyncio
import logging

from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error
from cls_mcp_server.utils.formatter import format_timestamp, truncate_text
from cls_mcp_server.utils.validators import (
    validate_list_metrics_params,
    validate_query_metric_params,
    validate_query_range_metric_params,
)

logger = logging.getLogger(__name__)


@cls_tool(
    name="cls_query_metric",
    level=ToolLevel.READ,
    description="""查询 CLS 指标数据（单时间点）。支持 PromQL 兼容查询语法，获取某一时刻的指标值。

### 参数说明
- topic_id: 指标主题 ID（必填），注意是时序指标主题 ID，非普通日志主题 ID
- query: 指标查询语句（必填），PromQL 兼容语法
- time: 查询时间点，Unix 时间戳（秒），默认当前时间

### PromQL 示例
- `metric_name` — 查询单个指标当前值
- `rate(metric_name[5m])` — 5 分钟速率
- `sum(metric_name) by (label)` — 按标签汇总
- `topk(5, metric_name)` — 取 Top 5

### 注意事项
- ⏰ **time 为秒级时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**""",
)
@handle_api_error
async def cls_query_metric(
    topic_id: str,
    query: str,
    time: int | None = None,
    region: str = "",
) -> str:
    """查询指标（单时间点）"""
    validate_query_metric_params(topic_id, query)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.QueryMetricRequest()
    req.TopicId = topic_id
    req.Query = query
    if time is not None:
        req.Time = time

    resp = await asyncio.to_thread(client.QueryMetric, req)

    parts: list[str] = [f"📈 指标查询结果"]
    parts.append(f"查询: {query}")

    if hasattr(resp, "ResultType") and resp.ResultType:
        parts.append(f"结果类型: {resp.ResultType}")

    if hasattr(resp, "Result") and resp.Result:
        parts.append(f"结果: {resp.Result}")

    return "\n".join(parts)


@cls_tool(
    name="cls_query_range_metric",
    level=ToolLevel.READ,
    description="""查询 CLS 指标数据（时间范围）。支持 PromQL 兼容查询语法，获取一段时间内的指标变化趋势。

### 参数说明
- topic_id: 指标主题 ID（必填），注意是时序指标主题 ID，非普通日志主题 ID
- query: 指标查询语句（必填），PromQL 兼容语法
- start_time: 起始时间，Unix 时间戳（秒）
- end_time: 结束时间，Unix 时间戳（秒）
- step: 步长（秒），数据点之间的间隔，默认 60

### 适用场景
- 查看指标随时间的变化趋势
- 告警前查看历史指标走势
- 对比不同时间段的指标数据

### 注意事项
- ⏰ **start_time/end_time 为秒级时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**""",
)
@handle_api_error
async def cls_query_range_metric(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    step: int = 60,
    region: str = "",
) -> str:
    """查询指标（时间范围）"""
    validate_query_range_metric_params(topic_id, query, start_time, end_time, step)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.QueryRangeMetricRequest()
    req.TopicId = topic_id
    req.Query = query
    req.Start = start_time
    req.End = end_time
    req.Step = step

    resp = await asyncio.to_thread(client.QueryRangeMetric, req)

    parts: list[str] = [f"📈 指标范围查询结果"]
    parts.append(f"查询: {query}")
    parts.append(f"时间: {format_timestamp(start_time)} ~ {format_timestamp(end_time)}")
    parts.append(f"步长: {step}s")

    if hasattr(resp, "ResultType") and resp.ResultType:
        parts.append(f"结果类型: {resp.ResultType}")

    if hasattr(resp, "Result") and resp.Result:
        parts.append(f"结果: {resp.Result}")

    return truncate_text("\n".join(parts))


@cls_tool(
    name="cls_list_metrics",
    level=ToolLevel.READ,
    description="""列出指标主题下的所有指标名称。用于在查询指标前了解有哪些可用指标。

### 参数说明
- topic_id: 指标主题 ID（必填），注意是时序指标主题 ID，非普通日志主题 ID
- start_time: 起始时间，Unix 时间戳（秒）
- end_time: 结束时间，Unix 时间戳（秒）

### 使用场景
- 在使用 cls_query_metric / cls_query_range_metric 查询指标前，先列出可用指标
- 了解某个指标主题下上报了哪些指标

### 注意事项
- ⏰ **start_time/end_time 为秒级时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**
- 返回的是指定时间范围内有数据的指标名称，建议查询最近 15 分钟即可""",
)
@handle_api_error
async def cls_list_metrics(
    topic_id: str,
    start_time: int,
    end_time: int,
    region: str = "",
) -> str:
    """列出指标主题下的所有指标名称"""
    validate_list_metrics_params(topic_id, start_time, end_time)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.GetMetricLabelValuesRequest()
    req.TopicId = topic_id
    req.LabelName = "__name__"
    req.Start = start_time
    req.End = end_time

    resp = await asyncio.to_thread(client.GetMetricLabelValues, req)

    values = resp.Values or []
    parts: list[str] = [f"📊 指标列表（共 {len(values)} 个）"]
    parts.append(f"主题: {topic_id}")
    parts.append(f"时间: {format_timestamp(start_time)} ~ {format_timestamp(end_time)}")
    parts.append("")

    if values:
        for name in sorted(values):
            parts.append(f"  - {name}")
    else:
        parts.append("（该时间范围内无指标数据）")

    return "\n".join(parts)
