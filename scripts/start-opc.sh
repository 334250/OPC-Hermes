#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# OPC-Hermes 启动脚本
# ─────────────────────────────────────────────────────────────────────
# 用法:
#   ./scripts/start-opc.sh              # 仅启动 WebUI 后端
#   ./scripts/start-opc.sh --seed       # 初始化默认数据 + 启动后端
#   ./scripts/start-opc.sh --full       # 初始化 + 后端 + 前端
#   ./scripts/start-opc.sh --help       # 查看帮助
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OPC_PORT="${OPC_WEBUI_PORT:-8765}"
OPC_HOST="${OPC_WEBUI_HOST:-127.0.0.1}"
VENV_PYTHON=""

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

# ── 帮助 ────────────────────────────────────────────────────────────
usage() {
    banner
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --seed          首次运行：初始化默认数据（管道模板、模型库）"
    echo "  --full          完整启动：初始化 + 后端 + 前端开发服务器"
    echo "  --frontend-only 仅启动前端开发服务器"
    echo "  --port <port>   指定后端端口（默认: 8765）"
    echo "  --help          显示此帮助"
    echo ""
    echo "环境变量:"
    echo "  OPC_WEBUI_PORT  后端端口（默认: 8765）"
    echo "  OPC_WEBUI_HOST  绑定地址（默认: 127.0.0.1）"
    echo "  OPC_WEBUI_CORS_ORIGINS  CORS 允许的源（默认: localhost:5173）"
    exit 0
}

# ── 查找 Python ─────────────────────────────────────────────────────
find_python() {
    # 优先使用 hermes-agent 的 venv
    if [ -f "$PROJECT_ROOT/hermes-agent/.venv/bin/python" ]; then
        VENV_PYTHON="$PROJECT_ROOT/hermes-agent/.venv/bin/python"
        log "使用 Hermes Agent venv: $VENV_PYTHON"
    elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
        VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
        log "使用项目 venv: $VENV_PYTHON"
    elif command -v python3 &>/dev/null; then
        VENV_PYTHON="python3"
    else
        err "未找到 Python 3。请安装 Python 3.11+ 或激活虚拟环境。"
        exit 1
    fi

    PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    info "Python $PYTHON_VERSION"
}

# ── 检查依赖 ────────────────────────────────────────────────────────
check_deps() {
    info "检查 Python 依赖..."
    if "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
        log "FastAPI 已安装"
    else
        warn "FastAPI 未安装，正在安装..."
        "$VENV_PYTHON" -m pip install fastapi uvicorn aiohttp pyyaml -q
        log "FastAPI 安装完成"
    fi
}

ensure_frontend_build() {
    FRONTEND_DIR="$PROJECT_ROOT/opc_hermes/webui/frontend"
    FRONTEND_DIST="$FRONTEND_DIR/dist/index.html"

    if [ -f "$FRONTEND_DIST" ]; then
        log "前端构建产物已存在"
        return
    fi

    if [ ! -f "$FRONTEND_DIR/package.json" ]; then
        warn "前端目录未找到，后端将只提供 API: $FRONTEND_DIR"
        return
    fi

    if ! command -v npm &>/dev/null; then
        warn "npm 未安装，无法构建前端；请安装 Node.js 或使用 --full 启动前端开发服务器。"
        return
    fi

    info "首次启动需要构建 WebUI 前端..."
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        info "安装前端依赖..."
        (cd "$FRONTEND_DIR" && npm install --no-package-lock --silent)
    fi
    (cd "$FRONTEND_DIR" && npm run build)
    log "前端构建完成"
}

# ── 初始化数据 ──────────────────────────────────────────────────────
seed_data() {
    info "初始化 OPC-Hermes 默认数据..."
    "$VENV_PYTHON" -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')

# 初始化管道模板
from opc_hermes.pipeline_manager import PipelineManager, PRESET_TEMPLATES
pm = PipelineManager()
existing = {t.id for t in pm.load_all()}
for t in PRESET_TEMPLATES:
    if t.id not in existing:
        pm.save(t)
        print(f'  + 管道模板: {t.name} ({t.id})')

# 初始化模型库（已在 ModelManager.__init__ 自动完成）
from opc_hermes.model_manager import ModelManager
mm = ModelManager()
print(f'  + 模型库: {len(mm.list_models())} 模型, {len(mm.list_groups())} 分组, {len(mm.list_providers())} 供应商')
print('默认数据初始化完成。')
"
    log "默认数据初始化完成"
}

# ── 启动后端 ────────────────────────────────────────────────────────
start_backend() {
    info "启动 OPC WebUI 后端 (http://$OPC_HOST:$OPC_PORT)..."
    echo ""
    OPC_WEBUI_HOST="$OPC_HOST" OPC_WEBUI_PORT="$OPC_PORT" "$VENV_PYTHON" -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT')
from opc_hermes.webui.server import main
main(host='$OPC_HOST', port=$OPC_PORT)
" &
    BACKEND_PID=$!
    sleep 2

    # 健康检查
    if kill -0 $BACKEND_PID 2>/dev/null; then
        log "后端已启动 (PID: $BACKEND_PID)"
        echo ""
        echo -e "  ${GREEN}▸${NC}  WebUI:  ${CYAN}http://$OPC_HOST:$OPC_PORT${NC}"
        echo -e "  ${GREEN}▸${NC}  API:    ${CYAN}http://$OPC_HOST:$OPC_PORT/api/health${NC}"
        echo -e "  ${GREEN}▸${NC}  API文档: ${CYAN}http://$OPC_HOST:$OPC_PORT/docs${NC}"
    else
        err "后端启动失败，请检查日志。"
        exit 1
    fi
}

# ── 启动前端 ────────────────────────────────────────────────────────
start_frontend() {
    FRONTEND_DIR="$PROJECT_ROOT/opc_hermes/webui/frontend"
    if [ ! -f "$FRONTEND_DIR/package.json" ]; then
        warn "前端目录未找到: $FRONTEND_DIR"
        return
    fi

    if ! command -v npm &>/dev/null; then
        warn "npm 未安装，跳过前端启动。安装 Node.js 后可使用 --frontend-only 启动。"
        return
    fi

    info "安装前端依赖..."
    (cd "$FRONTEND_DIR" && npm install --no-package-lock --silent 2>&1 | tail -1)
    log "依赖安装完成"

    info "启动前端开发服务器 (http://localhost:5173)..."
    (cd "$FRONTEND_DIR" && npm run dev) &
    FRONTEND_PID=$!
    sleep 3

    if kill -0 $FRONTEND_PID 2>/dev/null; then
        log "前端已启动 (PID: $FRONTEND_PID)"
        echo -e "  ${GREEN}▸${NC}  Dashboard: ${CYAN}http://localhost:5173${NC}"
    else
        warn "前端可能未成功启动，请手动启动: cd opc_hermes/webui/frontend && npm run dev"
    fi
}

# ── 主流程 ──────────────────────────────────────────────────────────
main() {
    local seed=false
    local full=false
    local frontend_only=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --seed) seed=true; shift ;;
            --full) full=true; shift ;;
            --frontend-only) frontend_only=true; shift ;;
            --port) OPC_PORT="$2"; shift 2 ;;
            --help|-h) usage ;;
            *) err "未知选项: $1"; usage ;;
        esac
    done

    banner
    find_python

    if $frontend_only; then
        start_frontend
        echo ""
        info "按 Ctrl+C 停止。"
        wait
        exit 0
    fi

    check_deps

    if $seed || $full; then
        seed_data
    fi

    if ! $full; then
        ensure_frontend_build
    fi

    if $full || ! $frontend_only; then
        start_backend
    fi

    if $full; then
        start_frontend
    fi

    echo ""
    info "按 Ctrl+C 停止所有服务。"
    echo ""

    # 等待信号
    trap "log '正在停止...'; kill $BACKEND_PID ${FRONTEND_PID:-} 2>/dev/null; exit 0" INT TERM
    wait
}

main "$@"
