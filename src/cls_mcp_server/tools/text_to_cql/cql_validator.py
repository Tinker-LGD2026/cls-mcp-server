"""CQL 语法校验器

对 LLM 生成的 CQL 进行基础语法校验，包括：
- 括号匹配检查
- CQL/SQL 关键字合法性
- CLS 特有语法格式验证
- 基本安全检查
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """校验结果"""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.is_valid = False
        self.errors.append(msg)


def validate_cql(cql: str) -> ValidationResult:
    """对生成的 CQL 进行基础语法校验

    Args:
        cql: 待校验的 CQL 查询语句

    Returns:
        ValidationResult 包含是否通过和错误列表
    """
    result = ValidationResult()

    if not cql or not cql.strip():
        result.add_error("CQL 查询为空")
        return result

    cql = cql.strip()

    # 移除 LLM 可能添加的 markdown 代码块标记
    cql = _strip_markdown_fences(cql)

    # 1. 括号匹配检查
    _check_brackets(cql, result)

    # 2. 引号匹配检查
    _check_quotes(cql, result)

    # 3. 如果包含管道符，检查 SQL 部分
    if "|" in cql:
        parts = cql.split("|", 1)
        sql_part = parts[1].strip() if len(parts) > 1 else ""
        if sql_part:
            _check_sql_part(sql_part, result)

    # 4. 安全检查
    _check_safety(cql, result)

    return result


def clean_cql(cql: str) -> str:
    """清理 LLM 生成的 CQL，去除常见的格式噪音

    Args:
        cql: 原始 CQL 字符串

    Returns:
        清理后的 CQL
    """
    cql = cql.strip()
    cql = _strip_markdown_fences(cql)

    # 去掉结尾的分号
    if cql.endswith(";"):
        cql = cql[:-1].strip()

    return cql


def _strip_markdown_fences(text: str) -> str:
    """移除 markdown 代码块标记"""
    # 匹配 ```sql ... ``` 或 ``` ... ```
    pattern = r"^```(?:sql|cql)?\s*\n?(.*?)\n?\s*```$"
    match = re.match(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


def _check_brackets(cql: str, result: ValidationResult) -> None:
    """检查括号匹配"""
    stack: list[str] = []
    bracket_pairs = {"(": ")", "[": "]"}
    in_string = False
    string_char = ""

    for char in cql:
        if in_string:
            if char == string_char:
                in_string = False
            continue

        if char in ("'", '"'):
            in_string = True
            string_char = char
            continue

        if char in bracket_pairs:
            stack.append(bracket_pairs[char])
        elif char in bracket_pairs.values():
            if not stack:
                result.add_error(f"多余的右括号 '{char}'")
                return
            expected = stack.pop()
            if char != expected:
                result.add_error(f"括号不匹配：期望 '{expected}'，实际 '{char}'")
                return

    if stack:
        result.add_error(f"缺少右括号：{', '.join(stack)}")


def _check_quotes(cql: str, result: ValidationResult) -> None:
    """检查引号匹配"""
    for quote_char, name in [("'", "单引号"), ('"', "双引号")]:
        count = cql.count(quote_char)
        # 跳过转义的引号
        escaped_count = cql.count(f"\\{quote_char}")
        effective_count = count - escaped_count
        if effective_count % 2 != 0:
            result.add_error(f"{name}未闭合")


def _check_sql_part(sql: str, result: ValidationResult) -> None:
    """检查 SQL 部分的基础合法性"""
    sql_upper = sql.upper().strip()

    # SQL 部分应该以 SELECT 开头
    if not sql_upper.startswith("SELECT"):
        result.add_error("SQL 分析部分应以 SELECT 开头")

    # 检查 histogram 用法
    if "HISTOGRAM(" in sql_upper:
        # 支持两种写法：
        # 1. LONG 型直传：histogram(__TIMESTAMP__, interval ...)  — 自动 UTC+8
        # 2. TIMESTAMP 型：histogram(cast(__TIMESTAMP__ as timestamp), interval ...)
        if "__TIMESTAMP__" not in sql_upper:
            result.add_error(
                "histogram 函数需要使用 __TIMESTAMP__ 字段，"
                "支持 histogram(__TIMESTAMP__, interval ...) 或 "
                "histogram(cast(__TIMESTAMP__ as timestamp), interval ...)"
            )

    # 检查 time_series 用法
    if "TIME_SERIES(" in sql_upper:
        if "__TIMESTAMP__" not in sql_upper:
            result.add_error(
                "time_series 函数需要使用 __TIMESTAMP__ 字段，"
                "支持 time_series(__TIMESTAMP__, ...) 或 "
                "time_series(cast(__TIMESTAMP__ as timestamp), ...)"
            )

    # 检查是否错误地包含了 FROM 子句（CLS SQL 不需要 FROM table）
    # 需排除合法的函数内 FROM 用法：EXTRACT(... FROM ...)、TRIM(... FROM ...)、
    # SUBSTRING(... FROM ...)、以及 UNNEST/JSON_EXTRACT 等
    if _has_invalid_from_clause(sql_upper):
        result.add_error(
            "CLS SQL 不需要 FROM 子句，数据来源为管道符左侧的检索结果"
        )


def _has_invalid_from_clause(sql_upper: str) -> bool:
    """检测 SQL 中是否包含非法的 FROM 表名引用

    CLS SQL 不需要 FROM 子句，但以下合法语法中包含 FROM 关键字需要排除：
    - EXTRACT(HOUR FROM timestamp)
    - TRIM(LEADING 'x' FROM col)
    - SUBSTRING(col FROM 1 FOR 3)
    - FROM UNNEST(...) — CLS 支持的合法用法

    策略：先移除所有函数内括号中的 FROM，再检测是否还有 FROM table_name 模式。
    """
    cleaned = sql_upper

    # 移除 EXTRACT(...FROM...) — 括号内的 FROM 是合法语法
    cleaned = re.sub(r"\bEXTRACT\s*\([^)]*\)", "", cleaned)
    # 移除 TRIM(...FROM...) — 如 TRIM(LEADING 'x' FROM col)
    cleaned = re.sub(r"\bTRIM\s*\([^)]*\)", "", cleaned)
    # 移除 SUBSTRING(...FROM...) — 如 SUBSTRING(col FROM 1 FOR 3)
    cleaned = re.sub(r"\bSUBSTRING\s*\([^)]*\)", "", cleaned)

    # 检查清理后的 SQL 中是否还有 FROM + 标识符（表名引用）
    # 但排除 FROM UNNEST(...) 和 FROM JSON_EXTRACT(...) 等 CLS 合法用法
    from_match = re.search(r"\bFROM\s+([A-Z_][A-Z0-9_]*)\b", cleaned)
    if from_match:
        target = from_match.group(1)
        # UNNEST 和 JSON_EXTRACT 是 CLS 支持的合法 FROM 目标
        if target in ("UNNEST", "JSON_EXTRACT"):
            return False
        return True

    return False


def _check_safety(cql: str, result: ValidationResult) -> None:
    """基础安全检查"""
    cql_upper = cql.upper()

    # 检查明显的注入或危险操作
    dangerous_patterns = [
        r"\bDROP\s+TABLE\b",
        r"\bDELETE\s+FROM\b",
        r"\bUPDATE\s+\w+\s+SET\b",
        r"\bINSERT\s+INTO\b",
        r"\bTRUNCATE\b",
        r"\bALTER\s+TABLE\b",
        r"\bCREATE\s+TABLE\b",
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, cql_upper):
            result.add_error(f"检测到危险 SQL 操作: {pattern}")
            break
