"""
Summary Bridge Entry — the gating mechanism between Workers.

The Summary Bridge is how OPC-Hermes enforces memory isolation:
  - When Worker A finishes, the Leader writes a **summary** of A's output
    into the Summary Bridge.
  - Worker B reads ONLY the summary — never A's full raw context.
  - This prevents context pollution and keeps each Worker focused.

Design reference: §6.2 三层物理存储 + 内部门控 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class SummaryBridgeEntry:
    """A gated summary entry passed from an upstream Worker to downstream Workers.

    Only the Leader and the upstream Worker can WRITE to this.
    Downstream Workers can only READ.
    """

    bridge_id: str                     # unique ID for this bridge entry
    task_id: str                       # the task this belongs to
    source_worker_id: str              # the worker that produced this summary
    source_step_index: int             # the step that produced this summary
    target_worker_ids: List[str] = field(default_factory=list)  # which workers can read this
    summary: str = ""                  # the gated summary (≤ 2 KB)
    key_findings: List[str] = field(default_factory=list)
    artifact_references: List[str] = field(default_factory=list)  # paths to output files
    data_schema: Dict[str, Any] = field(default_factory=dict)     # structure of output data
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SummaryBridgeEntry":
        return cls(
            bridge_id=data["bridge_id"],
            task_id=data["task_id"],
            source_worker_id=data["source_worker_id"],
            source_step_index=data.get("source_step_index", 0),
            target_worker_ids=data.get("target_worker_ids", []),
            summary=data.get("summary", ""),
            key_findings=data.get("key_findings", []),
            artifact_references=data.get("artifact_references", []),
            data_schema=data.get("data_schema", {}),
            created_at=data.get("created_at", ""),
        )
