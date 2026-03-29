"""CLS 独有扩展语法文档加载器

加载 reference/cls_extension_syntax.md 文档作为 LLM Prompt 上下文。
文档在模块加载时读取并缓存为不可变字符串（线程安全）。

路径解析策略：
1. 优先使用 importlib.resources 读取包内资源（pip install 后依然有效）
2. 回退到基于 __file__ 的相对路径推算（开发模式）
3. 最终回退到内嵌精简版本
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_syntax_doc_path() -> Path | None:
    """多策略定位语法文档文件路径

    1. 尝试从包资源中读取（支持 pip install 后的场景）
    2. 回退到基于 __file__ 推算项目根目录（开发模式）
    """
    # 策略 1：基于 __file__ 推算（开发模式）
    # __file__ -> text_to_cql/ -> tools/ -> cls_mcp_server/ -> src/ -> 项目根
    candidate = Path(__file__).resolve().parent.parent.parent.parent.parent / "reference" / "cls_extension_syntax.md"
    if candidate.is_file():
        return candidate

    # 策略 2：从当前工作目录查找
    cwd_candidate = Path.cwd() / "reference" / "cls_extension_syntax.md"
    if cwd_candidate.is_file():
        return cwd_candidate

    return None


def _load_syntax_docs() -> str:
    """加载语法文档，失败时返回内嵌的精简版本"""
    doc_path = _find_syntax_doc_path()
    if doc_path:
        try:
            content = doc_path.read_text(encoding="utf-8")
            logger.debug("Loaded syntax docs from %s", doc_path)
            return content
        except Exception:
            logger.exception("Failed to read syntax doc from %s", doc_path)

    logger.warning("Syntax doc not found, using embedded fallback")
    return _EMBEDDED_FALLBACK


# 内嵌精简版本，作为文件缺失时的兜底
_EMBEDDED_FALLBACK = """# CLS SQL 扩展语法（精简版）

## 管道符 `|`
CQL检索条件 | SQL分析语句。SQL 不需要 FROM 子句，不需要分号结尾。字符串用单引号，双引号用于字段名。

## 时区规则（⚠️ 重要）
- histogram(__TIMESTAMP__, interval ...) 和 time_series(__TIMESTAMP__, ...) 传 LONG 型自动 UTC+8
- 其他日期时间函数（date_trunc/date_format/from_unixtime等）默认 UTC+0，需手动加 8 小时
- 推荐：from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai') 或 cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR

## SQL 前提条件
- 标准存储才支持 SQL 分析，低频存储不支持
- 字段需开启键值索引 + 统计功能
- 默认返回 100 行，最大 100 万行

## histogram — 时间分桶
histogram(__TIMESTAMP__, interval N unit)  -- LONG 型，推荐，自动 UTC+8
histogram(cast(__TIMESTAMP__ as timestamp), interval N unit)  -- TIMESTAMP 型

## time_series — 时序补全
time_series(__TIMESTAMP__, 'interval', 'format', 'default')
interval: '1m', '5m', '1h', '1d'。填充值: '0', 'null', 'last', 'next', 'avg'
⚠️ 必须搭配 GROUP BY + ORDER BY，ORDER BY 不支持 DESC
⚠️ 分钟格式符是 %i 不是 %M

## compare — 同环比
compare(aggregate_expr, offset_seconds)  -- 基础对比
compare(aggregate_expr, offset_seconds, time_column)  -- 趋势对比
86400=日环比, 604800=周同比。返回 JSON 数组（下标从 1 开始）。

## 类型转换
cast(value AS type)  -- 失败终止查询
try_cast(value AS type)  -- 失败返回 NULL（推荐）
from_unixtime(__TIMESTAMP__/1000)  -- 毫秒转秒！

## IP 函数
ip_to_country/province/city/provider(ip), ip_to_domain(ip)
ip_to_threat_type(ip), ip_to_threat_level(ip)
ip_prefix(ip, bits), ip_subnet_min/max(ip, bits), is_subnet_of(ip, cidr)

## 内置字段
__TIMESTAMP__ (bigint, 毫秒), __SOURCE__ (varchar), __FILENAME__ (varchar)
"""

# 模块加载时即缓存（不可变字符串，线程安全）
CLS_EXTENSION_SYNTAX: str = _load_syntax_docs()


def get_syntax_docs(category: str = "") -> str:
    """获取语法文档

    Args:
        category: 可选的函数类别过滤关键词。
                  支持直接传入函数名（如 "histogram"）或自然语言查询。
                  为空返回全部文档。

    Returns:
        语法文档文本
    """
    if not category:
        return CLS_EXTENSION_SYNTAX

    # 提取有效的过滤关键词（函数名、技术术语）
    keywords = _extract_filter_keywords(category)
    if not keywords:
        return CLS_EXTENSION_SYNTAX

    # 按关键词过滤章节
    sections = CLS_EXTENSION_SYNTAX.split("\n## ")
    matched = []
    for section in sections:
        section_lower = section.lower()
        for kw in keywords:
            if kw in section_lower:
                matched.append("## " + section if not section.startswith("#") else section)
                break

    if matched:
        return "\n\n".join(matched)

    # 没有匹配到特定章节，返回全部
    return CLS_EXTENSION_SYNTAX


# 可被过滤的技术关键词（函数名、特性名）
_FILTER_KEYWORDS = {
    "histogram", "time_series", "compare", "ip_to",
    "ip函数", "ip function", "同环比", "时间分桶", "时序补全",
    "管道符", "内置字段", "timestamp", "source", "filename",
}


def _extract_filter_keywords(query: str) -> list[str]:
    """从用户查询中提取有效的过滤关键词

    过滤掉常见的疑问词和停用词，保留技术术语。
    """
    query_lower = query.lower().strip()

    matched = []
    for kw in _FILTER_KEYWORDS:
        if kw in query_lower:
            matched.append(kw)

    return matched
