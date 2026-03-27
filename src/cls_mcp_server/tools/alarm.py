"""告警管理工具模块

提供告警策略的增删改查、告警历史记录查询、通知渠道管理等能力。
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse, parse_qs

import httpx
from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error, parse_json_param
from cls_mcp_server.utils.formatter import format_list_result, format_timestamp

logger = logging.getLogger(__name__)


# ============================================================
# 读操作（默认注册）
# ============================================================


@cls_tool(
    name="cls_describe_alarms",
    level=ToolLevel.READ,
    description="""查询告警策略列表。获取当前账号下的告警策略信息，支持分页和过滤。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20，最大 100
- name: 按告警策略名称过滤（可选，模糊匹配）
- topic_id: 按关联日志主题 ID 过滤（可选）

### 返回信息
- 告警策略 ID、名称、状态（开启/关闭）
- 监控条件、触发规则、通知渠道
- 创建和最近修改时间""",
)
@handle_api_error
async def cls_describe_alarms(
    offset: int = 0,
    limit: int = 20,
    name: str = "",
    topic_id: str = "",
    region: str = "",
) -> str:
    """查询告警策略列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeAlarmsRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    filters = []
    if name:
        f = models.Filter()
        f.Key = "alarmName"
        f.Values = [name]
        filters.append(f)
    if topic_id:
        f = models.Filter()
        f.Key = "topicId"
        f.Values = [topic_id]
        filters.append(f)
    if filters:
        req.Filters = filters

    resp = await asyncio.to_thread(client.DescribeAlarms, req)

    if not resp.Alarms:
        return "📭 未找到告警策略"

    items = []
    for alarm in resp.Alarms:
        item = {
            "告警ID": alarm.AlarmId,
            "名称": alarm.Name,
            "状态": "开启" if alarm.Status == 1 else "关闭",
        }
        if hasattr(alarm, "MonitorTime") and alarm.MonitorTime:
            item["监控时间"] = f"{alarm.MonitorTime.Type}: {alarm.MonitorTime.Time}" if hasattr(alarm.MonitorTime, "Type") else str(alarm.MonitorTime)
        if hasattr(alarm, "Condition") and alarm.Condition:
            item["触发条件"] = alarm.Condition
        if hasattr(alarm, "CreateTime") and alarm.CreateTime:
            item["创建时间"] = alarm.CreateTime
        if hasattr(alarm, "UpdateTime") and alarm.UpdateTime:
            item["更新时间"] = alarm.UpdateTime
        items.append(item)

    return format_list_result(items, "告警策略列表", total=resp.TotalCount)


@cls_tool(
    name="cls_describe_alarm_detail",
    level=ToolLevel.READ,
    description="""获取告警策略详情。根据告警策略 ID 查看完整的告警配置信息。

### 参数说明
- alarm_id: 告警策略 ID（必填）

### 返回信息
- 完整的告警配置：名称、监控条件、触发规则
- 通知渠道配置、告警周期
- 关联的日志主题和查询条件""",
)
@handle_api_error
async def cls_describe_alarm_detail(
    alarm_id: str,
    region: str = "",
) -> str:
    """获取告警策略详情"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    # 通过过滤获取特定告警
    req = models.DescribeAlarmsRequest()
    req.Offset = 0
    req.Limit = 1

    f = models.Filter()
    f.Key = "alarmId"
    f.Values = [alarm_id]
    req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeAlarms, req)

    if not resp.Alarms:
        return f"📭 未找到告警策略: {alarm_id}"

    alarm = resp.Alarms[0]
    parts: list[str] = [f"📋 告警策略详情"]
    parts.append(f"  告警ID: {alarm.AlarmId}")
    parts.append(f"  名称: {alarm.Name}")
    parts.append(f"  状态: {'开启' if alarm.Status == 1 else '关闭'}")

    if hasattr(alarm, "AlarmTargets") and alarm.AlarmTargets:
        parts.append("\n  📌 监控目标:")
        for t in alarm.AlarmTargets:
            parts.append(f"    - 主题ID: {t.TopicId if hasattr(t, 'TopicId') else 'N/A'}")
            parts.append(f"      查询: {t.Query if hasattr(t, 'Query') else 'N/A'}")

    if hasattr(alarm, "Condition") and alarm.Condition:
        parts.append(f"\n  ⚡ 触发条件: {alarm.Condition}")

    if hasattr(alarm, "TriggerCount") and alarm.TriggerCount:
        parts.append(f"  触发次数阈值: {alarm.TriggerCount}")

    if hasattr(alarm, "AlarmPeriod") and alarm.AlarmPeriod:
        parts.append(f"  告警周期: {alarm.AlarmPeriod} 分钟")

    if hasattr(alarm, "AlarmNoticeIds") and alarm.AlarmNoticeIds:
        parts.append(f"\n  🔔 通知渠道ID: {', '.join(alarm.AlarmNoticeIds)}")

    if hasattr(alarm, "CreateTime") and alarm.CreateTime:
        parts.append(f"\n  创建时间: {alarm.CreateTime}")
    if hasattr(alarm, "UpdateTime") and alarm.UpdateTime:
        parts.append(f"  更新时间: {alarm.UpdateTime}")

    return "\n".join(parts)


@cls_tool(
    name="cls_describe_alarm_notices",
    level=ToolLevel.READ,
    description="""查询告警通知渠道列表。获取当前账号配置的告警通知方式（如邮件、短信、回调等）。

### 参数说明
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- name: 按通知名称过滤（可选）""",
)
@handle_api_error
async def cls_describe_alarm_notices(
    offset: int = 0,
    limit: int = 20,
    name: str = "",
    region: str = "",
) -> str:
    """查询告警通知渠道列表"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeAlarmNoticesRequest()
    req.Offset = offset
    req.Limit = min(limit, 100)

    if name:
        f = models.Filter()
        f.Key = "name"
        f.Values = [name]
        req.Filters = [f]

    resp = await asyncio.to_thread(client.DescribeAlarmNotices, req)

    if not resp.AlarmNotices:
        return "📭 未找到告警通知渠道"

    items = []
    for notice in resp.AlarmNotices:
        item = {
            "通知ID": notice.AlarmNoticeId,
            "名称": notice.Name,
            "类型": notice.Type,
        }
        if hasattr(notice, "NoticeReceivers") and notice.NoticeReceivers:
            item["接收人数"] = len(notice.NoticeReceivers)
        if hasattr(notice, "WebCallbacks") and notice.WebCallbacks:
            item["回调数"] = len(notice.WebCallbacks)
        items.append(item)

    return format_list_result(items, "告警通知渠道", total=resp.TotalCount)


@cls_tool(
    name="cls_describe_alarm_records",
    level=ToolLevel.READ,
    description="""查询告警历史记录。查看最近的告警触发记录，了解告警发生的时间、原因和处理状态。

### 参数说明
- start_time: 起始时间，Unix 时间戳（毫秒），如 1700000000000（必填）
- end_time: 结束时间，Unix 时间戳（毫秒）（必填）
- offset: 分页偏移量，默认 0
- limit: 每页条数，默认 20
- alarm_id: 按告警策略 ID 过滤（可选）
- topic_id: 按监控对象（日志主题）ID 过滤（可选）
- status: 按告警状态过滤（可选）：0=未恢复，1=已恢复，2=已失效
- alarm_level: 按告警等级过滤（可选）：0=警告，1=提醒，2=紧急

### 适用场景
- 排查某个告警策略的历史触发情况
- 查看某个日志主题关联的所有告警记录
- 按状态或等级筛选告警记录
- 了解最近告警的总体趋势

### 注意事项
- ⏰ **start_time/end_time 为毫秒时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**""",
)
@handle_api_error
async def cls_describe_alarm_records(
    start_time: int,
    end_time: int,
    offset: int = 0,
    limit: int = 20,
    alarm_id: str = "",
    topic_id: str = "",
    status: int | None = None,
    alarm_level: int | None = None,
    region: str = "",
) -> str:
    """查询告警历史记录"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeAlertRecordHistoryRequest()
    req.From = start_time
    req.To = end_time
    req.Offset = offset
    req.Limit = min(limit, 100)

    filters = []
    if alarm_id:
        f = models.Filter()
        f.Key = "alertId"
        f.Values = [alarm_id]
        filters.append(f)
    if topic_id:
        f = models.Filter()
        f.Key = "topicId"
        f.Values = [topic_id]
        filters.append(f)
    if status is not None:
        f = models.Filter()
        f.Key = "status"
        f.Values = [str(status)]
        filters.append(f)
    if alarm_level is not None:
        f = models.Filter()
        f.Key = "alarmLevel"
        f.Values = [str(alarm_level)]
        filters.append(f)
    if filters:
        req.Filters = filters

    resp = await asyncio.to_thread(client.DescribeAlertRecordHistory, req)

    if not resp.Records:
        return "📭 暂无告警历史记录"

    # 字段映射：SDK 属性名 -> 显示名称
    field_map = {
        "RecordId": "记录ID",
        "AlarmId": "告警策略ID",
        "AlarmName": "告警名称",
        "AlarmLevel": "告警等级",
        "Region": "地域",
        "TopicId": "日志主题ID",
        "TopicName": "日志主题名称",
        "Status": "告警状态",
        "Duration": "持续时长",
        "Trigger": "触发条件",
        "TriggerCount": "连续触发次数",
        "AlarmPeriod": "告警周期(分钟)",
        "Notices": "通知渠道",
        "CreateTime": "创建时间",
        "MonitorObjectType": "监控对象类型",
        "SendType": "发送类型",
        "GroupTriggerCondition": "分组触发条件",
    }

    # 状态和等级的可读映射
    status_map = {0: "未恢复", 1: "已恢复", 2: "已失效"}
    level_map = {0: "警告(Warn)", 1: "提醒(Info)", 2: "紧急(Critical)"}

    items = []
    for record in resp.Records:
        item = {}
        for attr, label in field_map.items():
            if not hasattr(record, attr) or getattr(record, attr) is None:
                continue
            value = getattr(record, attr)
            # 特殊格式化
            if attr == "Duration":
                value = f"{value}秒"
            elif attr == "Status":
                value = status_map.get(value, str(value))
            elif attr == "AlarmLevel":
                value = level_map.get(value, str(value))
            elif attr == "Notices" and isinstance(value, list):
                value = [
                    n.Name if hasattr(n, "Name") else str(n) for n in value
                ]
            item[label] = value
        items.append(item)

    return format_list_result(items, "告警历史记录", total=resp.TotalCount)


# ============================================================
# 写操作（需 CLS_ENABLE_WRITE=true）
# ============================================================


@cls_tool(
    name="cls_create_alarm",
    level=ToolLevel.WRITE,
    description="""创建告警策略。配置日志监控条件，当满足触发规则时自动发送告警通知。

### 参数说明
- name: 告警策略名称（必填）
- alarm_targets_json: 监控目标 JSON 数组字符串（必填），每项包含:
    - TopicId: 日志主题 ID
    - Query: 查询语句
    - Number: 查询序号（从 1 开始）
    - StartTimeOffset: 开始时间偏移（分钟），如 -15
    - EndTimeOffset: 结束时间偏移（分钟），如 0
    - SyntaxRule: 语法规则，1 为 CQL
- condition: 触发条件表达式（必填），如 `$1.count > 100`
- trigger_count: 连续触发次数阈值（必填），建议至少 1
- alarm_period: 告警周期（分钟），如 15
- alarm_notice_ids: 通知渠道 ID 列表（JSON 数组字符串），如 `["notice-xxx"]`

### 示例
创建一个"5分钟内错误日志超100条"的告警:
```json
alarm_targets_json: [{"TopicId":"xxx","Query":"level:ERROR | SELECT COUNT(*) AS count","Number":1,"StartTimeOffset":-5,"EndTimeOffset":0,"SyntaxRule":1}]
condition: "$1.count > 100"
trigger_count: 1
```""",
)
@handle_api_error
async def cls_create_alarm(
    name: str,
    alarm_targets_json: str,
    condition: str,
    trigger_count: int = 1,
    alarm_period: int = 15,
    alarm_notice_ids: str = "[]",
    region: str = "",
) -> str:
    """创建告警策略"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.CreateAlarmRequest()
    req.Name = name
    req.Condition = condition
    req.TriggerCount = trigger_count
    req.AlarmPeriod = alarm_period

    # 解析监控目标
    targets_data = parse_json_param(alarm_targets_json, "alarm_targets_json")
    targets = []
    for t_data in targets_data:
        target = models.AlarmTarget()
        target.TopicId = t_data["TopicId"]
        target.Query = t_data["Query"]
        target.Number = t_data.get("Number", 1)
        target.StartTimeOffset = t_data.get("StartTimeOffset", -15)
        target.EndTimeOffset = t_data.get("EndTimeOffset", 0)
        target.SyntaxRule = t_data.get("SyntaxRule", 1)
        targets.append(target)
    req.AlarmTargets = targets

    # 解析通知渠道
    notice_ids = parse_json_param(alarm_notice_ids, "alarm_notice_ids")
    if notice_ids:
        req.AlarmNoticeIds = notice_ids

    resp = await asyncio.to_thread(client.CreateAlarm, req)

    return f"✅ 告警策略创建成功\n告警ID: {resp.AlarmId}\n名称: {name}\n触发条件: {condition}"


@cls_tool(
    name="cls_modify_alarm",
    level=ToolLevel.WRITE,
    description="""修改告警策略。更新告警策略的名称、监控条件、触发规则等配置。

### 参数说明
- alarm_id: 要修改的告警策略 ID（必填）
- name: 新的策略名称（可选）
- condition: 新的触发条件（可选）
- status: 告警状态，true 开启 / false 关闭（可选）
- alarm_period: 新的告警周期（分钟，可选）

### 注意
仅传入需要修改的字段，未传入的字段保持不变。""",
)
@handle_api_error
async def cls_modify_alarm(
    alarm_id: str,
    name: str = "",
    condition: str = "",
    status: bool | None = None,
    alarm_period: int | None = None,
    region: str = "",
) -> str:
    """修改告警策略"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.ModifyAlarmRequest()
    req.AlarmId = alarm_id

    if name:
        req.Name = name
    if condition:
        req.Condition = condition
    if status is not None:
        req.Status = 1 if status else 0
    if alarm_period is not None:
        req.AlarmPeriod = alarm_period

    resp = await asyncio.to_thread(client.ModifyAlarm, req)

    changes = []
    if name:
        changes.append(f"名称 -> {name}")
    if condition:
        changes.append(f"触发条件 -> {condition}")
    if status is not None:
        changes.append(f"状态 -> {'开启' if status else '关闭'}")
    if alarm_period is not None:
        changes.append(f"告警周期 -> {alarm_period}分钟")

    return f"✅ 告警策略修改成功\n告警ID: {alarm_id}\n修改内容: {'; '.join(changes) if changes else '无变更'}"


@cls_tool(
    name="cls_delete_alarm",
    level=ToolLevel.DANGER,
    description="""删除告警策略。删除后不可恢复，相关的告警监控将停止。

### 参数说明
- alarm_id: 要删除的告警策略 ID（必填）""",
)
@handle_api_error
async def cls_delete_alarm(
    alarm_id: str,
    region: str = "",
) -> str:
    """删除告警策略"""
    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DeleteAlarmRequest()
    req.AlarmId = alarm_id

    resp = await asyncio.to_thread(client.DeleteAlarm, req)

    return f"✅ 告警策略已删除\n告警ID: {alarm_id}"


# ============================================================
# 告警详情（免密接口，不走 CLS SDK）
# ============================================================

# 允许访问的域名白名单后缀，防止 SSRF
_ALLOWED_DOMAINS = (
    ".cls.tencentcs.com",
    ".tencent.com",
)

# 短链接域名模式
_SHORT_URL_PATTERNS = (
    re.compile(r"^https?://alarm\.cls\.tencentcs\.com/\w+$"),
    re.compile(r"^https?://mc\.tencent\.com/\w+$"),
)


def _is_short_url(url: str) -> bool:
    """判断是否为告警短链接"""
    return any(p.match(url) for p in _SHORT_URL_PATTERNS)


def _is_allowed_domain(domain: str) -> bool:
    """校验域名是否在白名单中"""
    return any(domain.endswith(suffix) for suffix in _ALLOWED_DOMAINS)


async def _resolve_short_url(url: str) -> str:
    """跟踪短链接 302 重定向，返回最终长链接"""
    async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
        resp = await client.get(url)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            if not location:
                raise ValueError(f"短链接重定向未返回 Location 头: {url}")
            return location
        raise ValueError(
            f"短链接未返回重定向响应（HTTP {resp.status_code}）: {url}"
        )


def _parse_record_id_from_url(long_url: str) -> tuple[str, str]:
    """从长链接中提取 RecordId 和 API 域名。

    Returns:
        (record_id, api_domain) 元组
    """
    parsed = urlparse(long_url)

    # 从 fragment（#/alert?RecordId=xxx）或 query 中提取 RecordId
    record_id = ""

    # 优先尝试从 fragment 部分提取（长链接格式 #/alert?RecordId=xxx）
    if parsed.fragment:
        # fragment 可能是 /alert?RecordId=xxx&JumpDomainID=yyy
        frag_match = re.search(r"RecordId=([a-fA-F0-9-]+)", parsed.fragment)
        if frag_match:
            record_id = frag_match.group(1)

    # 其次从 query 参数中提取
    if not record_id:
        query_params = parse_qs(parsed.query)
        if "RecordId" in query_params:
            record_id = query_params["RecordId"][0]

    if not record_id:
        raise ValueError(f"无法从 URL 中提取 RecordId: {long_url}")

    # 域名直接从长链接截取，用于拼接 GetAlertDetail API
    api_domain = parsed.hostname
    if not api_domain or not _is_allowed_domain(api_domain):
        raise ValueError(f"不支持的域名: {api_domain}")

    return record_id, api_domain


async def _fetch_alarm_detail(api_domain: str, record_id: str) -> dict[str, object]:
    """调用免密 API 获取告警详情"""
    api_url = f"https://{api_domain}/cls_no_login?action=GetAlertDetail"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            api_url,
            json={"RecordId": record_id},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    # API 返回格式可能是 {"Response": {"Record": ...}} 或 {"Record": ...}
    if "Response" in data:
        data = data["Response"]

    if "Record" not in data:
        error_code = data.get("Error", {}).get("Code", "")
        error_msg = data.get("Error", {}).get("Message", "未知错误")
        if "ERR_INVALID_REQUEST" in error_code or "ERR_INVALID_REQUEST" in error_msg:
            raise ValueError("告警记录已失效或不存在，无法获取详情")
        raise ValueError(f"告警详情接口返回异常: {error_msg}")

    return data


def _format_alarm_detail_markdown(data: dict[str, object]) -> str:
    """将告警详情 JSON 格式化为 Markdown"""
    record = data.get("Record", {})
    snapshot = record.get("ResultsSnapshot", record.get("AlertSnapshot", {}))

    # 如果 ResultsSnapshot 不存在，尝试从顶层 Record 中取
    if not snapshot:
        snapshot = record

    parts: list[str] = []

    # === 1. 告警基本信息 ===
    parts.append("### ⚠️ 1. 告警基本信息\n")
    alarm_name = snapshot.get("AlertName") or snapshot.get("Alarm") or record.get("AlertName", "未知")
    parts.append(f"- **告警名称**: {alarm_name}")

    alarm_id = snapshot.get("AlertID") or snapshot.get("AlarmID") or record.get("AlertId", "")
    if alarm_id:
        parts.append(f"- **告警策略ID**: {alarm_id}")

    record_id = snapshot.get("RecordId") or record.get("RecordId", "")
    if record_id:
        parts.append(f"- **告警记录ID**: {record_id}")

    level = snapshot.get("Level") or ""
    level_zh = snapshot.get("level_zh") or ""
    if level or level_zh:
        level_display = f"{level_zh}({level})" if level_zh and level else (level_zh or level)
        parts.append(f"- **告警级别**: {level_display}")

    region = snapshot.get("Region") or ""
    if region:
        parts.append(f"- **地域**: {region}")

    platform = snapshot.get("PlatForm") or ""
    if platform:
        parts.append(f"- **平台**: {platform}")

    nickname = snapshot.get("Nickname") or ""
    uin = snapshot.get("UIN") or ""
    if nickname or uin:
        account = f"{nickname}(ID:{uin})" if nickname and uin else (nickname or str(uin))
        parts.append(f"- **账号**: {account}")

    # === 2. 告警详细数据 ===
    parts.append("\n### 🔍 2. 告警详细数据\n")

    topic_name = snapshot.get("TopicName") or ""
    topic_id = snapshot.get("TopicId") or snapshot.get("MonitoredObject") or ""
    if topic_name or topic_id:
        topic_display = f"{topic_name} (`{topic_id}`)" if topic_name and topic_id else (topic_name or topic_id)
        parts.append(f"- **监控对象**: {topic_display}")

    logset_name = snapshot.get("LogsetName") or ""
    logset_id = snapshot.get("LogsetId") or ""
    if logset_name or logset_id:
        logset_display = f"{logset_name} (`{logset_id}`)" if logset_name and logset_id else (logset_name or logset_id)
        parts.append(f"- **日志集**: {logset_display}")

    # 触发时间
    fire_time_unix = snapshot.get("FireTime") or snapshot.get("StartTimeUnix")
    notify_time = snapshot.get("NotifyTime") or snapshot.get("StartTime") or ""
    if notify_time:
        parts.append(f"- **告警触发时间**: {notify_time}")
    elif fire_time_unix:
        parts.append(f"- **告警触发时间**: {format_timestamp(fire_time_unix)}")

    # 持续时间
    duration = snapshot.get("Duration")
    if duration is not None:
        parts.append(f"- **持续时间**: {duration} 分钟")

    # 触发条件和当前值
    condition = snapshot.get("Condition") or snapshot.get("Trigger") or ""
    if condition:
        parts.append(f"- **触发条件**: `{condition}`")

    trigger_params = snapshot.get("TriggerParams") or ""
    if trigger_params:
        parts.append(f"- **当前值**: `{trigger_params}`")

    # 连续告警次数
    consecutive = snapshot.get("ConsecutiveAlertNums")
    if consecutive:
        parts.append(f"- **连续告警次数**: {consecutive}")

    happenthreshold = snapshot.get("HappenThreshold")
    if happenthreshold:
        parts.append(f"- **触发阈值**: {happenthreshold}")

    # === 3. 触发语句 ===
    parts.append("\n### 📝 3. 触发语句\n")

    # 从 QueryParams 中提取查询语句
    query_params = snapshot.get("QueryParams") or []
    if query_params:
        for i, qp in enumerate(query_params):
            query = qp.get("Query", "")
            topic = qp.get("TopicName", "")
            start_t = qp.get("StartTime")
            end_t = qp.get("EndTime")
            if query:
                parts.append(f"**查询 #{i+1}**" + (f" (主题: {topic})" if topic else ""))
                parts.append(f"```sql\n{query}\n```")
                if start_t and end_t:
                    parts.append(f"- 查询时间范围: {format_timestamp(start_t)} ~ {format_timestamp(end_t)}")
    else:
        # 回退到顶层 Query 字段
        query = snapshot.get("Query") or ""
        if query:
            parts.append(f"```sql\n{query}\n```")

    # 原始查询结果
    raw_results = snapshot.get("RawResults") or []
    if raw_results:
        parts.append("\n**查询结果**:")
        for i, result_group in enumerate(raw_results):
            if isinstance(result_group, list):
                for row in result_group:
                    if isinstance(row, dict):
                        row_str = ", ".join(f"{k}={v}" for k, v in row.items())
                        parts.append(f"- `{row_str}`")

    # === 4. 多维分析结果 ===
    analysis_info = snapshot.get("AnalysisInfo") or []
    if analysis_info:
        parts.append("\n### 📊 4. 多维分析结果\n")
        for ai in analysis_info:
            name = ai.get("Name", "")
            content = ai.get("Content", "")
            if name:
                parts.append(f"**{name}**")
            if content:
                parts.append(f"```sql\n{content}\n```")

            # 分析结果数据
            analysis_results = ai.get("AnalysisResults") or []
            if analysis_results:
                # 提取表头
                if analysis_results and isinstance(analysis_results[0], dict):
                    first_row_data = analysis_results[0].get("Data", [])
                    if first_row_data:
                        headers = [d.get("Key", "") for d in first_row_data]
                        parts.append("| " + " | ".join(headers) + " |")
                        parts.append("| " + " | ".join(["---"] * len(headers)) + " |")
                        for ar in analysis_results:
                            row_data = ar.get("Data", [])
                            values = [d.get("Value", "") for d in row_data]
                            parts.append("| " + " | ".join(values) + " |")

    # 格式化后的分析结果文本
    analysis_format = snapshot.get("AnalysisResultFormat") or ""
    if analysis_format and not analysis_info:
        parts.append("\n### 📊 4. 分析结果\n")
        parts.append(f"```\n{analysis_format}\n```")

    # === 5. 自定义告警内容 ===
    custom_msg = snapshot.get("CustomizeMessage") or ""
    if custom_msg:
        parts.append("\n### 💬 5. 告警通知内容\n")
        parts.append(f"```\n{custom_msg.strip()}\n```")

    # === 相关链接 ===
    detail_url = snapshot.get("DetailUrl") or ""
    query_url = snapshot.get("QueryUrl") or ""
    claim_url = snapshot.get("ClaimUrl") or ""
    if detail_url or query_url or claim_url:
        parts.append("\n### 🔗 相关链接\n")
        if detail_url:
            parts.append(f"- [告警详情]({detail_url})")
        if query_url:
            parts.append(f"- [查看日志]({query_url})")
        if claim_url:
            parts.append(f"- [认领告警]({claim_url})")

    return "\n".join(parts)


@cls_tool(
    name="cls_get_alarm_detail",
    level=ToolLevel.READ,
    description="""通过告警详情URL获取CLS告警的详细信息。从腾讯云告警详情URL中提取和解析告警信息，支持短链接和长链接格式。
该工具会自动解析URL、获取告警详情，并返回格式化的Markdown文档。

### 两种查询方式（二选一）

**方式一：通过 URL 查询**
- 传入 url 参数（短链接或长链接），工具自动解析并获取告警详情

**方式二：通过 record_id + region 查询**
- 传入 record_id 和 region 参数，工具直接构造 API 请求获取告警详情
- 这两个参数可从 cls_describe_alarm_records 工具的返回结果中获取

### 参数说明
- url: 告警详情 URL（可选），与 record_id+region 二选一
- record_id: 告警记录 ID（可选），从 cls_describe_alarm_records 获取
- region: 地域标识（可选），如 ap-guangzhou、ap-shanghai，从 cls_describe_alarm_records 获取

### 支持的URL格式
1. 短链接：https://alarm.cls.tencentcs.com/WeNZ5sSP
2. 短链接：https://mc.tencent.com/xxx
3. 长链接：https://ap-guangzhou-open-monitor.cls.tencentcs.com/cls_no_login?action=GetAlertDetailPage#/alert?RecordId=xxx

### 返回内容
- ⚠️ 告警基本信息（名称、ID、级别、地域）
- 🔍 告警详细数据（监控对象、触发时间、持续时间、触发条件、当前值）
- 📝 触发语句（CQL/SQL 查询）
- 📊 多维分析结果（如有）
- 💬 告警通知内容
- 🔗 相关链接（详情页、日志查询、认领）

### 应用场景
1. 快速查看告警详情：直接粘贴告警通知中的URL即可获取完整信息
2. 从告警记录列表查看详情：先用 cls_describe_alarm_records 获取 record_id 和 region，再调用本工具
3. 告警问题排查：查看告警触发条件、触发值、查询语句等关键信息

### 注意事项
- url 与 record_id+region 二选一，不能同时提供或同时为空
- 短链接会自动跳转到长链接进行解析
- 此接口为免密接口，无需额外认证信息""",
)
@handle_api_error
async def cls_get_alarm_detail(
    url: str = "",
    record_id: str = "",
    region: str = "",
) -> str:
    """通过告警 URL 或 record_id + region 获取告警详情"""
    url = url.strip()
    record_id = record_id.strip()
    region = region.strip()

    has_url = bool(url)
    has_record_id = bool(record_id and region)

    # 参数校验：二选一
    if has_url and has_record_id:
        return "❌ 请只提供 url 或 (record_id + region) 其中一组参数，不要同时提供"
    if not has_url and not has_record_id:
        if record_id and not region:
            return "❌ 使用 record_id 查询时，region 参数也是必填的"
        return "❌ 请提供 url 或 (record_id + region) 参数"

    if has_record_id:
        # 方式二：record_id + region 直接查询
        # region 格式校验，仅允许合法的腾讯云地域标识
        if not re.match(r"^[a-z]{2}-[a-z]+((-[a-z]+)?(-\d+)?)$", region):
            return f"❌ region 格式不合法: {region}，应为类似 ap-guangzhou、ap-shanghai 的格式"
        api_domain = f"{region}-monitor.cls.tencentcs.com"
        logger.info("直接查询模式: RecordId=%s, Region=%s", record_id, region)
        data = await _fetch_alarm_detail(api_domain, record_id)
        return _format_alarm_detail_markdown(data)

    # 方式一：URL 解析模式（原有逻辑）
    if _is_short_url(url):
        logger.info("检测到短链接，正在跟踪重定向: %s", url)
        long_url = await _resolve_short_url(url)
        logger.info("短链接跳转到: %s", long_url)
    else:
        long_url = url

    record_id_parsed, api_domain = _parse_record_id_from_url(long_url)
    logger.info("解析到 RecordId=%s, 域名=%s", record_id_parsed, api_domain)

    data = await _fetch_alarm_detail(api_domain, record_id_parsed)
    return _format_alarm_detail_markdown(data)
