"""
OPC Evaluator Agent

A specialized Hermes Agent instance that evaluates Worker output quality.
Runs with READ-ONLY access to Project Memory and writes ONLY to Eval Memory.

Phase 3 additions:
  - LocalEvaluator: rule-based scoring engine (no LLM dependency)
  - Trigger integration: called from worker_dispatcher after step completion
  - Score rubric v1: heuristics on output length, structure, tool calls
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
5. **leader_decomposition** (Leader only) — How well did the Leader break down the task?

## Rules

- Score honestly — inflated scores prevent the Optimizer from finding real issues.
- If the Worker failed (status='failed'), all scores should be 0.0.
- Write ONLY to Eval Memory — never modify Project Memory.
"""


# ── Evaluator Config ─────────────────────────────────────────────────────

@dataclass
class EvaluatorConfig:
    """Configuration for spawning an Evaluator agent instance."""
    model: str = "claude-sonnet-4"
    toolsets: List[str] = field(default_factory=lambda: ["opc-core", "opc-evaluator", "read_file"])
    system_prompt: str = EVALUATOR_SYSTEM_PROMPT
    max_iterations: int = 30
    quiet_mode: bool = True


# ══════════════════════════════════════════════════════════════════════════
# Local Evaluator (rule-based, no LLM needed)
# ══════════════════════════════════════════════════════════════════════════

class LocalEvaluator:
    """Rule-based evaluator that scores Worker outputs without an LLM call.

    This is the Phase 3 pragmatic path — uses heuristics to produce
    meaningful scores that the Optimizer can consume.  Full LLM-based
    evaluation is deferred to Phase 4+ once the scoring dimensions are
    validated against real data.

    Scoring heuristics:
      - quality:      output length, structure (headings/code blocks), keyword density
      - relevance:    keyword overlap between task prompt and output
      - completeness: presence of expected sections, file references
      - efficiency:   tool-call count vs output size ratio
      - leader_decomposition: step count reasonableness (Leader only)
    """

    # Weights for each dimension
    DIMENSION_WEIGHTS = {
        "quality": 1.0,
        "relevance": 1.0,
        "completeness": 1.0,
        "efficiency": 1.0,
        "leader_decomposition": 0.5,  # only for Leader
    }

    # Minimum scores for different output quality levels
    MIN_OUTPUT_LENGTH_SHORT = 100    # chars
    MIN_OUTPUT_LENGTH_GOOD = 500
    MIN_OUTPUT_LENGTH_EXCELLENT = 2000

    def evaluate(
        self,
        task_id: str,
        worker_id: str,
        task_prompt: str,
        output: str,
        expected_format: str = "",
        tool_calls: int = 0,
        status: str = "completed",
        is_leader: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate a Worker's output and return scores + notes.

        Args:
            task_id: Task identifier.
            worker_id: Worker that produced the output.
            task_prompt: The original task prompt.
            output: Worker's output text.
            expected_format: Expected output format hint.
            tool_calls: Number of tool calls made.
            status: "completed" | "failed" | "timeout".
            is_leader: Whether this worker is the Leader (adds leader_decomposition).

        Returns:
            Dict with scores, notes, and structured evaluation.
        """
        if status != "completed":
            return self._failed_evaluation(task_id, worker_id, status)

        scores = {
            "quality": self._score_quality(output),
            "relevance": self._score_relevance(task_prompt, output),
            "completeness": self._score_completeness(output, expected_format),
            "efficiency": self._score_efficiency(output, tool_calls),
        }

        if is_leader:
            scores["leader_decomposition"] = self._score_leader_decomposition(output)

        notes = self._generate_notes(scores, output, tool_calls)

        return {
            "task_id": task_id,
            "worker_id": worker_id,
            "scores": {k: round(v, 2) for k, v in scores.items()},
            "notes": notes,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "evaluator_type": "local_rules_v1",
        }

    def evaluate_and_write(
        self,
        task_id: str,
        worker_id: str,
        task_prompt: str,
        output: str,
        expected_format: str = "",
        tool_calls: int = 0,
        status: str = "completed",
        is_leader: bool = False,
    ) -> Dict[str, Any]:
        """Evaluate and write the result to Eval Memory + update registry."""
        result = self.evaluate(
            task_id, worker_id, task_prompt, output,
            expected_format, tool_calls, status, is_leader,
        )

        # Write to Eval Memory
        memory = get_memory_layer()
        evaluation = EvaluationRecord(
            task_id=task_id,
            worker_id=worker_id,
            evaluator_id="local_rules_v1",
            scores=result["scores"],
            notes=result["notes"],
            evaluated_at=result["evaluated_at"],
        )
        memory.write_evaluation(evaluation)

        # Update Agent Registry score
        try:
            from opc_hermes.agent_list.registry import get_registry
            scores = result["scores"]
            avg = sum(scores.values()) / max(len(scores), 1)
            get_registry().update_score(worker_id, round(avg, 2))
        except Exception:
            logger.debug("Could not update registry score for %s", worker_id)

        return result

    # ── Scoring heuristics ───────────────────────────────────────────────

    def _score_quality(self, output: str) -> float:
        """Score output quality based on length, structure, and formatting."""
        if not output:
            return 0.0

        score = 0.5  # baseline

        # Length bonus
        length = len(output)
        if length >= self.MIN_OUTPUT_LENGTH_EXCELLENT:
            score += 0.3
        elif length >= self.MIN_OUTPUT_LENGTH_GOOD:
            score += 0.2
        elif length >= self.MIN_OUTPUT_LENGTH_SHORT:
            score += 0.1

        # Structure bonus: has headings
        if re.search(r'^#{1,4}\s+', output, re.MULTILINE):
            score += 0.1

        # Structure bonus: has code blocks (indicates structured output)
        if '```' in output:
            score += 0.05

        # Structure bonus: has lists
        if re.search(r'^[-*•]\s+', output, re.MULTILINE):
            score += 0.05

        return min(score, 1.0)

    def _score_relevance(self, task_prompt: str, output: str) -> float:
        """Score relevance via keyword overlap between prompt and output."""
        if not task_prompt or not output:
            return 0.3

        # Extract meaningful keywords from prompt (words >= 4 chars, non-stopwords)
        prompt_words = set(
            w.lower().strip(".,;:!?()[]{}") for w in task_prompt.split()
            if len(w) >= 4 and w.lower() not in _STOPWORDS
        )
        if not prompt_words:
            return 0.5

        output_lower = output.lower()
        hits = sum(1 for w in prompt_words if w in output_lower)
        ratio = hits / len(prompt_words)

        if ratio >= 0.7:
            return 0.9
        elif ratio >= 0.4:
            return 0.7
        elif ratio >= 0.2:
            return 0.5
        return 0.3

    def _score_completeness(self, output: str, expected_format: str) -> float:
        """Score completeness: check for expected elements."""
        if not output:
            return 0.0

        score = 0.6  # baseline

        # Check for common expected elements
        if "saved" in output.lower() or "wrote" in output.lower() or "generated" in output.lower():
            score += 0.1
        if re.search(r'\.(?:pptx|docx|pdf|png|jpg|html|json|md|py)\b', output, re.IGNORECASE):
            score += 0.1
        if expected_format and expected_format.lower() in output.lower():
            score += 0.1
        # Has a conclusion or summary section
        if re.search(r'(?:conclusion|summary|总结|结论)', output, re.IGNORECASE):
            score += 0.1

        return min(score, 1.0)

    def _score_efficiency(self, output: str, tool_calls: int) -> float:
        """Score efficiency: tool calls vs output complexity."""
        if tool_calls == 0:
            return 0.5  # can't judge without data

        length = len(output)
        # Ideal: ~100-500 chars per tool call for complex work
        chars_per_call = length / max(tool_calls, 1)

        if 100 <= chars_per_call <= 500:
            return 0.9
        elif chars_per_call < 50:
            return 0.4  # too many calls for little output
        elif chars_per_call > 2000:
            return 0.7  # few calls, lots of output (may be pre-computed)
        return 0.6

    def _score_leader_decomposition(self, output: str) -> float:
        """Score Leader's task decomposition quality."""
        if not output:
            return 0.3

        score = 0.5
        # Check for plan elements
        if re.search(r'(?:plan|计划|steps?|steps?|DAG)', output, re.IGNORECASE):
            score += 0.15
        if re.search(r'(?:worker|agent)\s*[-:]\s*', output, re.IGNORECASE):
            score += 0.15
        if re.search(r'(?:upstream|dependency|依赖|上游)', output, re.IGNORECASE):
            score += 0.1
        if re.search(r'(?:complexity|SIMPLE|MEDIUM|COMPLEX)', output):
            score += 0.1

        return min(score, 1.0)

    def _failed_evaluation(self, task_id: str, worker_id: str, status: str) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "worker_id": worker_id,
            "scores": {
                "quality": 0.0,
                "relevance": 0.0,
                "completeness": 0.0,
                "efficiency": 0.0,
            },
            "notes": f"Worker {status} — all scores set to 0.0.",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "evaluator_type": "local_rules_v1",
        }

    def _generate_notes(self, scores: Dict[str, float], output: str, tool_calls: int) -> str:
        parts = []
        avg = sum(scores.values()) / max(len(scores), 1)

        if avg >= 0.8:
            parts.append("Overall: excellent output.")
        elif avg >= 0.6:
            parts.append("Overall: good output, minor improvements possible.")
        elif avg >= 0.4:
            parts.append("Overall: acceptable, consider improving.")
        else:
            parts.append("Overall: below threshold — review recommended.")

        if scores.get("quality", 0) < 0.6:
            parts.append("Quality: output is short or lacks structure.")
        if scores.get("relevance", 0) < 0.5:
            parts.append("Relevance: output may not fully address the task prompt.")
        if scores.get("completeness", 0) < 0.6:
            parts.append("Completeness: expected deliverables may be missing.")
        if tool_calls > 20:
            parts.append(f"Efficiency: high tool-call count ({tool_calls}) for output length ({len(output)} chars).")

        return " ".join(parts)


# ── Stopwords for relevance scoring ──────────────────────────────────────

_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "your", "have",
    "are", "was", "will", "what", "when", "where", "which", "about",
    "into", "than", "then", "them", "they", "their", "just", "also",
    "very", "much", "such", "been", "being", "does", "each", "over",
    "under", "after", "before", "between", "through", "during", "above",
    "below", "这里", "这个", "那个", "什么", "怎么", "如何", "可以",
    "需要", "应该", "能够", "已经", "这些", "那些", "不是", "还是",
})


# ══════════════════════════════════════════════════════════════════════════
# Tool Schemas (for LLM-based evaluator in Phase 4+)
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
            "task_id": {"type": "string"},
            "worker_id": {"type": "string"},
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
            "notes": {"type": "string"},
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

    scores = {
        "quality": round(quality, 2),
        "relevance": round(relevance, 2),
        "completeness": round(completeness, 2),
        "efficiency": round(efficiency, 2),
        "leader_decomposition": round(leader_decomposition, 2),
    }
    evaluation = EvaluationRecord(
        task_id=task_id,
        worker_id=worker_id,
        evaluator_id="evaluator",
        scores=scores,
        notes=notes,
    )
    memory.write_evaluation(evaluation)

    try:
        from opc_hermes.agent_list.registry import get_registry
        avg_score = sum(scores.values()) / max(len(scores), 1)
        get_registry().update_score(worker_id, round(avg_score, 2))
    except Exception:
        pass

    return json.dumps({"status": "written", "scores": scores, "message": f"Evaluation written for {worker_id}."})


def score_output(
    task_id: str, worker_id: str,
    quality: float = 0.0, relevance: float = 0.0,
    completeness: float = 0.0, efficiency: float = 0.0,
    leader_decomposition: float = 0.0,
    notes: str = "",
    task_id_internal: Optional[str] = None,
) -> str:
    """Return a normalized score payload without writing Eval Memory."""
    _require_evaluator_context(task_id, task_id_internal)
    return json.dumps({
        "task_id": task_id, "worker_id": worker_id,
        "scores": {
            "quality": round(quality, 2), "relevance": round(relevance, 2),
            "completeness": round(completeness, 2), "efficiency": round(efficiency, 2),
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
                name=name, handler=_make_handler(handler),
                schema=schema, toolset="opc-evaluator",
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
