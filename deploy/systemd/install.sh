#!/bin/bash
# ============================================================
# CLS MCP Server - 一键部署/升级脚本
# ============================================================
# 用法:
#   首次安装（远程 git clone）:
#     curl -fsSL https://raw.githubusercontent.com/TencentCloud/cls-mcp-server/main/deploy/systemd/install.sh | sudo bash
#     sudo bash install.sh
#
#   首次安装（本地源码）:
#     cd cls-mcp-server && sudo bash deploy/systemd/install.sh
#
#   升级:
#     sudo bash /opt/cls-mcp-server/deploy/systemd/install.sh --upgrade
#
#   指定参数:
#     sudo bash install.sh --port 9000 --region ap-shanghai
#     sudo bash install.sh --pypi-mirror https://pypi.tuna.tsinghua.edu.cn/simple
# ============================================================
#
# 权限模型:
#   - root:      创建用户、安装 uv 到 /usr/local/bin、管理 systemd、启停服务
#   - cls-mcp:   git clone/pull、uv sync、管理项目目录下所有文件
#   项目目录始终归 cls-mcp 所有，所有项目操作用 sudo -u cls-mcp 执行
#
# PyPI 源:
#   默认使用阿里云镜像 (https://mirrors.aliyun.com/pypi/simple)
#   可通过 --pypi-mirror 或 CLS_PYPI_INDEX_URL 环境变量覆盖
# ============================================================
set -euo pipefail

# ======================== 默认配置 ========================

INSTALL_DIR="/opt/cls-mcp-server"
SERVICE_NAME="cls-mcp-server"
SERVICE_USER="cls-mcp"
SERVICE_GROUP="cls-mcp"
REPO_URL="https://github.com/TencentCloud/cls-mcp-server.git"

# 运行模式
UPGRADE_MODE=false

# 服务运行参数（可通过命令行或环境变量覆盖）
CLS_PORT="${CLS_PORT:-8000}"
CLS_HOST="${CLS_HOST:-0.0.0.0}"
CLS_REGION="${CLS_REGION:-ap-guangzhou}"
CLS_TRANSPORT="${CLS_TRANSPORT:-streamable-http}"

# Python 版本
PYTHON_VERSION="3.12"

# PyPI 镜像源：默认阿里云，支持环境变量覆盖
PYPI_INDEX_URL="${CLS_PYPI_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"

# uv 绝对路径（由 find_uv/install_uv 设置）
UV_BIN=""

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 网络状态标记（由 check_network 设置）
NETWORK_ASTRAL_OK=false

# ======================== 工具函数 ========================

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

die() { log_error "$*"; exit 1; }

# 以 cls-mcp 用户身份执行命令（项目级操作专用）
# 使用 env 显式传递所需环境变量，避免 sudo 清空环境
run_as_user() {
    sudo -u "${SERVICE_USER}" \
        UV_PYTHON_INSTALL_DIR="${INSTALL_DIR}/.python" \
        UV_INDEX_URL="${PYPI_INDEX_URL}" \
        PATH="/usr/local/bin:/usr/bin:/bin:${PATH}" \
        HOME="$(eval echo ~${SERVICE_USER})" \
        bash -c "$*"
}

# ======================== 参数解析 ========================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --upgrade)       UPGRADE_MODE=true;     shift ;;
            --install-dir)   INSTALL_DIR="$2";      shift 2 ;;
            --port)          CLS_PORT="$2";         shift 2 ;;
            --host)          CLS_HOST="$2";         shift 2 ;;
            --region)        CLS_REGION="$2";       shift 2 ;;
            --transport)     CLS_TRANSPORT="$2";    shift 2 ;;
            --pypi-mirror)   PYPI_INDEX_URL="$2";   shift 2 ;;
            --help|-h)
                echo "用法: sudo bash install.sh [选项]"
                echo ""
                echo "模式:"
                echo "  (无参数)              首次安装模式"
                echo "  --upgrade             升级模式（git pull + 更新依赖 + 重启服务）"
                echo ""
                echo "选项:"
                echo "  --install-dir DIR     安装目录 (默认: /opt/cls-mcp-server)"
                echo "  --port PORT           监听端口 (默认: 8000)"
                echo "  --host HOST           监听地址 (默认: 0.0.0.0)"
                echo "  --region REGION       腾讯云地域 (默认: ap-guangzhou)"
                echo "  --transport MODE      传输方式: streamable-http|sse (默认: streamable-http)"
                echo "  --pypi-mirror URL     PyPI 镜像源 (默认: https://mirrors.aliyun.com/pypi/simple)"
                echo "  -h, --help            显示帮助"
                echo ""
                echo "环境变量:"
                echo "  CLS_PYPI_INDEX_URL    PyPI 镜像源（同 --pypi-mirror）"
                echo "  CLS_PORT / CLS_HOST / CLS_REGION / CLS_TRANSPORT"
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

    # 检测 systemd
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
    for cmd in curl tar git; do
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

    log_info "基础依赖检测通过 (curl, tar, git)"
}

check_network() {
    log_step "检测网络连通性..."

    NETWORK_ASTRAL_OK=false

    # 检测 astral.sh（决定 uv 安装方式）
    if curl -sf --connect-timeout 5 https://astral.sh >/dev/null 2>&1; then
        NETWORK_ASTRAL_OK=true
        log_info "astral.sh 可达 (海外网络)"
    else
        log_warn "astral.sh 不可达（国内服务器正常现象）"
    fi

    # 验证 PyPI 镜像源可达性
    log_info "PyPI 镜像源: ${PYPI_INDEX_URL}"
    local mirror_host
    mirror_host=$(echo "$PYPI_INDEX_URL" | sed -E 's|https?://([^/]+).*|\1|')
    if curl -sf --connect-timeout 5 "https://${mirror_host}" >/dev/null 2>&1; then
        log_info "镜像源 ${mirror_host} 可达 ✓"
    else
        log_warn "镜像源 ${mirror_host} 不可达，尝试备用源..."
        # 备用源回退：阿里 → 清华 → pypi.org
        if curl -sf --connect-timeout 5 https://mirrors.aliyun.com >/dev/null 2>&1; then
            PYPI_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
            log_info "回退到阿里云镜像: ${PYPI_INDEX_URL}"
        elif curl -sf --connect-timeout 5 https://pypi.tuna.tsinghua.edu.cn >/dev/null 2>&1; then
            PYPI_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
            log_info "回退到清华镜像: ${PYPI_INDEX_URL}"
        elif curl -sf --connect-timeout 5 https://pypi.org >/dev/null 2>&1; then
            PYPI_INDEX_URL="https://pypi.org/simple"
            log_info "回退到官方 PyPI: ${PYPI_INDEX_URL}"
        else
            die "无法访问任何 PyPI 源，Python 依赖无法安装。\n  请检查服务器网络或 DNS 配置。"
        fi
    fi
}

# ======================== 用户与目录 ========================

create_user() {
    log_step "创建服务用户 ${SERVICE_USER}..."

    if id "$SERVICE_USER" &>/dev/null; then
        log_info "用户 ${SERVICE_USER} 已存在，跳过创建"
    else
        useradd -r -s /sbin/nologin -d "$INSTALL_DIR" -m "$SERVICE_USER"
        log_info "已创建系统用户: ${SERVICE_USER}"
    fi
}

# 确保项目目录存在且归属 cls-mcp（仅在目录不存在时创建）
ensure_install_dir() {
    if [[ ! -d "$INSTALL_DIR" ]]; then
        mkdir -p "$INSTALL_DIR"
        chown "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"
        log_info "已创建安装目录: ${INSTALL_DIR}"
    fi
    # 确保目录归属正确（防止之前被 root 操作过）
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"
}

# ======================== uv 安装 ========================

# 搜索已安装的 uv，设置 UV_BIN 变量
find_uv() {
    # 按优先级搜索
    local search_paths=(
        "/usr/local/bin/uv"
        "/usr/bin/uv"
        "$HOME/.local/bin/uv"
        "/root/.local/bin/uv"
        "$HOME/.cargo/bin/uv"
        "/root/.cargo/bin/uv"
    )

    for p in "${search_paths[@]}"; do
        if [[ -x "$p" ]]; then
            UV_BIN="$p"
            return 0
        fi
    done

    # PATH 中搜索
    if command -v uv &>/dev/null; then
        UV_BIN="$(command -v uv)"
        return 0
    fi

    return 1
}

# 将 uv 复制到 /usr/local/bin（确保所有用户都能找到）
ensure_uv_in_global_path() {
    if [[ -z "$UV_BIN" ]]; then
        return 1
    fi

    # 已经在全局路径
    if [[ "$UV_BIN" == "/usr/local/bin/uv" ]] || [[ "$UV_BIN" == "/usr/bin/uv" ]]; then
        return 0
    fi

    log_info "将 uv 复制到 /usr/local/bin/ 确保全局可用..."
    cp -f "$UV_BIN" /usr/local/bin/uv
    chmod +x /usr/local/bin/uv

    # 同时处理 uvx
    local uvx_path
    uvx_path="$(dirname "$UV_BIN")/uvx"
    if [[ -x "$uvx_path" ]] && [[ ! -x /usr/local/bin/uvx ]]; then
        cp -f "$uvx_path" /usr/local/bin/uvx
        chmod +x /usr/local/bin/uvx
    fi

    UV_BIN="/usr/local/bin/uv"
    return 0
}

# 下载安装 uv（多源回退）
download_uv() {
    local arch
    arch="$(uname -m)"
    local os_type="unknown-linux-gnu"

    # 方式 1: 官方安装脚本
    if $NETWORK_ASTRAL_OK; then
        log_info "尝试从官方源安装 uv ..."
        if curl -LsSf --connect-timeout 15 --max-time 60 https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh 2>/dev/null; then
            if find_uv; then
                return 0
            fi
        fi
        log_warn "官方源安装失败"
    fi

    # 方式 2: GitHub 镜像代理下载二进制
    local mirror_urls=(
        "https://ghfast.top/https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
        "https://gh-proxy.com/https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
        "https://github.com/astral-sh/uv/releases/latest/download/uv-${arch}-${os_type}.tar.gz"
    )

    for url in "${mirror_urls[@]}"; do
        log_info "尝试从 $(echo "$url" | cut -d'/' -f3) 下载 uv 二进制..."
        if curl -fSL --connect-timeout 15 --max-time 120 "$url" -o /tmp/uv.tar.gz 2>/dev/null; then
            if tar -xzf /tmp/uv.tar.gz -C /tmp 2>/dev/null; then
                local extracted_dir="/tmp/uv-${arch}-${os_type}"
                if [[ -x "$extracted_dir/uv" ]]; then
                    cp -f "$extracted_dir/uv" /usr/local/bin/uv
                    chmod +x /usr/local/bin/uv
                    [[ -x "$extracted_dir/uvx" ]] && cp -f "$extracted_dir/uvx" /usr/local/bin/uvx && chmod +x /usr/local/bin/uvx
                    rm -rf /tmp/uv.tar.gz "$extracted_dir"
                    UV_BIN="/usr/local/bin/uv"
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

    if find_uv; then
        local uv_ver
        uv_ver=$("$UV_BIN" --version 2>/dev/null || echo "unknown")
        log_info "uv 已安装: $uv_ver (${UV_BIN})"
        ensure_uv_in_global_path
        return 0
    fi

    log_info "未检测到 uv，开始下载安装..."

    if download_uv; then
        ensure_uv_in_global_path
        log_info "uv 安装成功: $("$UV_BIN" --version)"
        return 0
    fi

    # 全部失败
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

# ======================== 项目安装 ========================

setup_project() {
    log_step "安装项目到 ${INSTALL_DIR}..."

    # 判断源码来源
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local source_dir
    source_dir="$(cd "$script_dir/../.." 2>/dev/null && pwd)" || source_dir=""

    local has_local_source=false
    if [[ -n "$source_dir" ]] && [[ -f "$source_dir/pyproject.toml" ]]; then
        has_local_source=true
    fi

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        # 已有 git 仓库，用 pull 更新
        log_info "检测到已有 git 仓库，拉取最新代码..."
        run_as_user "cd '${INSTALL_DIR}' && git pull"
    elif $has_local_source && [[ "$INSTALL_DIR" != "$source_dir" ]]; then
        # 本地有源码且不是同一目录，用 rsync 复制（保留 .git）
        log_info "从本地源码复制到 ${INSTALL_DIR}..."
        # rsync 以 root 执行（需要读取源码目录），复制完后修正归属
        if command -v rsync &>/dev/null; then
            rsync -a --delete \
                --exclude='.env' \
                --exclude='.codebuddy' \
                --exclude='.pytest_cache' \
                --exclude='__pycache__' \
                --exclude='*.pyc' \
                --exclude='.venv' \
                --exclude='.python' \
                --exclude='*.tar.gz' \
                "$source_dir/" "$INSTALL_DIR/"
        else
            log_warn "rsync 不可用，使用 cp 复制..."
            cp -r "$source_dir/src" "$INSTALL_DIR/"
            cp -r "$source_dir/deploy" "$INSTALL_DIR/"
            cp "$source_dir/pyproject.toml" "$INSTALL_DIR/"
            cp "$source_dir/uv.lock" "$INSTALL_DIR/" 2>/dev/null || true
            cp "$source_dir/.env.example" "$INSTALL_DIR/" 2>/dev/null || true
            # 复制 .git 目录以支持后续升级
            [[ -d "$source_dir/.git" ]] && cp -r "$source_dir/.git" "$INSTALL_DIR/"
        fi
        # rsync/cp 以 root 执行，需要修正归属
        chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"
    elif $has_local_source && [[ "$INSTALL_DIR" == "$source_dir" ]]; then
        # 安装目录就是源码目录，确保归属正确
        log_info "安装目录与源码目录相同，跳过复制"
        chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"
    else
        # 无本地源码，git clone
        log_info "从 GitHub 克隆仓库..."
        run_as_user "git clone '${REPO_URL}' '${INSTALL_DIR}'"
    fi

    # 配置 git safe.directory（以 cls-mcp 身份，避免后续 git 操作报错）
    run_as_user "git config --global --add safe.directory '${INSTALL_DIR}'" 2>/dev/null || true

    # 安装 Python 和依赖（以 cls-mcp 身份执行，文件天然属于 cls-mcp）
    log_info "使用 uv 安装 Python ${PYTHON_VERSION} 和项目依赖..."
    log_info "PyPI 镜像源: ${PYPI_INDEX_URL}"

    # 确保 .python 目录存在且归属正确
    run_as_user "mkdir -p '${INSTALL_DIR}/.python'"

    # 安装 Python
    run_as_user "cd '${INSTALL_DIR}' && /usr/local/bin/uv python install '${PYTHON_VERSION}'"

    # 升级兼容：检测已有 .venv 的 Python 是否指向项目外路径
    if [[ -L "${INSTALL_DIR}/.venv/bin/python" ]]; then
        local python_target
        python_target="$(readlink -f "${INSTALL_DIR}/.venv/bin/python" 2>/dev/null || true)"
        if [[ -n "$python_target" ]] && [[ ! "$python_target" == "${INSTALL_DIR}"* ]]; then
            log_warn "检测到旧 venv 的 Python 指向项目外路径: $python_target"
            log_warn "删除旧 venv 并重建..."
            rm -rf "${INSTALL_DIR}/.venv"
        fi
    fi

    # 安装依赖
    if [[ -f "${INSTALL_DIR}/uv.lock" ]]; then
        run_as_user "cd '${INSTALL_DIR}' && /usr/local/bin/uv sync --frozen --python '${PYTHON_VERSION}'"
    else
        run_as_user "cd '${INSTALL_DIR}' && /usr/local/bin/uv sync --python '${PYTHON_VERSION}'"
    fi

    # 验证安装
    if run_as_user "cd '${INSTALL_DIR}' && .venv/bin/cls-mcp-server --help" &>/dev/null; then
        log_info "项目安装成功"
    else
        die "项目安装失败：cls-mcp-server 命令不可用"
    fi

    # 验证 Python 路径
    if [[ -L "${INSTALL_DIR}/.venv/bin/python" ]]; then
        local final_python_target
        final_python_target="$(readlink -f "${INSTALL_DIR}/.venv/bin/python" 2>/dev/null || true)"
        if [[ -n "$final_python_target" ]] && [[ "$final_python_target" == "${INSTALL_DIR}"* ]]; then
            log_info "Python 路径验证通过: $final_python_target"
        else
            log_warn "Python 路径可能存在权限风险: $final_python_target"
            log_warn "服务用户 ${SERVICE_USER} 需要对该路径有读取和执行权限"
        fi
    fi
}

# ======================== 环境配置 ========================

setup_env_file() {
    log_step "配置环境变量..."

    local env_file="${INSTALL_DIR}/.env"

    if [[ -f "$env_file" ]]; then
        log_warn "环境变量文件已存在: ${env_file}"
        log_warn "跳过生成，请确认配置正确（特别是 CLS_SECRET_ID 和 CLS_SECRET_KEY）"
    else
        # 以 root 生成后修正归属
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

    # 安全加固：归属 cls-mcp，仅服务用户可读写
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$env_file"
    chmod 600 "$env_file"
    log_info "环境变量文件权限已设置为 600（仅 ${SERVICE_USER} 可读写）"
}

# ======================== systemd 服务 ========================

install_service() {
    log_step "安装 systemd 服务..."

    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    local template="${INSTALL_DIR}/deploy/systemd/cls-mcp-server.service"

    if [[ -f "$template" ]]; then
        # 使用项目模板，替换变量
        sed \
            -e "s|WorkingDirectory=.*|WorkingDirectory=${INSTALL_DIR}|" \
            -e "s|EnvironmentFile=.*|EnvironmentFile=${INSTALL_DIR}/.env|" \
            -e "s|ExecStart=.*cls-mcp-server.*|ExecStart=${INSTALL_DIR}/.venv/bin/cls-mcp-server \\\\|" \
            -e "s|--host [^ ]*|--host ${CLS_HOST}|" \
            -e "s|--port [0-9]*|--port ${CLS_PORT}|" \
            -e "s|--transport [^ ]*|--transport ${CLS_TRANSPORT}|" \
            -e "s|User=.*|User=${SERVICE_USER}|" \
            -e "s|Group=.*|Group=${SERVICE_GROUP}|" \
            "$template" > "$service_file"
    else
        # 模板不存在时直接生成
        cat > "$service_file" <<EOF
[Unit]
Description=CLS MCP Server - 腾讯云日志服务 MCP Server
Documentation=https://github.com/TencentCloud/cls-mcp-server
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

    systemctl daemon-reload
    log_info "systemd 服务已安装: ${service_file}"

    systemctl enable "$SERVICE_NAME"
    log_info "已设置开机自启"
}

# ======================== 升级模式 ========================

do_upgrade() {
    echo ""
    echo "============================================================"
    echo " CLS MCP Server 升级模式"
    echo "============================================================"
    echo ""

    # 前置检查
    if [[ ! -d "$INSTALL_DIR" ]]; then
        die "安装目录 ${INSTALL_DIR} 不存在，请先执行首次安装: sudo bash install.sh"
    fi

    if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
        die "未找到 ${INSTALL_DIR}/.git 目录，无法升级。\n  请重新执行首次安装: sudo bash install.sh"
    fi

    if ! id "$SERVICE_USER" &>/dev/null; then
        die "服务用户 ${SERVICE_USER} 不存在，请先执行首次安装"
    fi

    if ! find_uv; then
        die "未找到 uv，请确认已安装到 /usr/local/bin/"
    fi

    # 确保安装目录归属正确（修复历史遗留的权限问题，仅顶层目录）
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "$INSTALL_DIR"

    # 修复 .git 目录权限（如果之前被 root 操作过）
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        local git_owner
        git_owner=$(stat -c '%U' "${INSTALL_DIR}/.git" 2>/dev/null || stat -f '%Su' "${INSTALL_DIR}/.git" 2>/dev/null || echo "")
        if [[ "$git_owner" != "$SERVICE_USER" ]]; then
            log_warn "修复 .git 目录权限（当前属于 ${git_owner}）..."
            chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}/.git"
        fi
    fi

    # 配置 git safe.directory（以 cls-mcp 身份）
    run_as_user "git config --global --add safe.directory '${INSTALL_DIR}'" 2>/dev/null || true

    cd "$INSTALL_DIR"

    # 记录升级前版本
    local old_version
    old_version=$(run_as_user "cd '${INSTALL_DIR}' && git describe --tags --always" 2>/dev/null || echo "unknown")
    log_info "当前版本: ${old_version}"

    # Step 1: git pull（以 cls-mcp 身份）
    log_step "拉取最新代码..."
    if run_as_user "cd '${INSTALL_DIR}' && git pull"; then
        log_info "代码更新成功"
    else
        die "git pull 失败，请检查网络或 git 仓库配置"
    fi

    local new_version
    new_version=$(run_as_user "cd '${INSTALL_DIR}' && git describe --tags --always" 2>/dev/null || echo "unknown")
    log_info "更新后版本: ${new_version}"

    # Step 2: uv sync（以 cls-mcp 身份）
    log_step "同步 Python 依赖..."
    log_info "PyPI 镜像源: ${PYPI_INDEX_URL}"

    if [[ -f "${INSTALL_DIR}/uv.lock" ]]; then
        if run_as_user "cd '${INSTALL_DIR}' && /usr/local/bin/uv sync --frozen --python '${PYTHON_VERSION}'"; then
            log_info "依赖同步成功"
        else
            die "uv sync 失败，请检查依赖配置"
        fi
    else
        if run_as_user "cd '${INSTALL_DIR}' && /usr/local/bin/uv sync --python '${PYTHON_VERSION}'"; then
            log_info "依赖同步成功"
        else
            die "uv sync 失败，请检查依赖配置"
        fi
    fi

    # Step 3: 重新安装 systemd 服务（更新可能的配置变化）
    log_step "更新 systemd 服务配置..."
    install_service

    # Step 4: 重启服务（root 操作）
    log_step "重启服务..."
    if systemctl restart "$SERVICE_NAME"; then
        sleep 2
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log_info "服务重启成功"
        else
            log_error "服务重启后未正常运行，查看日志:"
            journalctl -u "$SERVICE_NAME" --no-pager -n 20
            exit 1
        fi
    else
        die "服务重启失败"
    fi

    # 健康检查
    sleep 1
    if curl -sf "http://127.0.0.1:${CLS_PORT}/health" >/dev/null 2>&1; then
        log_info "健康检查通过"
    else
        log_warn "健康检查端点暂未响应（服务可能正在启动中）"
    fi

    echo ""
    echo "============================================================"
    echo " CLS MCP Server 升级完成"
    echo "============================================================"
    echo ""
    echo "  版本变更:  ${old_version} → ${new_version}"
    echo "  安装目录:  ${INSTALL_DIR}"
    echo "  .env 文件: 未修改（保持原有配置）"
    echo "  PyPI 源:   ${PYPI_INDEX_URL}"
    echo ""
    echo "  查看状态:  sudo systemctl status ${SERVICE_NAME}"
    echo "  查看日志:  sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "============================================================"
}

# ======================== 启动与验证 ========================

start_and_verify() {
    log_step "启动服务..."

    local env_file="${INSTALL_DIR}/.env"
    if grep -q '<请替换为你的SecretId>' "$env_file" 2>/dev/null; then
        log_warn "检测到密钥尚未配置！"
        log_warn "请先编辑 ${env_file}，填入真实的 CLS_SECRET_ID 和 CLS_SECRET_KEY"
        log_warn "配置完成后执行: sudo systemctl start ${SERVICE_NAME}"
        echo ""
        print_summary "pending"
        return 0
    fi

    systemctl start "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "服务启动成功"

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
    echo "  PyPI 镜像:    ${PYPI_INDEX_URL}"
    echo ""
    echo "常用命令:"
    echo "  查看状态:     sudo systemctl status ${SERVICE_NAME}"
    echo "  查看日志:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  重启服务:     sudo systemctl restart ${SERVICE_NAME}"
    echo "  停止服务:     sudo systemctl stop ${SERVICE_NAME}"
    echo "  编辑配置:     sudo vim ${INSTALL_DIR}/.env"
    echo "  健康检查:     curl http://127.0.0.1:${CLS_PORT}/health"
    echo "  升级服务:     sudo bash ${INSTALL_DIR}/deploy/systemd/install.sh --upgrade"
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
    check_root

    # 升级模式
    if $UPGRADE_MODE; then
        do_upgrade
        return 0
    fi

    # 安装模式
    echo ""
    echo "============================================================"
    echo " CLS MCP Server 一键部署脚本"
    echo "============================================================"
    echo ""

    check_os
    check_dependencies
    check_network
    create_user
    ensure_install_dir
    install_uv
    setup_project
    setup_env_file
    install_service
    start_and_verify
}

main "$@"
