# ============================================================
# CLS MCP Server - 多阶段构建 Dockerfile
# ============================================================
# 构建: docker build -t cls-mcp-server -f deploy/docker/Dockerfile .
# 运行: docker run -p 8000:8000 --env-file .env cls-mcp-server
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装 uv 包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制依赖定义
COPY pyproject.toml uv.lock ./

# 安装依赖（不安装项目本身，利用缓存）
RUN uv sync --frozen --no-install-project

# 复制源码并安装项目
COPY src/ src/
RUN uv sync --frozen


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

LABEL maintainer="tinkerli"
LABEL description="腾讯云 CLS 日志服务 MCP Server"

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r mcp && useradd -r -g mcp -d /app -s /sbin/nologin mcp

# 从 builder 复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # 默认传输方式（可在运行时覆盖）
    CLS_TRANSPORT=streamable-http \
    CLS_HOST=0.0.0.0 \
    CLS_PORT=8000

# 暴露端口
EXPOSE 8000

# 切换到非 root 用户
USER mcp

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
ENTRYPOINT ["cls-mcp-server"]
CMD ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
