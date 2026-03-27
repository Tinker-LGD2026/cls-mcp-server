#!/bin/bash
# ============================================================
# CLS MCP Server - CentOS 7+ 一键部署脚本
# ============================================================
# 用法:
#   sudo bash install.sh
#   sudo bash install.sh --install-dir /opt/cls-mcp-server
#   sudo bash install.sh --port 9000 --region ap-shanghai
# ============================================================
set -euo pipefail

# ======================== 默认配置 ========================

INSTALL_DIR="/opt/cls-mcp-server"
SERVICE_NAME="cls-mcp-server"
SERVICE_USER="cls-mcp"
SERVICE_GROUP="cls-mcp"

# 服务运行参数（可通过命令行覆盖）
CLS_PORT="${CLS_PORT:-8000}"
CLS_HOST="${CLS_HOST:-0.0.0.0}"
CLS_REGION="${CLS_REGION:-ap-guangzhou}"
CLS_TRANSPORT="${CLS_TRANSPORT:-streamable-http}"

# Python 版本
PYTHON_VERSION="3.12"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 网络状态标记（由 check_network 设置）
NETWORK_ASTRAL_OK=false
NETWORK_PYPI_OK=false
NETWORK_CHINA_MIRROR_OK=false

# ======================== 工具函数 ========================

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

die() { log_error "$*"; exit 1; }

# ======================== 参数解析 ========================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --install-dir)  INSTALL_DIR="$2";   shift 2 ;;
            --port)         CLS_PORT="$2";      shift 2 ;;
            --host)         CLS_HOST="$2";      shift 2 ;;
            --region)       CLS_REGION="$2";    shift 2 ;;
            --transport)    CLS_TRANSPORT="$2"; shift 2 ;;
            --help|-h)
                echo "用法: sudo bash install.sh [选项]"
                echo ""
                echo "选项:"
                echo "  --install-dir DIR   安装目录 (默认: /opt/cls-mcp-server)"
                echo "  --port PORT         监听端口 (默认: 8000)"
                echo "  --host HOST         监听地址 (默认: 0.0.0.0)"
                echo "  --region REGION     腾讯云地域 (默认: ap-guangzhou)"
                echo "  --transport MODE    传输方式: streamable-http|sse (默认: streamable-http)"
                echo "  -h, --help          显示帮助"
                exit 0
                ;;
            *) die "未知参数: $1，使用 --help 查看帮助" ;;
        esac
    done
}

# ======================== 环境检测 ========================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "请使用 root 权限运行: sudo bash install.sh"
    fi
}

check_os() {
    log_step "检测操作系统..."

    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log_info "系统: ${PRETTY_NAME:-$ID $VERSION_ID}"
    elif [[ -f /etc/centos-release ]]; then
        log_info "系统: $(cat /etc/centos-release)"
    else
        log_warn "无法识别操作系统，继续安装..."
    fi

    # 检测 systemd 版本
    if command -v systemctl &>/dev/null; then
        local systemd_ver
        systemd_ver=$(systemctl --version | head -1 | awk '{print $2}')
        log_info "systemd 版本: $systemd_ver"
        if [[ "$systemd_ver" -lt 219 ]]; then
            die "systemd 版本过低 ($systemd_ver)，需要 219+"
        fi
    else
        die "未检测到 systemd，此脚本需要 systemd 支持"
    fi
}

check_dependencies() {
    log_step "检测基础依赖..."

    local missing=()
    for cmd in curl tar; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "缺少依赖: ${missing[*]}，尝试安装..."
        if command -v yum &>/dev/null; then
            yum install -y "${missing[@]}"
        elif command -v apt-get &>/dev/null; then
            apt-get update && apt-get install -y "${missing[@]}"
        else
            die "无法自动安装 ${missing[*]}，请手动安装后重试"
        fi
    fi

    log_info "基础依赖检测通过"
}

check_network() {
    log_step "检测网络连通性..."

    # 标记网络状况，供后续步骤使用
    NETWORK_ASTRAL_OK=false
    NETWORK_PYPI_OK=false
    NETWORK_CHINA_MIRROR_OK=false

    if curl -sf --connect-timeout 5 https://astral.sh >/dev/null 2>&1; then
        NETWORK_ASTRAL_OK=true
        log_info "astral.sh 可达 ✓"
    else
        log_warn "astral.sh 不可达（国内服务器正常现象）"
    fi

    if curl -sf --connect-timeout 5 https://pypi.org >/dev/null 2>&1; then
        NETWORK_PYPI_OK=true
        log_info "pypi.org 可达 ✓"
    else
        log_warn "pypi.org 不可达，将使用国内镜像源"
    fi

    if ! $NETWORK_PYPI_OK; then
        if curl -sf --connect-timeout 5 https://pypi.tuna.tsinghua.edu.cn >/dev/null 2>&1; then
            NETWORK_CHINA_MIRROR_OK=true
            log_info "清华 PyPI 镜像可达 ✓"
        elif curl -sf --connect-timeout 5 https://mirrors.aliyun.com >/dev/null 2>&1; then
            NETWORK_CHINA_MIRROR_OK=true
            log_info "阿里云镜像可达 ✓"
        fi
    fi

    # 至少要有一个 PyPI 源可达，否则无法安装依赖
    if ! $NETWORK_PYPI_OK && ! $NETWORK_CHINA_MIRROR_OK; then
        die "无法访问任何 PyPI 源（pypi.org / 清华镜像 / 阿里镜像），Python 依赖无法安装。\n  请检查服务器网络或 DNS 配置。"
    fi
}

# ======================== 安装步骤 ========================

create_user() {
    log_step "创建服务用户 ${SERVICE_USER}..."

    if id "$SERVICE_USER" &>/dev/null; then
        log_info "用户 ${SERVICE_USER} 已存在，跳过创建"
    else
        useradd -r -s /sbin/nologin -d "$INSTALL_DIR" -m "$SERVICE_USER"
        log_info "已创建系统用户: ${SERVICE_USER}"
    fi
}

# 在 sudo 环境下搜索已安装的 uv，解决 secure_path 找不到 uv 的问题
find_uv() {
    # 如果已经在 PATH 中，直接返回
    if command -v uv &>/dev/null; then
        return 0
    fi

    # sudo 的 secure_path 可能不包含用户目录，主动搜索常见安装位置
    local search_paths=(
        "/usr/local/bin"
        "/usr/bin"
        "$HOME/.local/bin"
        "/root/.local/bin"
        "$HOME/.cargo/bin"
        "/root/.cargo/bin"
    )

    for p in "${search_paths[@]}"; do
        if [[ -x "$p/uv" ]]; then
            log_info "在 $p 找到 uv，加入 PATH"
            export PATH="$p:$PATH"
            return 0
        fi
    done

    return 1
}

# 将 uv 复制到 /usr/local/bin，确保 sudo 和服务用户都能找到
ensure_uv_in_global_path() {
    local uv_real_path
    uv_real_path="$(command -v uv 2>/dev/null)"

    if [[ -z "$uv_real_path" ]]; then
        return 1
    fi

    # 已经在全局路径，不需要复制
    if [[ "$uv_real_path" == "/usr/local/bin/uv" ]] || [[ "$uv_real_path" == "/usr/bin/uv" ]]; then
        return 0
    fi

    # 复制到 /usr/local/bin（比软链接更可靠，避免 sudo secure_path 问题）
    log_info "将 uv 复制到 /usr/local/bin/ 确保全局可用..."
    cp -f "$uv_real_path" /usr/local/bin/uv
    chmod +x /usr/local/bin/uv

    # 同时处理 uvx
    local uvx_path
    uvx_path="$(dirname "$uv_real_path")/uvx"
    if [[ -x "$uvx_path" ]] && [[ ! -x /usr/local/bin/uvx ]]; then
        cp -f "$uvx_path" /usr/local/bin/uvx
        chmod +x /usr/local/bin/uvx
    fi

    export PATH="/usr/local/bin:$PATH"
    return 0
}

# 下载安装 uv（多源回退）
download_uv() {
    local arch
    arch="$(uname -m)"
    local os_type="unknown-linux-gnu"

    # 方式1: 官方安装脚本（海外服务器优先）
    if $NETWORK_ASTRAL_OK; then
        log_info "尝试从官方源安装 uv ..."
        if curl -LsSf --connect-timeout 15 --max-time 60 https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh 2>/dev/null; then
            if find_uv; then
                return 0
            fi
        fi
        log_warn "官方源安装失败"
    fi

    # 方式2: GitHub 镜像代理下载二进制
    local mirror_urls=(
        "https://ghfast.top/https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
        "https://gh-proxy.com/https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
        "https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
    )

    for url in "${mirror_urls[@]}"; do
        log_info "尝试从 $(echo "$url" | cut -d'/' -f3) 下载 uv 二进制..."
        if curl -fSL --connect-timeout 15 --max-time 120 "$url" -o /tmp/uv.tar.gz 2>/dev/null; then
            # 解压并安装到 /usr/local/bin
            if tar -xzf /tmp/uv.tar.gz -C /tmp 2>/dev/null; then
                local extracted_dir="/tmp/uv-${arch}-${os_type}"
                if [[ -x "$extracted_dir/uv" ]]; then
                    cp -f "$extracted_dir/uv" /usr/local/bin/uv
                    chmod +x /usr/local/bin/uv
                    [[ -x "$extracted_dir/uvx" ]] && cp -f "$extracted_dir/uvx" /usr/local/bin/uvx && chmod +x /usr/local/bin/uvx
                    rm -rf /tmp/uv.tar.gz "$extracted_dir"
                    export PATH="/usr/local/bin:$PATH"
                    log_info "uv 二进制安装成功"
                    return 0
                fi
            fi
            rm -f /tmp/uv.tar.gz
        fi
        log_warn "从该镜像下载失败，尝试下一个..."
    done

    return 1
}

install_uv() {
    log_step "安装 uv 包管理器..."

    # 第一步：搜索已存在的 uv
    if find_uv; then
        local uv_ver
        uv_ver=$(uv --version 2>/dev/null || echo "unknown")
        log_info "uv 已安装: $uv_ver"

        # 确保 uv 在全局路径（解决后续 sudo 调用问题）
        ensure_uv_in_global_path
        log_info "uv 路径: $(command -v uv)"
        return 0
    fi

    # 第二步：未安装，需要下载
    log_info "未检测到 uv，开始下载安装..."

    if download_uv; then
        ensure_uv_in_global_path
        log_info "uv 安装成功: $(uv --version)"
        return 0
    fi

    # 全部失败，给出手动安装指引
    echo ""
    log_error "uv 自动安装失败！请手动安装后重新运行此脚本。"
    echo ""
    echo "  手动安装方法（任选其一）："
    echo ""
    echo "  方法1 - 官方脚本（需要海外网络）："
    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "  方法2 - 手动下载二进制（推荐国内服务器）："
    echo "    wget https://ghfast.top/https://github.com/astral-sh/uv/releases/latest/download/uv-$(uname -m)-unknown-linux-gnu.tar.gz -O /tmp/uv.tar.gz"
    echo "    tar -xzf /tmp/uv.tar.gz -C /tmp"
    echo "    cp /tmp/uv-$(uname -m)-unknown-linux-gnu/uv /usr/local/bin/"
    echo "    chmod +x /usr/local/bin/uv"
    echo ""
    echo "  安装后重新运行: sudo bash $0"
    echo ""
    exit 1
}

setup_project() {
    log_step "安装项目到 ${INSTALL_DIR}..."

    # 检测源码位置（脚本所在目录的上两级即项目根目录）
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local source_dir
    source_dir="$(cd "$script_dir/../.." && pwd)"

    # 验证源码目录
    if [[ ! -f "$source_dir/pyproject.toml" ]]; then
        die "找不到 pyproject.toml，请确认脚本位于项目 deploy/systemd/ 目录下"
    fi

    # 如果安装目录不是源码目录，则复制必要文件
    if [[ "$INSTALL_DIR" != "$source_dir" ]]; then
        mkdir -p "$INSTALL_DIR"

        # 只复制运行所需的文件，排除不必要的内容
        log_info "复制项目文件到 ${INSTALL_DIR}..."
        rsync -a --delete \
            --exclude='.git' \
            --exclude='.gitignore' \
            --exclude='.dockerignore' \
            --exclude='.codebuddy' \
            --exclude='.pytest_cache' \
            --exclude='.env' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='tests/' \
            --exclude='docs/' \
            --exclude='cls-search-log-test/' \
            --exclude='docker-compose.yaml' \
            --exclude='.venv' \
            --exclude='*.tar.gz' \
            --exclude='需求大纲' \
            "$source_dir/" "$INSTALL_DIR/"

        # 如果没有 rsync，回退到 cp
        if [[ $? -ne 0 ]] && ! command -v rsync &>/dev/null; then
            log_warn "rsync 不可用，使用 cp 复制..."
            cp -r "$source_dir/src" "$INSTALL_DIR/"
            cp -r "$source_dir/deploy" "$INSTALL_DIR/"
            cp "$source_dir/pyproject.toml" "$INSTALL_DIR/"
            cp "$source_dir/uv.lock" "$INSTALL_DIR/" 2>/dev/null || true
            cp "$source_dir/.env.example" "$INSTALL_DIR/" 2>/dev/null || true
        fi
    fi

    # 使用 uv 安装 Python 和依赖
    cd "$INSTALL_DIR"

    # 如果官方 PyPI 不可达，配置国内镜像源
    if ! $NETWORK_PYPI_OK; then
        log_info "配置国内 PyPI 镜像源..."
        if curl -sf --connect-timeout 3 https://pypi.tuna.tsinghua.edu.cn >/dev/null 2>&1; then
            export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
            log_info "使用清华镜像: $UV_INDEX_URL"
        elif curl -sf --connect-timeout 3 https://mirrors.aliyun.com >/dev/null 2>&1; then
            export UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
            log_info "使用阿里镜像: $UV_INDEX_URL"
        fi
    fi

    log_info "使用 uv 安装 Python ${PYTHON_VERSION}..."
    uv python install "$PYTHON_VERSION"

    log_info "创建虚拟环境并安装依赖..."
    if [[ -f "uv.lock" ]]; then
        uv sync --frozen --python "$PYTHON_VERSION"
    else
        uv sync --python "$PYTHON_VERSION"
    fi

    # 验证安装
    if .venv/bin/cls-mcp-server --help &>/dev/null; then
        log_info "项目安装成功"
    else
        die "项目安装失败：cls-mcp-server 命令不可用"
    fi

    # 设置目录所有权
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"
}

setup_env_file() {
    log_step "配置环境变量..."

    local env_file="${INSTALL_DIR}/.env"

    if [[ -f "$env_file" ]]; then
        log_warn "环境变量文件已存在: ${env_file}"
        log_warn "跳过生成，请确认配置正确（特别是 CLS_SECRET_ID 和 CLS_SECRET_KEY）"
    else
        cat > "$env_file" <<EOF
# CLS MCP Server 环境变量配置
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ==============================
# !! 重要: 请替换下方密钥为真实值 !!

# [必填] 腾讯云 API 密钥
CLS_SECRET_ID=<请替换为你的SecretId>
CLS_SECRET_KEY=<请替换为你的SecretKey>

# [必填] 地域
CLS_REGION=${CLS_REGION}

# [可选] 传输方式
CLS_TRANSPORT=${CLS_TRANSPORT}

# [可选] 监听配置
CLS_HOST=${CLS_HOST}
CLS_PORT=${CLS_PORT}

# [可选] 无状态模式（推荐开启）
CLS_STATELESS_HTTP=true

# [可选] 权限控制（生产环境建议保持 false）
CLS_ENABLE_WRITE=false
CLS_ENABLE_DANGEROUS=false

# [可选] HTTP Bearer Token 认证（建议生产环境开启）
# 设置后，客户端请求需带 Authorization: Bearer <token> 头
# MCP_AUTH_TOKEN=your-secret-token-here

# [可选] 日志级别
CLS_LOG_LEVEL=INFO
EOF
        log_info "已生成环境变量文件: ${env_file}"
        log_warn "!! 请编辑 ${env_file}，填入真实的 CLS_SECRET_ID 和 CLS_SECRET_KEY !!"
    fi

    # 安全加固：仅服务用户可读写
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$env_file"
    chmod 600 "$env_file"
    log_info "环境变量文件权限已设置为 600（仅 ${SERVICE_USER} 可读写）"
}

install_service() {
    log_step "安装 systemd 服务..."

    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    local template="${INSTALL_DIR}/deploy/systemd/cls-mcp-server.service"

    if [[ -f "$template" ]]; then
        # 使用项目中的 service 模板，替换变量
        sed \
            -e "s|WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}|" \
            -e "s|EnvironmentFile=.*|EnvironmentFile=${INSTALL_DIR}/.env|" \
            -e "s|ExecStart=.*cls-mcp-server.*|ExecStart=${INSTALL_DIR}/.venv/bin/cls-mcp-server \\\\|" \
            -e "s|--host [^ ]*|--host ${CLS_HOST}|" \
            -e "s|--port [0-9]*|--port ${CLS_PORT}|" \
            -e "s|--transport [^ ]*|--transport ${CLS_TRANSPORT}|" \
            -e "s|User=.*|User=${SERVICE_USER}|" \
            -e "s|Group=.*|Group=${SERVICE_USER}|" \
            "$template" > "$service_file"
    else
        # 模板不存在时直接生成
        cat > "$service_file" <<EOF
[Unit]
Description=CLS MCP Server - 腾讯云日志服务 MCP Server
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/cls-mcp-server \\
    --transport ${CLS_TRANSPORT} \\
    --host ${CLS_HOST} \\
    --port ${CLS_PORT}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF
    fi

    # 重新加载 systemd 配置
    systemctl daemon-reload
    log_info "systemd 服务已安装: ${service_file}"

    # 设置开机自启
    systemctl enable "$SERVICE_NAME"
    log_info "已设置开机自启"
}

# ======================== 启动与验证 ========================

start_and_verify() {
    log_step "启动服务..."

    # 检查环境变量是否已配置
    local env_file="${INSTALL_DIR}/.env"
    if grep -q '<请替换为你的SecretId>' "$env_file" 2>/dev/null; then
        log_warn "检测到密钥尚未配置！"
        log_warn "请先编辑 ${env_file}，填入真实的 CLS_SECRET_ID 和 CLS_SECRET_KEY"
        log_warn "配置完成后执行: sudo systemctl start ${SERVICE_NAME}"
        echo ""
        print_summary "pending"
        return 0
    fi

    # 启动服务
    systemctl start "$SERVICE_NAME"
    sleep 2

    # 检查状态
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "服务启动成功"

        # 健康检查
        sleep 1
        if curl -sf "http://127.0.0.1:${CLS_PORT}/health" >/dev/null 2>&1; then
            log_info "健康检查通过"
            local health_resp
            health_resp=$(curl -sf "http://127.0.0.1:${CLS_PORT}/health" 2>/dev/null || echo "{}")
            log_info "响应: ${health_resp}"
        else
            log_warn "健康检查端点暂未响应（服务可能正在启动中）"
            log_warn "稍后可手动检查: curl http://127.0.0.1:${CLS_PORT}/health"
        fi

        print_summary "running"
    else
        log_error "服务启动失败，查看日志:"
        journalctl -u "$SERVICE_NAME" --no-pager -n 20
        echo ""
        log_error "请检查 ${env_file} 中的配置是否正确"
        exit 1
    fi
}

print_summary() {
    local status="${1:-unknown}"

    echo ""
    echo "============================================================"
    echo " CLS MCP Server 部署完成"
    echo "============================================================"
    echo ""
    echo "  安装目录:     ${INSTALL_DIR}"
    echo "  服务名称:     ${SERVICE_NAME}"
    echo "  运行用户:     ${SERVICE_USER}"
    echo "  传输方式:     ${CLS_TRANSPORT}"
    echo "  监听地址:     ${CLS_HOST}:${CLS_PORT}"
    echo "  服务状态:     ${status}"
    echo "  环境变量:     ${INSTALL_DIR}/.env"
    echo ""
    echo "常用命令:"
    echo "  查看状态:     sudo systemctl status ${SERVICE_NAME}"
    echo "  查看日志:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  重启服务:     sudo systemctl restart ${SERVICE_NAME}"
    echo "  停止服务:     sudo systemctl stop ${SERVICE_NAME}"
    echo "  编辑配置:     sudo vim ${INSTALL_DIR}/.env"
    echo "  健康检查:     curl http://127.0.0.1:${CLS_PORT}/health"
    echo ""

    if [[ "$status" == "pending" ]]; then
        echo "  !! 下一步: 编辑 ${INSTALL_DIR}/.env 填入密钥 !!"
        echo "  !! 然后执行: sudo systemctl start ${SERVICE_NAME}    !!"
        echo ""
    fi

    echo "客户端连接 URL:"
    if [[ "$CLS_TRANSPORT" == "streamable-http" ]]; then
        echo "  http://<服务器IP>:${CLS_PORT}/mcp"
    elif [[ "$CLS_TRANSPORT" == "sse" ]]; then
        echo "  http://<服务器IP>:${CLS_PORT}/sse"
    fi
    echo ""
    echo "============================================================"
}

# ======================== 主流程 ========================

main() {
    parse_args "$@"

    echo ""
    echo "============================================================"
    echo " CLS MCP Server 一键部署脚本"
    echo "============================================================"
    echo ""

    check_root
    check_os
    check_dependencies
    check_network
    create_user
    install_uv
    setup_project
    setup_env_file
    install_service
    start_and_verify
}

main "$@"
