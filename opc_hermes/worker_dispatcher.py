"""
OPC Worker Dispatcher

Thin wrapper (~150 lines) around Hermes Agent's ``delegate_tool``.
Does NOT build its own process manager — reuses the ThreadPoolExecutor
inside ``tools/delegate_tool.py``.

Responsibilities:
  1. Accept a structured task plan from the Leader Agent
  2. Run DAG topological sort (via workflow/dag_executor.py)
  3. For each worker in the sorted order:
     a. Build the worker's system prompt (from template + upstream summaries)
     b. Call ``delegate_task`` with the worker's configuration
     c. Collect the result and write to the Summary Bridge
  4. Return aggregated results to the Leader

Design reference: §9.6 DAG 编排器 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OPCWorkerDispatcher:
    """Dispatches tasks to Worker agents via Hermes delegate_tool.

    The dispatcher is stateless — task state lives in the Memory Layer.
    Each call to ``execute()`` is a self-contained pipeline execution.
    """

    def __init__(self):
        self._agent_registry = None  # lazily loaded

    @property
    def registry(self):
        """Lazy-load the Agent Registry singleton."""
        if self._agent_registry is None:
            from opc_hermes.agent_list.registry import get_registry
            self._agent_registry = get_registry()
        return self._agent_registry

    # ── Public API ───────────────────────────────────────────────────────

    def execute(self, task_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Leader-generated task plan.

        Args:
            task_plan: The structured plan from the Leader, containing:
                - mode: "sequential" | "parallel" | "pipeline" | "star"
                - steps: list of step dicts, each with:
                    - worker_id: the worker to assign
                    - prompt: the task prompt for this worker
                    - upstream: list of step indices this step depends on
                    - model_override: optional model to use
                - task_id: unique task identifier

        Returns:
            Dict with:
                - task_id: the task identifier
                - status: "completed" | "partial" | "failed"
                - steps: list of step results
                - aggregated_result: combined output from all steps
        """
        task_id = task_plan.get("task_id", "unknown")
        mode = task_plan.get("mode", "sequential")
        steps = task_plan.get("steps", [])

        logger.info(
            "OPCWorkerDispatcher: executing task %s in %s mode with %d steps",
            task_id, mode, len(steps),
        )

        if not steps:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": "No steps in task plan.",
                "steps": [],
                "aggregated_result": "",
            }

        # ── DAG Topological Sort ─────────────────────────────────────────
        try:
            from opc_hermes.workflow.dag_executor import topological_sort
            sorted_steps = topological_sort(steps)
        except ImportError:
            # Phase 1 stub — fall back to sequential ordering
            sorted_steps = list(steps)
        except ValueError as e:
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"Cycle detected in task plan: {e}",
                "steps": [],
                "aggregated_result": "",
            }

        # ── Execute steps ────────────────────────────────────────────────
        step_results: List[Dict[str, Any]] = []
        upstream_outputs: Dict[int, str] = {}  # step_index → output

        for step in sorted_steps:
            step_index = step.get("index", len(step_results))
            result = self._execute_step(
                step=step,
                task_id=task_id,
                upstream_outputs=upstream_outputs,
            )
            step_results.append(result)

            if result.get("status") == "completed":
                upstream_outputs[step_index] = result.get("output", "")
            else:
                logger.warning(
                    "Step %d (%s) failed: %s",
                    step_index, step.get("worker_id", "unknown"),
                    result.get("error", "unknown error"),
                )
                # Continue executing independent parallel branches;
                # a failure in one branch doesn't cancel the whole DAG.

        # ── Aggregate ────────────────────────────────────────────────────
        all_completed = all(r.get("status") == "completed" for r in step_results)
        aggregated = self._aggregate_results(step_results)

        return {
            "task_id": task_id,
            "status": "completed" if all_completed else "partial",
            "steps": step_results,
            "aggregated_result": aggregated,
        }

    # ── Internal ─────────────────────────────────────────────────────────

    def _execute_step(
        self,
        step: Dict[str, Any],
        task_id: str,
        upstream_outputs: Dict[int, str],
    ) -> Dict[str, Any]:
        """Execute a single step by dispatching to the assigned worker.

        In Phase 1, this is a stub that simulates execution.
        In Phase 2, this will call Hermes' ``delegate_task`` with:
          - The worker's system prompt (from template)
          - Upstream summaries (from the Summary Bridge)
          - The step's task prompt
        """
        worker_id = step.get("worker_id", "unknown")
        prompt = step.get("prompt", "")
        model = step.get("model_override", "")

        # ── Phase 1 stub ─────────────────────────────────────────────────
        logger.info(
            "[STUB] Would delegate to worker '%s' with model '%s': %s",
            worker_id, model or "default", prompt[:100],
        )

        return {
            "step_index": step.get("index", -1),
            "worker_id": worker_id,
            "status": "completed",
            "output": f"[Phase 1 stub] Worker '{worker_id}' output for: {prompt[:200]}",
            "model_used": model or "default",
            "tool_calls": 0,
            "duration_ms": 0,
        }

    def _aggregate_results(self, step_results: List[Dict[str, Any]]) -> str:
        """Combine all step outputs into a single aggregated result.

        In Phase 2, this will call the Leader Agent to produce a summary.
        """
        parts = []
        for r in step_results:
            worker = r.get("worker_id", "unknown")
            status = r.get("status", "unknown")
            output = r.get("output", "")
            parts.append(f"## {worker} ({status})\n\n{output}")

        return "\n\n".join(parts)
