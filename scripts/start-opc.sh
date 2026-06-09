#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# OPC-Hermes 启动脚本
# ─────────────────────────────────────────────────────────────────────
# 用法:
#   ./scripts/start-opc.sh              # 启动 OPC WebUI + 内嵌 Hermes 原生 API
#   ./scripts/start-opc.sh --seed       # 初始化数据 + 启动 WebUI
#   ./scripts/start-opc.sh --full       # 初始化 + WebUI + Gateway + 前端开发服务器
#   ./scripts/start-opc.sh --gateway    # 额外启动 Hermes Gateway（消息平台/Cron）
#   ./scripts/start-opc.sh --no-hermes  # 兼容旧参数：不启动 Gateway
#   ./scripts/start-opc.sh --help       # 查看帮助
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OPC_PORT="${OPC_WEBUI_PORT:-8765}"
OPC_HOST="${OPC_WEBUI_HOST:-127.0.0.1}"
VENV_PYTHON=""
BACKEND_PID=""
HERMES_PID=""
FRONTEND_PID=""
CLEANED_UP=false

# ── 颜色 ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║           O P C - H e r m e s            ║"
    echo "  ║     Multi-Agent Management Platform      ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${BLUE}[i]${NC} $*"; }

# ── 清理 ────────────────────────────────────────────────────────────
cleanup() {
    $CLEANED_UP && return
    CLEANED_UP=true
    trap - INT TERM EXIT
    echo ""
    log "正在停止所有服务..."
    for pid in $BACKEND_PID $HERMES_PID $FRONTEND_PID; do
        if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    log "已停止。"
}
trap cleanup INT TERM EXIT

# ── 帮助 ────────────────────────────────────────────────────────────
usage() {
    banner
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --seed          首次运行：初始化默认数据 + 启动 WebUI"
    echo "  --full          完整启动：初始化 + OPC + Hermes Gateway + 前端"
    echo "  --gateway       启动 Hermes Gateway（消息平台/Cron；默认不启动）"
    echo "  --no-hermes     兼容旧参数：不启动 Hermes Gateway"
    echo "  --frontend-only 仅启动前端开发服务器"
    echo "  --port <port>   指定 OPC 后端端口（默认: 8765）"
    echo "  --help          显示此帮助"
    echo ""
    echo "环境变量:"
    echo "  OPC_WEBUI_PORT  OPC 后端端口（默认: 8765）"
    echo "  OPC_WEBUI_HOST  OPC 绑定地址（默认: 127.0.0.1）"
    exit 0
}

# ── 查找 Python ─────────────────────────────────────────────────────
find_python() {
    if [ -f "$PROJECT_ROOT/hermes-agent/.venv/bin/python" ]; then
        VENV_PYTHON="$PROJECT_ROOT/hermes-agent/.venv/bin/python"
        log "使用 Hermes Agent venv"
    elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
        VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
        log "使用项目 venv"
    elif command -v python3 &>/dev/null; then
        VENV_PYTHON="python3"
    else
        err "未找到 Python 3。请安装 Python 3.11+ 或运行 ./scripts/setup-venv.sh"
        exit 1
    fi

    PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    info "Python $PYTHON_VERSION"
}

# ── 检查依赖 ────────────────────────────────────────────────────────
check_deps() {
    if "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
        return
    fi
    warn "FastAPI 未安装，正在安装..."
    "$VENV_PYTHON" -m pip install fastapi uvicorn aiohttp pyyaml -q
}

ensure_frontend_build() {
    local dist="$PROJECT_ROOT/opc_hermes/webui/frontend/dist/index.html"
    [ -f "$dist" ] && return
    local pkg="$PROJECT_ROOT/opc_hermes/webui/frontend/package.json"
    if [ ! -f "$pkg" ]; then warn "前端目录未找到"; return; fi
    if ! command -v npm &>/dev/null; then warn "npm 未安装，跳过前端构建"; return; fi
    info "构建 WebUI 前端..."
    if [ ! -d "$PROJECT_ROOT/opc_hermes/webui/frontend/node_modules" ]; then
        npm --prefix "$PROJECT_ROOT/opc_hermes/webui/frontend" install --silent
    fi
    npm --prefix "$PROJECT_ROOT/opc_hermes/webui/frontend" run build
    log "前端构建完成"
}

# ── 初始化数据 ──────────────────────────────────────────────────────
seed_data() {
    info "初始化 OPC-Hermes 默认数据..."
    "$VENV_PYTHON" "$PROJECT_ROOT/scripts/opc_cli.py" seed 2>&1 | grep -E "^\s*\+" || true
    log "默认数据初始化完成"
}

api_server_disabled() {
    case "${API_SERVER_ENABLED:-}" in
        false|FALSE|0|no|NO|off|OFF) return 0 ;;
        *) return 1 ;;
    esac
}

configure_gateway_api_env() {
    api_server_disabled && return

    export API_SERVER_ENABLED="${API_SERVER_ENABLED:-true}"
    export API_SERVER_HOST="${API_SERVER_HOST:-127.0.0.1}"
    export API_SERVER_PORT="${API_SERVER_PORT:-8642}"

    if [ -z "${API_SERVER_KEY:-}" ]; then
        if [ -n "${OPC_HERMES_API_KEY:-}" ]; then
            API_SERVER_KEY="$OPC_HERMES_API_KEY"
        else
            API_SERVER_KEY="$("$VENV_PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
        fi
        export API_SERVER_KEY
    fi

    export OPC_HERMES_API_KEY="${OPC_HERMES_API_KEY:-$API_SERVER_KEY}"
    export OPC_HERMES_API_SERVER_URL="${OPC_HERMES_API_SERVER_URL:-http://127.0.0.1:${API_SERVER_PORT}/v1/chat/completions}"
}

# ── 启动 Hermes Agent ───────────────────────────────────────────────
start_hermes() {
    local hermes_bin=""
    for candidate in \
        "$PROJECT_ROOT/.venv/bin/hermes" \
        "$PROJECT_ROOT/hermes-agent/.venv/bin/hermes" \
        ; do
        if [ -x "$candidate" ]; then hermes_bin="$candidate"; break; fi
    done

    if [ -z "$hermes_bin" ]; then
        warn "未找到 hermes 可执行文件，跳过 Hermes Agent 启动。"
        warn "请先安装 Hermes Agent: cd hermes-agent && pip install -e ."
        return
    fi

    configure_gateway_api_env

    info "启动 Hermes Agent Gateway（消息平台/Cron/API）..."
    "$hermes_bin" gateway &
    HERMES_PID=$!
    sleep 3

    if kill -0 "$HERMES_PID" 2>/dev/null; then
        log "Hermes Gateway 已启动 (PID: $HERMES_PID)"
        echo -e "  ${GREEN}▸${NC}  Hermes Gateway: ${CYAN}运行中${NC}"
        if ! api_server_disabled; then
            echo -e "  ${GREEN}▸${NC}  Hermes API:     ${CYAN}http://127.0.0.1:${API_SERVER_PORT}${NC}"
        fi
    else
        warn "Hermes Gateway 启动失败；OPC WebUI 将继续启动，Hermes 原生 API 会以内嵌模式提供。"
        HERMES_PID=""
    fi
}

# ── 启动 OPC 后端 ───────────────────────────────────────────────────
start_backend() {
    info "启动 OPC WebUI 后端 (http://$OPC_HOST:$OPC_PORT)..."
    OPC_WEBUI_HOST="$OPC_HOST" OPC_WEBUI_PORT="$OPC_PORT" "$VENV_PYTHON" -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from opc_hermes.webui.server import main
main(host='$OPC_HOST', port=$OPC_PORT)
" &
    BACKEND_PID=$!
    sleep 2

    if kill -0 "$BACKEND_PID" 2>/dev/null; then
        log "OPC WebUI 已启动 (PID: $BACKEND_PID)"
        echo ""
        echo -e "  ${GREEN}▸${NC}  WebUI:     ${CYAN}http://$OPC_HOST:$OPC_PORT${NC}"
        echo -e "  ${GREEN}▸${NC}  API:       ${CYAN}http://$OPC_HOST:$OPC_PORT/api/health${NC}"
        echo -e "  ${GREEN}▸${NC}  API 文档:  ${CYAN}http://$OPC_HOST:$OPC_PORT/docs${NC}"
        echo -e "  ${GREEN}▸${NC}  Hermes API: ${CYAN}内嵌可用${NC}"
        [ -n "$HERMES_PID" ] && echo -e "  ${GREEN}▸${NC}  Gateway:   ${CYAN}已启动（消息平台/Cron）${NC}"
        [ -n "$HERMES_PID" ] && ! api_server_disabled && echo -e "  ${GREEN}▸${NC}  Chat API:  ${CYAN}http://127.0.0.1:${API_SERVER_PORT}/v1${NC}"
        return 0
    else
        err "OPC 后端启动失败。"
        exit 1
    fi
}

# ── 启动前端 ────────────────────────────────────────────────────────
start_frontend() {
    local dir="$PROJECT_ROOT/opc_hermes/webui/frontend"
    [ ! -f "$dir/package.json" ] && { warn "前端目录未找到"; return; }
    command -v npm &>/dev/null || { warn "npm 未安装"; return; }
    info "启动前端开发服务器 (http://localhost:5173)..."
    (cd "$dir" && npm run dev) &
    FRONTEND_PID=$!
    sleep 3
    kill -0 "$FRONTEND_PID" 2>/dev/null \
        && log "前端已启动 (http://localhost:5173)" \
        || warn "前端启动失败，请手动启动: cd $dir && npm run dev"
}

wait_for_services() {
    local primary_pid="${BACKEND_PID:-$FRONTEND_PID}"
    if [ -z "${primary_pid:-}" ]; then
        return
    fi
    wait "$primary_pid"
}

# ── 主流程 ──────────────────────────────────────────────────────────
main() {
    local seed=false full=false frontend_only=false start_gateway=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --seed)          seed=true; shift ;;
            --full)          full=true; start_gateway=true; shift ;;
            --gateway|--with-gateway) start_gateway=true; shift ;;
            --no-hermes)     start_gateway=false; shift ;;
            --frontend-only) frontend_only=true; shift ;;
            --port)          OPC_PORT="$2"; shift 2 ;;
            --help|-h)       usage ;;
            *) err "未知选项: $1"; usage ;;
        esac
    done

    banner
    find_python

    if $frontend_only; then
        start_frontend
        info "按 Ctrl+C 停止。"
        wait_for_services
        exit 0
    fi

    check_deps
    $seed || $full && seed_data
    $full || ensure_frontend_build
    $start_gateway && start_hermes
    start_backend
    $full && start_frontend

    echo ""
    info "所有服务已启动，按 Ctrl+C 停止。"
    echo ""

    wait_for_services
}

main "$@"
