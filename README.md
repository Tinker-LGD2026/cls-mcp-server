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

先确认你的使用场景，选择对应章节：

| 场景 | 说明 | 跳转 |
|------|------|------|
| **本地使用** | 在自己电脑上配合 Claude Desktop / Cursor / VS Code 等 IDE 使用 | [场景一：本地 stdio 模式](#场景一本地-stdio-模式) |
| **远程服务** | 部署到服务器，团队共用或远程访问 | [场景二：远程服务模式](#场景二远程服务模式) |

---

### 环境准备

#### 1. 安装 uv（Python 包管理器）

[uv](https://docs.astral.sh/uv/) 是一个极快的 Python 包管理器，本项目推荐使用。如已安装可跳过。

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装完成后，让命令生效（二选一）：
source $HOME/.local/bin/env    # 立即生效
# 或者关闭终端重新打开          # 重启终端也行
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

验证安装成功：

```bash
uv --version
# 预期输出: uv 0.11.x（版本号可能不同）
```

> **没有 uv？** 也可以用 `pip install cls-mcp-server` 安装，但 uv 更快且能自动管理 Python 版本。

#### 2. 获取腾讯云密钥

访问 [腾讯云控制台 - API 密钥管理](https://console.cloud.tencent.com/cam/capi)，获取 `SecretId` 和 `SecretKey`。

---

### 场景一：本地 stdio 模式

适合在自己电脑上使用，MCP 客户端（Claude Desktop / Cursor 等）自动拉起 Server 进程，无需手动启动服务。

#### 第一步：配置 MCP 客户端

选择你使用的客户端，将以下配置写入对应的配置文件：

<details>
<summary><b>Claude Desktop</b></summary>

配置文件位置：
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "cls": {
      "command": "uvx",
      "args": ["cls-mcp-server"],
      "env": {
        "CLS_SECRET_ID": "替换为你的SecretId",
        "CLS_SECRET_KEY": "替换为你的SecretKey",
        "CLS_REGION": "ap-guangzhou"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Cursor</b></summary>

配置文件位置：`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "cls": {
      "command": "uvx",
      "args": ["cls-mcp-server"],
      "env": {
        "CLS_SECRET_ID": "替换为你的SecretId",
        "CLS_SECRET_KEY": "替换为你的SecretKey",
        "CLS_REGION": "ap-guangzhou"
      }
    }
  }
}
```

</details>

<details>
<summary><b>VS Code (Copilot)</b></summary>

在 VS Code 的 `settings.json` 中添加：

```json
{
  "mcp": {
    "servers": {
      "cls": {
        "command": "uvx",
        "args": ["cls-mcp-server"],
        "env": {
          "CLS_SECRET_ID": "替换为你的SecretId",
          "CLS_SECRET_KEY": "替换为你的SecretKey",
          "CLS_REGION": "ap-guangzhou"
        }
      }
    }
  }
}
```

</details>

> **说明**：`uvx` 会自动从 PyPI 下载并运行 `cls-mcp-server`，无需手动 `pip install`。`CLS_REGION` 改为你的日志所在地域（如 `ap-shanghai`、`ap-beijing`）。

#### 第二步：重启客户端

保存配置后，**重启** Claude Desktop / Cursor / VS Code，客户端会自动拉起 CLS MCP Server。

#### 第三步：验证

在客户端中发送一条消息测试：

```
帮我查看 CLS 支持哪些地域
```

如果返回了地域列表（广州、上海、北京等），说明连接成功。

#### 其他安装方式

如果不想用 `uvx`，也可以手动安装后在配置中使用 `cls-mcp-server` 命令：

```bash
# 方式一：pip 安装（适合已有 pip 工作流的用户）
pip install cls-mcp-server

# 方式二：源码安装（适合需要修改源码的开发者）
git clone https://github.com/Tinker-LGD2026/cls-mcp-server.git
cd cls-mcp-server
uv sync
# 验证: uv run cls-mcp-server --help
```

使用 `pip install` 安装后，客户端配置中把 `"command": "uvx"` 改为 `"command": "cls-mcp-server"`，`"args"` 改为 `[]` 即可。

---

### 场景二：远程服务模式

适合将 Server 部署到服务器上，作为独立 HTTP 服务运行，供远程 MCP 客户端连接。

#### 方式一：Docker 部署（推荐，最简单）

一条命令即可启动，无需安装 Python 或任何依赖：

```bash
docker run -d \
  --name cls-mcp-server \
  -p 8000:8000 \
  -e CLS_SECRET_ID=替换为你的SecretId \
  -e CLS_SECRET_KEY=替换为你的SecretKey \
  -e CLS_REGION=ap-guangzhou \
  ghcr.io/tinker-lgd2026/cls-mcp-server:latest
```

验证服务是否启动成功：

```bash
curl http://localhost:8000/health
# 预期输出: {"status":"ok","version":"0.3.0","transport":"streamable-http"}
```

#### 方式二：一键部署脚本（适合无 Docker 的虚拟机）

支持 CentOS 7+、Ubuntu 18.04+、Debian 10+，脚本自动安装 uv + Python 3.12 + 依赖 + 注册 systemd 服务，**零前置依赖**：

```bash
# 1. 将源码上传到服务器（git clone 或 tar.gz 打包上传）
git clone https://github.com/Tinker-LGD2026/cls-mcp-server.git
cd cls-mcp-server

# 2. 运行一键部署脚本
sudo bash deploy/systemd/install.sh

# 3. 编辑配置文件，填入真实密钥
sudo vim /opt/cls-mcp-server/.env

# 4. 启动服务
sudo systemctl start cls-mcp-server

# 5. 验证
curl http://127.0.0.1:8000/health
```

> **CentOS 7 用户**：不用担心 Python 版本问题，脚本通过 uv 自动下载 Python 3.12，不影响系统自带 Python。如果 git clone 太慢，可以在本地打包后 scp 上传，详见 [部署手册 - systemd 部署](docs/deployment-guide.md#43-systemd-服务虚拟机部署)。

#### 客户端连接远程服务

服务启动后，在 MCP 客户端中配置远程连接：

```json
{
  "mcpServers": {
    "cls": {
      "url": "http://你的服务器IP:8000/mcp"
    }
  }
}
```

> 如需 SSE 模式（兼容旧版客户端），端点改为 `/sse`。如已设置 Bearer Token 认证，需添加 `"headers": {"Authorization": "Bearer 你的token"}`。

---

## 配置参考

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `CLS_SECRET_ID` | 是 | — | 腾讯云 API SecretId |
| `CLS_SECRET_KEY` | 是 | — | 腾讯云 API SecretKey |
| `CLS_REGION` | 是 | `ap-guangzhou` | 地域（如 `ap-shanghai`、`ap-beijing`） |
| `CLS_TRANSPORT` | 否 | `stdio` | 传输方式：`stdio` / `sse` / `streamable-http` |
| `CLS_HOST` | 否 | `0.0.0.0` | HTTP 监听地址（远程模式） |
| `CLS_PORT` | 否 | `8000` | HTTP 监听端口（远程模式） |
| `MCP_AUTH_TOKEN` | 否 | — | HTTP Bearer Token 认证（远程模式，建议开启） |
| `CLS_ENABLE_WRITE` | 否 | `false` | 启用写操作工具（创建/修改） |
| `CLS_ENABLE_DANGEROUS` | 否 | `false` | 启用危险操作工具（删除，需同时开启写操作） |
| `CLS_LOG_LEVEL` | 否 | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CLS_REQUEST_TIMEOUT` | 否 | `60` | SDK 请求超时时间（秒） |
| `CLS_RETRY_MAX_ATTEMPTS` | 否 | `3` | 失败重试最大尝试次数（含首次调用） |
| `CLS_RETRY_BASE_DELAY` | 否 | `1.0` | 重试基础退避延迟（秒），实际延迟会指数递增 |
| `CLS_CB_FAILURE_THRESHOLD` | 否 | `5` | 熔断器触发阈值：连续失败多少次后熔断 |
| `CLS_CB_RECOVERY_TIMEOUT` | 否 | `30` | 熔断恢复超时（秒）：熔断后多久尝试恢复 |
| `CLS_ENABLED_TOOLS` | 否 | — | 工具白名单（逗号分隔），未设置则注册全部工具，详见下方说明 |

### 工具白名单（CLS_ENABLED_TOOLS）

默认情况下，Server 会注册所有符合权限等级的工具。如果你只需要部分功能，可以通过 `CLS_ENABLED_TOOLS` 精确控制注册哪些工具，**未列出的工具不会注册，AI 助手也无法调用**。

**配置格式**：工具名用英文逗号分隔，名称必须与上方"工具清单"中的工具名完全一致。

```bash
# 只注册日志查询相关工具
CLS_ENABLED_TOOLS="cls_search_log,cls_get_log_context,cls_get_log_histogram,cls_get_log_count,cls_describe_search_syntax,cls_convert_time"

# 只注册告警管理相关工具
CLS_ENABLED_TOOLS="cls_describe_alarms,cls_describe_alarm_detail,cls_describe_alarm_notices,cls_describe_alarm_records,cls_get_alarm_detail"

# CLI 方式
cls-mcp-server --enabled-tools "cls_search_log,cls_get_log_context,cls_describe_topics,cls_describe_index"
```

**常见场景示例**：

| 场景 | 推荐配置 |
|------|----------|
| 只做日志查询分析 | `cls_search_log,cls_get_log_context,cls_get_log_histogram,cls_get_log_count,cls_describe_search_syntax,cls_convert_time` |
| 只做告警监控 | `cls_describe_alarms,cls_describe_alarm_detail,cls_describe_alarm_notices,cls_describe_alarm_records,cls_get_alarm_detail` |
| 日志查询 + 资源浏览 | `cls_search_log,cls_get_log_context,cls_get_log_count,cls_describe_topics,cls_describe_logsets,cls_describe_index,cls_convert_time` |
| 不设置（默认） | 注册全部工具 |

> **提示**：白名单与权限控制（`CLS_ENABLE_WRITE` / `CLS_ENABLE_DANGEROUS`）是 AND 关系，两者同时满足才会注册。填写了不存在的工具名会在启动日志中输出警告，不会影响其他工具注册。

---

## 部署指南

除了上面"快速开始"中的 Docker 和一键脚本，还支持更多部署方式：

| 方式 | 适用场景 | 文档 |
|------|----------|------|
| Docker / Docker Compose | 远程服务，生产环境推荐 | [详细说明](docs/deployment-guide.md#5-docker-部署) |
| systemd + 一键脚本 | 传统虚拟机（CentOS/Ubuntu） | [详细说明](docs/deployment-guide.md#43-systemd-服务虚拟机部署) |
| Kubernetes / Helm | 容器编排，多副本水平扩展 | [详细说明](docs/deployment-guide.md#6-kubernetes-部署) |
| Nginx 反向代理 + HTTPS | 生产环境 TLS 终结 | [详细说明](docs/deployment-guide.md#44-nginx-反向代理) |
| HTTP Bearer Token 认证 | 远程服务访问控制 | [详细说明](docs/deployment-guide.md#7-http-认证bearer-token) |

完整部署手册请参考 [docs/deployment-guide.md](docs/deployment-guide.md)。

---

## 国内环境加速

如果 pip / Docker / uv 下载速度慢：

```bash
# pip 使用清华源
pip install cls-mcp-server -i https://pypi.tuna.tsinghua.edu.cn/simple

# uv 使用国内源
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uvx cls-mcp-server --help
```

更多加速方案（Docker 镜像加速、uv 离线安装、GitHub 代理等）请参考 [部署手册 - 国内环境加速](docs/deployment-guide.md#9-国内环境加速)。

## 许可证

[Apache-2.0](LICENSE)