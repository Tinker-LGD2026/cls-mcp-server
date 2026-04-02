"""跨模块共享的描述常量

提供 topic_id 等参数的标准化描述文本，在各工具描述中引用以保持一致性。
"""

# 日志主题 topic_id 必填参数提示（search.py + resource.py 使用）
TOPIC_ID_HINT = (
    "日志主题 ID（必填）。格式不固定，可能是 UUID（如 `550b584b-xxxx`）"
    "或自定义字符串。当用户提供的值不确定是 ID 还是名称时，优先当作 topic_id 直接使用；"
    "如果报错（如\"主题不存在\"），再通过 cls_describe_topics 按名称搜索获取正确的 topic_id"
)

# 指标主题 topic_id 必填参数提示（metrics.py 使用）
METRIC_TOPIC_ID_HINT = (
    "指标主题 ID（必填），注意是时序指标主题 ID，非普通日志主题 ID。"
    "格式不固定，可能是 UUID 或自定义字符串。当用户提供的值不确定是 ID 还是名称时，"
    "优先当作 topic_id 直接使用；如果报错，再通过 cls_describe_topics(biz_type=1) "
    "按名称搜索获取正确的指标主题 ID"
)

# 可选过滤 topic_id 参数提示后缀（alarm.py + data_transform.py 使用）
TOPIC_ID_FILTER_HINT = "如不确定 ID，可先通过 cls_describe_topics 按名称搜索"
