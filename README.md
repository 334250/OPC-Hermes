# OPC-Hermes

OPC-Hermes (Orchestrated Professional Colleagues) is a multi-agent
management layer built on top of Hermes Agent. It keeps Hermes Agent source
code untouched and adds orchestration through plugins, tools, configuration,
gated memory, quality evaluation, and optimization proposals.

## Repository Layout

- `opc_hermes/` — OPC-Hermes Python package.
- `docs/` — architecture, integration, development-agent, and project-plan docs.
- `hermes-agent/` — upstream Hermes Agent checkout used as integration reference.

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
- WebUI: React dashboard with 9 pages (Dashboard, Agents, Tasks, Memory, Artifacts, Proposals, Config)
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
