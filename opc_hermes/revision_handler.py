"""
Revision Handler — processes user revision feedback.

When a user provides revision feedback on a completed task, the
Revision Handler:
  1. Analyzes the feedback to determine scope (local / structural / global)
  2. Identifies which Workers are affected
  3. Routes revision sub-tasks ONLY to the affected Workers
  4. Avoids re-running the entire DAG

Design reference: §9.3 修订/反馈闭环 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RevisionScope(Enum):
    """How broadly a revision affects the task output."""
    LOCAL = "local"           # e.g., "fix this typo", "change this color"
    STRUCTURAL = "structural" # e.g., "reorganize chapter 3", "add a new section"
    GLOBAL = "global"         # e.g., "rewrite the whole thing", "change the tone everywhere"


def analyze_revision(
    feedback: str,
    task_plan: Dict[str, Any],
    completed_steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Analyze user revision feedback and determine affected workers.

    In Phase 3, this is a keyword-based heuristic. Future phases can
    use an LLM call for more nuanced analysis.

    Args:
        feedback: The user's revision request (free text).
        task_plan: The original task plan (with steps and worker assignments).
        completed_steps: The completed step results.

    Returns:
        Dict with:
          - scope: "local" | "structural" | "global"
          - affected_workers: list of worker_ids that need to re-run
          - revision_tasks: list of sub-tasks for each affected worker
          - unaffected_workers: workers whose output is unchanged
    """
    feedback_lower = feedback.lower().strip()

    # ── Determine scope ──────────────────────────────────────────────────
    scope = _determine_scope(feedback_lower)

    # ── Identify affected workers ────────────────────────────────────────
    if scope == RevisionScope.GLOBAL:
        # Everything needs redo
        affected = [s.get("worker_id") for s in task_plan.get("steps", [])]
        unaffected = []
    elif scope == RevisionScope.STRUCTURAL:
        # Find workers whose output mentions the feedback topics
        affected, unaffected = _match_workers_by_content(
            feedback_lower, task_plan, completed_steps
        )
    else:  # LOCAL
        # Try to find the specific worker(s) mentioned or implied
        affected, unaffected = _match_workers_by_content(
            feedback_lower, task_plan, completed_steps
        )
        if not affected:
            # If we can't determine, ask the user (return empty = need clarification)
            pass

    # ── Build revision sub-tasks ─────────────────────────────────────────
    revision_tasks = []
    for worker_id in affected:
        for step in completed_steps:
            if step.get("worker_id") == worker_id:
                revision_tasks.append({
                    "worker_id": worker_id,
                    "original_output": step.get("output", ""),
                    "revision_prompt": _build_revision_prompt(
                        feedback, worker_id, step, scope
                    ),
                })
                break

    return {
        "scope": scope.value,
        "affected_workers": affected,
        "unaffected_workers": unaffected,
        "revision_tasks": revision_tasks,
        "requires_full_redo": scope == RevisionScope.GLOBAL,
    }


def _determine_scope(feedback_lower: str) -> RevisionScope:
    """Classify revision scope from the feedback text."""
    # GLOBAL indicators
    global_keywords = [
        "rewrite", "重写", "redo", "重新做", "start over", "重新开始",
        "completely", "完全", "entire", "整个", "different approach", "换个方式",
    ]
    if any(kw in feedback_lower for kw in global_keywords):
        return RevisionScope.GLOBAL

    # STRUCTURAL indicators
    structural_keywords = [
        "reorganize", "重组", "restructure", "重构结构", "add section", "添加章节",
        "remove section", "删除章节", "change order", "调整顺序", "move", "移动",
        "merge", "合并", "split", "拆分",
    ]
    if any(kw in feedback_lower for kw in structural_keywords):
        return RevisionScope.STRUCTURAL

    # Default: LOCAL
    return RevisionScope.LOCAL


def _match_workers_by_content(
    feedback_lower: str,
    task_plan: Dict[str, Any],
    completed_steps: List[Dict[str, Any]],
) -> tuple:
    """Match feedback to workers based on step descriptions and output content."""
    affected = []
    unaffected = []

    for step in task_plan.get("steps", []):
        worker_id = step.get("worker_id", "")
        step_prompt = (step.get("prompt", "") or "").lower()

        # Check if feedback mentions the worker's role or capability
        from opc_hermes.agent_list.registry import get_registry
        worker = get_registry().get_worker(worker_id)

        is_affected = False

        # Check worker name/description
        if worker:
            if worker.display_name.lower() in feedback_lower:
                is_affected = True
            if any(cap.lower() in feedback_lower for cap in worker.capabilities):
                is_affected = True

        # Check step prompt for matching keywords
        if not is_affected:
            feedback_words = set(feedback_lower.split())
            prompt_words = set(step_prompt.split())
            overlap = feedback_words & prompt_words
            if len(overlap) >= 3:
                is_affected = True

        if is_affected:
            affected.append(worker_id)
        else:
            unaffected.append(worker_id)

    return affected, unaffected


def _build_revision_prompt(
    feedback: str,
    worker_id: str,
    step: Dict[str, Any],
    scope: RevisionScope,
) -> str:
    """Build a revision-specific prompt for the affected worker."""
    original_prompt = step.get("prompt", "")
    original_output = step.get("output", "")

    if scope == RevisionScope.LOCAL:
        return (
            f"## Original Task\n{original_prompt}\n\n"
            f"## Your Previous Output\n{original_output[:500]}...\n\n"
            f"## Revision Request\n{feedback}\n\n"
            f"Make ONLY the requested change. Preserve everything else unchanged."
        )
    elif scope == RevisionScope.STRUCTURAL:
        return (
            f"## Original Task\n{original_prompt}\n\n"
            f"## Structural Revision\n{feedback}\n\n"
            f"Restructure your output as requested while preserving the core content."
        )
    else:  # GLOBAL
        return (
            f"## Original Task\n{original_prompt}\n\n"
            f"## Complete Rewrite\n{feedback}\n\n"
            f"Redo the entire task based on this feedback."
        )
