# CLS MCP Server

腾讯云日志服务（Cloud Log Service）MCP Server —— 从可观测性视角为 AI 助手提供全方位日志服务能力。

## 功能特性

- **日志查询分析**：CQL 检索 + SQL 管道分析、上下文查看、直方图、日志计数
- **指标查询**：PromQL 兼容的单时间点/时间范围指标查询
- **告警管理**：告警策略/通知渠道/告警记录查询与管理
- **资源管理**：日志集、日志主题、索引、机器组、仪表盘的增删改查
- **数据加工 & 定时 SQL**：数据加工任务和定时 SQL 任务管理
- **三级权限控制**：READ（默认）/ WRITE / DANGER 分级保护

共 **37 个工具**，覆盖 CLS 日志服务的完整能力。

## 工具清单

### 日志检索（5 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_search_log` | 检索分析 CLS 日志，支持 CQL 语法检索和 SQL 管道分析 | 只读 |
| `cls_get_log_context` | 获取日志上下文，查看目标日志前后的记录 | 只读 |
| `cls_get_log_histogram` | 获取日志数量直方图，观察日志量随时间的分布 | 只读 |
| `cls_get_log_count` | 快速获取日志数量，比 search_log 更快 | 只读 |
| `cls_describe_search_syntax` | 获取 CLS 日志检索语法参考和常用查询模板 | 只读 |

### 指标查询（3 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_query_metric` | 查询指标数据（单时间点），支持 PromQL 语法 | 只读 |
| `cls_query_range_metric` | 查询指标数据（时间范围），获取指标变化趋势 | 只读 |
| `cls_list_metrics` | 列出指标主题下的所有可用指标名称 | 只读 |

### 告警管理（8 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_alarms` | 查询告警策略列表，支持分页和过滤 | 只读 |
| `cls_describe_alarm_detail` | 根据告警策略 ID 获取完整告警配置 | 只读 |
| `cls_describe_alarm_notices` | 查询告警通知渠道列表（邮件、短信、回调等） | 只读 |
| `cls_describe_alarm_records` | 查询告警历史触发记录 | 只读 |
| `cls_get_alarm_detail` | 通过告警详情 URL 获取告警详细信息 | 只读 |
| `cls_create_alarm` | 创建告警策略 | ⚠️ 写入 |
| `cls_modify_alarm` | 修改告警策略配置 | ⚠️ 写入 |
| `cls_delete_alarm` | 删除告警策略（不可恢复） | 🚨 危险 |

### 资源管理（14 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_logsets` | 查询日志集列表 | 只读 |
| `cls_describe_topics` | 查询日志主题列表 | 只读 |
| `cls_describe_topic_detail` | 获取日志主题详细配置 | 只读 |
| `cls_describe_index` | 查询日志主题的索引配置 | 只读 |
| `cls_describe_machine_groups` | 查询机器组列表 | 只读 |
| `cls_describe_machine_group_detail` | 获取机器组详情和机器在线状态 | 只读 |
| `cls_describe_dashboards` | 查询仪表盘列表 | 只读 |
| `cls_describe_regions` | 查询 CLS 支持的地域列表 | 只读 |
| `cls_create_logset` | 创建日志集 | ⚠️ 写入 |
| `cls_create_topic` | 创建日志主题 | ⚠️ 写入 |
| `cls_modify_topic` | 修改日志主题配置 | ⚠️ 写入 |
| `cls_modify_index` | 修改日志主题的索引配置 | ⚠️ 写入 |
| `cls_delete_logset` | 删除日志集（不可恢复） | 🚨 危险 |
| `cls_delete_topic` | 删除日志主题及所有日志数据（不可恢复） | 🚨 危险 |

### 数据加工（3 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_data_transform_tasks` | 查询数据加工任务列表 | 只读 |
| `cls_create_data_transform` | 创建数据加工任务 | ⚠️ 写入 |
| `cls_delete_data_transform` | 删除数据加工任务 | 🚨 危险 |

### 定时 SQL（3 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_scheduled_sql_tasks` | 查询定时 SQL 任务列表 | 只读 |
| `cls_create_scheduled_sql` | 创建定时 SQL 分析任务 | ⚠️ 写入 |
| `cls_delete_scheduled_sql` | 删除定时 SQL 任务 | 🚨 危险 |

### 时间工具（1 个）

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_convert_time` | 时间与时间戳互转，避免手动计算出错 | 只读 |

> **权限说明**：只读工具默认启用；⚠️ 写入工具需设置 `CLS_ENABLE_WRITE=true`；🚨 危险工具需同时设置 `CLS_ENABLE_WRITE=true` 和 `CLS_ENABLE_DANGEROUS=true`。

## 快速开始

### 方式一：PyPI 安装（推荐）

```bash
# 使用 uvx 直接运行
uvx cls-mcp-server --help

# 或使用 pip 安装
pip install cls-mcp-server
```

### 方式二：Docker 运行

```bash
docker run -d \
  -p 8000:8000 \
  -e CLS_SECRET_ID=your-secret-id \
  -e CLS_SECRET_KEY=your-secret-key \
  -e CLS_REGION=ap-guangzhou \
  ghcr.io/tinker-lgd2026/cls-mcp-server:latest
```

### 方式三：源码安装

```bash
git clone https://github.com/Tinker-LGD2026/cls-mcp-server.git
cd cls-mcp-server
uv sync
uv run cls-mcp-server --help
```

## 配置

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CLS_SECRET_ID` | 是 | — | 腾讯云 API SecretId |
| `CLS_SECRET_KEY` | 是 | — | 腾讯云 API SecretKey |
| `CLS_REGION` | 是 | `ap-guangzhou` | 地域 |
| `CLS_TRANSPORT` | 否 | `stdio` | 传输方式：`stdio` / `sse` / `streamable-http` |
| `MCP_AUTH_TOKEN` | 否 | — | HTTP Bearer Token 认证（SSE/Streamable HTTP 模式） |
| `CLS_ENABLE_WRITE` | 否 | `false` | 启用写操作工具 |
| `CLS_ENABLE_DANGEROUS` | 否 | `false` | 启用危险操作工具 |

### MCP 客户端配置

**Claude Desktop / Cursor**（stdio 模式）：

```json
{
  "mcpServers": {
    "cls": {
      "command": "uvx",
      "args": ["cls-mcp-server"],
      "env": {
        "CLS_SECRET_ID": "your-secret-id",
        "CLS_SECRET_KEY": "your-secret-key",
        "CLS_REGION": "ap-guangzhou"
      }
    }
  }
}
```

**远程服务**（Streamable HTTP 模式，推荐）：

```json
{
  "mcpServers": {
    "cls": {
      "url": "https://your-server:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
```

**远程服务**（SSE 模式，兼容旧版客户端）：

```json
{
  "mcpServers": {
    "cls": {
      "url": "https://your-server:8000/sse",
      "headers": {
        "Authorization": "Bearer your-token"
      }
    }
  }
}
```

> SSE 模式端点为 `/sse`，Streamable HTTP 模式端点为 `/mcp`。新部署推荐使用 Streamable HTTP，SSE 模式主要用于兼容不支持 Streamable HTTP 的旧版 MCP 客户端。

## 部署

支持多种部署方式：

| 方式 | 适用场景 |
|------|----------|
| PyPI (`uvx` / `pip`) | 本地开发，stdio 模式 |
| Docker / Docker Compose | 远程服务，生产环境 |
| systemd + 一键脚本 | 传统虚拟机部署 |
| Kubernetes / Helm | 容器编排环境 |

详细部署指南请参考 [docs/deployment-guide.md](docs/deployment-guide.md)。

## 国内环境

如果 pip / Docker 下载速度慢，可使用国内镜像源：

```bash
# pip 使用清华源
pip install cls-mcp-server -i https://pypi.tuna.tsinghua.edu.cn/simple
```

更多加速方案请参考 [部署手册 - 国内环境加速](docs/deployment-guide.md#9-国内环境加速)。

## 许可证

[Apache-2.0](LICENSE