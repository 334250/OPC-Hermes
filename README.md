# OPC-Hermes

OPC-Hermes (Orchestrated Professional Colleagues) is a multi-agent
management layer built on top of Hermes Agent. It keeps Hermes Agent source
code untouched and adds orchestration through plugins, tools, configuration,
gated memory, quality evaluation, and optimization proposals.

## Repository Layout

- `opc_hermes/` — OPC-Hermes Python package.
- `docs/` — architecture, integration, development-agent, and project-plan docs.
- `hermes-agent/` — upstream Hermes Agent checkout used as integration reference.

## Quick Start

```bash
# 克隆仓库
git clone https://github.com/334250/OPC-Hermes.git
cd OPC-Hermes

# 首次运行：初始化数据 + 启动 WebUI
./scripts/start-opc.sh --seed

# 日常启动（跳过初始化）
./scripts/start-opc.sh

# 完整启动：初始化 + 后端 + 前端开发服务器
./scripts/start-opc.sh --full
```

启动后访问：

| 服务 | 地址 |
|------|------|
| **WebUI Dashboard** | http://127.0.0.1:8765 |
| **API 文档 (Swagger)** | http://127.0.0.1:8765/docs |
| **健康检查** | http://127.0.0.1:8765/api/health |
| **前端开发模式** | http://localhost:5173 (需 `--full`) |

### 命令行工具

```bash
python3 scripts/opc_cli.py start              # 启动 WebUI
python3 scripts/opc_cli.py start --port 9000  # 指定端口
python3 scripts/opc_cli.py seed               # 初始化默认数据
python3 scripts/opc_cli.py status             # 查看系统状态
```

### 安装为 Hermes Agent 插件

```bash
# 复制到 Hermes 插件目录
cp -r opc_hermes/ ~/.hermes/plugins/opc-hermes/

# 重启 Hermes 后自动发现
hermes

# 发起 OPC 任务
/opc 帮我做一份 Q2 销售分析 PPT
```

## Development Setup

Install in editable mode from the repository root:

```bash
python3 -m pip install -e .[dev]
```

Run the baseline checks:

```bash
python3 -m compileall -q opc_hermes
python3 -m pytest
```

The test suite is designed to run without a live Hermes Agent process, model
provider, network access, or writes to the user's real `~/.hermes` directory.

## Current Implementation Status

| Phase | Name | Status |
|-------|------|--------|
| 0 | Engineering Baseline | ✅ Complete |
| 1 | Plugin & Leader Routing | ✅ Complete |
| 2 | Worker Dispatch & DAG | ✅ Complete |
| 3 | Evaluator Quality Loop | ✅ Complete |
| 3b | Agent/Model/Pipeline Management Backend | ✅ Complete |
| 4 | Optimizer + KB + Revision | ✅ Complete |
| 5 | WebUI (taste-skill + React) | ✅ Complete |
| 6 | Production Hardening | ✅ Complete |

**Core capabilities delivered:**
- Leader Agent receives user requests, evaluates complexity, generates plans
- Worker Dispatcher executes DAG plans with parallel/sequential/pipeline modes
- Evaluator scores Worker output on 5 dimensions, writes to Eval Memory
- Optimizer scans evaluations, generates proposals, requires human approval
- Knowledge Pipeline ingests files (md/txt/csv/json) into Knowledge Base
- Revision Handler classifies feedback and routes to affected Workers only
- WebUI: React dashboard with 14 pages (Dashboard, Agent Manager, Model Manager, Pipeline Templates, Workflow Panel, etc.)
- Agent Manager: CRUD + 5 preset groups (Doc Team, Dev Team, Security Team, etc.)
- Model Manager: 6 default models + 5 groups + 6 providers + connection validation
- Pipeline Templates: 5 presets with one-click execution + custom template builder
- Workflow Panel: 4-tab detail view (DAG / Agent Status / Memory Strategy / Artifacts & Evals)
- CLI: `./scripts/start-opc.sh` + `python3 scripts/opc_cli.py start|seed|status`
- Security: path validation, secret scanning, prompt injection guards, WebUI CORS control

## Runtime State

At runtime, OPC-Hermes stores its own state under `~/.hermes/opc/`:

- `config.yaml`
- `agent_list/`
- `memory/`
- `artifacts/`
- `proposals/`
- `logs/`

## Security Notes

- Keep runtime state outside the repository. Do not commit `config.yaml`,
  SQLite databases, artifacts, logs, proposals, or local override files.
- Keep `~/.hermes/opc/` private to the local user. Config files may later
  include model preferences, paths, and provider-related settings.
- Do not put API keys or tokens in ordinary OPC config fields. Use the
  provider secret mechanisms supplied by Hermes Agent.
- Treat user-provided task content, imported knowledge, and SummaryBridge
  entries as untrusted unless a Worker explicitly verifies the source.
