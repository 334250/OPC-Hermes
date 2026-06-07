"""
Complexity Rater — shared Skill that classifies task difficulty.

Registered as a Hermes Agent Tool so the Leader Agent can call it
before routing a task to workers.  Uses the cheapest available model
to minimize routing overhead.

Design principle (§5.1 of the architecture doc):
  Complexity is a Skill, not every agent's embedded logic.
  It's a reusable, independently-evolvable shared capability.

Output: {level, confidence, reasoning, recommended_model_tier}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Complexity levels ────────────────────────────────────────────────────
# Mirrors §5.2 of opc-hermes-design-v3.0.md

SIMPLE = "SIMPLE"
MEDIUM = "MEDIUM"
COMPLEX = "COMPLEX"

COMPLEXITY_LEVELS = (SIMPLE, MEDIUM, COMPLEX)

# ── Rule-based pre-filter ────────────────────────────────────────────────
# Fast path before calling an LLM: simple heuristics catch obvious cases.
# These rules are intentionally conservative — they only classify as SIMPLE
# or COMPLEX when the answer is unambiguous; ambiguous cases fall through
# to LLM-based rating.

_SIMPLE_PATTERNS = [
    "translate", "翻译", "summarize", "摘要", "summarise",
    "format", "格式化", "what is", "什么是", "define", "定义",
    "convert", "转换", "list", "列出",
]

_COMPLEX_PATTERNS = [
    "full-stack", "full stack", "全栈",
    "end-to-end", "端到端", "e2e",
    "research and write", "调研并撰写",
    "design and implement", "设计并实现",
    "从零开始", "from scratch",
    "multi-agent", "multi agent", "多智能体",
    "migrate", "迁移",
    "comprehensive", "全面", "完整系统",
    "production-ready", "生产级",
    "CI/CD", "pipeline",
]

# ── Model tier mapping ───────────────────────────────────────────────────
# Maps complexity levels to recommended model tiers.
# See §5.5 of the design doc for the full capability matrix.

_DEFAULT_MODEL_TIER: Dict[str, str] = {
    SIMPLE: "budget",    # gpt-4o-mini, gemini-2.5-flash, minicpmv4.6
    MEDIUM: "standard",  # claude-sonnet-4, gpt-4o, deepseek-v3
    COMPLEX: "premium",  # claude-sonnet-4, gpt-4o (best available)
}


# ── Tool schema ──────────────────────────────────────────────────────────

COMPLEXITY_RATER_SCHEMA = {
    "name": "complexity_rater",
    "description": (
        "Classify a task's complexity as SIMPLE, MEDIUM, or COMPLEX. "
        "SIMPLE = single-step, one tool, no coordination. "
        "MEDIUM = multi-step, 2-4 tools, moderate coordination. "
        "COMPLEX = many steps, parallel workers, cross-domain, "
        "requires plan generation and DAG orchestration. "
        "Call this BEFORE routing a task to workers — the result "
        "determines model selection and delegation strategy."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task_text": {
                "type": "string",
                "description": "The full user task description to rate.",
            },
            "agent_id": {
                "type": "string",
                "description": "Optional: the ID of the worker agent being rated (for scoring history).",
            },
            "criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of criteria dimensions to evaluate. "
                    "Defaults to ['steps', 'coordination', 'domain_scope', 'tool_count']. "
                    "Available: steps, coordination, domain_scope, tool_count, "
                    "ambiguity, safety_risk, context_size."
                ),
            },
        },
        "required": ["task_text"],
    },
}


# ── Core rating logic ────────────────────────────────────────────────────

def rate_complexity(
    task_text: str,
    agent_id: Optional[str] = None,
    criteria: Optional[list] = None,
    task_id: Optional[str] = None,
) -> str:
    """Rate a task's complexity.

    Called as a Hermes tool handler. The registry auto-wraps this
    function with argument parsing and JSON-serialization.

    Returns a JSON string with {level, confidence, reasoning, recommended_model_tier}.
    """
    if not task_text or not task_text.strip():
        return json.dumps({
            "level": SIMPLE,
            "confidence": 0.0,
            "reasoning": "Empty task — defaulting to SIMPLE.",
            "recommended_model_tier": _DEFAULT_MODEL_TIER[SIMPLE],
        })

    task_lower = task_text.lower().strip()

    # ── Rule-based pre-filter ────────────────────────────────────────────
    # Check for unambiguous SIMPLE patterns
    simple_hits = sum(1 for p in _SIMPLE_PATTERNS if p in task_lower)
    complex_hits = sum(1 for p in _COMPLEX_PATTERNS if p in task_lower)

    if simple_hits >= 2 and complex_hits == 0:
        return _build_result(SIMPLE, 0.85, "Multiple SIMPLE-indicator keywords matched.")

    if complex_hits >= 2:
        return _build_result(COMPLEX, 0.80, "Multiple COMPLEX-indicator keywords matched.")

    # ── Length-based heuristic ───────────────────────────────────────────
    if len(task_text) < 50:
        return _build_result(SIMPLE, 0.70, "Very short task — likely SIMPLE.")

    if len(task_text) > 800:
        return _build_result(COMPLEX, 0.65, "Very long task description — likely COMPLEX.")

    # ── Fallback: LLM-based rating ───────────────────────────────────────
    # In Phase 1, we use heuristics-only. The LLM-rating path calls
    # the cheapest configured model (gpt-4o-mini or equivalent) and
    # is implemented in Phase 2 once the auxiliary_client integration
    # is validated.
    return _build_result(MEDIUM, 0.50, "No strong signal — defaulting to MEDIUM. LLM rating in Phase 2.")


def _build_result(level: str, confidence: float, reasoning: str) -> str:
    """Serialize a complexity rating result to JSON."""
    return json.dumps({
        "level": level,
        "confidence": round(confidence, 2),
        "reasoning": reasoning,
        "recommended_model_tier": _DEFAULT_MODEL_TIER[level],
    })


# ── Plugin registration ──────────────────────────────────────────────────

def register(ctx: Any) -> None:
    """Register the complexity_rater tool into the given plugin context.

    Called by opc_hermes.plugin._register_tools().
    """
    ctx.register_tool(
        name="complexity_rater",
        handler=lambda args, **kw: rate_complexity(
            task_text=args.get("task_text", ""),
            agent_id=args.get("agent_id"),
            criteria=args.get("criteria"),
            task_id=kw.get("task_id"),
        ),
        schema=COMPLEXITY_RATER_SCHEMA,
        toolset="opc-core",
    )
    logger.info("Registered OPC tool: complexity_rater")


# ── Standalone usage ─────────────────────────────────────────────────────

def check_requirements() -> bool:
    """Complexity rater works without any external API keys (rule-based path)."""
    return True
