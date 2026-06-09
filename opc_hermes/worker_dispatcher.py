"""
OPC Worker Dispatcher — Phase 2 real execution engine.

Wraps Hermes Agent's ``delegate_task`` via a swappable adapter
(``delegate_adapter.py``). Does NOT build its own process manager.

Phase 2 additions over Phase 1 stub:
  - Real delegate_task calls via DelegateAdapter
  - TaskProtocol written to Project Memory before each step
  - SummaryBridge written after each step completes
  - ProgressReport saved at step start and finish
  - Failure strategy: retry / skip / abort per config
  - Recovery: skip already-completed steps on re-execution
  - Parallel group batch dispatch
  - Worker prompt rendering from templates
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from opc_hermes.delegate_adapter import (
    DelegateRequest,
    DelegateResult,
    delegate as _delegate,
)
from opc_hermes.memory_layer.gated_memory import get_memory_layer
from opc_hermes.memory_layer.task_protocol import (
    ProgressReport,
    TaskProtocol,
)
from opc_hermes.memory_layer.summary_bridge import SummaryBridgeEntry

logger = logging.getLogger(__name__)


def _infer_provider_from_model(model: str) -> str:
    """Best-effort provider inference for legacy Worker.default_model values."""
    lower = (model or "").strip().lower()
    if not lower:
        return ""
    prefix = lower.split("/", 1)[0] if "/" in lower else ""
    prefix_map = {
        "anthropic": "anthropic",
        "openai": "openai-api",
        "google": "gemini",
        "x-ai": "xai",
        "deepseek": "deepseek",
        "qwen": "alibaba",
        "z-ai": "zai",
        "moonshotai": "kimi-coding",
        "mistralai": "mistral",
        "minimax": "minimax",
        "nvidia": "nvidia",
    }
    if prefix in prefix_map:
        return prefix_map[prefix]
    starts = (
        ("claude", "anthropic"),
        ("gpt-", "openai-api"),
        ("o1", "openai-api"),
        ("o3", "openai-api"),
        ("o4", "openai-api"),
        ("gemini", "gemini"),
        ("gemma", "gemini"),
        ("deepseek", "deepseek"),
        ("grok", "xai"),
        ("glm", "zai"),
        ("kimi", "kimi-coding"),
        ("qwen", "alibaba"),
        ("mistral", "mistral"),
        ("mixtral", "mistral"),
        ("codestral", "mistral"),
    )
    for marker, provider in starts:
        if lower.startswith(marker):
            return provider
    return ""


# ── Failure strategy ─────────────────────────────────────────────────────

class FailurePolicy(Enum):
    RETRY = "retry"       # retry the step up to max_retries times
    SKIP = "skip"         # skip this step, continue with downstream
    ABORT = "abort"       # abort the entire task


DEFAULT_FAILURE_POLICY: Dict[str, FailurePolicy] = {
    "failed": FailurePolicy.RETRY,
    "timeout": FailurePolicy.RETRY,
    "cancelled": FailurePolicy.ABORT,
}
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_DELAY_SECONDS = 5


# ══════════════════════════════════════════════════════════════════════════
# OPCWorkerDispatcher
# ══════════════════════════════════════════════════════════════════════════

class OPCWorkerDispatcher:
    """Dispatches tasks to Worker agents via the delegate adapter."""

    def __init__(
        self,
        *,
        failure_policy: Optional[Dict[str, FailurePolicy]] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        evaluator_enabled: bool = True,
    ):
        self._agent_registry = None
        self.failure_policy = failure_policy or DEFAULT_FAILURE_POLICY
        self.max_retries = max_retries
        self.evaluator_enabled = evaluator_enabled

    @property
    def registry(self):
        if self._agent_registry is None:
            from opc_hermes.agent_list.registry import get_registry
            self._agent_registry = get_registry()
        return self._agent_registry

    # ── Public API ───────────────────────────────────────────────────────

    def execute(self, task_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a Leader-generated task plan.

        Returns {task_id, status, steps, aggregated_result, artifacts}.
        """
        task_id = task_plan.get("task_id", f"opc-{uuid.uuid4().hex[:12]}")
        mode = task_plan.get("mode", "sequential")
        steps = task_plan.get("steps", [])

        logger.info("Dispatching task %s in %s mode with %d steps", task_id, mode, len(steps))

        if not steps:
            return self._abort(task_id, "No steps in task plan.")

        # ── Validate plan ────────────────────────────────────────────────
        from opc_hermes.plan_schema import validate_task_plan
        try:
            validate_task_plan(task_plan)
        except Exception as e:
            return self._abort(task_id, f"Plan validation failed: {e}")

        # ── Topological sort ─────────────────────────────────────────────
        from opc_hermes.workflow.dag_executor import topological_sort, find_parallel_groups

        try:
            sorted_steps = topological_sort(steps)
            parallel_groups = find_parallel_groups(sorted_steps)
        except ValueError as e:
            return self._abort(task_id, f"DAG error: {e}")

        # ── Check for already-completed steps (recovery) ─────────────────
        memory = get_memory_layer()
        completed_steps: set[int] = set()
        for step in sorted_steps:
            idx = step.get("index", -1)
            if idx < 0:
                continue
            worker_id = step.get("worker_id", "")
            reports = memory.get_progress_reports(task_id)
            for r in reports:
                if (
                    r.worker_id == worker_id
                    and r.step_index == idx
                    and r.status == "completed"
                ):
                    completed_steps.add(idx)
                    logger.info("Recovery: step %d (%s) already completed — skipping", idx, worker_id)
                    break

        # ── Execute in parallel groups ───────────────────────────────────
        step_results: List[Dict[str, Any]] = []
        upstream_outputs: Dict[int, str] = {}
        all_artifacts: List[str] = []
        abort_reason: Optional[str] = None

        for batch_index, batch in enumerate(parallel_groups):
            if abort_reason:
                # Mark remaining steps as skipped
                for step in batch:
                    step_results.append(self._skip_result(step, abort_reason))
                continue

            # Write TaskProtocols before execution
            for step in batch:
                idx = step.get("index", -1)
                if idx in completed_steps:
                    continue
                worker_id = step.get("worker_id", "unknown")
                protocol = TaskProtocol(
                    task_id=task_id,
                    worker_id=worker_id,
                    step_index=idx,
                    prompt=step.get("prompt", ""),
                    complexity=task_plan.get("complexity", {}).get("level", "MEDIUM"),
                    model=step.get("model_override", ""),
                    upstream_step_indices=step.get("upstream", []),
                    expected_output_format=step.get("expected_output_format", "text"),
                    timeout_seconds=step.get("timeout_seconds", 600),
                )
                memory.save_task_protocol(protocol)

            # Execute batch (concurrent for parallel, serial for pipeline)
            if mode in ("parallel", "star") and len(batch) > 1:
                batch_results = self._execute_batch(
                    batch, task_id, upstream_outputs, completed_steps,
                )
                batch_abort: Optional[str] = None
            else:
                batch_results, batch_abort = self._execute_sequential(
                    batch, task_id, upstream_outputs, completed_steps,
                    abort_reason=abort_reason,
                )
            if batch_abort:
                abort_reason = batch_abort

            for result in batch_results:
                idx = result.get("step_index", -1)
                step_results.append(result)

                if result.get("status") == "completed":
                    upstream_outputs[idx] = result.get("output", "")
                    all_artifacts.extend(result.get("artifacts", []))
                    # Write SummaryBridge
                    self._write_summary_bridge(task_id, result, step, task_plan)
                elif result.get("status") in ("failed", "timeout") and not abort_reason:
                    policy = self.failure_policy.get(result["status"], FailurePolicy.ABORT)
                    if policy == FailurePolicy.ABORT:
                        abort_reason = f"Step {idx} {result['status']}: {result.get('error', '')}"
                    # RETRY/SKIP handled inside _execute_step_with_retry

        # ── Aggregate ────────────────────────────────────────────────────
        all_completed = all(
            r.get("status") == "completed" or r.get("status") == "skipped"
            for r in step_results
        )
        status = "completed" if all_completed else ("aborted" if abort_reason else "partial")

        return {
            "task_id": task_id,
            "status": status,
            "error": abort_reason,
            "steps": step_results,
            "artifacts": all_artifacts,
            "aggregated_result": self._aggregate_results(step_results),
        }

    # ── Batch execution ──────────────────────────────────────────────────

    def _execute_batch(
        self,
        batch: List[Dict[str, Any]],
        task_id: str,
        upstream_outputs: Dict[int, str],
        completed_steps: set[int],
    ) -> List[Dict[str, Any]]:
        """Execute a batch of steps concurrently via thread pool."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: Dict[int, Dict[str, Any]] = {}
        max_workers = min(len(batch), 8)  # cap concurrent workers

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_step = {}
            for step in batch:
                idx = step.get("index", -1)
                if idx in completed_steps:
                    results[idx] = self._completed_already_result(step)
                    continue
                future = executor.submit(
                    self._execute_step_with_retry,
                    step, task_id, upstream_outputs,
                )
                future_to_step[future] = step

            for future in as_completed(future_to_step):
                step = future_to_step[future]
                idx = step.get("index", -1)
                try:
                    results[idx] = future.result(timeout=step.get("timeout_seconds", 600) + 30)
                except Exception as e:
                    results[idx] = self._error_result(step, f"Batch execution error: {e}")

        return [results[s.get("index", i)] for i, s in enumerate(batch)]

    def _execute_sequential(
        self,
        batch: List[Dict[str, Any]],
        task_id: str,
        upstream_outputs: Dict[int, str],
        completed_steps: set[int],
        abort_reason: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Execute steps sequentially within a batch.

        Returns (results, abort_reason) — abort_reason is set if a step
        with ABORT policy fails, so the caller can stop subsequent batches.
        """
        results = []
        for step in batch:
            if abort_reason:
                results.append(self._skip_result(step, abort_reason))
                continue
            idx = step.get("index", -1)
            if idx in completed_steps:
                results.append(self._completed_already_result(step))
                continue
            result = self._execute_step_with_retry(step, task_id, upstream_outputs)
            results.append(result)
            # Update upstream_outputs for subsequent steps in this batch
            if result.get("status") == "completed":
                upstream_outputs[idx] = result.get("output", "")
            elif result.get("status") in ("failed", "timeout"):
                policy = self.failure_policy.get(result["status"], FailurePolicy.ABORT)
                if policy == FailurePolicy.ABORT:
                    abort_reason = (
                        f"Step {idx} ({result['status']}): "
                        f"{result.get('error', 'unknown')}"
                    )
        return results, abort_reason

    # ── Single step execution with retry ─────────────────────────────────

    def _execute_step_with_retry(
        self,
        step: Dict[str, Any],
        task_id: str,
        upstream_outputs: Dict[int, str],
    ) -> Dict[str, Any]:
        """Execute a step with retry logic."""
        worker_id = step.get("worker_id", "unknown")
        step_index = step.get("index", -1)
        memory = get_memory_layer()

        for attempt in range(self.max_retries + 1):
            # Save in_progress report
            memory.save_progress_report(ProgressReport(
                task_id=task_id,
                worker_id=worker_id,
                step_index=step_index,
                status="in_progress",
                summary=f"Attempt {attempt + 1}/{self.max_retries + 1}",
                reported_at=datetime.now(timezone.utc).isoformat(),
            ))

            result = self._execute_step(step, task_id, upstream_outputs)

            if result.get("status") == "completed":
                # Save completed report
                memory.save_progress_report(ProgressReport(
                    task_id=task_id,
                    worker_id=worker_id,
                    step_index=step_index,
                    status="completed",
                    summary=result.get("output", "")[:500],
                    output_preview=result.get("output", "")[:2048],
                    artifact_paths=result.get("artifacts", []),
                    tool_call_count=result.get("tool_calls", 0),
                    reported_at=datetime.now(timezone.utc).isoformat(),
                ))
                # Update agent registry stats
                try:
                    self.registry.record_task_outcome(worker_id, success=True)
                except Exception:
                    pass

                # ── Phase 3: Trigger evaluator ───────────────────────────
                if self.evaluator_enabled:
                    self._evaluate_step(task_id, step, result)

                return result

            # Failed — determine what to do
            status = result.get("status", "failed")
            policy = self.failure_policy.get(status, FailurePolicy.ABORT)

            if policy == FailurePolicy.RETRY and attempt < self.max_retries:
                logger.warning(
                    "Step %d (%s) failed (attempt %d/%d): %s. Retrying in %ds...",
                    step_index, worker_id, attempt + 1, self.max_retries + 1,
                    result.get("error", "unknown"),
                    DEFAULT_RETRY_DELAY_SECONDS,
                )
                time.sleep(DEFAULT_RETRY_DELAY_SECONDS)
                continue

            # Final failure — save failure report
            memory.save_progress_report(ProgressReport(
                task_id=task_id,
                worker_id=worker_id,
                step_index=step_index,
                status=status,
                summary=f"Failed after {attempt + 1} attempt(s)",
                error_message=result.get("error", ""),
                reported_at=datetime.now(timezone.utc).isoformat(),
            ))
            try:
                self.registry.record_task_outcome(worker_id, success=False)
            except Exception:
                pass

            if policy == FailurePolicy.SKIP:
                result["status"] = "skipped"
            return result

        return self._error_result(step, "Max retries exhausted")

    # ── Core step execution ──────────────────────────────────────────────

    def _execute_step(
        self,
        step: Dict[str, Any],
        task_id: str,
        upstream_outputs: Dict[int, str],
    ) -> Dict[str, Any]:
        """Execute a single Worker step via the delegate adapter."""
        worker_id = step.get("worker_id", "unknown")
        step_index = step.get("index", -1)
        prompt = step.get("prompt", "")
        model = step.get("model_override", "")
        provider = step.get("provider_override", "")

        # Resolve worker config
        worker = self.registry.get_worker(worker_id)
        if worker is None:
            return self._error_result(step, f"Unknown worker: {worker_id}")

        # Build system prompt from template
        system_prompt = self._render_worker_prompt(
            worker_id=worker_id,
            task_prompt=prompt,
            upstream_outputs=upstream_outputs,
            step=step,
        )

        # Build upstream context
        upstream_indices = step.get("upstream", [])
        if isinstance(upstream_indices, int):
            upstream_indices = [upstream_indices]
        context = self._build_upstream_context(task_id, worker_id, upstream_indices, upstream_outputs)

        # Determine model
        effective_model = model or worker.default_model
        effective_provider = provider or getattr(worker, "default_provider", "") or _infer_provider_from_model(effective_model)
        if not effective_model:
            from opc_hermes.model_prefs import resolve_model
            complexity = "MEDIUM"
            effective_model, _ = resolve_model(complexity)

        # Determine toolsets
        toolsets = worker.toolsets or ["opc-core", "opc-worker"]

        # Build and send delegate request
        request = DelegateRequest(
            task_id=task_id,
            worker_id=worker_id,
            prompt=prompt,
            system_prompt=system_prompt,
            provider=effective_provider,
            model=effective_model,
            toolsets=toolsets,
            max_iterations=step.get("max_iterations", 60),
            timeout_seconds=step.get("timeout_seconds", 600),
            context=context,
        )

        delegate_result = _delegate(request)

        # Convert to step result
        return {
            "step_index": step_index,
            "worker_id": worker_id,
            "status": delegate_result.status,
            "output": delegate_result.output,
            "error": delegate_result.error,
            "model_used": delegate_result.model_used,
            "tool_calls": delegate_result.tool_calls,
            "duration_ms": delegate_result.duration_ms,
            "artifacts": self._extract_artifacts(delegate_result.output),
            "attempts": 1,
        }

    # ── Prompt rendering ─────────────────────────────────────────────────

    def _render_worker_prompt(
        self,
        worker_id: str,
        task_prompt: str,
        upstream_outputs: Dict[int, str],
        step: Dict[str, Any],
    ) -> str:
        """Render a Worker's system prompt from its template."""
        try:
            from pathlib import Path
            import yaml

            templates_path = Path(__file__).parent / "config" / "worker_templates" / "prompts.yaml"
            if templates_path.exists():
                with open(templates_path, "r", encoding="utf-8") as f:
                    templates = yaml.safe_load(f) or {}
                template = templates.get(worker_id, "")
                if template:
                    # Simple variable substitution (Jinja2 in Phase 4)
                    upstream_text = self._build_upstream_text(upstream_outputs, step)
                    return (
                        template
                        .replace("{{ task_prompt }}", task_prompt)
                        .replace("{{ upstream_summaries }}", upstream_text or "No upstream context.")
                        .replace("{{ worker_config }}", f"Worker: {worker_id}")
                    )
        except Exception as e:
            logger.debug("Could not render worker template: %s", e)

        # Fallback: minimal system prompt
        return (
            f"You are the OPC Worker '{worker_id}'. "
            f"Complete the following task and save output with write_file.\n\n"
            f"Task: {task_prompt}"
        )

    def _build_upstream_text(
        self,
        upstream_outputs: Dict[int, str],
        step: Dict[str, Any],
    ) -> str:
        """Build human-readable upstream context text."""
        upstream_indices = step.get("upstream", [])
        if isinstance(upstream_indices, int):
            upstream_indices = [upstream_indices]
        if not upstream_indices:
            return ""

        parts = []
        for idx in upstream_indices:
            output = upstream_outputs.get(idx, "")
            if output:
                parts.append(f"### From Step {idx}\n\n{output[:2000]}")
        return "\n\n".join(parts)

    def _build_upstream_context(
        self,
        task_id: str,
        worker_id: str,
        upstream_indices: List[int],
        upstream_outputs: Dict[int, str],
    ) -> Optional[str]:
        """Build upstream context from SummaryBridge (preferred) or in-memory outputs."""
        memory = get_memory_layer()

        # Try SummaryBridge first
        entries = memory.get_upstream_summaries(task_id, worker_id, upstream_indices)
        if entries:
            return "\n\n".join(
                f"## Upstream Summary (Step {e.source_step_index}, {e.source_worker_id})\n\n{e.summary}"
                for e in entries
            )

        # Fall back to in-memory upstream outputs
        return self._build_upstream_text(upstream_outputs, {"upstream": upstream_indices})

    # ── Summary Bridge ───────────────────────────────────────────────────

    def _write_summary_bridge(
        self,
        task_id: str,
        result: Dict[str, Any],
        step: Dict[str, Any],
        task_plan: Dict[str, Any],
    ) -> None:
        """Write a SummaryBridge entry after a step completes."""
        worker_id = result.get("worker_id", "")
        step_index = result.get("step_index", -1)
        output = result.get("output", "")

        # Find downstream workers
        downstream = [
            s.get("worker_id", "")
            for s in task_plan.get("steps", [])
            if step_index in (
                s.get("upstream", []) if isinstance(s.get("upstream"), list)
                else [s.get("upstream")] if isinstance(s.get("upstream"), int)
                else []
            )
        ]

        memory = get_memory_layer()
        entry = SummaryBridgeEntry(
            bridge_id=f"bridge-{task_id}-{worker_id}-{step_index}",
            task_id=task_id,
            source_worker_id=worker_id,
            source_step_index=step_index,
            target_worker_ids=downstream,
            summary=output[:2000],
            key_findings=self._extract_key_findings(output),
            artifact_references=result.get("artifacts", []),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        memory.write_to_bridge(entry)

    # ── Evaluator trigger (Phase 3) ──────────────────────────────────────

    def _evaluate_step(
        self, task_id: str, step: Dict[str, Any], result: Dict[str, Any],
    ) -> None:
        """Trigger evaluator after a step completes (non-blocking, failure-isolated)."""
        try:
            from opc_hermes.evaluator import LocalEvaluator

            evaluator = LocalEvaluator()
            worker_id = result.get("worker_id", "unknown")
            worker = self.registry.get_worker(worker_id)
            is_leader = worker is not None and worker.role == "leader"

            eval_result = evaluator.evaluate_and_write(
                task_id=task_id,
                worker_id=worker_id,
                task_prompt=step.get("prompt", ""),
                output=result.get("output", ""),
                expected_format=step.get("expected_output_format", ""),
                tool_calls=result.get("tool_calls", 0),
                status=result.get("status", "completed"),
                is_leader=is_leader,
            )
            logger.info(
                "Evaluator scored %s: avg=%.2f (%s)",
                worker_id,
                sum(eval_result["scores"].values()) / max(len(eval_result["scores"]), 1),
                eval_result.get("notes", "")[:80],
            )
        except Exception as exc:
            # P3-8: Evaluator failure never blocks task delivery
            logger.warning("Evaluator failed for %s/%s: %s", task_id, result.get("worker_id", "?"), exc)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _aggregate_results(self, step_results: List[Dict[str, Any]]) -> str:
        parts = []
        for r in step_results:
            worker = r.get("worker_id", "unknown")
            status = r.get("status", "unknown")
            output = r.get("output", "")
            error = r.get("error", "")
            parts.append(f"## Step {r.get('step_index', '?')}: {worker} ({status})")
            if output:
                parts.append(output[:1000])
            if error:
                parts.append(f"**Error:** {error}")
            parts.append("")
        return "\n".join(parts)

    def _extract_artifacts(self, output: str) -> List[str]:
        """Extract file paths from worker output (best-effort heuristic)."""
        import re
        patterns = [
            r'(?:saved|wrote|created|output|generated|artifact)[:\s]+([^\s,;]+\.(?:pptx|docx|pdf|png|jpg|svg|html|json|md|txt|py|drawio|mmd))',
            r'`([^`]+\.(?:pptx|docx|pdf|png|jpg|svg|html|json|md))`',
            r'(?:file|path)[:\s]+([^\s,;]+)',
        ]
        artifacts = set()
        for pattern in patterns:
            for match in re.findall(pattern, output, re.IGNORECASE):
                artifacts.add(match.strip())
        return sorted(artifacts)[:20]

    def _extract_key_findings(self, output: str) -> List[str]:
        """Extract key findings from output (bullet points and key sentences)."""
        import re
        findings = []
        for line in output.split("\n"):
            stripped = line.strip()
            if re.match(r'^[-*•]\s+', stripped):
                findings.append(stripped.lstrip("-*• ").strip()[:200])
        if not findings:
            # Grab first few substantial sentences
            sentences = re.split(r'(?<=[.!?])\s+', output)
            findings = [s.strip()[:200] for s in sentences[:3] if len(s) > 20]
        return findings[:5]

    # ── Result builders ──────────────────────────────────────────────────

    def _completed_already_result(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "step_index": step.get("index", -1),
            "worker_id": step.get("worker_id", "unknown"),
            "status": "completed",
            "output": "[Recovered — this step was already completed in a previous run]",
            "model_used": step.get("model_override", "default"),
            "tool_calls": 0,
            "duration_ms": 0,
            "artifacts": [],
            "recovered": True,
        }

    def _error_result(self, step: Dict[str, Any], error: str) -> Dict[str, Any]:
        return {
            "step_index": step.get("index", -1),
            "worker_id": step.get("worker_id", "unknown"),
            "status": "failed",
            "error": error,
            "output": "",
            "model_used": "",
            "tool_calls": 0,
            "duration_ms": 0,
            "artifacts": [],
        }

    def _skip_result(self, step: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "step_index": step.get("index", -1),
            "worker_id": step.get("worker_id", "unknown"),
            "status": "skipped",
            "error": reason,
            "output": "",
            "model_used": "",
            "tool_calls": 0,
            "duration_ms": 0,
            "artifacts": [],
        }

    def _abort(self, task_id: str, error: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "aborted",
            "error": error,
            "steps": [],
            "artifacts": [],
            "aggregated_result": "",
        }
