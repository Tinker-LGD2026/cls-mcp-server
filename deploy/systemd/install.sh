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

    if curl -sf --connect-timeout 5 https://astral.sh >/dev/null 2>&1; then
        log_info "网络连通 (astral.sh)"
    elif curl -sf --connect-timeout 5 https://pypi.org >/dev/null 2>&1; then
        log_info "网络连通 (pypi.org)"
    else
        die "无法访问外网，uv 和 Python 安装需要网络连接"
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

install_uv() {
    log_step "安装 uv 包管理器..."

    # 检查是否已安装
    if command -v uv &>/dev/null; then
        local uv_ver
        uv_ver=$(uv --version 2>/dev/null || echo "unknown")
        log_info "uv 已安装: $uv_ver，跳过"
        return 0
    fi

    # 安装 uv 到 /usr/local/bin（全局可用）
    log_info "正在下载并安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh

    # uv 默认安装到 ~/.local/bin 或 ~/.cargo/bin
    # 创建符号链接到 /usr/local/bin 方便全局使用
    local uv_path=""
    for p in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [[ -x "$p" ]]; then
            uv_path="$p"
            break
        fi
    done

    if [[ -z "$uv_path" ]]; then
        die "uv 安装失败：找不到 uv 可执行文件"
    fi

    if [[ ! -x /usr/local/bin/uv ]]; then
        ln -sf "$uv_path" /usr/local/bin/uv
    fi

    log_info "uv 安装成功: $(uv --version)"
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
