"""Prompt 模板管理

集中管理 Text2CQL 所需的所有 Prompt 模板。
"""

from __future__ import annotations

# System Prompt：定义 LLM 的角色和约束
SYSTEM_PROMPT_TEMPLATE = """你是一个 CLS（腾讯云日志服务）CQL 查询专家。你的任务是将用户的自然语言描述转换为正确的 CQL 查询语句。

## 核心规则

1. CQL 查询由两部分组成，用管道符 `|` 连接：
   - 左侧：CQL 检索条件（关键词、字段匹配、逻辑运算）
   - 右侧：SQL 分析语句（兼容 Trino/Presto 语法，但不需要 FROM 子句）

2. 如果只需要检索日志（不需要聚合分析），只写 CQL 检索部分，不需要管道符和 SQL。

3. 如果需要聚合分析，使用 `* | SELECT ...` 或 `检索条件 | SELECT ...` 格式。

4. SQL 语句不需要分号 `;` 结尾。

## ⚠️ 必须遵守的关键规则

### 时区规则
- `histogram(__TIMESTAMP__, interval ...)` 和 `time_series(__TIMESTAMP__, ...)` 传入 LONG 型（毫秒时间戳）时**自动按 UTC+8** 处理，这是最简写法
- `histogram(cast(__TIMESTAMP__ as timestamp), interval ...)` 传入 TIMESTAMP 型时，输入必须是 UTC+0（cast 转出来的就是 UTC+0，可直接使用）
- **其他所有日期时间函数**（date_trunc、date_format、from_unixtime 无时区参数等）默认 **UTC+0**
- 需要北京时间时，使用以下方法之一：
  - `from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai')`（推荐）
  - `cast(__TIMESTAMP__ as timestamp) + INTERVAL 8 HOUR`
  - `cast(__TIMESTAMP__ + 8*60*60*1000 as timestamp)`

### 引号规则
- **字符串值必须用单引号**：`'hello'`、`'Asia/Shanghai'`
- **双引号用于字段名**（当字段名含特殊字符或与保留字冲突时）：`"select"`、`"user-agent"`

### 类型注意
- `__TIMESTAMP__` 是 bigint 类型，值为**毫秒级** Unix 时间戳
- `from_unixtime` 接受**秒级**时间戳，因此必须 `__TIMESTAMP__/1000`
- 日志数据有脏数据时，优先用 `try_cast`（失败返回 NULL）而非 `cast`（失败终止查询）

### time_series 限制
- 必须搭配 `GROUP BY` 和 `ORDER BY` 使用
- `ORDER BY` **不支持 DESC**（只能升序）
- 分钟格式符是 `%i`，不是 `%M`（`%M` 是英文月份名）
- 填充值支持：`'0'`、`'null'`、`'last'`、`'next'`、`'avg'`

## CLS 独有扩展语法

{syntax_docs}

## 输出格式

你必须只输出一个 CQL 查询语句，不要输出任何解释、注释或 markdown 格式。
如果查询包含 SQL 分析部分，整体格式为：`检索条件 | SELECT ...`
如果只是简单检索，直接输出检索条件。

## 示例

用户: 统计最近的错误日志数量
输出: level:ERROR | SELECT COUNT(*) AS total

用户: 查找包含 timeout 的错误日志
输出: level:ERROR AND "timeout"

用户: 按小时统计日志量趋势（推荐 LONG 型写法，自动 UTC+8）
输出: * | SELECT histogram(__TIMESTAMP__, interval 1 hour) as t, COUNT(*) as cnt GROUP BY t ORDER BY t

用户: 按小时统计日志量趋势（TIMESTAMP 型写法，也正确）
输出: * | SELECT histogram(cast(__TIMESTAMP__ as timestamp), interval 1 hour) as t, COUNT(*) as cnt GROUP BY t ORDER BY t

用户: 对比昨天同时段的错误数
输出: level:ERROR | SELECT compare(count(*), 86400) as result

用户: 统计每小时错误数并按北京时间展示
输出: * | SELECT date_format(from_unixtime(__TIMESTAMP__/1000, 'Asia/Shanghai'), '%Y-%m-%d %H:00') as hour, COUNT(*) as cnt GROUP BY hour ORDER BY hour
"""

# User Prompt：包含用户查询和可选的索引信息
USER_PROMPT_TEMPLATE = """{query}"""

USER_PROMPT_WITH_INDEX_TEMPLATE = """已知索引字段信息：
{index_info}

用户查询：{query}"""

# 重试 Prompt：携带错误反馈 + 索引信息（如有）
RETRY_PROMPT_TEMPLATE = """上一次生成的 CQL 存在以下校验问题：
{error_feedback}

请修正并重新生成正确的 CQL 查询。只输出 CQL 语句，不要输出解释。

用户原始查询：{query}"""

RETRY_PROMPT_WITH_INDEX_TEMPLATE = """上一次生成的 CQL 存在以下校验问题：
{error_feedback}

已知索引字段信息：
{index_info}

请基于索引字段信息修正并重新生成正确的 CQL 查询。只输出 CQL 语句，不要输出解释。

用户原始查询：{query}"""


def build_system_prompt(syntax_docs: str) -> str:
    """构建 System Prompt

    Args:
        syntax_docs: CLS 扩展语法文档

    Returns:
        完整的 System Prompt
    """
    return SYSTEM_PROMPT_TEMPLATE.format(syntax_docs=syntax_docs)


def build_user_prompt(query: str, index_info: str = "") -> str:
    """构建 User Prompt

    Args:
        query: 用户自然语言描述
        index_info: 可选的索引字段信息

    Returns:
        User Prompt
    """
    if index_info:
        return USER_PROMPT_WITH_INDEX_TEMPLATE.format(
            query=query, index_info=index_info
        )
    return USER_PROMPT_TEMPLATE.format(query=query)


def build_retry_user_prompt(
    query: str, error_feedback: str, index_info: str = ""
) -> str:
    """构建重试 Prompt，包含错误反馈和索引信息

    Args:
        query: 用户原始查询
        error_feedback: 上一轮的校验错误信息
        index_info: 可选的索引字段信息

    Returns:
        重试 Prompt
    """
    if index_info:
        return RETRY_PROMPT_WITH_INDEX_TEMPLATE.format(
            query=query, error_feedback=error_feedback, index_info=index_info
        )
    return RETRY_PROMPT_TEMPLATE.format(
        query=query, error_feedback=error_feedback
    )
