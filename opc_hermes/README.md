# OPC-Hermes

OPC-Hermes is a multi-agent management layer built on top of Hermes Agent.
It adds Leader/Worker orchestration, gated memory, task complexity routing,
quality evaluation, and optimization proposals without modifying Hermes Agent
source code.

## Development

Install the package in editable mode from this directory:

```bash
python3 -m pip install -e .[dev]
```

Run the current test suite:

```bash
python3 -m pytest opc_hermes/tests
```

Run a syntax/import baseline check:

```bash
python3 -m compileall -q opc_hermes
```

## Runtime Data

OPC-Hermes stores runtime data under `~/.hermes/opc/` by default:

- `config.yaml`
- `agent_list/`
- `memory/`
- `artifacts/`
- `proposals/`
- `logs/`
