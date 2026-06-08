#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# OPC-Hermes 虚拟环境创建脚本
# ─────────────────────────────────────────────────────────────────────
# 用法:
#   ./scripts/setup-venv.sh              # 创建 .venv + 安装依赖
#   ./scripts/setup-venv.sh --dev        # 含 dev 依赖 (pytest)
#   ./scripts/setup-venv.sh --webui      # 含 WebUI 依赖 (fastapi)
#   ./scripts/setup-venv.sh --full       # 全部依赖
#   ./scripts/setup-venv.sh --recreate   # 删除重建
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── 参数解析 ────────────────────────────────────────────────────────
WITH_DEV=false
WITH_WEBUI=false
RECREATE=false

for arg in "$@"; do
    case "$arg" in
        --dev)    WITH_DEV=true ;;
        --webui)  WITH_WEBUI=true ;;
        --full)   WITH_DEV=true; WITH_WEBUI=true ;;
        --recreate) RECREATE=true ;;
        --help|-h)
            echo "OPC-Hermes 虚拟环境创建脚本"
            echo ""
            echo "用法: $0 [选项]"
            echo "  --dev        安装开发依赖 (pytest)"
            echo "  --webui      安装 WebUI 依赖 (fastapi, uvicorn)"
            echo "  --full       安装全部依赖"
            echo "  --recreate   删除现有 venv 后重建"
            exit 0
            ;;
    esac
done

# ── 检查 Python ─────────────────────────────────────────────────────
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON_BIN="$candidate"
        break
    fi
done
[ -z "$PYTHON_BIN" ] && err "未找到 Python 3.11+。请安装 Python 3.11 或更高版本。"

PY_VER=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
MAJOR=$(echo "$PY_VER" | cut -d. -f1)
MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || { [ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]; }; then
    err "需要 Python 3.11+，当前为 $PY_VER"
fi
log "Python $PY_VER ($PYTHON_BIN)"

# ── 重建 ────────────────────────────────────────────────────────────
if $RECREATE && [ -d "$VENV_DIR" ]; then
    warn "删除现有虚拟环境: $VENV_DIR"
    rm -rf "$VENV_DIR"
fi

# ── 创建 venv ───────────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    log "虚拟环境已存在: $VENV_DIR"
else
    echo ""
    log "创建虚拟环境..."
    "$PYTHON_BIN" -m venv "$VENV_DIR" --clear
    log "虚拟环境创建完成: $VENV_DIR"
fi

# ── 激活 + 升级 pip ─────────────────────────────────────────────────
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip -q
log "pip 已升级"

# ── 安装核心依赖 ────────────────────────────────────────────────────
echo ""
log "安装核心依赖..."

pip install -e "$PROJECT_ROOT" -q

if $WITH_WEBUI; then
    log "安装 WebUI 依赖 (fastapi, uvicorn)..."
    pip install fastapi uvicorn aiohttp -q
fi

if $WITH_DEV; then
    log "安装开发依赖 (pytest)..."
    pip install pytest -q
fi

# ── 初始化默认数据 ──────────────────────────────────────────────────
echo ""
log "初始化 OPC-Hermes 默认数据..."
python "$PROJECT_ROOT/scripts/opc_cli.py" seed 2>&1 | grep -E "^   \+" || true

# ── 完成 ────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         OPC-Hermes 环境就绪！             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "  激活环境:"
echo -e "    ${GREEN}source .venv/bin/activate${NC}"
echo ""
echo "  启动 WebUI:"
echo -e "    ${GREEN}./scripts/start-opc.sh${NC}"
echo ""
echo "  查看状态:"
echo -e "    ${GREEN}python scripts/opc_cli.py status${NC}"
echo ""
echo "  运行测试:"
echo -e "    ${GREEN}python -m pytest opc_hermes/tests/ -v${NC}"
echo ""
