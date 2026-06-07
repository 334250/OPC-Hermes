"""
Task Protocol and Progress Report data structures.

These are the canonical data shapes that flow between Leader,
Worker, and Evaluator agents through the OPC Memory Layer.

Design reference: §6.4 核心数据结构 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class TaskProtocol:
    """The task specification the Leader produces for each Worker.

    This is what the Leader writes BEFORE dispatching a Worker.
    The Worker reads its own TaskProtocol to understand what to do.
    """

    task_id: str                       # unique task identifier (e.g., UUID hex[:12])
    worker_id: str                     # assigned worker
    step_index: int                    # position in the DAG
    prompt: str                        # the task prompt (self-contained)
    complexity: str                    # SIMPLE | MEDIUM | COMPLEX
    model: str                         # resolved model to use
    upstream_step_indices: List[int] = field(default_factory=list)
    expected_output_format: str = ""   # e.g., "markdown", "json", ".pptx"
    max_iterations: int = 60
    timeout_seconds: int = 600
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProtocol":
        return cls(
            task_id=data["task_id"],
            worker_id=data["worker_id"],
            step_index=data.get("step_index", 0),
            prompt=data["prompt"],
            complexity=data.get("complexity", "MEDIUM"),
            model=data.get("model", ""),
            upstream_step_indices=data.get("upstream_step_indices", []),
            expected_output_format=data.get("expected_output_format", ""),
            max_iterations=data.get("max_iterations", 60),
            timeout_seconds=data.get("timeout_seconds", 600),
            created_at=data.get("created_at", ""),
        )


@dataclass
class ProgressReport:
    """A Worker's progress report, saved after each major milestone.

    Workers call ``opc_save_progress_report`` to persist these.
    The Leader reads them to track overall task progress.
    The Evaluator reads them to score quality.
    """

    task_id: str
    worker_id: str
    step_index: int
    status: str                       # "in_progress" | "completed" | "failed" | "blocked"
    summary: str                      # human-readable progress summary (≤ 500 chars)
    output_preview: str = ""          # first 2 KB of output (for evaluator)
    artifact_paths: List[str] = field(default_factory=list)
    tool_call_count: int = 0
    error_message: str = ""
    reported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProgressReport":
        return cls(
            task_id=data["task_id"],
            worker_id=data["worker_id"],
            step_index=data.get("step_index", 0),
            status=data.get("status", "in_progress"),
            summary=data.get("summary", ""),
            output_preview=data.get("output_preview", ""),
            artifact_paths=data.get("artifact_paths", []),
            tool_call_count=data.get("tool_call_count", 0),
            error_message=data.get("error_message", ""),
            reported_at=data.get("reported_at", ""),
        )


@dataclass
class EvaluationRecord:
    """An evaluator's structured assessment of a Worker's output.

    Written to Eval Memory by the Evaluator Agent.
    Read by the Optimizer for trend analysis.
    """

    task_id: str
    worker_id: str
    evaluator_id: str = "evaluator"
    scores: Dict[str, float] = field(default_factory=dict)
    # Standard score dimensions:
    #   - quality: 0.0-1.0 overall output quality
    #   - relevance: 0.0-1.0 how well the output matches the task
    #   - completeness: 0.0-1.0 whether all requested elements are present
    #   - efficiency: 0.0-1.0 tool calls vs. output complexity ratio
    #   - leader_decomposition: 0.0-1.0 (only for Leader evaluation)
    notes: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvaluationRecord":
        return cls(
            task_id=data["task_id"],
            worker_id=data["worker_id"],
            evaluator_id=data.get("evaluator_id", "evaluator"),
            scores=data.get("scores", {}),
            notes=data.get("notes", ""),
            evaluated_at=data.get("evaluated_at", ""),
        )
