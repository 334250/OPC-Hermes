"""
OPC-Hermes Toolset Definitions

Defines OPC-specific toolsets that are registered into Hermes Agent's
toolset system via the plugin framework.  Users can enable/disable these
toolsets through ``hermes tools`` like any built-in toolset.

Toolset naming convention:
  - opc-core      — tools every OPC agent needs
  - opc-leader    — tools specific to the Leader Agent
  - opc-worker    — tools available to Worker agents
  - opc-evaluator — tools specific to the Evaluator Agent
  - opc-memory    — memory-layer tools (opc_ prefix)
"""

from __future__ import annotations

from typing import Dict, List

# ══════════════════════════════════════════════════════════════════════════
# Toolset Definitions
# ══════════════════════════════════════════════════════════════════════════

OPC_TOOLSETS: Dict[str, Dict] = {
    # ── Core OPC tools (every OPC agent gets these) ──────────────────────
    "opc-core": {
        "description": (
            "OPC-Hermes core tools — complexity rating and agent discovery. "
            "Every OPC agent (Leader, Worker, Evaluator) receives these."
        ),
        "tools": [
            "complexity_rater",
        ],
        "includes": [],
    },

    # ── Leader-specific tools ────────────────────────────────────────────
    "opc-leader": {
        "description": (
            "OPC Leader Agent tools — plan generation, worker discovery, "
            "and DAG-based dispatch.  Only the Leader Agent receives these."
        ),
        "tools": [
            "opc_dispatch_workers",
            "opc_register_pending_plan",
        ],
        "includes": ["opc-memory"],
    },

    # ── Worker tools ─────────────────────────────────────────────────────
    "opc-worker": {
        "description": (
            "OPC Worker Agent tools — memory read/write for task context "
            "and progress reporting. All Workers receive these."
        ),
        "tools": [
            "opc_save_context",
            "opc_get_upstream_summaries",
            "opc_write_to_bridge",
            "opc_save_progress_report",
            "opc_get_worker_context",
        ],
        "includes": ["opc-memory"],
    },

    # ── Memory-layer tools ───────────────────────────────────────────────
    "opc-memory": {
        "description": (
            "OPC gated-memory tools — context save/load, summary bridge, "
            "progress reporting.  All OPC agents can read from SummaryBridge; "
            "only Workers can write project context; only Evaluator can write "
            "to Eval Memory."
        ),
        "tools": [
            "opc_save_context",
            "opc_get_upstream_summaries",
            "opc_write_to_bridge",
            "opc_save_progress_report",
            "opc_get_worker_context",
        ],
        "includes": [],
    },

    # ── Evaluator tools ──────────────────────────────────────────────────
    "opc-evaluator": {
        "description": (
            "OPC Evaluator Agent tools — snapshot capture, output scoring, "
            "and structured evaluation writing. Only the Evaluator Agent "
            "receives these.  Writes exclusively to Eval Memory."
        ),
        "tools": [
            "opc_eval_capture_snapshot",
            "opc_eval_score_output",
            "opc_eval_write_evaluation",
        ],
        "includes": [],
    },
}

# ══════════════════════════════════════════════════════════════════════════
# Tool-to-toolset mapping (for backward compat with TOOL_TO_TOOLSET_MAP)
# ══════════════════════════════════════════════════════════════════════════

def get_opc_toolset_map() -> Dict[str, str]:
    """Return {tool_name: toolset_name} for all OPC tools."""
    mapping: Dict[str, str] = {}
    for ts_name, ts_def in OPC_TOOLSETS.items():
        for tool_name in ts_def.get("tools", []):
            mapping[tool_name] = ts_name
    return mapping


def register_opc_toolsets(registry) -> None:
    """Register OPC toolsets into a Hermes tool registry.

    ``registry`` is the Hermes Agent tool registry (tools.registry.registry).
    Called by plugin.py at discovery time.

    Each toolset is registered as a known toolset so ``hermes tools``
    can list and toggle them.
    """
    for ts_name, ts_def in OPC_TOOLSETS.items():
        if hasattr(registry, 'register_toolset'):
            try:
                registry.register_toolset(
                    ts_name,
                    ts_def.get("description", ""),
                    ts_def.get("tools", []),
                )
            except TypeError:
                registry.register_toolset(ts_name, ts_def.get("description", ""))
