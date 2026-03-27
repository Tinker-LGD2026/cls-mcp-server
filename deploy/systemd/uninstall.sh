#!/bin/bash
# ============================================================
# CLS MCP Server - 卸载脚本
# ============================================================
# 用法:
#   sudo bash uninstall.sh
#   sudo bash uninstall.sh --install-dir /opt/cls-mcp-server
#   sudo bash uninstall.sh --keep-config   # 保留配置文件
# ============================================================
set -euo pipefail

INSTALL_DIR="/opt/cls-mcp-server"
SERVICE_NAME="cls-mcp-server"
SERVICE_USER="cls-mcp"
KEEP_CONFIG=false

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}==>${NC} $*"; }

# 参数解析
while [[ $# -gt 0 ]]; do
    case $1 in
        --install-dir)  INSTALL_DIR="$2"; shift 2 ;;
        --keep-config)  KEEP_CONFIG=true; shift ;;
        --help|-h)
            echo "用法: sudo bash uninstall.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --install-dir DIR   安装目录 (默认: /opt/cls-mcp-server)"
            echo "  --keep-config       保留环境变量配置文件（含密钥）"
            echo "  -h, --help          显示帮助"
            exit 0
            ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# 检查 root
if [[ $EUID -ne 0 ]]; then
    log_error "请使用 root 权限运行: sudo bash uninstall.sh"
    exit 1
fi

echo ""
echo "============================================================"
echo " CLS MCP Server 卸载"
echo "============================================================"
echo ""
echo "  安装目录: ${INSTALL_DIR}"
echo "  服务名称: ${SERVICE_NAME}"
echo "  保留配置: ${KEEP_CONFIG}"
echo ""

# 确认
read -rp "确认卸载? (y/N): " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "已取消"
    exit 0
fi

# 1. 停止并禁用服务
log_step "停止 systemd 服务..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    log_info "服务已停止"
else
    log_info "服务未在运行"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME"
    log_info "已取消开机自启"
fi

# 2. 删除 service 文件
log_step "删除 systemd 服务文件..."
local_service="/etc/systemd/system/${SERVICE_NAME}.service"
if [[ -f "$local_service" ]]; then
    rm -f "$local_service"
    systemctl daemon-reload
    log_info "已删除: ${local_service}"
else
    log_info "服务文件不存在，跳过"
fi

# 3. 备份并清理配置
if [[ "$KEEP_CONFIG" == true ]]; then
    log_step "保留配置文件..."
    local env_file="${INSTALL_DIR}/.env"
    if [[ -f "$env_file" ]]; then
        local backup="/tmp/cls-mcp-server-env-backup-$(date +%Y%m%d%H%M%S).env"
        cp "$env_file" "$backup"
        chmod 600 "$backup"
        log_info "配置已备份到: ${backup}"
    fi
fi

# 4. 删除安装目录
log_step "清理安装目录..."
if [[ -d "$INSTALL_DIR" ]]; then
    rm -rf "$INSTALL_DIR"
    log_info "已删除: ${INSTALL_DIR}"
else
    log_info "安装目录不存在，跳过"
fi

# 5. 删除服务用户
log_step "清理服务用户..."
if id "$SERVICE_USER" &>/dev/null; then
    userdel "$SERVICE_USER" 2>/dev/null || true
    log_info "已删除用户: ${SERVICE_USER}"
else
    log_info "用户不存在，跳过"
fi

echo ""
echo "============================================================"
echo " CLS MCP Server 卸载完成"
echo "============================================================"
echo ""
if [[ "$KEEP_CONFIG" == true ]]; then
    echo "  配置备份位于 /tmp/cls-mcp-server-env-backup-*.env"
    echo "  请注意: 备份文件包含密钥，请妥善保管或及时删除"
    echo ""
fi
