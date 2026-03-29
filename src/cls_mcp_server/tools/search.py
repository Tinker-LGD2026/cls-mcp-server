"""日志查询分析工具模块

提供日志检索、上下文查询、直方图统计等核心日志查询能力。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.utils.errors import handle_api_error
from cls_mcp_server.utils.formatter import (
    format_log_results,
    format_timestamp_ms,
    truncate_text,
)
from cls_mcp_server.utils.validators import (
    validate_log_context_params,
    validate_log_count_params,
    validate_log_histogram_params,
    validate_search_log_params,
)

logger = logging.getLogger(__name__)

# 语法参考文档路径：从包内 reference/ 目录加载
_SYNTAX_DOC_PATH = Path(__file__).resolve().parent.parent / "reference" / "cls_extension_syntax.md"


# ============================================================
# CQL 语法参考（嵌入到 Tool 描述中，引导 LLM 生成查询）
# ============================================================
CQL_SYNTAX_GUIDE = """
## CQL 语法速查

CQL (CLS Query Language) 是 CLS 自研的检索分析语法，语句结构为：`[检索条件] | [SQL 语句]`。
检索条件用于过滤日志，SQL 用于统计分析。不需要分析时可省略 `|` 及 SQL 部分。

### 检索语法
- **键值检索**: `status:404`、`level:ERROR`（字段值包含该词）
- **全文检索**: `error`、`timeout`（全文中包含该词）
- **短语检索**: `"connection timeout"` 或 `'user_name:"bob"'`（精确短语，支持通配符如 `"/var/log/acc*.log"`）
- **逻辑操作符**: `AND`、`OR`、`NOT`（不区分大小写，AND 优先级高于 OR）
- **分组**: `level:(ERROR OR WARNING) AND pid:1234`
- **数值比较**: `status:>400`、`status:>=400`、`status:=200`、`latency:<100`
- **模糊匹配**: `host:www.test*.com`（`*` 匹配零到多个字符，不支持前缀模糊如 `*test`）
- **字段存在性**: `key:*`（字段存在）、`key:""`（字段存在但值为空）
- **转义**: `body:user_name\\:bob`（特殊字符用 `\\` 转义）

### SQL 分析（检索条件 | SQL，无需 FROM 和分号）
- 字符串用单引号 `''`，字段名冲突用双引号 `""`
- `* | SELECT COUNT(*) AS total`
- `* | SELECT status, COUNT(*) AS cnt GROUP BY status ORDER BY cnt DESC`
- 默认返回 100 行，LIMIT 最大 100 万行

### CLS 扩展函数
- **histogram**（时间分桶）: `histogram(__TIMESTAMP__, interval 1 hour)` — 直接传 LONG 型，自动 UTC+8
- **time_series**（时序补全）: `time_series(__TIMESTAMP__, '5m', '%Y-%m-%d %H:%i:%s', '0')` — 必须 GROUP BY + ORDER BY，不支持 DESC，分钟用 %i
- **compare**（同环比）: `compare(count(*), 86400)` — 返回数组下标从 1 开始，86400=日/604800=周
- **IP 地理**: `ip_to_province/city/country/provider(ip)`
- **百分位**: `APPROX_PERCENTILE(field, 0.99)`

### 关键注意
- CQL 是 CLS 推荐语法（SyntaxRule=1），相比 Lucene 更简便，特殊字符限制更少
- CQL 中多个分词默认为 AND 关系（Lucene 默认为 OR）
- `__TIMESTAMP__` 是 bigint 毫秒时间戳，`from_unixtime` 要除 1000
- 脏数据用 `try_cast` 代替 `cast`
- 时区：histogram/time_series 传 LONG 型自动 UTC+8，其他日期函数默认 UTC+0，需手动加 8 小时
"""


@cls_tool(
    name="cls_search_log",
    level=ToolLevel.READ,
    description=f"""检索分析 CLS 日志。支持 CQL 检索和 SQL 管道分析。

{CQL_SYNTAX_GUIDE}

### 参数说明
- topic_id: 日志主题 ID（必填）
- query: CQL 检索语句（必填），如 `level:ERROR` 或 `* | SELECT COUNT(*) as cnt`
- start_time: 起始时间，Unix 时间戳（毫秒）
- end_time: 结束时间，Unix 时间戳（毫秒）
- limit: 返回条数，默认 100，最大 1000（仅对原始日志有效，SQL 分析不受此限制）
- context: 翻页游标，首次查询无需传入，从上次返回结果获取
- sort: 排序方式，asc（升序）或 desc（降序，默认）

### 注意事项
- ⏰ **start_time/end_time 为毫秒时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**
- 💡 **编写 SQL 分析语句前，建议先调用 cls_describe_index 获取索引配置，确认字段名称和类型**
- ❌ **CQL 执行报错时，可调用 cls_describe_search_syntax 获取 CLS 完整扩展语法参考文档**
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域""",
)
@handle_api_error
async def cls_search_log(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    limit: int = 100,
    context: str = "",
    sort: str = "desc",
    region: str = "",
) -> str:
    """检索分析 CLS 日志"""
    validate_search_log_params(topic_id, query, start_time, end_time, limit, sort)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.SearchLogRequest()
    req.TopicId = topic_id
    req.Query = query
    req.From = start_time
    req.To = end_time
    req.Limit = min(limit, 1000)
    req.SyntaxRule = 1  # 使用 CQL 语法
    req.Sort = sort

    if context:
        req.Context = context

    resp = await asyncio.to_thread(client.SearchLog, req)

    # 格式化结果
    parts: list[str] = []

    # 原始日志结果
    if resp.Results:
        parts.append(format_log_results(resp.Results, list_over=bool(resp.ListOver)))

    # SQL 分析结果
    if resp.AnalysisResults:
        parts.append("📈 SQL 分析结果:")
        for i, row in enumerate(resp.AnalysisResults[:50], 1):
            if hasattr(row, "Data") and row.Data:
                if isinstance(row.Data, list):
                    # Data 是 list[LogItem]，每个有 Key/Value
                    kv_pairs = {getattr(item, "Key", ""): getattr(item, "Value", "") for item in row.Data}
                    parts.append(f"  {i}. {kv_pairs}")
                else:
                    parts.append(f"  {i}. {row.Data}")
        if len(resp.AnalysisResults) > 50:
            parts.append(f"  ... (共 {len(resp.AnalysisResults)} 行，仅展示前 50 行)")

    # 翻页信息
    if not resp.ListOver and resp.Context:
        parts.append(f"\n📌 还有更多结果，使用 context=\"{resp.Context}\" 获取下一页")

    # Analysis 字段处理
    if resp.Analysis and resp.ColNames:
        parts.append(f"\n📊 分析列: {', '.join(resp.ColNames)}")

    if not parts:
        return "📭 未查询到匹配的日志记录。请检查 topic_id、时间范围和查询条件是否正确。"

    return "\n\n".join(parts)


@cls_tool(
    name="cls_get_log_context",
    level=ToolLevel.READ,
    description="""获取日志上下文。根据一条日志的定位信息，查看其前后的日志记录，用于排查问题时了解完整的日志上下文。

### 参数说明
- topic_id: 日志主题 ID（必填）
- btime: 目标日志的时间，支持两种格式：
  1. **Unix 毫秒时间戳**（如 `1774537847429`）：工具内部自动转换为所需格式，可直接使用 cls_search_log 返回的"时间"对应的毫秒时间戳
  2. **字符串格式** `YYYY-mm-dd HH:MM:SS.FFF`（如 `2026-03-25 14:25:00.000`，UTC+8 时区）：用户自行构造的时间字符串
- pkg_id: 目标日志的包序号（从 cls_search_log 返回的 PkgId 字段获取）
- pkg_log_id: 目标日志在包内的序号（从 cls_search_log 返回的 PkgLogId 字段获取）
- prev_logs: 向前获取的日志条数，默认 10，最大 100
- next_logs: 向后获取的日志条数，默认 10，最大 100

### 使用流程
1. 先用 cls_search_log 查找目标日志
2. 从结果中获取 PkgId、PkgLogId，以及"时间"对应的毫秒时间戳（或自行构造 btime 字符串）
3. 用这些信息调用本工具获取上下文

### 注意事项
- 支持传入毫秒时间戳（纯数字）或 `YYYY-mm-dd HH:MM:SS.FFF` 格式字符串
- 毫秒精度会影响定位准确性，建议尽量使用精确的时间值
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_get_log_context(
    topic_id: str,
    btime: str,
    pkg_id: str,
    pkg_log_id: int,
    prev_logs: int = 10,
    next_logs: int = 10,
    region: str = "",
) -> str:
    """获取日志上下文"""
    validate_log_context_params(topic_id, btime, pkg_id, pkg_log_id, prev_logs, next_logs)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    # 自动检测 btime 格式：若为纯数字（毫秒时间戳），自动转换为 YYYY-mm-dd HH:MM:SS.FFF
    btime_str = str(btime).strip()
    if btime_str.isdigit():
        btime_str = format_timestamp_ms(int(btime_str))

    req = models.DescribeLogContextRequest()
    req.TopicId = topic_id
    req.BTime = btime_str
    req.PkgId = pkg_id
    req.PkgLogId = int(pkg_log_id)
    req.PrevLogs = min(prev_logs, 100)
    req.NextLogs = min(next_logs, 100)

    resp = await asyncio.to_thread(client.DescribeLogContext, req)

    parts: list[str] = [f"📜 日志上下文（前 {prev_logs} 条 + 后 {next_logs} 条）"]

    logs = resp.LogContextInfos or []
    target_found = False

    for log_item in logs:
        # 通过 PkgId + PkgLogId 精确匹配目标日志
        is_target = (
            hasattr(log_item, "PkgId") and log_item.PkgId == pkg_id
            and hasattr(log_item, "PkgLogId") and str(log_item.PkgLogId) == str(pkg_log_id)
        )

        if is_target:
            target_found = True
            marker = "🎯"
        elif not target_found:
            marker = "⬆️"
        else:
            marker = "⬇️"

        line = f"{marker} "
        if hasattr(log_item, "BTime") and log_item.BTime:
            btime_val = log_item.BTime
            try:
                btime_int = int(float(btime_val))
                line += f"[{format_timestamp_ms(btime_int)} ({btime_int})] "
            except (ValueError, TypeError):
                line += f"[{btime_val}] "
        if hasattr(log_item, "Source") and log_item.Source:
            line += f"({log_item.Source}) "
        if hasattr(log_item, "Content") and log_item.Content:
            try:
                content = json.loads(log_item.Content)
                line += json.dumps(content, ensure_ascii=False)
            except json.JSONDecodeError:
                line += log_item.Content
        parts.append(line)

    if not logs:
        parts.append("未找到上下文日志")

    if hasattr(resp, "PrevOver") and resp.PrevOver:
        parts.append("\n📌 上文日志已全部返回")
    if hasattr(resp, "NextOver") and resp.NextOver:
        parts.append("📌 下文日志已全部返回")

    return truncate_text("\n".join(parts), max_length=8000)


@cls_tool(
    name="cls_get_log_histogram",
    level=ToolLevel.READ,
    description="""获取日志数量直方图。统计指定时间范围内日志在时间维度上的分布情况，用于观察日志量趋势和异常波动。

### 参数说明
- topic_id: 日志主题 ID（必填）
- query: CQL 检索语句（必填），如 `level:ERROR` 或 `*`（全部日志）
- start_time: 起始时间，Unix 时间戳（毫秒）
- end_time: 结束时间，Unix 时间戳（毫秒）
- interval: 时间间隔（毫秒），系统会自动选择合适间隔，也可手动指定

### 适用场景
- 观察日志量随时间的变化趋势
- 发现某个时间段的日志突增或突降
- 结合 cls_search_log 定位具体异常时段

### 注意事项
- ⏰ **start_time/end_time 为毫秒时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**
- 💡 **编写 SQL 分析语句前，建议先调用 cls_describe_index 获取目标主题的索引配置，确认字段名称、类型及是否开启统计，避免因字段信息不明确导致查询失败**
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域""",
)
@handle_api_error
async def cls_get_log_histogram(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    interval: int | None = None,
    region: str = "",
) -> str:
    """获取日志数量直方图"""
    validate_log_histogram_params(topic_id, query, start_time, end_time, interval)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    req = models.DescribeLogHistogramRequest()
    req.TopicId = topic_id
    req.Query = query
    req.From = start_time
    req.To = end_time
    req.SyntaxRule = 1  # CQL 语法

    if interval is not None:
        req.Interval = interval

    resp = await asyncio.to_thread(client.DescribeLogHistogram, req)

    parts: list[str] = [f"📊 日志直方图（{format_timestamp_ms(start_time)} ~ {format_timestamp_ms(end_time)}）"]

    total_count = 0
    if resp.HistogramInfos:
        parts.append(f"时间间隔: {resp.Interval}ms | 共 {len(resp.HistogramInfos)} 个时间桶")
        parts.append("")

        max_count = max((h.Count for h in resp.HistogramInfos), default=1)

        for h in resp.HistogramInfos:
            total_count += h.Count
            # 文本柱状图
            bar_len = int((h.Count / max_count) * 30) if max_count > 0 else 0
            bar = "█" * bar_len
            time_str = format_timestamp_ms(h.BTime)
            parts.append(f"  {time_str} | {bar} {h.Count}")

        parts.append(f"\n总计: {total_count} 条日志")
    else:
        parts.append("📭 该时间范围内无日志数据")

    return "\n".join(parts)


@cls_tool(
    name="cls_get_log_count",
    level=ToolLevel.READ,
    description="""快速获取日志数量。相比 cls_search_log 更快，适合只需要知道日志总数的场景。

### 参数说明
- topic_id: 日志主题 ID（必填）
- query: CQL 检索语句（必填）
- start_time: 起始时间，Unix 时间戳（毫秒）
- end_time: 结束时间，Unix 时间戳（毫秒）
- region: 地域（可选），如 ap-guangzhou、na-ashburn，不传则使用默认地域，可通过 cls_describe_regions 查询所有可用地域

### 适用场景
- 快速确认某类日志是否存在
- 统计特定时间范围内的日志总量

### 注意事项
- ⏰ **start_time/end_time 为毫秒时间戳，请先调用 cls_convert_time 工具转换，不要手动计算**
- 💡 **编写 SQL 分析语句前，建议先调用 cls_describe_index 获取目标主题的索引配置，确认字段名称、类型及是否开启统计，避免因字段信息不明确导致查询失败**""",
)
@handle_api_error
async def cls_get_log_count(
    topic_id: str,
    query: str,
    start_time: int,
    end_time: int,
    region: str = "",
) -> str:
    """快速获取日志数量"""
    validate_log_count_params(topic_id, query, start_time, end_time)

    config = get_config()
    client = get_cls_client(config, region=region or None)

    # 通过 SQL 分析获取总数
    # 若 query 已包含 SQL 管道（如 "level:ERROR | SELECT ..."），仅保留检索部分
    if "|" in query:
        search_part = query.split("|", 1)[0].strip()
        count_query = f"{search_part} | SELECT COUNT(*) AS total"
    else:
        count_query = f"{query} | SELECT COUNT(*) AS total"

    req = models.SearchLogRequest()
    req.TopicId = topic_id
    req.Query = count_query
    req.From = start_time
    req.To = end_time
    req.Limit = 1
    req.SyntaxRule = 1

    resp = await asyncio.to_thread(client.SearchLog, req)

    if resp.AnalysisResults:
        for row in resp.AnalysisResults:
            if hasattr(row, "Data") and row.Data:
                try:
                    # Data 是 list[LogItem]，每个 LogItem 有 Key/Value 属性
                    if isinstance(row.Data, list):
                        for item in row.Data:
                            key = getattr(item, "Key", "")
                            value = getattr(item, "Value", "")
                            if key == "total":
                                return f"📊 日志数量: {value} 条\n时间范围: {format_timestamp_ms(start_time)} ~ {format_timestamp_ms(end_time)}\n查询条件: {query}"
                    # 兼容字符串格式
                    elif isinstance(row.Data, str):
                        data = json.loads(row.Data)
                        if isinstance(data, dict):
                            total = data.get("total", "未知")
                        else:
                            total = row.Data
                        return f"📊 日志数量: {total} 条\n时间范围: {format_timestamp_ms(start_time)} ~ {format_timestamp_ms(end_time)}\n查询条件: {query}"
                except (json.JSONDecodeError, AttributeError):
                    return f"📊 查询结果: {row.Data}"

    return "📊 无法获取日志数量，请检查查询条件"


@cls_tool(
    name="cls_describe_search_syntax",
    level=ToolLevel.READ,
    description="""CQL 检索分析语法完整参考文档。当 cls_search_log 执行报错或不确定如何编写查询语句时使用。

返回 CLS CQL 完整语法参考文档，包含：
- CQL 检索语法（键值检索、短语检索、逻辑操作符、数值比较、模糊匹配、字段存在性等）
- CQL 与 Lucene 语法的核心区别
- SQL 分析语法（管道符、FROM 省略、引号规则等）
- histogram（时间分桶）、time_series（时序补全）、compare（同环比）等 CLS 扩展函数
- IP 地理函数、百分位数函数等特殊函数
- 时区处理规则、脏数据处理、类型转换等关键注意事项

调用此工具不需要任何参数。""",
)
@handle_api_error
async def cls_describe_search_syntax() -> str:
    """返回 CLS 完整扩展语法参考文档"""
    try:
        return _SYNTAX_DOC_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    logger.warning("语法参考文档未找到，已降级为精简版本")
    return f"""# CLS CQL 检索分析语法参考
{CQL_SYNTAX_GUIDE}

## 额外说明
- CQL (CLS Query Language) 是 CLS 自研的检索分析语法，推荐优先使用（SyntaxRule=1）
- CQL 相比 Lucene 更简便：逻辑操作符不区分大小写、多分词默认 AND 关系、短语中支持通配符
- SQL 分析部分基于 Trino/Presto SQL，支持聚合函数和窗口函数
- 时间字段 __TIMESTAMP__ 为日志采集时间（毫秒级 Unix 时间戳）
- 查询语句大小限制: 最大 10KB
- SQL 分析默认返回 100 行，LIMIT 最大 100 万行
"""
