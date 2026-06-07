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

- Phase 0 baseline is implemented: package metadata, config loading, default
  registry resources, import stability, and local-state path handling.
- Phase 1 routing and planning guards are implemented: `/opc` gateway routing,
  Leader prompt injection, strict plan JSON validation, model allowlisting, and
  pending-plan approval binding.
- Worker dispatch is still a Phase 1 stub. Approved plans are validated and
  routed through `OPCWorkerDispatcher`, but real Hermes Worker delegation and
  durable approval storage belong to the next implementation phase.

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
