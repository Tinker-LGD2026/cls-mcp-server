"""Auto 模式路由判断

根据用户输入判断应走 syntax_only 还是 generate 路径。
"""

from __future__ import annotations

import re

# 语法查询相关的短词和精确匹配词（用于短查询和精确匹配）
_SYNTAX_EXACT_PHRASES: list[str] = [
    # 中文
    "语法", "用法", "怎么用", "如何使用", "语法参考",
    "有哪些函数", "什么函数", "支持哪些", "函数列表",
    "文档", "参考",
    # 英文
    "syntax", "usage", "how to use", "reference", "doc",
    # CLS 特有函数名（直接查语法时可能输入）
    "histogram", "time_series", "compare", "ip_to_",
]

# 组合正则：包含函数/扩展相关词 + 疑问词
_SYNTAX_COMBO_PATTERNS: list[str] = [
    r"(函数|function|扩展|独有).*(有哪些|是什么|怎么)",
    r"(有哪些|是什么|怎么).*(函数|function|扩展|独有)",
]

# 生成查询相关的信号词
_GENERATE_SIGNALS: list[str] = [
    r"查(询|看|找|一下|下)",
    r"统计",
    r"分析",
    r"(多少|数量|总数|计数)",
    r"(top|排名|排行|前\d+)",
    r"(趋势|分布|占比|比例|平均|最大|最小)",
    r"(环比|同比|对比|比较)",
    r"(告警|错误|异常|慢|超时)",
    r"帮我(写|生成|构造)",
    r"(请|麻烦).*(查|统计|分析|生成)",
]


def route_mode(query: str) -> str:
    """判断用户输入应该走哪个模式

    Args:
        query: 用户输入

    Returns:
        "syntax_only" 或 "generate"
    """
    query_lower = query.lower().strip()

    # 如果查询非常短（<= 5 个字符），可能是语法关键词查询
    if len(query_lower) <= 5:
        for kw in _SYNTAX_EXACT_PHRASES:
            if kw in query_lower:
                return "syntax_only"
        return "syntax_only"

    # 显式询问语法/文档（精确短语匹配）
    for phrase in _SYNTAX_EXACT_PHRASES:
        if phrase in query_lower:
            return "syntax_only"

    # 组合模式匹配
    for pattern in _SYNTAX_COMBO_PATTERNS:
        if re.search(pattern, query_lower):
            return "syntax_only"

    # 检查是否有生成信号
    for pattern in _GENERATE_SIGNALS:
        if re.search(pattern, query_lower):
            return "generate"

    # 默认走生成模式（大部分用户场景是想查询数据）
    return "generate"
