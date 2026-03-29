"""cls_text_to_cql 工具定义

统一的 Text2CQL 工具，支持三种模式：
- auto: 智能路由，根据用户输入自动判断走 syntax_only 或 generate
- syntax_only: 返回 CLS 独有扩展语法文档
- generate: 通过 LLM 将自然语言转换为 CQL 查询语句
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from tencentcloud.cls.v20201016 import models

from cls_mcp_server.auth import get_cls_client
from cls_mcp_server.tools._state import get_config
from cls_mcp_server.tools.registry import ToolLevel, cls_tool
from cls_mcp_server.tools.text_to_cql.cql_generator import CqlGenerator, CqlResult, LlmConfig
from cls_mcp_server.tools.text_to_cql.mode_router import route_mode
from cls_mcp_server.tools.text_to_cql.syntax_docs import get_syntax_docs
from cls_mcp_server.utils.errors import handle_api_error

logger = logging.getLogger(__name__)

# ---------- 索引信息 TTL 缓存 ----------
_INDEX_CACHE_TTL = 300.0  # 5 分钟
_index_cache: dict[tuple[str, str], tuple[float, str]] = {}


def _get_cached_index(topic_id: str, region: str) -> str | None:
    """查询索引缓存，过期或未命中返回 None"""
    cache_key = (topic_id, region)
    if cache_key in _index_cache:
        cached_time, cached_result = _index_cache[cache_key]
        if time.monotonic() - cached_time < _INDEX_CACHE_TTL:
            logger.debug("Index cache hit for topic=%s region=%s", topic_id, region)
            return cached_result
        # 过期，删除
        del _index_cache[cache_key]
    return None


def _set_cached_index(topic_id: str, region: str, data: str) -> None:
    """写入索引缓存"""
    _index_cache[(topic_id, region)] = (time.monotonic(), data)


def _get_llm_config() -> LlmConfig | None:
    """从 ServerConfig 获取 LLM 配置，未配置则返回 None"""
    config = get_config()
    if not all([config.llm_api_base, config.llm_api_key, config.llm_model]):
        return None

    return LlmConfig(
        api_base=config.llm_api_base,
        api_key=config.llm_api_key,
        model=config.llm_model,
    )


async def _fetch_index_info(topic_id: str, region: str = "") -> str:
    """获取主题索引信息，用于辅助 LLM 生成更精准的 CQL

    带 TTL 缓存（5 分钟），按 (topic_id, region) 维度缓存，避免重复 API 调用。

    Args:
        topic_id: 日志主题 ID
        region: 地域

    Returns:
        格式化的索引字段信息字符串，失败返回空字符串
    """
    # 查缓存
    cached = _get_cached_index(topic_id, region)
    if cached is not None:
        return cached

    try:
        config = get_config()
        client = get_cls_client(config, region=region or None)

        req = models.DescribeIndexRequest()
        req.TopicId = topic_id

        resp = await asyncio.to_thread(client.DescribeIndex, req)

        fields: list[str] = []
        if resp.Rule and resp.Rule.KeyValue and resp.Rule.KeyValue.KeyValues:
            for kv in resp.Rule.KeyValue.KeyValues:
                key = getattr(kv, "Key", "")
                value_info = getattr(kv, "Value", None)
                if key and value_info:
                    field_type = getattr(value_info, "Type", "text")
                    sql_flag = getattr(value_info, "SqlFlag", False)
                    stat = "统计" if sql_flag else ""
                    fields.append(f"  - {key} ({field_type}{', ' + stat if stat else ''})")

        if resp.Rule and resp.Rule.Tag and resp.Rule.Tag.KeyValues:
            for kv in resp.Rule.Tag.KeyValues:
                key = getattr(kv, "Key", "")
                value_info = getattr(kv, "Value", None)
                if key and value_info:
                    field_type = getattr(value_info, "Type", "text")
                    fields.append(f"  - {key} ({field_type}, 标签)")

        result = "可用字段：\n" + "\n".join(fields) if fields else ""

        # 写入缓存（即使空结果也缓存，避免对不存在索引的 topic 反复请求）
        _set_cached_index(topic_id, region, result)
        logger.debug("Index cache set for topic=%s region=%s (%d fields)", topic_id, region, len(fields))
        return result

    except Exception as e:
        logger.warning("Failed to fetch index info for topic %s: %s", topic_id, e)
        return ""


def _format_result(result: CqlResult, syntax_docs: str = "") -> str:
    """格式化输出结果"""
    parts: list[str] = []

    if result.mode == "syntax_only":
        parts.append("📖 CLS 独有扩展语法参考")
        parts.append("")
        parts.append(syntax_docs or get_syntax_docs())
        return "\n".join(parts)

    if result.success:
        parts.append("✅ CQL 生成成功")
        parts.append("")
        parts.append(f"```")
        parts.append(result.cql)
        parts.append(f"```")
        parts.append("")
        parts.append(f"⏱️ 耗时 {result.elapsed_ms}ms | 尝试 {result.attempts} 次")
        parts.append("")
        parts.append("💡 提示：请将生成的 CQL 传给 cls_search_log 工具执行查询。")
    else:
        parts.append("⚠️ CQL 生成未完全成功")
        parts.append("")
        if result.cql:
            parts.append("最佳结果（可能存在问题）：")
            parts.append(f"```")
            parts.append(result.cql)
            parts.append(f"```")
            parts.append("")
        if result.validation_errors:
            parts.append("校验问题：")
            for err in result.validation_errors:
                parts.append(f"  - {err}")
            parts.append("")
        if result.error_message:
            parts.append(f"错误信息：{result.error_message}")
        parts.append("")
        parts.append(f"⏱️ 耗时 {result.elapsed_ms}ms | 尝试 {result.attempts} 次")

    return "\n".join(parts)


@cls_tool(
    name="cls_text_to_cql",
    level=ToolLevel.READ,
    description="""将自然语言转换为 CLS CQL 查询语句，或获取 CLS 独有扩展语法参考。服务端内置 CQL 语法校验，可帮助生成准确可靠的查询语句。

### 何时使用此工具
1. **生成 CQL**：用户用自然语言描述查询需求（如"统计每小时错误量趋势"），由服务端 AI 生成经过校验的 CQL
2. **语法参考**：需要了解 CLS 独有扩展函数（histogram、time_series、compare、IP 函数等）的用法时，获取详细语法文档
3. **辅助纠错**：直接编写 CQL 在 cls_search_log 执行失败时，可将需求描述传给此工具生成正确的 CQL

### CQL 基础语法速查

CQL 由**检索条件**和可选的 **SQL 分析**通过管道符 `|` 连接：`[检索条件] | [SQL语句]`

**检索语法**：
- 关键词: `error`、`"connection timeout"`（精确短语）
- 字段匹配: `status:200`、`level:ERROR`、`host:"10.0.0.1"`
- 逻辑运算: `AND`、`OR`、`NOT`（大写），如 `level:ERROR AND status:500`
- 范围查询: `response_time:>1000`、`code:[400 TO 499]`
- 通配符: `path:/api/v1/*`（仅尾部）
- 存在性: `field_name:*`（字段存在）、`field_name:""`（字段为空）

**SQL 分析**（管道符右侧，兼容 Trino/Presto 语法，无需 FROM 子句）：
- 统计: `* | SELECT COUNT(*) AS total`
- 分组 TopN: `* | SELECT status, COUNT(*) AS cnt GROUP BY status ORDER BY cnt DESC LIMIT 10`
- 时间聚合: `* | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 hour) as t, COUNT(*) as cnt GROUP BY t ORDER BY t`
- 百分位: `* | SELECT APPROX_PERCENTILE(response_time, 0.99) AS p99`

### CLS 独有扩展函数概要（详细语法通过 mode="syntax_only" 获取）

| 函数 | 用途 | 示例片段 |
|------|------|----------|
| `histogram(ts, interval)` | 时间分桶聚合 | `histogram(cast(__TIMESTAMP__ as timestamp), interval 5 minute)` |
| `time_series(ts, interval, fmt, default)` | 时序补全（补零），适合绘图 | `time_series(cast(__TIMESTAMP__ as timestamp), '1h', '%Y-%m-%d %H:%i:%s', '0')` |
| `compare(agg_expr, offset_sec)` | 同环比对比 | `compare(count(*), 86400)` → 日环比 |
| `ip_to_province/city/country/provider(ip)` | IP 地理解析 | `ip_to_province(client_ip)` |
| `ip_to_threat_type/level(ip)` | IP 威胁情报 | `ip_to_threat_level(remote_addr)` |

**内置字段**：`__TIMESTAMP__`（毫秒时间戳）、`__SOURCE__`（采集机器 IP）、`__FILENAME__`（日志文件名）

### 参数说明
- **query**（必填）：自然语言查询描述 或 语法关键词。如 "统计各状态码分布" 或 "histogram"
- **mode**（可选，默认 auto）：`auto` 智能判断 | `syntax_only` 返回语法文档 | `generate` AI 生成 CQL
- **topic_id**（可选）：日志主题 ID，传入后自动获取索引字段信息，使生成的 CQL 包含正确字段名
- **region**（可选）：地域，如 ap-shanghai，不传使用默认地域

### 使用示例
1. 生成 CQL：`query="统计最近错误日志 Top10 的 path"`, `topic_id="xxx"`
2. 查语法：`query="compare"`, `mode="syntax_only"`
3. 自动判断：`query="按小时统计日志量趋势"`

### 注意事项
- generate 模式需要配置 LLM 环境变量：CLS_LLM_API_BASE、CLS_LLM_API_KEY、CLS_LLM_MODEL
- 未配置 LLM 时 auto 模式会自动降级为 syntax_only，返回语法参考供客户端自行构造 CQL
- 传入 topic_id 可显著提高生成准确率（自动获取字段名和类型）
- 生成的 CQL 经过语法校验（最多重试 3 次），但建议人工确认后再执行
- ⚠️ 时区陷阱：histogram/time_series 传 LONG 型自动 UTC+8，其他日期时间函数默认 UTC+0
- 字符串值用单引号，双引号用于字段名；SQL 不需要 FROM 子句和分号
- 默认返回 100 行，最大 100 万行；字段需开启统计才能 SQL 分析""",
)
@handle_api_error
async def cls_text_to_cql(
    query: str,
    mode: str = "auto",
    topic_id: str = "",
    region: str = "",
) -> str:
    """将自然语言转换为 CQL 或查询语法文档"""
    # 参数校验
    if not query or not query.strip():
        return json.dumps(
            {"success": False, "error_type": "PARAM_ERROR", "message": "query 参数不能为空"},
            ensure_ascii=False,
        )

    mode = mode.lower().strip()
    if mode not in ("auto", "syntax_only", "generate"):
        return json.dumps(
            {
                "success": False,
                "error_type": "PARAM_ERROR",
                "message": f"mode 参数无效: {mode}，支持 auto/syntax_only/generate",
            },
            ensure_ascii=False,
        )

    original_mode = mode

    # Auto 模式路由
    if mode == "auto":
        mode = route_mode(query)
        logger.info("Auto mode routed to: %s", mode)

    # Syntax Only 模式
    if mode == "syntax_only":
        syntax = get_syntax_docs(category=query)
        result = CqlResult(success=True, mode="syntax_only")
        return _format_result(result, syntax_docs=syntax)

    # Generate 模式
    llm_config = _get_llm_config()
    if not llm_config:
        if original_mode == "auto":
            # auto 路由到 generate 但未配置 LLM，降级为 syntax_only 返回语法参考
            logger.info("LLM not configured, auto mode fallback to syntax_only")
            syntax = get_syntax_docs(category=query)
            result = CqlResult(success=True, mode="syntax_only")
            fallback_hint = (
                "\n\n---\n💡 提示：未配置 LLM 环境变量，已自动返回语法参考。"
                "如需服务端 AI 生成 CQL，请设置 CLS_LLM_API_BASE、CLS_LLM_API_KEY、CLS_LLM_MODEL。"
            )
            return _format_result(result, syntax_docs=syntax) + fallback_hint
        else:
            return json.dumps(
                {
                    "success": False,
                    "error_type": "CONFIG_ERROR",
                    "message": "CQL 生成模式需要配置 LLM 环境变量",
                    "suggestion": "请设置 CLS_LLM_API_BASE、CLS_LLM_API_KEY、CLS_LLM_MODEL 环境变量。"
                    "或使用 mode='syntax_only' 获取语法参考，由客户端自行构造 CQL。",
                },
                ensure_ascii=False,
            )

    # 获取语法文档
    syntax_docs = get_syntax_docs()

    # 可选：获取索引信息
    index_info = ""
    if topic_id:
        index_info = await _fetch_index_info(topic_id, region)

    # 创建独立的生成器实例（并发隔离）
    generator = CqlGenerator(
        llm_config=llm_config,
        syntax_docs=syntax_docs,
        index_info=index_info,
    )

    # 执行生成
    result = await generator.generate(query)

    return _format_result(result)
