"""
OPC Evaluator Agent

A specialized Hermes Agent instance that evaluates Worker output quality.
Runs with READ-ONLY access to Project Memory and writes ONLY to Eval Memory.

Key design principles:
  - Reads:    Project Memory (TaskProtocols, ProgressReports, artifacts)
  - Writes:   Eval Memory (EvaluationRecords)
  - Does NOT: modify Project Memory or interact with users directly
  - Scope:    per-task evaluation (triggered after each Worker completes)

The Evaluator IS a standard Hermes Agent instance — no special runtime.
Its system prompt defines the scoring dimensions and output format.

Scoring dimensions:
  - quality (0.0-1.0): overall output quality
  - relevance (0.0-1.0): how well the output matches the task prompt
  - completeness (0.0-1.0): whether all requested elements are present
  - efficiency (0.0-1.0): tool calls vs. output complexity ratio
  - leader_decomposition (0.0-1.0): quality of Leader's task breakdown (Leader only)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from opc_hermes.memory_layer.gated_memory import get_memory_layer
from opc_hermes.memory_layer.task_protocol import EvaluationRecord

logger = logging.getLogger(__name__)


class EvaluatorPermissionError(PermissionError):
    """Raised when evaluator tools are called outside evaluator context."""

# ── Evaluator System Prompt ──────────────────────────────────────────────

EVALUATOR_SYSTEM_PROMPT = """You are the **OPC-Hermes Evaluator Agent** — a quality assessment specialist.

Your job is to evaluate Worker output quality across five dimensions.
You have READ-ONLY access to Project Memory. You write ONLY to Eval Memory.

## Scoring Dimensions (0.0 = worst, 1.0 = best)

1. **quality** — Overall output quality. Is the output well-structured, clear, and correct?
2. **relevance** — How well does the output address the task prompt?
3. **completeness** — Are all requested elements present?
4. **efficiency** — Was the work done with an appropriate number of tool calls?
   - Too few tool calls for a complex output → low score
   - Excessive tool calls for a simple output → low score
5. **leader_decomposition** (Leader only) — How well did the Leader break down the task?

## Output Format

After evaluating, call `opc_eval_write_evaluation` with your scores.

## Rules

- Score honestly — inflated scores prevent the Optimizer from finding real issues.
- If the Worker failed (status='failed'), all scores should be 0.0.
- If you can't determine a score, use 0.5 and note why in your notes.
- Write ONLY to Eval Memory — never modify Project Memory.
"""


# ── Evaluator Config ─────────────────────────────────────────────────────

@dataclass
class EvaluatorConfig:
    """Configuration for spawning an Evaluator agent instance."""
    model: str = "claude-sonnet-4"
    toolsets: List[str] = None
    system_prompt: str = EVALUATOR_SYSTEM_PROMPT
    max_iterations: int = 30  # evaluation is simpler than production work
    quiet_mode: bool = True   # evaluator runs in background

    def __post_init__(self):
        if self.toolsets is None:
            self.toolsets = ["opc-core", "opc-evaluator", "read_file"]


# ══════════════════════════════════════════════════════════════════════════
# Evaluator Tool Schemas
# ══════════════════════════════════════════════════════════════════════════

_CAPTURE_SNAPSHOT_SCHEMA = {
    "name": "opc_eval_capture_snapshot",
    "description": (
        "Capture a snapshot of a Worker's input and output for evaluation. "
        "Reads Project Memory to gather the TaskProtocol, ProgressReports, "
        "and upstream summaries for the specified worker."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task to evaluate."},
            "worker_id": {"type": "string", "description": "The worker to evaluate."},
        },
        "required": ["task_id", "worker_id"],
    },
}

_SCORE_OUTPUT_SCHEMA = {
    "name": "opc_eval_score_output",
    "description": (
        "Score a Worker's output on the five standard dimensions. "
        "Returns the score breakdown for review before writing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "worker_id": {"type": "string"},
            "quality": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "relevance": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "completeness": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "efficiency": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "leader_decomposition": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "notes": {"type": "string", "description": "Free-text evaluation notes."},
        },
        "required": ["task_id", "worker_id", "quality", "relevance", "completeness", "efficiency"],
    },
}

_WRITE_EVALUATION_SCHEMA = {
    "name": "opc_eval_write_evaluation",
    "description": (
        "Write a finalized evaluation to Eval Memory. "
        "Only call this AFTER you have determined your final scores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "worker_id": {"type": "string"},
            "quality": {"type": "number"},
            "relevance": {"type": "number"},
            "completeness": {"type": "number"},
            "efficiency": {"type": "number"},
            "leader_decomposition": {"type": "number"},
            "notes": {"type": "string"},
        },
        "required": ["task_id", "worker_id"],
    },
}


# ── Tool Handlers ────────────────────────────────────────────────────────

def capture_snapshot(
    task_id: str,
    worker_id: str,
    task_id_internal: Optional[str] = None,
) -> str:
    """Capture a Worker's input/output snapshot for evaluation."""
    _require_evaluator_context(task_id, task_id_internal)
    memory = get_memory_layer()

    protocol = memory.get_task_protocol(task_id, worker_id)
    reports = memory.get_progress_reports(task_id)
    my_reports = [r for r in reports if r.worker_id == worker_id]
    summaries = memory.get_upstream_summaries(task_id, worker_id)

    return json.dumps({
        "task_protocol": protocol.to_dict() if protocol else None,
        "progress_reports": [r.to_dict() for r in my_reports],
        "upstream_summaries": [
            {"source": s.source_worker_id, "summary": s.summary}
            for s in summaries
        ],
        "message": f"Snapshot captured for {worker_id} in task {task_id}.",
    })


def write_evaluation(
    task_id: str,
    worker_id: str,
    quality: float = 0.0,
    relevance: float = 0.0,
    completeness: float = 0.0,
    efficiency: float = 0.0,
    leader_decomposition: float = 0.0,
    notes: str = "",
    task_id_internal: Optional[str] = None,
) -> str:
    """Write a finalized evaluation to Eval Memory."""
    _require_evaluator_context(task_id, task_id_internal)
    memory = get_memory_layer()

    evaluation = EvaluationRecord(
        task_id=task_id,
        worker_id=worker_id,
        evaluator_id="evaluator",
        scores={
            "quality": round(quality, 2),
            "relevance": round(relevance, 2),
            "completeness": round(completeness, 2),
            "efficiency": round(efficiency, 2),
            "leader_decomposition": round(leader_decomposition, 2),
        },
        notes=notes,
    )
    memory.write_evaluation(evaluation)

    # Also update the agent registry score
    try:
        from opc_hermes.agent_list.registry import get_registry
        avg_score = sum(evaluation.scores.values()) / len(evaluation.scores)
        get_registry().update_score(worker_id, round(avg_score, 2))
    except Exception:
        pass

    return json.dumps({
        "status": "written",
        "scores": evaluation.scores,
        "message": f"Evaluation written for {worker_id}.",
    })


def score_output(
    task_id: str,
    worker_id: str,
    quality: float = 0.0,
    relevance: float = 0.0,
    completeness: float = 0.0,
    efficiency: float = 0.0,
    leader_decomposition: float = 0.0,
    notes: str = "",
    task_id_internal: Optional[str] = None,
) -> str:
    """Return a normalized score payload without writing Eval Memory."""
    _require_evaluator_context(task_id, task_id_internal)
    return json.dumps({
        "task_id": task_id,
        "worker_id": worker_id,
        "scores": {
            "quality": round(quality, 2),
            "relevance": round(relevance, 2),
            "completeness": round(completeness, 2),
            "efficiency": round(efficiency, 2),
            "leader_decomposition": round(leader_decomposition, 2),
        },
        "notes": notes,
    })


# ── Plugin Registration ──────────────────────────────────────────────────

_EVAL_TOOL_REGISTRATIONS = [
    ("opc_eval_capture_snapshot", capture_snapshot, _CAPTURE_SNAPSHOT_SCHEMA),
    ("opc_eval_score_output", score_output, _SCORE_OUTPUT_SCHEMA),
    ("opc_eval_write_evaluation", write_evaluation, _WRITE_EVALUATION_SCHEMA),
]


def register_all(ctx: Any) -> None:
    """Register evaluator tools into the given plugin context."""
    def _make_handler(handler):
        def _wrapped(args, **kw):
            _require_evaluator_tool_call(args, kw)
            return handler(
                **{k: v for k, v in args.items() if v is not None},
                task_id_internal=kw.get("task_id"),
            )

        return _wrapped

    for name, handler, schema in _EVAL_TOOL_REGISTRATIONS:
        if handler is not None:
            ctx.register_tool(
                name=name,
                handler=_make_handler(handler),
                schema=schema,
                toolset="opc-evaluator",
            )
        logger.debug("Registered evaluator tool: %s", name)


def _require_evaluator_tool_call(args: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    agent_id = metadata.get("agent_id") or metadata.get("caller_agent_id")
    if agent_id != "evaluator" or metadata.get("evaluator_internal_flag") is not True:
        raise EvaluatorPermissionError("Evaluator tools require trusted evaluator context.")

    internal_task_id = metadata.get("task_id")
    requested_task_id = args.get("task_id")
    if not internal_task_id:
        raise EvaluatorPermissionError("Evaluator tools require an active internal task_id.")
    if requested_task_id and internal_task_id != requested_task_id:
        raise EvaluatorPermissionError("Evaluator tools cannot access a different task_id.")


def _require_evaluator_context(task_id: str, task_id_internal: Optional[str]) -> None:
    if task_id_internal and task_id_internal != task_id:
        raise EvaluatorPermissionError("Evaluator task_id does not match the active task.")
