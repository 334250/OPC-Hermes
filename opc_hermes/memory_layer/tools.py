"""
OPC Memory-Layer Tools

These are Hermes Agent tools (``opc_`` prefix) that Worker and Leader
agents call at runtime to interact with the gated memory layer.

Registered into the Hermes tool registry via ``register_all(ctx)``.

All handlers return JSON strings (Hermes tool contract).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opc_hermes.memory_layer.gated_memory import get_memory_layer
from opc_hermes.memory_layer.task_protocol import ProgressReport
from opc_hermes.memory_layer.summary_bridge import SummaryBridgeEntry

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
# Tool Schemas
# ══════════════════════════════════════════════════════════════════════════

_SAVE_CONTEXT_SCHEMA = {
    "name": "opc_save_context",
    "description": (
        "Save the current worker's output context to Project Memory. "
        "Call this AFTER completing a major milestone in your work. "
        "Your output will be summarized into a SummaryBridge entry "
        "that downstream workers can read. "
        "Provide a concise summary (≤ 500 chars) and key findings."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task identifier."},
            "worker_id": {"type": "string", "description": "Your worker ID."},
            "step_index": {"type": "integer", "description": "Your step index in the DAG."},
            "summary": {"type": "string", "description": "Concise summary of your output (≤ 500 chars)."},
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of key findings or decisions.",
            },
            "artifact_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to any output files you created.",
            },
            "target_workers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Worker IDs that should read this summary (empty = all).",
            },
        },
        "required": ["task_id", "worker_id", "summary"],
    },
}

_GET_UPSTREAM_SUMMARIES_SCHEMA = {
    "name": "opc_get_upstream_summaries",
    "description": (
        "Read summaries from upstream workers that completed before you. "
        "Only returns summaries you're authorized to read (gated access). "
        "Call this at the START of your work to understand what's already been done."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task identifier."},
            "worker_id": {"type": "string", "description": "Your worker ID."},
            "upstream_step_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional: only get summaries from these specific steps.",
            },
        },
        "required": ["task_id", "worker_id"],
    },
}

_WRITE_TO_BRIDGE_SCHEMA = {
    "name": "opc_write_to_bridge",
    "description": (
        "Write a structured data entry to the Summary Bridge. "
        "Use this when you have structured output (JSON data, schema definitions) "
        "that downstream workers need in a machine-readable format."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task identifier."},
            "source_worker_id": {"type": "string", "description": "Your worker ID."},
            "source_step_index": {"type": "integer", "description": "Your step index."},
            "summary": {"type": "string", "description": "Human-readable summary."},
            "data_schema": {
                "type": "object",
                "description": "Structured data schema or data object for downstream consumers.",
            },
            "target_workers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Worker IDs that should receive this (empty = all).",
            },
        },
        "required": ["task_id", "source_worker_id", "summary"],
    },
}

_SAVE_PROGRESS_SCHEMA = {
    "name": "opc_save_progress_report",
    "description": (
        "Save a progress report to Project Memory. Call this: "
        "(1) when you START working (status='in_progress'), "
        "(2) when you FINISH (status='completed'), "
        "(3) if you encounter an error (status='failed'), "
        "(4) if you're blocked waiting for input (status='blocked'). "
        "The Leader uses these to track overall task progress."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task identifier."},
            "worker_id": {"type": "string", "description": "Your worker ID."},
            "status": {
                "type": "string",
                "enum": ["in_progress", "completed", "failed", "blocked"],
                "description": "Current status of your work.",
            },
            "summary": {"type": "string", "description": "Brief progress summary (≤ 200 chars)."},
            "output_preview": {"type": "string", "description": "First ~2 KB of your output (for evaluator)."},
            "error_message": {"type": "string", "description": "Error details if status='failed'."},
        },
        "required": ["task_id", "worker_id", "status", "summary"],
    },
}

_GET_WORKER_CONTEXT_SCHEMA = {
    "name": "opc_get_worker_context",
    "description": (
        "Reload your full task context from Project Memory. "
        "Use this when recovering from an interruption — it returns "
        "your TaskProtocol and the latest progress report so you can "
        "resume where you left off."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task identifier."},
            "worker_id": {"type": "string", "description": "Your worker ID."},
        },
        "required": ["task_id", "worker_id"],
    },
}


# ══════════════════════════════════════════════════════════════════════════
# Tool Handlers
# ══════════════════════════════════════════════════════════════════════════

def opc_save_context(
    task_id: str,
    worker_id: str,
    summary: str,
    step_index: int = 0,
    key_findings: Optional[list] = None,
    artifact_paths: Optional[list] = None,
    target_workers: Optional[list] = None,
    task_id_internal: Optional[str] = None,
) -> str:
    """Save Worker output context and create a SummaryBridge entry."""
    memory = get_memory_layer()

    # 1. Save progress report
    report = ProgressReport(
        task_id=task_id,
        worker_id=worker_id,
        step_index=step_index,
        status="completed",
        summary=summary[:500],
        artifact_paths=artifact_paths or [],
    )
    memory.save_progress_report(report)

    # 2. Write to Summary Bridge
    entry = SummaryBridgeEntry(
        bridge_id="",
        task_id=task_id,
        source_worker_id=worker_id,
        source_step_index=step_index,
        target_worker_ids=target_workers or [],
        summary=summary[:2000],
        key_findings=key_findings or [],
        artifact_references=artifact_paths or [],
    )
    bridge_id = memory.write_to_bridge(entry)

    return json.dumps({
        "status": "saved",
        "bridge_id": bridge_id,
        "message": f"Context saved. {len(target_workers or []) or 'all'} downstream workers can now read your summary.",
    })


def opc_get_upstream_summaries(
    task_id: str,
    worker_id: str,
    upstream_step_indices: Optional[list] = None,
    task_id_internal: Optional[str] = None,
) -> str:
    """Get gated upstream summaries for a Worker."""
    memory = get_memory_layer()
    entries = memory.get_upstream_summaries(
        task_id=task_id,
        worker_id=worker_id,
        upstream_step_indices=upstream_step_indices,
    )

    if not entries:
        return json.dumps({
            "status": "empty",
            "message": "No upstream summaries available for you. You may be the first worker.",
            "entries": [],
        })

    return json.dumps({
        "status": "ok",
        "count": len(entries),
        "entries": [
            {
                "source_worker": e.source_worker_id,
                "step": e.source_step_index,
                "summary": e.summary,
                "key_findings": e.key_findings,
                "artifacts": e.artifact_references,
            }
            for e in entries
        ],
    })


def opc_write_to_bridge(
    task_id: str,
    source_worker_id: str,
    summary: str,
    source_step_index: int = 0,
    data_schema: Optional[dict] = None,
    target_workers: Optional[list] = None,
    task_id_internal: Optional[str] = None,
) -> str:
    """Write structured data to the Summary Bridge."""
    memory = get_memory_layer()

    entry = SummaryBridgeEntry(
        bridge_id="",
        task_id=task_id,
        source_worker_id=source_worker_id,
        source_step_index=source_step_index,
        target_worker_ids=target_workers or [],
        summary=summary[:2000],
        data_schema=data_schema or {},
    )
    bridge_id = memory.write_to_bridge(entry)

    return json.dumps({
        "status": "written",
        "bridge_id": bridge_id,
        "message": "Data written to Summary Bridge.",
    })


def opc_save_progress_report(
    task_id: str,
    worker_id: str,
    status: str,
    summary: str,
    output_preview: str = "",
    error_message: str = "",
    task_id_internal: Optional[str] = None,
) -> str:
    """Save a progress report."""
    memory = get_memory_layer()

    step_index = 0  # derived from task protocol in full implementation
    report = ProgressReport(
        task_id=task_id,
        worker_id=worker_id,
        step_index=step_index,
        status=status,
        summary=summary[:200],
        output_preview=output_preview[:2048] if output_preview else "",
        error_message=error_message[:1000] if error_message else "",
    )
    memory.save_progress_report(report)

    return json.dumps({
        "status": "saved",
        "message": f"Progress report saved: {status}.",
    })


def opc_get_worker_context(
    task_id: str,
    worker_id: str,
    task_id_internal: Optional[str] = None,
) -> str:
    """Reload a Worker's full context from Project Memory (for recovery)."""
    memory = get_memory_layer()

    protocol = memory.get_task_protocol(task_id, worker_id)
    reports = memory.get_progress_reports(task_id)
    my_reports = [r for r in reports if r.worker_id == worker_id]
    last_report = my_reports[-1] if my_reports else None

    return json.dumps({
        "status": "ok",
        "task_protocol": protocol.to_dict() if protocol else None,
        "last_progress": last_report.to_dict() if last_report else None,
        "total_reports": len(my_reports),
        "message": "Context reloaded. Resume from last_progress if available.",
    })


# ══════════════════════════════════════════════════════════════════════════
# Plugin Registration
# ══════════════════════════════════════════════════════════════════════════

_TOOL_REGISTRATIONS = [
    ("opc_save_context", opc_save_context, _SAVE_CONTEXT_SCHEMA),
    ("opc_get_upstream_summaries", opc_get_upstream_summaries, _GET_UPSTREAM_SUMMARIES_SCHEMA),
    ("opc_write_to_bridge", opc_write_to_bridge, _WRITE_TO_BRIDGE_SCHEMA),
    ("opc_save_progress_report", opc_save_progress_report, _SAVE_PROGRESS_SCHEMA),
    ("opc_get_worker_context", opc_get_worker_context, _GET_WORKER_CONTEXT_SCHEMA),
]


def register_all(ctx: Any) -> None:
    """Register all OPC memory tools into the given plugin context.

    Called by opc_hermes.plugin._register_memory_tools().
    """
    def _make_handler(handler):
        def _wrapped(args, **kw):
            return handler(
                **{k: v for k, v in args.items() if v is not None},
                task_id_internal=kw.get("task_id"),
            )

        return _wrapped

    for name, handler, schema in _TOOL_REGISTRATIONS:
        ctx.register_tool(
            name=name,
            handler=_make_handler(handler),
            schema=schema,
            toolset="opc-memory",
        )
        logger.debug("Registered OPC memory tool: %s", name)
