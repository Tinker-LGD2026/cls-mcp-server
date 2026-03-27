"""资源管理工具模块

管理 CLS 核心资源：日志集、日志主题、机器组、索引、仪表盘、地域。
"""

from __future__ import annotations

import asyncio
import json
import logging

from tencentcloud.cls.v20201016 import models
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.region.v20220627 import region_client as region_sdk_client
from tencentcloud.region.v20220627 import models as region_models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error, parse_json_param
from cls_mcp_server.utils.formatter import format_list_result

logger = logging.getLogger(__name__)


# ============================================================
# 日志集（Logset）
# ============================================================


@cls_tool(
    name="cls_describe_logsets",
    level=ToolLevel.READ,
    description="""查询日志集列表。日志集是 CLS 的项目管理单元，包含多个日志主题。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- logset_name: 按日志集名称过滤（可选，模糊匹配）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 返回信息
- 日志集 ID、名称、标签
- 保存周期、创建时间
- 包含的日志主题数量""",
)
@handle_api_error
async def cls_describe_logsets(
    offset: int = 0,
    limit: int = 20,
    logset_name: str = "",
    region: str = "",
) -> str:
    """查询日志集列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeLogsetsRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    if logset_name:
        f = models.Filter()
        f.Key = "logsetName"
        f.Values = [logset_name]
        req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeLogsets, req)

    if not resp.Logsets:
        return "📭 未找到日志集"

    items = []
    for ls in resp.Logsets:
        item = {
            "日志集ID": ls.LogsetId,
            "名称": ls.LogsetName,
        }
        if hasattr(ls, "Period") and ls.Period is not None:
            item["保存天数"] = ls.Period
        if hasattr(ls, "TopicCount") and ls.TopicCount is not None:
            item["主题数"] = ls.TopicCount
        if hasattr(ls, "CreateTime") and ls.CreateTime:
            item["创建时间"] = ls.CreateTime
        items.append(item)

    return format_list_result(items, "日志集列表", total=resp.TotalCount)


@cls_tool(
    name="cls_create_logset",
    level=ToolLevel.WRITE,
    description="""创建日志集。日志集是日志主题的容器，用于组织和管理相关的日志主题。

### 参数说明
- logset_name: 日志集名称（必填），3-255 个字符
- period: 日志保存天数（可选），默认 30，可选值: 1-3600 天，-1 表示永久
- tags_json: 标签 JSON 对象字符串（可选），如 `{"env": "prod"}`
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_create_logset(
    logset_name: str,
    period: int = 30,
    tags_json: str = "{}",
    region: str = "",
) -> str:
    """创建日志集"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.CreateLogsetRequest()
    req.LogsetName = logset_name
    req.Period = period

    tags_data = parse_json_param(tags_json, "tags_json")
    if tags_data:
        tags = []
        for k, v in tags_data.items():
            tag = models.Tag()
            tag.Key = k
            tag.Value = v
            tags.append(tag)
        req.Tags = tags

    resp = await asyncio.to_thread(client.CreateLogset, req)

    return f"✅ 日志集创建成功\n日志集ID: {resp.LogsetId}\n名称: {logset_name}\n保存天数: {period}"


@cls_tool(
    name="cls_delete_logset",
    level=ToolLevel.DANGER,
    description="""删除日志集。删除前需确保日志集下无日志主题，否则会失败。

### 参数说明
- logset_id: 日志集 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_delete_logset(
    logset_id: str,
    region: str = "",
) -> str:
    """删除日志集"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DeleteLogsetRequest()
    req.LogsetId = logset_id
    resp = await asyncio.to_thread(client.DeleteLogset, req)

    return f"✅ 日志集已删除: {logset_id}"


# ============================================================
# 日志主题（Topic）
# ============================================================


@cls_tool(
    name="cls_describe_topics",
    level=ToolLevel.READ,
    description="""查询日志主题列表。日志主题是日志数据的基本存储单元。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- logset_id: 按日志集 ID 过滤（可选）
- topic_name: 按日志主题名称过滤（可选，模糊匹配）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 返回信息
- 日志主题 ID、名称、所属日志集
- 存储类型、保存周期、分区数
- 采集和索引状态""",
)
@handle_api_error
async def cls_describe_topics(
    offset: int = 0,
    limit: int = 20,
    logset_id: str = "",
    topic_name: str = "",
    region: str = "",
) -> str:
    """查询日志主题列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeTopicsRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    filters = []
    if logset_id:
        f = models.Filter()
        f.Key = "logsetId"
        f.Values = [logset_id]
        filters.append(f)
    if topic_name:
        f = models.Filter()
        f.Key = "topicName"
        f.Values = [topic_name]
        filters.append(f)
    if filters:
        req.Filters = filters

    resp = await asyncio.to_thread(client.DescribeTopics, req)

    if not resp.Topics:
        return "📭 未找到日志主题"

    items = []
    for topic in resp.Topics:
        item = {
            "主题ID": topic.TopicId,
            "名称": topic.TopicName,
            "日志集ID": topic.LogsetId,
        }
        if hasattr(topic, "Period") and topic.Period is not None:
            item["保存天数"] = topic.Period
        if hasattr(topic, "PartitionCount") and topic.PartitionCount is not None:
            item["分区数"] = topic.PartitionCount
        if hasattr(topic, "Status") and topic.Status is not None:
            item["状态"] = "正常" if topic.Status is True or topic.Status == 1 else "关闭"
        if hasattr(topic, "StorageType") and topic.StorageType:
            item["存储类型"] = topic.StorageType
        if hasattr(topic, "CreateTime") and topic.CreateTime:
            item["创建时间"] = topic.CreateTime
        items.append(item)

    return format_list_result(items, "日志主题列表", total=resp.TotalCount)


@cls_tool(
    name="cls_describe_topic_detail",
    level=ToolLevel.READ,
    description="""获取日志主题详情。查看日志主题的完整配置信息。

### 参数说明
- topic_id: 日志主题 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_describe_topic_detail(
    topic_id: str,
    region: str = "",
) -> str:
    """获取日志主题详情"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeTopicsRequest()
    req.Offset = 0
    req.Limit = 1

    f = models.Filter()
    f.Key = "topicId"
    f.Values = [topic_id]
    req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeTopics, req)

    if not resp.Topics:
        return f"📭 未找到日志主题: {topic_id}"

    topic = resp.Topics[0]
    parts: list[str] = ["📋 日志主题详情"]
    parts.append(f"  主题ID: {topic.TopicId}")
    parts.append(f"  名称: {topic.TopicName}")
    parts.append(f"  日志集ID: {topic.LogsetId}")

    optional_fields = [
        ("Period", "保存天数"), ("PartitionCount", "分区数"),
        ("Status", "状态"), ("StorageType", "存储类型"),
        ("AutoSplit", "自动分裂"), ("MaxSplitPartitions", "最大分裂数"),
        ("CreateTime", "创建时间"), ("Describes", "描述"),
    ]
    for field, label in optional_fields:
        if hasattr(topic, field) and getattr(topic, field) is not None:
            value = getattr(topic, field)
            if field == "Status":
                value = "正常" if value is True or value == 1 else "关闭"
            parts.append(f"  {label}: {value}")

    if hasattr(topic, "Tags") and topic.Tags:
        tags = {t.Key: t.Value for t in topic.Tags}
        parts.append(f"  标签: {json.dumps(tags, ensure_ascii=False)}")

    return "\n".join(parts)


@cls_tool(
    name="cls_create_topic",
    level=ToolLevel.WRITE,
    description="""创建日志主题。在指定日志集下创建新的日志主题用于存储日志数据。

### 参数说明
- logset_id: 所属日志集 ID（必填）
- topic_name: 日志主题名称（必填），1-255 个字符
- partition_count: 初始分区数量（可选），默认 1，建议根据日志量评估
- period: 日志保存天数（可选），默认继承日志集配置
- storage_type: 存储类型（可选），`hot`（标准存储）或 `cold`（低频存储）
- auto_split: 是否开启自动分裂（可选），默认 true
- describes: 描述信息（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_create_topic(
    logset_id: str,
    topic_name: str,
    partition_count: int = 1,
    period: int | None = None,
    storage_type: str = "hot",
    auto_split: bool = True,
    describes: str = "",
    region: str = "",
) -> str:
    """创建日志主题"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.CreateTopicRequest()
    req.LogsetId = logset_id
    req.TopicName = topic_name
    req.PartitionCount = partition_count
    req.StorageType = storage_type
    req.AutoSplit = auto_split

    if period is not None:
        req.Period = period
    if describes:
        req.Describes = describes

    resp = await asyncio.to_thread(client.CreateTopic, req)

    return f"✅ 日志主题创建成功\n主题ID: {resp.TopicId}\n名称: {topic_name}\n日志集: {logset_id}\n存储类型: {storage_type}"


@cls_tool(
    name="cls_modify_topic",
    level=ToolLevel.WRITE,
    description="""修改日志主题配置。更新主题名称、保存周期、分区数等设置。

### 参数说明
- topic_id: 日志主题 ID（必填）
- topic_name: 新名称（可选）
- period: 新保存天数（可选）
- status: 是否开启采集，true 开启 / false 关闭（可选）
- auto_split: 是否自动分裂（可选）
- describes: 描述信息（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_modify_topic(
    topic_id: str,
    topic_name: str = "",
    period: int | None = None,
    status: bool | None = None,
    auto_split: bool | None = None,
    describes: str = "",
    region: str = "",
) -> str:
    """修改日志主题"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.ModifyTopicRequest()
    req.TopicId = topic_id

    if topic_name:
        req.TopicName = topic_name
    if period is not None:
        req.Period = period
    if status is not None:
        req.Status = status
    if auto_split is not None:
        req.AutoSplit = auto_split
    if describes:
        req.Describes = describes

    resp = await asyncio.to_thread(client.ModifyTopic, req)

    changes = []
    if topic_name:
        changes.append(f"名称 -> {topic_name}")
    if period is not None:
        changes.append(f"保存天数 -> {period}")
    if status is not None:
        changes.append(f"状态 -> {'开启' if status else '关闭'}")

    return f"✅ 日志主题修改成功\n主题ID: {topic_id}\n修改: {'; '.join(changes) if changes else '无变更'}"


@cls_tool(
    name="cls_delete_topic",
    level=ToolLevel.DANGER,
    description="""删除日志主题。删除后该主题下的所有日志数据将被清除，不可恢复。

### 参数说明
- topic_id: 日志主题 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_delete_topic(
    topic_id: str,
    region: str = "",
) -> str:
    """删除日志主题"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DeleteTopicRequest()
    req.TopicId = topic_id
    resp = await asyncio.to_thread(client.DeleteTopic, req)

    return f"✅ 日志主题已删除: {topic_id}"


# ============================================================
# 索引配置
# ============================================================


@cls_tool(
    name="cls_describe_index",
    level=ToolLevel.READ,
    description="""查询日志主题的索引配置。索引决定了哪些字段可被检索和分析。

### 参数说明
- topic_id: 日志主题 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 返回信息
- 全文索引配置（是否开启、分词符等）
- 键值索引配置（字段名、类型、是否开启统计）
- 索引状态""",
)
@handle_api_error
async def cls_describe_index(
    topic_id: str,
    region: str = "",
) -> str:
    """查询索引配置"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeIndexRequest()
    req.TopicId = topic_id

    resp = await asyncio.to_thread(client.DescribeIndex, req)

    parts: list[str] = [f"📋 索引配置 (主题: {topic_id})"]
    parts.append(f"  状态: {'开启' if resp.Status else '关闭'}")

    if hasattr(resp, "Rule") and resp.Rule:
        rule = resp.Rule

        # 动态索引
        dynamic_index = getattr(rule, "DynamicIndex", None)
        if dynamic_index is not None:
            di_status = getattr(dynamic_index, "Status", False)
            parts.append(f"\n  🔄 动态索引: {'开启' if di_status else '关闭'}")

        # 全文索引
        if hasattr(rule, "FullText") and rule.FullText:
            ft = rule.FullText
            parts.append(f"\n  📝 全文索引:")
            parts.append(f"    大小写敏感: {'是' if getattr(ft, 'CaseSensitive', False) else '否'}")
            parts.append(f"    包含中文: {'是' if getattr(ft, 'ContainZH', False) else '否'}")
            tokenizer = getattr(ft, "Tokenizer", "")
            if tokenizer:
                parts.append(f"    分词符: {tokenizer}")

        # 键值索引
        if hasattr(rule, "KeyValue") and rule.KeyValue:
            kv = rule.KeyValue
            parts.append(f"\n  🔑 键值索引:")
            parts.append(f"    大小写敏感: {'是' if getattr(kv, 'CaseSensitive', False) else '否'}")
            key_values = getattr(kv, "KeyValues", None)
            if key_values:
                parts.append(f"    字段数: {len(key_values)}")
                for f in key_values[:20]:
                    ftype = getattr(f.Value, "Type", "unknown") if f.Value else "unknown"
                    sql_flag = getattr(f.Value, "SqlFlag", False) if f.Value else False
                    parts.append(f"      - {f.Key} ({ftype}{', 统计' if sql_flag else ''})")
                if len(key_values) > 20:
                    parts.append(f"      ... 共 {len(key_values)} 个字段")

        # 标签索引
        tag = getattr(rule, "Tag", None)
        if tag:
            parts.append(f"\n  🏷️ 标签索引:")
            parts.append(f"    大小写敏感: {'是' if getattr(tag, 'CaseSensitive', False) else '否'}")
            tag_kvs = getattr(tag, "KeyValues", None)
            if tag_kvs:
                parts.append(f"    字段数: {len(tag_kvs)}")
                for f in tag_kvs:
                    ftype = getattr(f.Value, "Type", "unknown") if f.Value else "unknown"
                    parts.append(f"      - {f.Key} ({ftype})")

    if hasattr(resp, "ModifyTime") and resp.ModifyTime:
        parts.append(f"\n  最后修改: {resp.ModifyTime}")

    return "\n".join(parts)


@cls_tool(
    name="cls_modify_index",
    level=ToolLevel.WRITE,
    description="""修改日志主题的索引配置。更新全文索引和键值索引设置。

### 参数说明
- topic_id: 日志主题 ID（必填）
- rule_json: 索引规则 JSON 字符串（必填），格式参考 CLS 官方文档
- status: 是否开启索引，默认 true

### 注意
修改索引配置后，新的配置仅对后续写入的日志生效，已有日志不会重新索引。
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_modify_index(
    topic_id: str,
    rule_json: str,
    status: bool = True,
    region: str = "",
) -> str:
    """修改索引配置"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.ModifyIndexRequest()
    req.TopicId = topic_id
    req.Status = 1 if status else 0

    # 解析规则 JSON
    rule_data = parse_json_param(rule_json, "rule_json")
    rule = models.RuleInfo()

    if "FullText" in rule_data:
        ft_data = rule_data["FullText"]
        ft = models.FullTextInfo()
        ft.Status = ft_data.get("Status", True)
        ft.Tokenizer = ft_data.get("Tokenizer", "@&?|#()='\",;:<>[]{}/ \\n\\t\\r")
        ft.CaseSensitive = ft_data.get("CaseSensitive", False)
        rule.FullText = ft

    if "KeyValue" in rule_data:
        kv_data = rule_data["KeyValue"]
        kv = models.RuleKeyValueInfo()
        kv.Status = kv_data.get("Status", True)
        if "KeyValues" in kv_data:
            kvs = []
            for kv_item in kv_data["KeyValues"]:
                ki = models.KeyValueInfo()
                ki.Key = kv_item["Key"]
                vi = models.ValueInfo()
                vi.Type = kv_item.get("Type", "text")
                vi.Tokenizer = kv_item.get("Tokenizer", "")
                vi.SqlFlag = kv_item.get("SqlFlag", True)
                ki.Value = vi
                kvs.append(ki)
            kv.KeyValues = kvs
        rule.KeyValue = kv

    req.Rule = rule
    resp = await asyncio.to_thread(client.ModifyIndex, req)

    return f"✅ 索引配置修改成功\n主题ID: {topic_id}\n状态: {'开启' if status else '关闭'}"


# ============================================================
# 机器组（MachineGroup）
# ============================================================


@cls_tool(
    name="cls_describe_machine_groups",
    level=ToolLevel.READ,
    description="""查询机器组列表。机器组是日志采集端的管理单元，用于统一管理一组日志源机器。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- group_name: 按机器组名称过滤（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_describe_machine_groups(
    offset: int = 0,
    limit: int = 20,
    group_name: str = "",
    region: str = "",
) -> str:
    """查询机器组列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeMachineGroupsRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    if group_name:
        f = models.Filter()
        f.Key = "machineGroupName"
        f.Values = [group_name]
        req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeMachineGroups, req)

    if not resp.MachineGroups:
        return "📭 未找到机器组"

    items = []
    for mg in resp.MachineGroups:
        item = {
            "机器组ID": mg.GroupId,
            "名称": mg.GroupName,
        }
        if hasattr(mg, "MachineGroupType") and mg.MachineGroupType:
            item["类型"] = mg.MachineGroupType.Type if hasattr(mg.MachineGroupType, "Type") else str(mg.MachineGroupType)
        if hasattr(mg, "CreateTime") and mg.CreateTime:
            item["创建时间"] = mg.CreateTime
        items.append(item)

    return format_list_result(items, "机器组列表", total=resp.TotalCount)


@cls_tool(
    name="cls_describe_machine_group_detail",
    level=ToolLevel.READ,
    description="""获取机器组详情和机器状态。查看机器组的配置信息和组内机器的在线状态。

### 参数说明
- group_id: 机器组 ID（必填）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_describe_machine_group_detail(
    group_id: str,
    region: str = "",
) -> str:
    """获取机器组详情"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    # 获取机器组配置
    req = models.DescribeMachineGroupsRequest()
    req.Offset = 0
    req.Limit = 1
    f = models.Filter()
    f.Key = "machineGroupId"
    f.Values = [group_id]
    req.Filters = [f]
    resp = await asyncio.to_thread(client.DescribeMachineGroups, req)

    parts: list[str] = [f"📋 机器组详情"]

    if resp.MachineGroups:
        mg = resp.MachineGroups[0]
        parts.append(f"  机器组ID: {mg.GroupId}")
        parts.append(f"  名称: {mg.GroupName}")
        if hasattr(mg, "MachineGroupType") and mg.MachineGroupType:
            parts.append(f"  类型: {mg.MachineGroupType.Type if hasattr(mg.MachineGroupType, 'Type') else mg.MachineGroupType}")
        if hasattr(mg, "CreateTime") and mg.CreateTime:
            parts.append(f"  创建时间: {mg.CreateTime}")

    # 获取机器状态
    try:
        req2 = models.DescribeMachinesRequest()
        req2.GroupId = group_id
        resp2 = await asyncio.to_thread(client.DescribeMachines, req2)

        if resp2.Machines:
            parts.append(f"\n  🖥️ 机器列表 ({len(resp2.Machines)} 台):")
            for m in resp2.Machines:
                status = "🟢 在线" if hasattr(m, "Status") and m.Status == 1 else "🔴 离线"
                ip = m.Ip if hasattr(m, "Ip") else "N/A"
                parts.append(f"    {status} {ip}")
        else:
            parts.append("\n  🖥️ 机器列表: 暂无机器")
    except Exception as e:
        parts.append(f"\n  获取机器状态失败: {e}")

    return "\n".join(parts)


# ============================================================
# 仪表盘（Dashboard）
# ============================================================


@cls_tool(
    name="cls_describe_dashboards",
    level=ToolLevel.READ,
    description="""查询仪表盘列表。获取当前账号下的 CLS 仪表盘。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- dashboard_name: 按仪表盘名称过滤（可选）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_describe_dashboards(
    offset: int = 0,
    limit: int = 20,
    dashboard_name: str = "",
    region: str = "",
) -> str:
    """查询仪表盘列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeDashboardsRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    if dashboard_name:
        f = models.Filter()
        f.Key = "dashboardName"
        f.Values = [dashboard_name]
        req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeDashboards, req)

    if not resp.DashboardInfos:
        return "📭 未找到仪表盘"

    items = []
    for d in resp.DashboardInfos:
        item = {
            "仪表盘ID": d.DashboardId,
            "名称": d.DashboardName,
        }
        if hasattr(d, "CreateTime") and d.CreateTime:
            item["创建时间"] = d.CreateTime
        items.append(item)

    return format_list_result(items, "仪表盘列表", total=resp.TotalCount)


# ============================================================
# 地域（Region）
# ============================================================


@cls_tool(
    name="cls_describe_regions",
    level=ToolLevel.READ,
    description="""查询 CLS 支持的地域列表。返回所有可用地域的 ID 和中文名称，用于确认地域参数的正确取值。

### 无需参数
直接调用即可，无需传入任何参数。

### 返回信息
- 地域 ID（如 ap-guangzhou、ap-shanghai）
- 地域中文名称（如 广州、上海）

### 使用场景
- 不确定某个城市/地区对应的地域 ID 时，先调用此工具查询
- 需要列出所有可用地域供用户选择时使用""",
)
@handle_api_error
async def cls_describe_regions() -> str:
    """查询 CLS 支持的地域列表"""
    config = get_config()

    cred = credential.Credential(config.secret_id, config.secret_key)

    http_profile = HttpProfile()
    http_profile.endpoint = "region.tencentcloudapi.com"
    http_profile.reqMethod = "POST"

    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile

    client = region_sdk_client.RegionClient(cred, "", client_profile)

    req = region_models.DescribeRegionsRequest()
    req.Product = "cls"

    resp = await asyncio.to_thread(client.DescribeRegions, req)

    if not resp.RegionSet:
        return "📭 未找到 CLS 可用地域"

    items = []
    for r in resp.RegionSet:
        item = {
            "地域ID": r.Region,
            "地域名称": r.RegionName,
        }
        if hasattr(r, "RegionState") and r.RegionState:
            item["状态"] = "可用" if r.RegionState == "AVAILABLE" else r.RegionState
        items.append(item)

    return format_list_result(items, "CLS 可用地域列表", total=len(resp.RegionSet))
