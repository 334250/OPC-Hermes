"""Leader task-plan parsing and validation.

Phase 1 keeps this dependency-free so it can run in plugin hooks and tests
without requiring a full JSON-schema stack.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List


ALLOWED_COORDINATION_MODES = {"sequential", "parallel", "pipeline", "star"}
ALLOWED_COMPLEXITY_LEVELS = {"SIMPLE", "MEDIUM", "COMPLEX"}
ALLOWED_TOP_LEVEL_FIELDS = {
    "task_id",
    "title",
    "complexity",
    "mode",
    "requires_user_approval",
    "steps",
    "memory_rules",
    "acceptance_criteria",
}
ALLOWED_COMPLEXITY_FIELDS = {"level", "confidence"}
ALLOWED_STEP_FIELDS = {
    "index",
    "worker_id",
    "prompt",
    "upstream",
    "expected_output_format",
    "requires_vision",
    "requires_tool_calling",
    "model_override",
    "timeout_seconds",
}
MAX_STEP_PROMPT_CHARS = 8000
MAX_PLAN_JSON_CHARS = 100_000
MAX_STEPS = 20


class PlanValidationError(ValueError):
    """Raised when a Leader-generated plan is malformed or unsafe."""


def parse_plan_json(
    text: str,
    *,
    allowed_worker_ids: Iterable[str] | None = None,
    allowed_models: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Parse a Leader plan from raw JSON or a fenced JSON block."""
    if not isinstance(text, str) or not text.strip():
        raise PlanValidationError("Plan text must be a non-empty string.")
    if len(text) > MAX_PLAN_JSON_CHARS:
        raise PlanValidationError("Plan text is too large.")

    candidate = _extract_json_candidate(text.strip())
    try:
        plan = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"Could not parse plan JSON: {exc}") from exc

    validate_task_plan(
        plan,
        allowed_worker_ids=allowed_worker_ids,
        allowed_models=allowed_models,
    )
    return plan


def validate_task_plan(
    plan: Dict[str, Any],
    *,
    allowed_worker_ids: Iterable[str] | None = None,
    allowed_models: Iterable[str] | None = None,
) -> None:
    """Validate the minimal executable Leader task-plan contract."""
    if not isinstance(plan, dict):
        raise PlanValidationError("Plan must be a JSON object.")
    _reject_unknown_fields(plan, ALLOWED_TOP_LEVEL_FIELDS, "Plan")

    _require_string(plan, "task_id")
    _require_string(plan, "title")

    mode = plan.get("mode")
    if mode not in ALLOWED_COORDINATION_MODES:
        raise PlanValidationError(
            f"Plan mode must be one of {sorted(ALLOWED_COORDINATION_MODES)}."
        )

    complexity = plan.get("complexity")
    if not isinstance(complexity, dict):
        raise PlanValidationError("Plan complexity must be an object.")
    _reject_unknown_fields(complexity, ALLOWED_COMPLEXITY_FIELDS, "Plan complexity")
    level = complexity.get("level")
    if level not in ALLOWED_COMPLEXITY_LEVELS:
        raise PlanValidationError(
            f"Complexity level must be one of {sorted(ALLOWED_COMPLEXITY_LEVELS)}."
        )
    confidence = complexity.get("confidence", 0.0)
    if not _is_plain_number(confidence) or not 0 <= confidence <= 1:
        raise PlanValidationError("Complexity confidence must be between 0 and 1.")

    approval = plan.get("requires_user_approval")
    if not isinstance(approval, bool):
        raise PlanValidationError("requires_user_approval must be a boolean.")

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PlanValidationError("Plan steps must be a non-empty list.")
    if len(steps) > MAX_STEPS:
        raise PlanValidationError(f"Plan must not contain more than {MAX_STEPS} steps.")

    seen_indices: set[int] = set()
    for position, step in enumerate(steps):
        _validate_step(
            step,
            position,
            allowed_worker_ids=set(allowed_worker_ids) if allowed_worker_ids else None,
            allowed_models=set(allowed_models) if allowed_models else None,
        )
        index = step["index"]
        if index in seen_indices:
            raise PlanValidationError(f"Duplicate step index: {index}.")
        seen_indices.add(index)

    expected = set(range(len(steps)))
    if seen_indices != expected:
        raise PlanValidationError(
            f"Step indices must be contiguous from 0 to {len(steps) - 1}."
        )

    for step in steps:
        for upstream in _normalize_upstream(step.get("upstream", []), step["index"]):
            if upstream not in expected:
                raise PlanValidationError(
                    f"Step {step['index']} references invalid upstream step {upstream}."
                )
            if upstream == step["index"]:
                raise PlanValidationError(f"Step {step['index']} cannot depend on itself.")
    _reject_cycles(steps)

    criteria = plan.get("acceptance_criteria", [])
    if criteria is not None:
        if not isinstance(criteria, list) or not all(isinstance(item, str) for item in criteria):
            raise PlanValidationError("acceptance_criteria must be a list of strings.")

    memory_rules = plan.get("memory_rules", [])
    if memory_rules is not None:
        if not isinstance(memory_rules, list):
            raise PlanValidationError("memory_rules must be a list.")


def render_plan_summary(plan: Dict[str, Any]) -> str:
    """Render a validated plan into a compact user-facing summary."""
    validate_task_plan(plan)

    complexity = plan["complexity"]
    lines = [
        f"## Task Plan: {plan['title']}",
        "",
        f"- Task ID: `{plan['task_id']}`",
        f"- Mode: `{plan['mode']}`",
        f"- Complexity: `{complexity['level']}` ({complexity.get('confidence', 0):.0%})",
        f"- Requires approval: `{plan['requires_user_approval']}`",
        "",
        "### Steps",
    ]
    for step in plan["steps"]:
        upstream = step.get("upstream", [])
        if isinstance(upstream, int):
            upstream = [upstream]
        deps = ", ".join(str(item) for item in upstream) if upstream else "none"
        lines.append(
            f"{step['index']}. `{step['worker_id']}` after [{deps}] - {step['prompt']}"
        )

    criteria = plan.get("acceptance_criteria") or []
    if criteria:
        lines.extend(["", "### Acceptance Criteria"])
        lines.extend(f"- {item}" for item in criteria)

    return "\n".join(lines)


def _validate_step(
    step: Any,
    position: int,
    *,
    allowed_worker_ids: set[str] | None = None,
    allowed_models: set[str] | None = None,
) -> None:
    if not isinstance(step, dict):
        raise PlanValidationError(f"Step {position} must be an object.")
    _reject_unknown_fields(step, ALLOWED_STEP_FIELDS, f"Step {position}")
    index = step.get("index")
    if not _is_plain_int(index):
        raise PlanValidationError(f"Step {position} index must be an integer.")
    _require_string(step, "worker_id", label=f"Step {index}")
    if allowed_worker_ids is not None and step["worker_id"] not in allowed_worker_ids:
        raise PlanValidationError(f"Step {index} references unknown worker: {step['worker_id']}.")
    _require_string(step, "prompt", label=f"Step {index}")
    _require_string(step, "expected_output_format", label=f"Step {index}")
    if len(step["prompt"]) > MAX_STEP_PROMPT_CHARS:
        raise PlanValidationError(f"Step {index} prompt is too long.")
    _normalize_upstream(step.get("upstream", []), index)

    for key in ("requires_vision", "requires_tool_calling"):
        if key in step and not isinstance(step[key], bool):
            raise PlanValidationError(f"Step {index} {key} must be a boolean.")

    timeout = step.get("timeout_seconds")
    if timeout is not None and (
        not _is_plain_int(timeout) or timeout < 1 or timeout > 24 * 60 * 60
    ):
        raise PlanValidationError(f"Step {index} timeout_seconds is invalid.")

    model = step.get("model_override")
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise PlanValidationError(f"Step {index} model_override must be a string.")
        if allowed_models is not None and model not in allowed_models:
            raise PlanValidationError(f"Step {index} references unknown model: {model}.")


def _normalize_upstream(upstream: Any, step_index: int) -> List[int]:
    if upstream is None:
        return []
    if (
        not isinstance(upstream, list)
        or not all(_is_plain_int(item) for item in upstream)
        or len(set(upstream)) != len(upstream)
    ):
        raise PlanValidationError(f"Step {step_index} upstream must be a list of integers.")
    if any(item < 0 for item in upstream):
        raise PlanValidationError(f"Step {step_index} upstream cannot contain negative indices.")
    return upstream


def _require_string(data: Dict[str, Any], key: str, *, label: str = "Plan") -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PlanValidationError(f"{label} {key} must be a non-empty string.")


def _extract_json_candidate(text: str) -> str:
    fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if len(fenced_blocks) > 1:
        raise PlanValidationError("Plan text must contain exactly one JSON block.")
    if len(fenced_blocks) == 1:
        return fenced_blocks[0]
    if not text.startswith("{") or not text.endswith("}"):
        raise PlanValidationError("Plan text must be raw JSON or one fenced JSON block.")
    return text


def _reject_unknown_fields(data: Dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise PlanValidationError(f"{label} contains unsupported fields: {sorted(unknown)}.")


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_plain_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _reject_cycles(steps: List[Dict[str, Any]]) -> None:
    index_to_step = {step["index"]: step for step in steps}
    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visited:
            return
        if index in visiting:
            raise PlanValidationError("Plan contains a dependency cycle.")
        visiting.add(index)
        for upstream in _normalize_upstream(index_to_step[index].get("upstream", []), index):
            visit(upstream)
        visiting.remove(index)
        visited.add(index)

    for step in steps:
        visit(step["index"])
