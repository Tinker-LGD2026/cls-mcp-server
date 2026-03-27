# CLS MCP Server

腾讯云日志服务（Cloud Log Service）MCP Server —— 从可观测性视角为 AI 助手提供全方位日志服务能力。

## 功能特性

- **日志查询分析**：CQL 检索 + SQL 管道分析、上下文查看、直方图、日志计数
- **指标查询**：PromQL 兼容的单时间点/时间范围指标查询
- **告警管理**：告警策略/通知渠道/告警记录查询与管理
- **资源管理**：日志集、日志主题、索引、机器组、仪表盘的增删改查
- **数据加工 & 定时 SQL**：数据加工任务和定时 SQL 任务管理
- **三级权限控制**：READ（默认）/ WRITE / DANGER 分级保护

共 **33 个工具**，覆盖 CLS 日志服务的完整能力。

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

**远程服务**（Streamable HTTP 模式）：

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