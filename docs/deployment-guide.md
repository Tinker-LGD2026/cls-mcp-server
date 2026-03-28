# CLS MCP Server 部署手册

## 目录

- [1. 概述](#1-概述)
- [2. 前置条件](#2-前置条件)
- [3. stdio 模式本地部署](#3-stdio-模式本地部署)
  - [3.1 安装](#31-安装)
  - [3.2 配置](#32-配置)
  - [3.3 启动与验证](#33-启动与验证)
  - [3.4 接入 MCP 客户端](#34-接入-mcp-客户端)
- [4. 远程部署（SSE / Streamable HTTP）](#4-远程部署sse--streamable-http)
  - [4.1 传输模式选择](#41-传输模式选择)
  - [4.2 直接启动](#42-直接启动)
  - [4.3 systemd 服务](#43-systemd-服务)
  - [4.4 Nginx 反向代理](#44-nginx-反向代理)
  - [4.5 远程客户端接入](#45-远程客户端接入)
- [5. Docker 部署](#5-docker-部署)
  - [5.1 构建镜像](#51-构建镜像)
  - [5.2 docker compose 快速启动](#52-docker-compose-快速启动)
  - [5.3 直接运行容器](#53-直接运行容器)
  - [5.4 健康检查](#54-健康检查)
- [6. Kubernetes 部署](#6-kubernetes-部署)
  - [6.1 原始 YAML 部署](#61-原始-yaml-部署)
  - [6.2 Helm Chart 部署](#62-helm-chart-部署)
  - [6.3 架构说明](#63-架构说明)
- [7. HTTP 认证（Bearer Token）](#7-http-认证bearer-token)
- [8. 高级配置](#8-高级配置)
- [9. 国内环境加速](#9-国内环境加速)
- [10. CI/CD 自动发布](#10-cicd-自动发布)
- [11. 常见问题与故障排查](#11-常见问题与故障排查)
- [12. 更新与卸载](#12-更新与卸载)

---

## 1. 概述

CLS MCP Server 是腾讯云日志服务（Cloud Log Service）的 MCP Server 实现，为 AI 助手提供日志查询分析、指标查询、告警管理、资源管理等可观测性能力。

### 部署模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **stdio** | 通过标准输入/输出通信，由 MCP 客户端直接拉起进程 | 本地开发，Claude Desktop / Cursor 等桌面客户端 |
| **SSE** | 作为独立 HTTP 服务运行，通过 Server-Sent Events 通信 | 远程部署，兼容旧版 MCP 客户端 |
| **Streamable HTTP**（推荐） | 作为独立 HTTP 服务运行，基于标准 HTTP 请求/响应通信 | 远程部署，K8s 无状态水平扩展，推荐新部署 |

### 工具概览

Server 共提供 **33 个工具**，按权限分为三级：

| 权限级别 | 工具数 | 启用条件 | 说明 |
|----------|--------|----------|------|
| READ（只读） | 20 | 默认开启 | 查询、列表、搜索类操作 |
| WRITE（写入） | 8 | 需设置 `CLS_ENABLE_WRITE=true` | 创建、修改类操作 |
| DANGER（危险） | 5 | 需同时设置 `CLS_ENABLE_WRITE=true` 和 `CLS_ENABLE_DANGEROUS=true` | 删除类操作（不可逆） |

---

## 2. 前置条件

### 系统要求

- **操作系统**：macOS / Linux / Windows
- **Python**：>= 3.10（支持 3.10、3.11、3.12）
- **包管理器**：[uv](https://docs.astral.sh/uv/)（推荐）

### 安装 uv

如尚未安装 uv：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或通过 pip
pip install uv
```

### 腾讯云密钥

需要一组腾讯云 API 密钥（SecretId + SecretKey），且该密钥拥有 CLS 相关接口的访问权限。

获取方式：[腾讯云控制台 - API 密钥管理](https://console.cloud.tencent.com/cam/capi)

---

## 3. stdio 模式本地部署

stdio 是最简单的部署方式——MCP 客户端（如 Claude Desktop）直接启动 Server 进程，通过标准输入/输出通信，无需单独运行服务。

### 3.1 安装

**方式一：PyPI 安装（推荐）**

```bash
# 使用 uvx 直接运行（无需手动安装）
uvx cls-mcp-server --help

# 或使用 pip 安装
pip install cls-mcp-server

# 或使用 pipx 安装（隔离环境）
pipx install cls-mcp-server
```

**方式二：源码安装**

```bash
# 克隆项目
git clone https://github.com/Tinker-LGD2026/cls-mcp-server.git
cd cls-mcp-server

# 安装依赖
uv sync
```

安装完成后，`cls-mcp-server` 命令即可使用：

```bash
# 验证安装
uv run cls-mcp-server --help
```

### 3.2 配置

#### 方式一：`.env` 文件（推荐）

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env`，填入你的配置：

```env
# [必填] 腾讯云 API 密钥
CLS_SECRET_ID=你的SecretId
CLS_SECRET_KEY=你的SecretKey

# [必填] 地域
CLS_REGION=ap-guangzhou

# stdio 模式无需修改以下配置
CLS_TRANSPORT=stdio
CLS_LOG_LEVEL=INFO
```

#### 方式二：CLI 参数

CLI 参数会覆盖 `.env` 中的同名配置：

```bash
uv run cls-mcp-server --transport stdio --log-level DEBUG --enable-write
```

#### 环境变量完整列表

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `CLS_SECRET_ID` | 是 | — | 腾讯云 API SecretId |
| `CLS_SECRET_KEY` | 是 | — | 腾讯云 API SecretKey |
| `CLS_REGION` | 是 | `ap-guangzhou` | 腾讯云地域（如 `ap-shanghai`、`ap-beijing`） |
| `CLS_TRANSPORT` | 否 | `stdio` | 传输方式：`stdio` / `sse` / `streamable-http` |
| `CLS_HOST` | 否 | `0.0.0.0` | HTTP 监听地址（SSE / Streamable HTTP 模式） |
| `CLS_PORT` | 否 | `8000` | HTTP 监听端口（SSE / Streamable HTTP 模式） |
| `CLS_STATELESS_HTTP` | 否 | `true` | Streamable HTTP 无状态模式（推荐 K8s 部署开启） |
| `CLS_ENABLE_WRITE` | 否 | `false` | 启用写操作工具 |
| `CLS_ENABLE_DANGEROUS` | 否 | `false` | 启用危险操作工具（需同时开启写操作） |
| `MCP_AUTH_TOKEN` | 否 | — | HTTP Bearer Token 认证令牌（SSE/Streamable HTTP 模式） |
| `CLS_LOG_LEVEL` | 否 | `INFO` | 日志级别：`DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CLS_REQUEST_TIMEOUT` | 否 | `60` | SDK 请求超时时间（秒） |
| `CLS_RETRY_MAX_ATTEMPTS` | 否 | `3` | 失败重试最大尝试次数（含首次调用） |
| `CLS_RETRY_BASE_DELAY` | 否 | `1.0` | 重试基础退避延迟（秒），实际延迟会指数递增加随机抖动 |
| `CLS_CB_FAILURE_THRESHOLD` | 否 | `5` | 熔断器触发阈值：连续失败多少次后触发熔断 |
| `CLS_CB_RECOVERY_TIMEOUT` | 否 | `30` | 熔断恢复超时（秒）：熔断后多久进入半开状态尝试恢复 |
| `CLS_ENABLED_TOOLS` | 否 | — | 工具白名单（逗号分隔），未设置则注册全部工具 |

> 向后兼容：`CLS_SSE_HOST` / `CLS_SSE_PORT` 仍可使用，作为 `CLS_HOST` / `CLS_PORT` 的回退。

#### CLI 参数列表

| 参数 | 说明 | 示例 |
|------|------|------|
| `--transport` | 传输方式，覆盖 `CLS_TRANSPORT` | `--transport streamable-http` |
| `--host` | HTTP 监听地址，覆盖 `CLS_HOST` | `--host 127.0.0.1` |
| `--port` | HTTP 端口，覆盖 `CLS_PORT` | `--port 8765` |
| `--enable-write` | 启用写操作工具 | `--enable-write` |
| `--enable-dangerous` | 启用危险操作工具 | `--enable-dangerous` |
| `--auth-token` | HTTP Bearer Token 认证令牌，覆盖 `MCP_AUTH_TOKEN` | `--auth-token my-secret` |
| `--log-level` | 日志级别 | `--log-level DEBUG` |
| `--request-timeout` | SDK 请求超时（秒），覆盖 `CLS_REQUEST_TIMEOUT` | `--request-timeout 120` |
| `--retry-max-attempts` | 最大重试次数（含首次），覆盖 `CLS_RETRY_MAX_ATTEMPTS` | `--retry-max-attempts 5` |
| `--enabled-tools` | 工具白名单（逗号分隔），覆盖 `CLS_ENABLED_TOOLS` | `--enabled-tools "cls_search_log,cls_get_log_context"` |

> **优先级**：CLI 参数 > 环境变量 > 默认值

### 3.3 启动与验证

#### 直接启动

```bash
uv run cls-mcp-server
```

启动成功后会在 stderr 输出配置摘要：

```
2026-03-25 10:00:00 [INFO] cls_mcp_server.config: === CLS MCP Server Configuration ===
2026-03-25 10:00:00 [INFO] cls_mcp_server.config:   Region:     ap-guangzhou
2026-03-25 10:00:00 [INFO] cls_mcp_server.config:   Transport:  stdio
2026-03-25 10:00:00 [INFO] cls_mcp_server.config:   SecretId:   AKID****ZIoB
2026-03-25 10:00:00 [INFO] cls_mcp_server.config:   Write mode: DISABLED (read-only)
2026-03-25 10:00:00 [INFO] cls_mcp_server.config:   Danger mode:DISABLED
```

> stdio 模式下，Server 通过 stdin/stdout 通信，日志输出到 stderr，不会干扰 MCP 协议。

#### 配置校验

如果密钥未配置，启动时会报错退出：

```
Configuration error: CLS_SECRET_ID is required
Configuration error: CLS_SECRET_KEY is required
```

### 3.4 接入 MCP 客户端

#### Claude Desktop

编辑 Claude Desktop 配置文件：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**方式一：使用 PyPI 安装（推荐）**

```json
{
  "mcpServers": {
    "cls": {
      "command": "uvx",
      "args": ["cls-mcp-server"],
      "env": {
        "CLS_SECRET_ID": "你的SecretId",
        "CLS_SECRET_KEY": "你的SecretKey",
        "CLS_REGION": "ap-shanghai"
      }
    }
  }
}
```

**方式二：使用源码**

```json
{
  "mcpServers": {
    "cls": {
      "command": "uv",
      "args": [
        "--directory", "/你的路径/cls-mcp-server",
        "run", "cls-mcp-server"
      ],
      "env": {
        "CLS_SECRET_ID": "你的SecretId",
        "CLS_SECRET_KEY": "你的SecretKey",
        "CLS_REGION": "ap-shanghai"
      }
    }
  }
}
```

> 将 `/你的路径/cls-mcp-server` 替换为项目实际路径。

如需开启写操作：

```json
{
  "mcpServers": {
    "cls": {
      "command": "uv",
      "args": [
        "--directory", "/你的路径/cls-mcp-server",
        "run", "cls-mcp-server",
        "--enable-write"
      ],
      "env": {
        "CLS_SECRET_ID": "你的SecretId",
        "CLS_SECRET_KEY": "你的SecretKey",
        "CLS_REGION": "ap-shanghai"
      }
    }
  }
}
```

#### Cursor

编辑 Cursor MCP 配置文件 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "cls": {
      "command": "uv",
      "args": [
        "--directory", "/你的路径/cls-mcp-server",
        "run", "cls-mcp-server"
      ],
      "env": {
        "CLS_SECRET_ID": "你的SecretId",
        "CLS_SECRET_KEY": "你的SecretKey",
        "CLS_REGION": "ap-shanghai"
      }
    }
  }
}
```

#### VS Code (Copilot)

在 VS Code 的 `settings.json` 中添加：

```json
{
  "mcp": {
    "servers": {
      "cls": {
        "command": "uv",
        "args": [
          "--directory", "/你的路径/cls-mcp-server",
          "run", "cls-mcp-server"
        ],
        "env": {
          "CLS_SECRET_ID": "你的SecretId",
          "CLS_SECRET_KEY": "你的SecretKey",
          "CLS_REGION": "ap-shanghai"
        }
      }
    }
  }
}
```

#### 使用 .env 文件简化配置

如果已在项目根目录配置好 `.env` 文件，客户端配置中可省略 `env` 字段：

```json
{
  "mcpServers": {
    "cls": {
      "command": "uv",
      "args": [
        "--directory", "/你的路径/cls-mcp-server",
        "run", "cls-mcp-server"
      ]
    }
  }
}
```

---

## 4. 远程部署（SSE / Streamable HTTP）

远程部署适用于将 CLS MCP Server 作为独立服务运行，供远程 MCP 客户端连接。

### 4.1 传输模式选择

| 模式 | 端点路径 | 特点 | 推荐场景 |
|------|----------|------|----------|
| **Streamable HTTP** | `/mcp` | 无状态 HTTP，支持水平扩展，无需 session affinity | K8s 部署，新项目（推荐） |
| **SSE** | `/sse` | 长连接，需要 session affinity | 兼容旧版 MCP 客户端 |

> 推荐使用 **Streamable HTTP** 模式，它基于标准 HTTP 请求/响应，天然支持负载均衡和水平扩展。

### 4.2 直接启动

```bash
# Streamable HTTP 模式（推荐）
uv run cls-mcp-server --transport streamable-http --host 0.0.0.0 --port 8000

# SSE 模式
uv run cls-mcp-server --transport sse --host 0.0.0.0 --port 8000
```

启动后可通过健康检查端点验证：

```bash
# 存活检查
curl http://localhost:8000/health

# 就绪检查（验证密钥配置）
curl http://localhost:8000/readiness
```

### 4.3 systemd 服务（虚拟机部署）

在传统虚拟机上，建议使用 systemd 管理服务进程。提供**一键脚本**和**手动安装**两种方式。

#### 方式一：一键部署脚本（推荐）

适用于 CentOS 7+、Ubuntu 18.04+、Debian 10+ 等 Linux 发行版。脚本自动处理 uv 安装、Python 3.12 下载、依赖安装、服务注册全流程。

**第一步：将源码上传到服务器**

Git clone（推荐，支持后续一键升级）：

```bash
git clone <repo-url> /tmp/cls-mcp-server
cd /tmp/cls-mcp-server
```

> **提示**：使用 git clone 方式安装后，安装目录会保留 `.git` 信息，后续可通过 `install.sh --upgrade` 一键升级。

或者 **tar.gz 打包上传**（网络差时使用）：

```bash
# === 在开发机上执行 ===

# 打包（排除不需要的文件）
cd cls-mcp-server
tar czf cls-mcp-server.tar.gz \
    --exclude='.git' \
    --exclude='.gitignore' \
    --exclude='.dockerignore' \
    --exclude='.codebuddy' \
    --exclude='.pytest_cache' \
    --exclude='.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='tests' \
    --exclude='docs' \
    --exclude='cls-search-log-test' \
    --exclude='.venv' \
    --exclude='docker-compose.yaml' \
    -C .. cls-mcp-server

# 上传到服务器
scp cls-mcp-server.tar.gz root@your-server:/tmp/

# === 在服务器上执行 ===
cd /tmp
tar xzf cls-mcp-server.tar.gz
cd cls-mcp-server
```

> **安全提示**：tar.gz 包中**不包含** `.env` 文件（含密钥），密钥在服务器上单独配置。

**第二步：运行一键部署脚本**

```bash
# 默认安装到 /opt/cls-mcp-server，监听 8000 端口
sudo bash deploy/systemd/install.sh

# 或指定参数
sudo bash deploy/systemd/install.sh \
    --install-dir /opt/cls-mcp-server \
    --port 8000 \
    --region ap-shanghai
```

脚本会自动完成：
1. 检测操作系统和 systemd 版本
2. 安装 uv 包管理器
3. 通过 uv 自动下载 Python 3.12（无需系统自带 Python 3.10+）
4. 安装项目依赖
5. 生成环境变量文件（`.env`，权限 600）
6. 注册并启动 systemd 服务

**第三步：配置密钥并启动**

```bash
# 编辑环境变量文件，填入真实密钥
sudo vim /opt/cls-mcp-server/.env

# 如果脚本检测到密钥未配置会跳过启动，手动启动：
sudo systemctl start cls-mcp-server

# 验证
sudo systemctl status cls-mcp-server
curl http://127.0.0.1:8000/health
```

> **CentOS 7 特别说明**：CentOS 7 自带 Python 2.7，不满足项目要求（>= 3.10）。一键脚本通过 uv 自动下载独立的 Python 3.12，不影响系统自带 Python。

#### 方式二：手动安装

如果需要更细粒度的控制，可按以下步骤手动安装：

```bash
# 1. 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 创建服务用户
sudo useradd -r -s /sbin/nologin -d /opt/cls-mcp-server cls-mcp

# 3. 部署代码到安装目录
sudo mkdir -p /opt/cls-mcp-server
sudo cp -r src pyproject.toml uv.lock deploy .env.example /opt/cls-mcp-server/

# 4. 安装 Python 和依赖
cd /opt/cls-mcp-server
sudo uv python install 3.12
sudo uv sync --frozen --python 3.12

# 5. 配置环境变量
sudo cp .env.example .env
sudo vim .env  # 填入 CLS_SECRET_ID、CLS_SECRET_KEY、CLS_REGION
sudo chown cls-mcp:cls-mcp .env
sudo chmod 600 .env

# 6. 安装 systemd 服务
sudo cp deploy/systemd/cls-mcp-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cls-mcp-server
sudo systemctl start cls-mcp-server

# 7. 查看状态和日志
sudo systemctl status cls-mcp-server
sudo journalctl -u cls-mcp-server -f
```

#### 卸载

```bash
sudo bash /opt/cls-mcp-server/deploy/systemd/uninstall.sh

# 保留配置文件（含密钥备份）
sudo bash /opt/cls-mcp-server/deploy/systemd/uninstall.sh --keep-config
```

### 4.4 Nginx 反向代理

推荐在前端使用 Nginx 做反向代理和 TLS 终结：

```nginx
upstream cls_mcp_backend {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl;
    server_name cls-mcp.example.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 健康检查端点
    location /health {
        proxy_pass http://cls_mcp_backend;
    }

    location /readiness {
        proxy_pass http://cls_mcp_backend;
    }

    # Streamable HTTP 模式
    location /mcp {
        proxy_pass http://cls_mcp_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    # SSE 模式（如需同时支持）
    location /sse {
        proxy_pass http://cls_mcp_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    location /messages/ {
        proxy_pass http://cls_mcp_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

### 4.5 远程客户端接入

**Streamable HTTP 模式** — 客户端连接 URL：`http(s)://your-server:8000/mcp`

**SSE 模式** — 客户端连接 URL：`http(s)://your-server:8000/sse`

> 如果启用了 Bearer Token 认证（`MCP_AUTH_TOKEN`），客户端需要在连接时携带认证头，详见 [第 7 节 HTTP 认证](#7-http-认证bearer-token)。

Claude Desktop 配置示例（Streamable HTTP）：

```json
{
  "mcpServers": {
    "cls": {
      "url": "https://cls-mcp.example.com/mcp"
    }
  }
}
```

Cursor 配置示例（SSE）：

```json
{
  "mcpServers": {
    "cls": {
      "url": "https://cls-mcp.example.com/sse"
    }
  }
}
```

---

## 5. Docker 部署

### 5.1 获取镜像

**方式一：从容器镜像仓库拉取（推荐）**

```bash
# 从 GitHub Container Registry 拉取
docker pull ghcr.io/tinker-lgd2026/cls-mcp-server:latest
```

**方式二：本地构建**

```bash
# 在项目根目录执行
docker build -t cls-mcp-server:latest -f deploy/docker/Dockerfile .
```

镜像特点：
- 多阶段构建，最终镜像基于 `python:3.12-slim`
- 使用 uv 安装依赖，构建可复现
- 以非 root 用户运行
- 默认传输方式为 `streamable-http`

### 5.2 docker compose 快速启动

```bash
# 创建 .env 文件（如果还没有）
cp .env.example .env
# 编辑 .env，填入密钥和地域

# 启动
docker compose up -d

# 查看日志
docker compose logs -f

# 验证
curl http://localhost:8000/health
```

### 5.3 直接运行容器

```bash
docker run -d \
  --name cls-mcp-server \
  -p 8000:8000 \
  -e CLS_SECRET_ID=your-secret-id \
  -e CLS_SECRET_KEY=your-secret-key \
  -e CLS_REGION=ap-guangzhou \
  -e CLS_TRANSPORT=streamable-http \
  -e MCP_AUTH_TOKEN=your-secret-token \
  cls-mcp-server:latest
```

使用 SSE 模式：

```bash
docker run -d \
  --name cls-mcp-server \
  -p 8000:8000 \
  -e CLS_SECRET_ID=your-secret-id \
  -e CLS_SECRET_KEY=your-secret-key \
  -e CLS_REGION=ap-guangzhou \
  -e CLS_TRANSPORT=sse \
  cls-mcp-server:latest \
  --transport sse --host 0.0.0.0 --port 8000
```

### 5.4 健康检查

镜像内置 Docker HEALTHCHECK，也可手动验证：

```bash
# 存活检查
curl http://localhost:8000/health
# 返回: {"status":"ok","version":"0.1.0","transport":"streamable-http"}

# 就绪检查
curl http://localhost:8000/readiness
# 返回: {"status":"ready","checks":{"config_valid":true,"credentials":true,"region":"ap-guangzhou"}}
```

---

## 6. Kubernetes 部署

CLS MCP Server 是**无状态服务**（Streamable HTTP 模式下），可作为 Deployment 运行多副本，前面挂负载均衡。

### 6.1 原始 YAML 部署

```bash
# 1. 编辑密钥配置
vim deploy/kubernetes/secret.yaml  # 填入实际的 SecretId 和 SecretKey

# 2. 编辑非敏感配置（地域、传输方式等）
vim deploy/kubernetes/configmap.yaml

# 3. 按顺序部署
kubectl apply -f deploy/kubernetes/configmap.yaml
kubectl apply -f deploy/kubernetes/secret.yaml
kubectl apply -f deploy/kubernetes/deployment.yaml
kubectl apply -f deploy/kubernetes/service.yaml

# 4. 可选：部署 Ingress
kubectl apply -f deploy/kubernetes/ingress.yaml

# 5. 验证
kubectl get pods -l app=cls-mcp-server
kubectl logs -l app=cls-mcp-server -f
```

### 6.2 Helm Chart 部署

```bash
# 安装（设置密钥和地域）
helm install cls-mcp deploy/helm/cls-mcp-server \
  --set secret.secretId=your-secret-id \
  --set secret.secretKey=your-secret-key \
  --set config.region=ap-guangzhou

# 启用 Ingress
helm install cls-mcp deploy/helm/cls-mcp-server \
  --set secret.secretId=your-secret-id \
  --set secret.secretKey=your-secret-key \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=cls-mcp.example.com

# 启用自动扩缩容
helm install cls-mcp deploy/helm/cls-mcp-server \
  --set secret.secretId=your-secret-id \
  --set secret.secretKey=your-secret-key \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=10

# 升级配置
helm upgrade cls-mcp deploy/helm/cls-mcp-server --reuse-values \
  --set config.region=ap-shanghai

# 卸载
helm uninstall cls-mcp
```

### 6.3 架构说明

```
                    ┌─────────────┐
                    │  Ingress /  │
                    │ LoadBalancer│
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   Service   │
                    └──────┬──────┘
              ┌────────────┼────────────┐
              │            │            │
         ┌────┴────┐ ┌────┴────┐ ┌────┴────┐
         │  Pod 1  │ │  Pod 2  │ │  Pod N  │
         │ :8000   │ │ :8000   │ │ :8000   │
         └─────────┘ └─────────┘ └─────────┘
```

**关键特性：**

- **无状态**：Streamable HTTP 模式（`stateless_http=true`）下，每个请求独立处理，不依赖服务端会话状态
- **水平扩展**：可任意增减 Pod 副本数，负载均衡自动分配请求
- **健康检查**：`/health`（livenessProbe）和 `/readiness`（readinessProbe）确保故障 Pod 自动重启和流量摘除
- **滚动更新**：ConfigMap 变更通过 annotation checksum 自动触发 Deployment 滚动更新
- **SSE 模式注意**：如使用 SSE 传输，需开启 Service 的 `sessionAffinity: ClientIP`，因为 SSE 是长连接

---

## 7. HTTP 认证（Bearer Token）

远程部署（SSE / Streamable HTTP 模式）时，**强烈建议**启用 HTTP 认证，防止未授权访问。

### 7.1 启用认证

通过环境变量或 CLI 参数设置 Bearer Token：

```bash
# 环境变量方式
export MCP_AUTH_TOKEN="your-secret-token-here"
cls-mcp-server --transport streamable-http

# CLI 参数方式（优先级高于环境变量）
cls-mcp-server --transport streamable-http --auth-token "your-secret-token-here"

# Docker 方式
docker run -e MCP_AUTH_TOKEN="your-secret-token-here" ...

# docker compose 方式（在 .env 中添加）
MCP_AUTH_TOKEN=your-secret-token-here
```

启用后，所有 HTTP 请求（除 `/health` 和 `/readiness`）必须携带认证头：

```
Authorization: Bearer your-secret-token-here
```

### 7.2 客户端配置

Claude Desktop / Cursor 等客户端连接带认证的远程服务时，需在配置中添加 `headers`：

```json
{
  "mcpServers": {
    "cls": {
      "url": "https://cls-mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer your-secret-token-here"
      }
    }
  }
}
```

### 7.3 认证行为

| 场景 | 结果 |
|------|------|
| 未设置 `MCP_AUTH_TOKEN` | 不启用认证，所有请求直接通过（向后兼容） |
| 已设置 token，请求无 `Authorization` 头 | 返回 `401 Unauthorized` |
| 已设置 token，请求 token 不匹配 | 返回 `403 Forbidden` |
| 已设置 token，请求 token 匹配 | 正常处理请求 |
| 访问 `/health` 或 `/readiness` | 始终免认证（用于健康检查） |

### 7.4 Token 生成建议

```bash
# 使用 openssl 生成随机 token
openssl rand -hex 32

# 或使用 Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

> **安全提示**：Token 以常量时间比较（防止计时攻击），认证失败时不记录 Token 值。

---

## 8. 高级配置

### 三级权限控制

| 级别 | 工具数 | 环境变量 | 说明 |
|------|--------|----------|------|
| READ | 22 | 默认启用 | 查询、搜索、列表操作 |
| WRITE | 8 | `CLS_ENABLE_WRITE=true` | 创建、修改操作，工具描述自动追加 ⚠️ 警告 |
| DANGER | 5 | `CLS_ENABLE_WRITE=true` + `CLS_ENABLE_DANGEROUS=true` | 删除操作（不可逆），工具描述自动追加 🚨 警告 |

生产环境建议仅开启 READ 权限。如需写操作，建议单独部署一个开启写权限的实例，限制访问范围。

### 工具白名单（CLS_ENABLED_TOOLS）

默认情况下，Server 注册所有符合权限等级的工具。通过 `CLS_ENABLED_TOOLS` 可以精确控制注册哪些工具——**只有列在白名单中的工具才会被注册，AI 助手只能调用已注册的工具**。

#### 为什么要用白名单？

- **减少干扰**：工具越多，AI 越可能调用不相关的工具，缩小范围能提高准确率
- **安全隔离**：只暴露业务需要的能力，降低误操作风险
- **场景定制**：为不同团队/用途部署不同的工具集合

#### 配置语法

- **格式**：工具名用英文逗号 `,` 分隔，名称区分大小写
- **环境变量**：`CLS_ENABLED_TOOLS="cls_search_log,cls_get_log_context"`
- **CLI 参数**：`--enabled-tools "cls_search_log,cls_get_log_context"`
- **不设置**（默认）：注册全部符合权限等级的工具

#### 可选工具清单

以下是所有可配置的工具名称，按功能分组：

**日志查询（5 个）**

| 工具名称 | 功能说明 |
|---------|---------|
| `cls_search_log` | 检索分析 CLS 日志，支持 CQL 语法检索和 SQL 管道分析 |
| `cls_get_log_context` | 获取日志上下文，查看目标日志前后的记录 |
| `cls_get_log_histogram` | 获取日志数量直方图 |
| `cls_get_log_count` | 快速获取日志数量 |
| `cls_describe_search_syntax` | 获取检索语法参考和查询模板 |

**指标查询（3 个）**

| 工具名称 | 功能说明 |
|---------|---------|
| `cls_query_metric` | 查询指标数据（单时间点） |
| `cls_query_range_metric` | 查询指标数据（时间范围） |
| `cls_list_metrics` | 列出指标主题下所有可用指标 |

**告警管理（5 个只读 + 2 个写入 + 1 个危险）**

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_alarms` | 查询告警策略列表 | READ |
| `cls_describe_alarm_detail` | 获取告警策略详情 | READ |
| `cls_describe_alarm_notices` | 查询告警通知渠道 | READ |
| `cls_describe_alarm_records` | 查询告警历史记录 | READ |
| `cls_get_alarm_detail` | 通过 URL 获取告警详情 | READ |
| `cls_create_alarm` | 创建告警策略 | WRITE |
| `cls_modify_alarm` | 修改告警策略 | WRITE |
| `cls_delete_alarm` | 删除告警策略 | DANGER |

**资源管理（8 个只读 + 4 个写入 + 2 个危险）**

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_logsets` | 查询日志集列表 | READ |
| `cls_describe_topics` | 查询日志主题列表 | READ |
| `cls_describe_topic_detail` | 获取主题详情 | READ |
| `cls_describe_index` | 查询索引配置 | READ |
| `cls_describe_machine_groups` | 查询机器组列表 | READ |
| `cls_describe_machine_group_detail` | 获取机器组详情 | READ |
| `cls_describe_dashboards` | 查询仪表盘列表 | READ |
| `cls_describe_regions` | 查询支持的地域 | READ |
| `cls_create_logset` | 创建日志集 | WRITE |
| `cls_create_topic` | 创建日志主题 | WRITE |
| `cls_modify_topic` | 修改日志主题 | WRITE |
| `cls_modify_index` | 修改索引配置 | WRITE |
| `cls_delete_logset` | 删除日志集 | DANGER |
| `cls_delete_topic` | 删除日志主题 | DANGER |

**数据加工（1 个只读 + 1 个写入 + 1 个危险）**

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_data_transform_tasks` | 查询数据加工任务 | READ |
| `cls_create_data_transform` | 创建数据加工任务 | WRITE |
| `cls_delete_data_transform` | 删除数据加工任务 | DANGER |

**定时 SQL（1 个只读 + 1 个写入 + 1 个危险）**

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_describe_scheduled_sql_tasks` | 查询定时 SQL 任务 | READ |
| `cls_create_scheduled_sql` | 创建定时 SQL 任务 | WRITE |
| `cls_delete_scheduled_sql` | 删除定时 SQL 任务 | DANGER |

**时间工具（1 个）**

| 工具名称 | 功能说明 | 权限 |
|---------|---------|------|
| `cls_convert_time` | 时间与时间戳互转 | READ |

#### 常见场景示例

**场景一：只做日志查询分析**

```bash
CLS_ENABLED_TOOLS="cls_search_log,cls_get_log_context,cls_get_log_histogram,cls_get_log_count,cls_describe_search_syntax,cls_convert_time"
```

适合：日常日志排查、问题定位。

**场景二：只做告警监控**

```bash
CLS_ENABLED_TOOLS="cls_describe_alarms,cls_describe_alarm_detail,cls_describe_alarm_notices,cls_describe_alarm_records,cls_get_alarm_detail"
```

适合：告警值班、告警分析。

**场景三：日志查询 + 资源浏览**

```bash
CLS_ENABLED_TOOLS="cls_search_log,cls_get_log_context,cls_get_log_count,cls_describe_topics,cls_describe_logsets,cls_describe_index,cls_describe_regions,cls_convert_time"
```

适合：需要先浏览有哪些日志主题，再查询日志内容。

**场景四：指标查询**

```bash
CLS_ENABLED_TOOLS="cls_query_metric,cls_query_range_metric,cls_list_metrics,cls_convert_time"
```

适合：只做时序指标分析。

**场景五：全功能（默认）**

不设置 `CLS_ENABLED_TOOLS`，或设为空字符串。

#### 注意事项

1. **白名单与权限是 AND 关系**：工具同时满足白名单和权限等级才会被注册。例如 `cls_create_alarm` 即使在白名单中，也需要 `CLS_ENABLE_WRITE=true` 才会注册
2. **工具名必须完全匹配**：填写了不存在的工具名，启动时会在日志中输出警告（`⚠️ Unknown tool names in CLS_ENABLED_TOOLS`），但不影响其他工具正常注册
3. **建议搭配 `cls_convert_time`**：日志查询和指标查询都需要时间戳参数，建议白名单中包含 `cls_convert_time` 工具
4. **Docker / K8s 配置**：在 Docker 环境变量或 K8s ConfigMap 中设置即可，与其他环境变量用法相同

```bash
# Docker
docker run -e CLS_ENABLED_TOOLS="cls_search_log,cls_get_log_context" ...

# docker-compose.yaml
environment:
  CLS_ENABLED_TOOLS: "cls_search_log,cls_get_log_context,cls_convert_time"
```

### 稳定性配置（重试 & 熔断）

Server 内置了自动重试和熔断保护机制，应对网络抖动和后端服务异常，默认配置适合大多数场景。

#### 重试机制

当 SDK 调用因网络超时或服务端临时错误失败时，自动进行指数退避重试：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CLS_REQUEST_TIMEOUT` | `60` | 单次 SDK 请求超时（秒） |
| `CLS_RETRY_MAX_ATTEMPTS` | `3` | 最大尝试次数（含首次），设为 `1` 可禁用重试 |
| `CLS_RETRY_BASE_DELAY` | `1.0` | 基础退避延迟（秒），第 N 次重试延迟约为 `base_delay * 2^(N-1)` + 随机抖动 |

```bash
# 增大超时和重试次数（网络不稳定的环境）
CLS_REQUEST_TIMEOUT=120
CLS_RETRY_MAX_ATTEMPTS=5
CLS_RETRY_BASE_DELAY=2.0

# 禁用重试（调试用）
CLS_RETRY_MAX_ATTEMPTS=1
```

#### 熔断器

当某个工具连续失败达到阈值时，自动触发熔断——后续调用直接返回错误而不实际请求后端，避免雪崩。熔断一段时间后自动进入半开状态尝试恢复。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CLS_CB_FAILURE_THRESHOLD` | `5` | 连续失败多少次后触发熔断 |
| `CLS_CB_RECOVERY_TIMEOUT` | `30` | 熔断后多少秒进入半开状态尝试恢复 |

```bash
# 更敏感的熔断（3 次失败就熔断，15 秒后尝试恢复）
CLS_CB_FAILURE_THRESHOLD=3
CLS_CB_RECOVERY_TIMEOUT=15
```

### 多地域配置

**单实例即可管理所有地域**。每个工具函数都支持 `region` 可选参数，调用时指定即可动态切换地域，无需部署多个实例。

**工作原理**：
- `CLS_REGION` 环境变量设置默认地域（不传 `region` 参数时使用）
- 工具调用时传入 `region` 参数可覆盖默认地域，如 `region="ap-shanghai"`
- 不同地域的 SDK Client 按 `(secret_id, secret_key, region)` 缓存，互不混淆，线程安全

```bash
# 只需部署一个实例，设置默认地域即可
CLS_REGION=ap-guangzhou cls-mcp-server --transport streamable-http

# 调用工具时通过 region 参数查询其他地域
# 例如：cls_search_log(topic_id="xxx", query="*", region="ap-shanghai")
```

> **注意**：多地域访问要求所配置的密钥（SecretId/SecretKey）对目标地域拥有相应权限。

### 日志级别调优

| 级别 | 用途 |
|------|------|
| `ERROR` | 仅输出错误，生产环境推荐 |
| `WARNING` | 输出警告和错误 |
| `INFO` | 默认级别，输出启动信息和请求概况 |
| `DEBUG` | 详细调试信息，包括 SDK 调用详情，排查问题时使用 |

### Streamable HTTP vs SSE 对比

| 特性 | Streamable HTTP | SSE |
|------|----------------|-----|
| 连接方式 | 标准 HTTP 请求/响应 | 长连接 (Server-Sent Events) |
| 无状态支持 | ✅ 原生支持 | ❌ 需要 session affinity |
| K8s 水平扩展 | ✅ 无限制 | ⚠️ 受限于 session affinity |
| 负载均衡 | ✅ 任意 LB | ⚠️ 需要粘性会话 |
| 端点路径 | `/mcp` | `/sse` |
| 推荐场景 | 新部署、K8s 环境 | 兼容旧版客户端 |

---

## 9. 国内环境加速

国内网络访问 PyPI、GitHub、Docker Hub 等海外服务可能较慢，以下提供加速方案。

### 9.1 pip / uv 国内镜像

```bash
# pip 使用清华源
pip install cls-mcp-server -i https://pypi.tuna.tsinghua.edu.cn/simple

# pip 永久配置（写入 ~/.pip/pip.conf）
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# uv 使用国内源
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple uv sync

# uv 永久配置（写入 ~/.config/uv/uv.toml）
# [pip]
# index-url = "https://pypi.tuna.tsinghua.edu.cn/simple"
```

常用国内 PyPI 镜像源：

| 镜像源 | URL |
|--------|-----|
| 清华大学 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| 阿里云 | `https://mirrors.aliyun.com/pypi/simple` |
| 腾讯云 | `https://mirrors.cloud.tencent.com/pypi/simple` |
| 中科大 | `https://pypi.mirrors.ustc.edu.cn/simple` |

### 9.2 Docker 国内镜像加速

配置 Docker daemon 使用国内镜像加速器：

```bash
# 编辑 Docker 配置
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://hub-mirror.c.163.com"
  ]
}
EOF

# 重启 Docker
sudo systemctl daemon-reload
sudo systemctl restart docker
```

> **腾讯云服务器**内网环境下推荐使用 `https://mirror.ccs.tencentyun.com`，速度最快。

### 9.3 uv 安装加速

如果 `curl https://astral.sh/uv/install.sh` 下载慢，可以手动下载 uv 二进制：

```bash
# 从 GitHub Release 手动下载（可使用代理或镜像站）
# x86_64 Linux
wget https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz
tar xzf uv-x86_64-unknown-linux-gnu.tar.gz
sudo mv uv /usr/local/bin/

# aarch64 Linux (ARM)
wget https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-unknown-linux-gnu.tar.gz
```

### 9.4 GitHub 访问加速

如果 `git clone` GitHub 仓库速度慢：

```bash
# 方式一：使用国内 GitHub 代理（临时）
git clone https://ghproxy.com/https://github.com/Tinker-LGD2026/cls-mcp-server.git

# 方式二：下载 tar.gz 包上传（最可靠，参考 4.3 节 tar.gz 打包方式）

# 方式三：配置 Git 代理（如果有代理服务器）
git config --global http.proxy http://your-proxy:port
```

---

## 10. CI/CD 自动发布

项目配置了 GitHub Actions 工作流，在推送 Git Tag 时自动构建并发布。

### 10.1 PyPI 发布

**触发条件**：推送 `v*` 格式的 Tag（如 `v0.1.0`）

**所需 Secrets**：

| Secret 名称 | 说明 | 获取方式 |
|-------------|------|----------|
| `PYPI_API_TOKEN` | PyPI API Token | [pypi.org](https://pypi.org) → Account Settings → API tokens |

**配置步骤**：

1. 注册 [PyPI](https://pypi.org) 账号
2. 在 Account Settings → API tokens 中创建 Token
3. 到 GitHub 仓库 Settings → Secrets and variables → Actions
4. 点击 "New repository secret"，Name 填 `PYPI_API_TOKEN`，Value 粘贴 Token

**发布流程**：

```bash
# 1. 更新 pyproject.toml 中的版本号
# version = "0.2.0"

# 2. 提交并打 Tag
git add pyproject.toml
git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main --tags

# 3. GitHub Actions 自动执行：构建 → 验证 → 发布到 PyPI
```

> **首次发布前**，可先发到 [TestPyPI](https://test.pypi.org) 验证，在 workflow 中取消注释 `repository-url` 行即可。

### 10.2 Docker 镜像发布

**触发条件**：推送 `v*` 格式的 Tag（同上）

**默认推送到 GHCR**（GitHub Container Registry），无需额外配置。

推送 Tag 时自动构建并推送到 GHCR。

### 10.3 发布检查清单

发布新版本前确认：

- [ ] `pyproject.toml` 中的 `version` 已更新
- [ ] 代码已合并到 main 分支
- [ ] 本地测试通过：`uv run cls-mcp-server --help`
- [ ] Tag 格式正确：`v{major}.{minor}.{patch}`（如 `v0.2.0`）
- [ ] Tag 版本与 `pyproject.toml` 中的 `version` 一致

---

## 11. 常见问题与故障排查

### Q: 启动报错 `CLS_SECRET_ID is required`

确认已正确配置环境变量。检查方式：

```bash
# 确认 .env 文件存在且内容正确
cat .env

# 或直接设置环境变量后启动
CLS_SECRET_ID=xxx CLS_SECRET_KEY=xxx CLS_REGION=ap-guangzhou uv run cls-mcp-server
```

### Q: CentOS 7 上 Python 版本不满足要求

CentOS 7 自带 Python 2.7，项目要求 Python >= 3.10。**无需手动编译安装 Python**，使用 uv 自动管理：

```bash
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# uv 自动下载 Python 3.12 并创建虚拟环境
cd /opt/cls-mcp-server
uv python install 3.12
uv sync --frozen --python 3.12
```

或直接使用一键部署脚本 `deploy/systemd/install.sh`，它会自动处理。

### Q: CentOS 7 上 systemd service 启动报错

CentOS 7 的 systemd 版本为 219，不支持部分安全沙箱指令。项目提供的 service 文件已做兼容处理。如果使用自定义 service 文件，请确保**不包含**以下指令：

```ini
# 以下指令需要 systemd 232+，CentOS 7 不支持
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=...
```

### Q: git clone 太慢怎么办？

在开发机上打包 tar.gz 后通过 scp 上传：

```bash
# 开发机上打包（自动排除不需要的文件）
tar czf cls-mcp-server.tar.gz \
    --exclude='.git' --exclude='.env' --exclude='__pycache__' \
    --exclude='tests' --exclude='docs' --exclude='.codebuddy' \
    --exclude='cls-search-log-test' --exclude='.venv' \
    --exclude='.pytest_cache' --exclude='*.pyc' \
    -C .. cls-mcp-server

# 上传并解压
scp cls-mcp-server.tar.gz root@your-server:/tmp/
ssh root@your-server "cd /tmp && tar xzf cls-mcp-server.tar.gz"
```

### Q: Claude Desktop 中看不到 CLS 工具

1. 确认 `claude_desktop_config.json` 配置路径正确
2. 确认 `--directory` 指向项目根目录（包含 `pyproject.toml` 的目录）
3. 重启 Claude Desktop
4. 检查 Claude Desktop 日志中是否有 MCP Server 启动错误

### Q: 调用工具返回认证错误

1. 检查 SecretId / SecretKey 是否正确
2. 确认该密钥拥有 CLS 相关接口的访问权限
3. 确认 `CLS_REGION` 与目标资源所在地域一致

### Q: 只看到 20 个工具，缺少创建/删除类工具

默认只注册只读工具。如需写操作：

```bash
# 开启写操作（+8 个工具）
uv run cls-mcp-server --enable-write

# 开启写操作 + 危险操作（+13 个工具）
uv run cls-mcp-server --enable-write --enable-dangerous
```

### Q: 远程连接返回 401 Unauthorized

服务端启用了 Bearer Token 认证（`MCP_AUTH_TOKEN`），客户端需携带认证头。参考 [第 7 节 HTTP 认证](#7-http-认证bearer-token) 配置 `Authorization: Bearer <token>`。

### Q: 如何查看调试日志？

```bash
uv run cls-mcp-server --log-level DEBUG
```

或在 `.env` 中设置 `CLS_LOG_LEVEL=DEBUG`。日志输出到 stderr。

systemd 服务模式下查看日志：

```bash
sudo journalctl -u cls-mcp-server -f
sudo journalctl -u cls-mcp-server --since "10 minutes ago"
```

### Q: 密钥安全如何保障？

1. `.env` 文件权限设置为 600：`chmod 600 .env`
2. `.env` 已在 `.gitignore` 中排除，不会被提交到 Git
3. 打包 tar.gz 时**不包含** `.env` 文件，密钥在服务器上单独配置
4. systemd 服务以专用用户 `cls-mcp` 运行，仅该用户可读取 `.env`

---

## 12. 更新与卸载

### 更新

**PyPI 安装模式：**

```bash
# pip 方式
pip install --upgrade cls-mcp-server

# uvx 会自动使用最新版本，也可强制更新缓存
uvx --reinstall cls-mcp-server --help
```

**stdio 本地源码模式：**

```bash
cd cls-mcp-server
git pull
uv sync
```

**systemd 服务模式：**

方式一：一键升级（推荐）

```bash
# 在安装目录执行升级脚本，自动完成 git pull + 依赖更新 + 重启
sudo bash /opt/cls-mcp-server/deploy/systemd/install.sh --upgrade
```

脚本自动执行：
1. 在安装目录 `git pull` 拉取最新代码
2. `uv sync` 同步 Python 依赖
3. `systemctl restart` 重启服务
4. 健康检查验证

> **注意**：`.env` 配置文件在升级过程中**不会被修改**，你的密钥和配置保持不变。
>
> **前提**：首次安装时需使用 `git clone` 方式上传源码（而非 tar.gz），这样安装目录才有 `.git` 信息支持 `--upgrade`。如果是 tar.gz 方式安装的，升级时需重新上传 tar.gz 并重跑 `install.sh`（不加 `--upgrade`），`.env` 同样不会被覆盖。

方式二：手动升级

```bash
cd /opt/cls-mcp-server

# 配置 safe.directory（首次手动操作需要，避免 git 报 dubious ownership）
sudo git config --global --add safe.directory /opt/cls-mcp-server

# 拉取最新代码（用服务用户执行，保持文件权限一致）
sudo -u cls-mcp git pull

# 更新依赖
sudo -u cls-mcp bash -c "export UV_PYTHON_INSTALL_DIR=/opt/cls-mcp-server/.python && cd /opt/cls-mcp-server && uv sync --frozen --python 3.12"

# 重启服务
sudo systemctl restart cls-mcp-server

# 验证
sudo systemctl status cls-mcp-server
curl http://127.0.0.1:8000/health
```

> **权限说明**：安装目录 owner 是 `cls-mcp` 服务用户，手动操作 git/uv 时建议用 `sudo -u cls-mcp` 执行，避免产生 root 所有的文件导致服务运行时权限问题。

**Docker 部署模式：**

```bash
# 拉取最新镜像
docker pull ghcr.io/tinker-lgd2026/cls-mcp-server:latest

# 重启容器
docker compose down && docker compose up -d
```

### 卸载

**stdio 本地模式：**

```bash
rm -rf cls-mcp-server
```

**systemd 服务模式：**

```bash
# 使用卸载脚本
sudo bash /opt/cls-mcp-server/deploy/systemd/uninstall.sh

# 保留配置文件备份
sudo bash /opt/cls-mcp-server/deploy/systemd/uninstall.sh --keep-config
```
