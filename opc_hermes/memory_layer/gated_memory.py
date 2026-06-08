"""
Gated Memory Layer — the central memory orchestrator for OPC-Hermes.

Three physically-separated storage partitions:
  1. Project Memory   (project.db)     — task execution context, Worker outputs
  2. Eval Memory      (eval.db)        — quality metrics, evaluator scores
  3. Knowledge Base   (kb.db + chromadb/) — domain knowledge, user uploads

Internal gating rules:
  - Workers read ONLY their own TaskProtocol + upstream SummaryBridge entries
  - Workers write to Project Memory (their own outputs + progress reports)
  - Evaluator reads Project Memory, writes ONLY to Eval Memory
  - Leader reads everything, writes to Project Memory + Summary Bridge
  - Knowledge Base is read-only for all agents (populated by knowledge_pipeline)

Storage location: ~/.hermes/opc/memory/
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from opc_hermes.memory_layer.task_protocol import (
    TaskProtocol,
    ProgressReport,
    EvaluationRecord,
)
from opc_hermes.memory_layer.summary_bridge import SummaryBridgeEntry

logger = logging.getLogger(__name__)


class GatedMemoryLayer:
    """Central memory orchestrator for OPC-Hermes.

    Each partition is a separate SQLite database for physical isolation.
    ChromaDB is used optionally for the Knowledge Base's vector index.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            from opc_hermes.config.loader import get_opc_home

            base_dir = get_opc_home() / "memory"

        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

        # Per-DB locks (SQLite is single-writer, but separate DBs can
        # be written concurrently from different threads).
        self._project_lock = threading.Lock()
        self._eval_lock = threading.Lock()
        self._kb_lock = threading.Lock()

        self._init_schemas()

    # ── Paths ────────────────────────────────────────────────────────────

    @property
    def project_db(self) -> Path:
        return self._base_dir / "project.db"

    @property
    def eval_db(self) -> Path:
        return self._base_dir / "eval.db"

    @property
    def kb_db(self) -> Path:
        return self._base_dir / "kb.db"

    # ── Schema initialization ────────────────────────────────────────────

    def _init_schemas(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        # Project Memory
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS task_protocols (
                    task_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL DEFAULT 0,
                    prompt TEXT NOT NULL,
                    complexity TEXT NOT NULL DEFAULT 'MEDIUM',
                    model TEXT DEFAULT '',
                    upstream_step_indices TEXT DEFAULT '[]',
                    expected_output_format TEXT DEFAULT '',
                    max_iterations INTEGER DEFAULT 60,
                    timeout_seconds INTEGER DEFAULT 600,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, worker_id)
                );

                CREATE TABLE IF NOT EXISTS progress_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'in_progress',
                    summary TEXT DEFAULT '',
                    output_preview TEXT DEFAULT '',
                    artifact_paths TEXT DEFAULT '[]',
                    tool_call_count INTEGER DEFAULT 0,
                    error_message TEXT DEFAULT '',
                    reported_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_progress_task
                    ON progress_reports(task_id, worker_id);

                CREATE TABLE IF NOT EXISTS summary_bridges (
                    bridge_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    source_worker_id TEXT NOT NULL,
                    source_step_index INTEGER NOT NULL DEFAULT 0,
                    target_worker_ids TEXT DEFAULT '[]',
                    summary TEXT DEFAULT '',
                    key_findings TEXT DEFAULT '[]',
                    artifact_references TEXT DEFAULT '[]',
                    data_schema TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_bridge_task
                    ON summary_bridges(task_id);
            """)
            conn.commit()
            conn.close()

        # Eval Memory
        with self._eval_lock:
            conn = sqlite3.connect(str(self.eval_db))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    evaluator_id TEXT DEFAULT 'evaluator',
                    scores TEXT DEFAULT '{}',
                    notes TEXT DEFAULT '',
                    evaluated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_eval_worker
                    ON evaluations(worker_id);
                CREATE INDEX IF NOT EXISTS idx_eval_task
                    ON evaluations(task_id);
            """)
            conn.commit()
            conn.close()

        # Knowledge Base
        with self._kb_lock:
            conn = sqlite3.connect(str(self.kb_db))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS knowledge_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_url TEXT DEFAULT '',
                    source_type TEXT DEFAULT 'upload',
                    tags TEXT DEFAULT '[]',
                    quality_score REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kb_agent_index (
                    agent_id TEXT NOT NULL,
                    entry_id INTEGER NOT NULL,
                    relevance_score REAL DEFAULT 0.0,
                    PRIMARY KEY (agent_id, entry_id)
                );
            """)
            conn.commit()
            conn.close()

    # ══════════════════════════════════════════════════════════════════════
    # Project Memory API
    # ══════════════════════════════════════════════════════════════════════

    def save_task_protocol(self, protocol: TaskProtocol) -> None:
        """Save a task protocol (Leader writes this before dispatch)."""
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.execute(
                """INSERT OR REPLACE INTO task_protocols
                   (task_id, worker_id, step_index, prompt, complexity, model,
                    upstream_step_indices, expected_output_format,
                    max_iterations, timeout_seconds, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    protocol.task_id,
                    protocol.worker_id,
                    protocol.step_index,
                    protocol.prompt,
                    protocol.complexity,
                    protocol.model,
                    json.dumps(protocol.upstream_step_indices),
                    protocol.expected_output_format,
                    protocol.max_iterations,
                    protocol.timeout_seconds,
                    protocol.created_at,
                ),
            )
            conn.commit()
            conn.close()
        logger.debug("Saved TaskProtocol: %s/%s", protocol.task_id, protocol.worker_id)

    def get_task_protocol(self, task_id: str, worker_id: str) -> Optional[TaskProtocol]:
        """Get a task protocol (Worker reads this to know what to do)."""
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM task_protocols WHERE task_id = ? AND worker_id = ?",
                (task_id, worker_id),
            ).fetchone()
            conn.close()

        if not row:
            return None

        return TaskProtocol(
            task_id=row["task_id"],
            worker_id=row["worker_id"],
            step_index=row["step_index"],
            prompt=row["prompt"],
            complexity=row["complexity"],
            model=row["model"],
            upstream_step_indices=json.loads(row["upstream_step_indices"]),
            expected_output_format=row["expected_output_format"],
            max_iterations=row["max_iterations"],
            timeout_seconds=row["timeout_seconds"],
            created_at=row["created_at"],
        )

    def get_all_task_protocols(self, task_id: str) -> List[TaskProtocol]:
        """Get all task protocols for a task (Leader reads all)."""
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM task_protocols WHERE task_id = ? ORDER BY step_index",
                (task_id,),
            ).fetchall()
            conn.close()

        return [
            TaskProtocol(
                task_id=r["task_id"],
                worker_id=r["worker_id"],
                step_index=r["step_index"],
                prompt=r["prompt"],
                complexity=r["complexity"],
                model=r["model"],
                upstream_step_indices=json.loads(r["upstream_step_indices"]),
                expected_output_format=r["expected_output_format"],
                max_iterations=r["max_iterations"],
                timeout_seconds=r["timeout_seconds"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def save_progress_report(self, report: ProgressReport) -> None:
        """Save a Worker's progress report."""
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.execute(
                """INSERT INTO progress_reports
                   (task_id, worker_id, step_index, status, summary,
                    output_preview, artifact_paths, tool_call_count,
                    error_message, reported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.task_id,
                    report.worker_id,
                    report.step_index,
                    report.status,
                    report.summary,
                    report.output_preview,
                    json.dumps(report.artifact_paths),
                    report.tool_call_count,
                    report.error_message,
                    report.reported_at,
                ),
            )
            conn.commit()
            conn.close()
        logger.debug("Saved ProgressReport: %s/%s (%s)", report.task_id, report.worker_id, report.status)

    def get_progress_reports(self, task_id: str) -> List[ProgressReport]:
        """Get all progress reports for a task (Leader reads for tracking)."""
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM progress_reports WHERE task_id = ? ORDER BY reported_at",
                (task_id,),
            ).fetchall()
            conn.close()

        return [
            ProgressReport(
                task_id=r["task_id"],
                worker_id=r["worker_id"],
                step_index=r["step_index"],
                status=r["status"],
                summary=r["summary"],
                output_preview=r["output_preview"],
                artifact_paths=json.loads(r["artifact_paths"]),
                tool_call_count=r["tool_call_count"],
                error_message=r["error_message"],
                reported_at=r["reported_at"],
            )
            for r in rows
        ]

    # ══════════════════════════════════════════════════════════════════════
    # Summary Bridge API
    # ══════════════════════════════════════════════════════════════════════

    def write_to_bridge(self, entry: SummaryBridgeEntry) -> str:
        """Write a summary to the bridge (Leader or upstream Worker).

        Returns the bridge_id.
        """
        if not entry.bridge_id:
            entry.bridge_id = uuid.uuid4().hex[:12]

        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.execute(
                """INSERT OR REPLACE INTO summary_bridges
                   (bridge_id, task_id, source_worker_id, source_step_index,
                    target_worker_ids, summary, key_findings,
                    artifact_references, data_schema, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.bridge_id,
                    entry.task_id,
                    entry.source_worker_id,
                    entry.source_step_index,
                    json.dumps(entry.target_worker_ids),
                    entry.summary,
                    json.dumps(entry.key_findings),
                    json.dumps(entry.artifact_references),
                    json.dumps(entry.data_schema),
                    entry.created_at,
                ),
            )
            conn.commit()
            conn.close()

        logger.debug("Wrote SummaryBridge: %s → %s", entry.source_worker_id, entry.target_worker_ids)
        return entry.bridge_id

    def get_upstream_summaries(
        self,
        task_id: str,
        worker_id: str,
        upstream_step_indices: Optional[List[int]] = None,
    ) -> List[SummaryBridgeEntry]:
        """Get upstream summaries a Worker is allowed to read.

        Gating: only returns summaries where this worker_id is in the
        target_worker_ids list (or the list is empty, meaning "all workers").

        If ``upstream_step_indices`` is provided, additionally filters by
        source_step_index.
        """
        with self._project_lock:
            conn = sqlite3.connect(str(self.project_db))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM summary_bridges WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ).fetchall()
            conn.close()

        entries = []
        for r in rows:
            target_ids = json.loads(r["target_worker_ids"])
            # Gate: only return if this worker is a target (or no targets = public)
            if target_ids and worker_id not in target_ids:
                continue
            if upstream_step_indices is not None:
                if r["source_step_index"] not in upstream_step_indices:
                    continue

            entries.append(SummaryBridgeEntry(
                bridge_id=r["bridge_id"],
                task_id=r["task_id"],
                source_worker_id=r["source_worker_id"],
                source_step_index=r["source_step_index"],
                target_worker_ids=target_ids,
                summary=r["summary"],
                key_findings=json.loads(r["key_findings"]),
                artifact_references=json.loads(r["artifact_references"]),
                data_schema=json.loads(r["data_schema"]),
                created_at=r["created_at"],
            ))

        return entries

    # ══════════════════════════════════════════════════════════════════════
    # Eval Memory API
    # ══════════════════════════════════════════════════════════════════════

    def write_evaluation(self, evaluation: EvaluationRecord) -> None:
        """Write an evaluation record (Evaluator only)."""
        with self._eval_lock:
            conn = sqlite3.connect(str(self.eval_db))
            conn.execute(
                """INSERT INTO evaluations
                   (task_id, worker_id, evaluator_id, scores, notes, evaluated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    evaluation.task_id,
                    evaluation.worker_id,
                    evaluation.evaluator_id,
                    json.dumps(evaluation.scores),
                    evaluation.notes,
                    evaluation.evaluated_at,
                ),
            )
            conn.commit()
            conn.close()
        logger.debug("Wrote EvaluationRecord: %s/%s", evaluation.task_id, evaluation.worker_id)

    def get_evaluations(
        self,
        worker_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[EvaluationRecord]:
        """Get evaluation records, optionally filtered by worker (Optimizer reads these)."""
        with self._eval_lock:
            conn = sqlite3.connect(str(self.eval_db))
            conn.row_factory = sqlite3.Row

            if worker_id:
                rows = conn.execute(
                    "SELECT * FROM evaluations WHERE worker_id = ? ORDER BY evaluated_at DESC LIMIT ?",
                    (worker_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM evaluations ORDER BY evaluated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            conn.close()

        return [
            EvaluationRecord(
                task_id=r["task_id"],
                worker_id=r["worker_id"],
                evaluator_id=r["evaluator_id"],
                scores=json.loads(r["scores"]),
                notes=r["notes"],
                evaluated_at=r["evaluated_at"],
            )
            for r in rows
        ]

    def get_worker_score_trend(self, worker_id: str, limit: int = 50) -> List[Tuple[str, float]]:
        """Get a worker's quality score over time (for Optimizer trend analysis).

        Returns list of (evaluated_at, overall_score) tuples.
        """
        with self._eval_lock:
            conn = sqlite3.connect(str(self.eval_db))
            rows = conn.execute(
                "SELECT evaluated_at, scores FROM evaluations WHERE worker_id = ? ORDER BY evaluated_at ASC LIMIT ?",
                (worker_id, limit),
            ).fetchall()
            conn.close()

        trend = []
        for r in rows:
            scores = json.loads(r[1])
            overall = scores.get("quality", scores.get("overall", 0.5))
            trend.append((r[0], overall))
        return trend

    # ══════════════════════════════════════════════════════════════════════
    # Knowledge Base API
    # ══════════════════════════════════════════════════════════════════════

    def kb_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search the knowledge base (simple SQLite LIKE for now; chromadb in Phase 4)."""
        with self._kb_lock:
            conn = sqlite3.connect(str(self.kb_db))
            conn.row_factory = sqlite3.Row
            # Simple full-text search via LIKE
            like_query = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM knowledge_entries
                   WHERE title LIKE ? OR content LIKE ?
                   ORDER BY quality_score DESC LIMIT ?""",
                (like_query, like_query, top_k),
            ).fetchall()
            conn.close()

        return [dict(r) for r in rows]

    def kb_add_entry(
        self, title: str, content: str, *,
        source_url: str = "", source_type: str = "upload", tags: Optional[List[str]] = None,
    ) -> int:
        """Add a knowledge base entry (called by knowledge_pipeline)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._kb_lock:
            conn = sqlite3.connect(str(self.kb_db))
            cursor = conn.execute(
                """INSERT INTO knowledge_entries
                   (title, content, source_url, source_type, tags, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (title, content, source_url, source_type, json.dumps(tags or []), now, now),
            )
            conn.commit()
            entry_id = cursor.lastrowid
            conn.close()
        return entry_id


# ── Module-level singleton ───────────────────────────────────────────────

_memory_layer: Optional[GatedMemoryLayer] = None
_memory_lock = threading.Lock()


def get_memory_layer() -> GatedMemoryLayer:
    """Return the module-level GatedMemoryLayer singleton."""
    global _memory_layer
    if _memory_layer is None:
        with _memory_lock:
            if _memory_layer is None:
                _memory_layer = GatedMemoryLayer()
    return _memory_layer
