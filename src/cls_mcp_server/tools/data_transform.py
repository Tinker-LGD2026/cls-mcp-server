"""数据加工工具模块

管理 CLS 数据加工（ETL）任务的生命周期。
"""

from __future__ import annotations

import asyncio
import logging

from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error, parse_json_param
from cls_mcp_server.utils.formatter import format_list_result

logger = logging.getLogger(__name__)


@cls_tool(
    name="cls_describe_data_transform_tasks",
    level=ToolLevel.READ,
    description="""查询数据加工任务列表。数据加工用于对日志数据进行清洗、转换、分发等处理。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- task_name: 按任务名称过滤（可选）
- topic_id: 按源日志主题 ID 过滤（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 返回信息
- 任务 ID、名称、状态（运行中/已停止/异常等）
- 源主题和目标主题
- 加工语句和创建时间""",
)
@handle_api_error
async def cls_describe_data_transform_tasks(
    offset: int = 0,
    limit: int = 20,
    task_name: str = "",
    topic_id: str = "",
    region: str = "",
) -> str:
    """查询数据加工任务列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeDataTransformInfoRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    filters = []
    if task_name:
        f = models.Filter()
        f.Key = "taskName"
        f.Values = [task_name]
        filters.append(f)
    if topic_id:
        f = models.Filter()
        f.Key = "topicId"
        f.Values = [topic_id]
        filters.append(f)
    if filters:
        req.Filters = filters

    resp = await asyncio.to_thread(client.DescribeDataTransformInfo, req)

    if not resp.DataTransformTaskInfos:
        return "📭 未找到数据加工任务"

    STATUS_MAP = {1: "准备中", 2: "运行中", 3: "停止中", 4: "已停止"}

    items = []
    for task in resp.DataTransformTaskInfos:
        item = {}
        if hasattr(task, "TaskId"):
            item["任务ID"] = task.TaskId
        if hasattr(task, "Name"):
            item["名称"] = task.Name
        if hasattr(task, "Status"):
            item["状态"] = STATUS_MAP.get(task.Status, str(task.Status))
        if hasattr(task, "SrcTopicId"):
            item["源主题ID"] = task.SrcTopicId
        if hasattr(task, "EtlContent") and task.EtlContent:
            content = task.EtlContent
            if len(content) > 100:
                content = content[:100] + "..."
            item["加工语句"] = content
        if hasattr(task, "CreateTime"):
            item["创建时间"] = task.CreateTime
        items.append(item)

    return format_list_result(items, "数据加工任务", total=resp.TotalCount)


@cls_tool(
    name="cls_create_data_transform",
    level=ToolLevel.WRITE,
    description="""创建数据加工任务。配置源日志主题的数据加工规则和目标投递。

### 参数说明
- name: 任务名称（必填）
- src_topic_id: 源日志主题 ID（必填）
- etl_content: 数据加工 DSL 语句（必填）
- task_type: 任务类型，1 为基础加工（默认）
- dst_resources_json: 目标资源 JSON 数组（必填），每项包含:
    - TopicId: 目标主题 ID
    - Alias: 别名（在 DSL 中引用）

### DSL 语句示例
- 丢弃特定字段: `e_drop_fields("debug_info")`
- 过滤日志: `e_if(e_match("level", "DEBUG"), DROP)`
- 字段重命名: `e_rename("old_name", "new_name")`
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_create_data_transform(
    name: str,
    src_topic_id: str,
    etl_content: str,
    task_type: int = 1,
    dst_resources_json: str = "[]",
    region: str = "",
) -> str:
    """创建数据加工任务"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.CreateDataTransformRequest()
    req.Name = name
    req.SrcTopicId = src_topic_id
    req.EtlContent = etl_content
    req.TaskType = task_type

    dst_data = parse_json_param(dst_resources_json, "dst_resources_json")
    if dst_data:
        resources = []
        for d in dst_data:
            res = models.DataTransformResouceInfo()
            res.TopicId = d["TopicId"]
            res.Alias = d.get("Alias", "")
            resources.append(res)
        req.DstResources = resources

    resp = await asyncio.to_thread(client.CreateDataTransform, req)

    return f"✅ 数据加工任务创建成功\n任务ID: {resp.TaskId}\n名称: {name}\n源主题: {src_topic_id}"


@cls_tool(
    name="cls_delete_data_transform",
    level=ToolLevel.DANGER,
    description="""删除数据加工任务。停止并删除指定的数据加工任务。

### 参数说明
- task_id: 数据加工任务 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_delete_data_transform(
    task_id: str,
    region: str = "",
) -> str:
    """删除数据加工任务"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DeleteDataTransformRequest()
    req.TaskId = task_id
    resp = await asyncio.to_thread(client.DeleteDataTransform, req)

    return f"✅ 数据加工任务已删除: {task_id}"
