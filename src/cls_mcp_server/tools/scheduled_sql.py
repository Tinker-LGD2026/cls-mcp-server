"""定时 SQL 工具模块

管理 CLS 定时 SQL 分析任务，支持任务创建、查询和执行历史查看。
"""

from __future__ import annotations

import asyncio
import logging

from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error
from cls_mcp_server.utils.formatter import format_list_result

logger = logging.getLogger(__name__)


@cls_tool(
    name="cls_describe_scheduled_sql_tasks",
    level=ToolLevel.READ,
    description="""查询定时 SQL 任务列表。定时 SQL 用于周期性执行 SQL 分析并将结果存入目标日志主题。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- task_name: 按任务名称过滤（可选）
- src_topic_id: 按源日志主题 ID 过滤（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 返回信息
- 任务 ID、名称、状态
- 源主题、SQL 语句、调度周期
- 目标主题、创建时间""",
)
@handle_api_error
async def cls_describe_scheduled_sql_tasks(
    offset: int = 0,
    limit: int = 20,
    task_name: str = "",
    src_topic_id: str = "",
    region: str = "",
) -> str:
    """查询定时 SQL 任务列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeScheduledSqlInfoRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    filters = []
    if task_name:
        f = models.Filter()
        f.Key = "taskName"
        f.Values = [task_name]
        filters.append(f)
    if src_topic_id:
        f = models.Filter()
        f.Key = "srcTopicId"
        f.Values = [src_topic_id]
        filters.append(f)
    if filters:
        req.Filters = filters

    resp = await asyncio.to_thread(client.DescribeScheduledSqlInfo, req)

    if not resp.ScheduledSqlTaskInfos:
        return "📭 未找到定时 SQL 任务"

    STATUS_MAP = {
        1: "运行",
        2: "停止",
        3: "异常-找不到源日志主题",
        4: "异常-找不到目标主题",
        5: "访问权限问题",
        6: "内部故障",
        7: "其他故障",
    }

    items = []
    for task in resp.ScheduledSqlTaskInfos:
        item = {}
        if hasattr(task, "TaskId"):
            item["任务ID"] = task.TaskId
        if hasattr(task, "Name"):
            item["名称"] = task.Name
        if hasattr(task, "Status"):
            item["状态"] = STATUS_MAP.get(task.Status, str(task.Status))
        if hasattr(task, "SrcTopicId"):
            item["源主题ID"] = task.SrcTopicId
        if hasattr(task, "ScheduledSqlContent") and task.ScheduledSqlContent:
            content = task.ScheduledSqlContent
            if len(content) > 100:
                content = content[:100] + "..."
            item["SQL语句"] = content
        if hasattr(task, "ProcessPeriod"):
            item["调度周期"] = f"{task.ProcessPeriod}分钟"
        if hasattr(task, "CreateTime"):
            item["创建时间"] = task.CreateTime
        items.append(item)

    return format_list_result(items, "定时SQL任务", total=resp.TotalCount)


@cls_tool(
    name="cls_create_scheduled_sql",
    level=ToolLevel.WRITE,
    description="""创建定时 SQL 分析任务。周期性执行 SQL 查询并将分析结果保存到目标日志主题。

### 参数说明
- name: 任务名称（必填）
- src_topic_id: 源日志主题 ID（必填）
- sql_content: SQL 分析语句（必填），格式: `[检索条件] | [SQL语句]`
- dst_topic_id: 目标日志主题 ID（必填），分析结果写入此主题
- process_period: 调度周期（分钟，必填），如 5、15、60
- process_time_window: 每次处理的时间窗口（分钟，必填），通常与调度周期相同
- process_delay: 延迟处理时间（秒，可选），默认 0
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### SQL 示例
- 每5分钟统计各状态码数量:
  `* | SELECT status, COUNT(*) AS cnt GROUP BY status`
- 每小时计算 P99 延迟:
  `* | SELECT APPROX_PERCENTILE(latency, 0.99) AS p99_latency`""",
)
@handle_api_error
async def cls_create_scheduled_sql(
    name: str,
    src_topic_id: str,
    sql_content: str,
    dst_topic_id: str,
    process_period: int,
    process_time_window: int,
    process_delay: int = 0,
    region: str = "",
) -> str:
    """创建定时 SQL 任务"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.CreateScheduledSqlRequest()
    req.Name = name
    req.SrcTopicId = src_topic_id
    req.ScheduledSqlContent = sql_content
    req.ProcessPeriod = process_period
    req.ProcessTimeWindow = process_time_window
    req.ProcessDelay = process_delay
    req.SrcTopicRegion = region or config.region
    req.SyntaxRule = 1  # CQL 语法

    # 目标配置
    dst = models.ScheduledSqlResouceInfo()
    dst.TopicId = dst_topic_id
    dst.Region = region or config.region
    req.DstResource = dst

    resp = await asyncio.to_thread(client.CreateScheduledSql, req)

    return f"✅ 定时SQL任务创建成功\n任务ID: {resp.TaskId}\n名称: {name}\nSQL: {sql_content}\n周期: {process_period}分钟"


@cls_tool(
    name="cls_delete_scheduled_sql",
    level=ToolLevel.DANGER,
    description="""删除定时 SQL 任务。停止并删除指定的定时 SQL 分析任务。

### 参数说明
- task_id: 定时 SQL 任务 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_delete_scheduled_sql(
    task_id: str,
    region: str = "",
) -> str:
    """删除定时 SQL 任务"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DeleteScheduledSqlRequest()
    req.TaskId = task_id
    resp = await asyncio.to_thread(client.DeleteScheduledSql, req)

    return f"✅ 定时SQL任务已删除: {task_id}"
