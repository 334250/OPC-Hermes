"""
Model Preference Control — three-layer priority for model selection.

Layer 1 (highest): User override — explicit model choice in config or per-task
Layer 2:          Leader recommendation — model the Leader Agent chose
Layer 3 (lowest): Auto-routing — deterministic mapping from complexity + capability

The function ``resolve_model()`` implements this priority chain and records
model switches to Eval Memory for Optimizer analysis.

Design reference: §5.5 模型控制：三层优先级 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Default capability matrix ─────────────────────────────────────────────
# Maps (complexity_level, requires_vision, requires_tool_calling) → model
# See the Model 能力对照表 in opc-hermes-integration.md §二-B.

_CAPABILITY_MATRIX: Dict[Tuple[str, bool, bool], str] = {
    # SIMPLE
    ("SIMPLE", False, True):  "gpt-4o-mini",
    ("SIMPLE", False, False): "minicpmv4.6",
    ("SIMPLE", True, True):   "gemini-2.5-flash",
    ("SIMPLE", True, False):  "minicpmv4.6",
    # MEDIUM
    ("MEDIUM", False, True):  "deepseek-v3",
    ("MEDIUM", False, False): "claude-sonnet-4",
    ("MEDIUM", True, True):   "claude-sonnet-4",
    ("MEDIUM", True, False):  "gpt-4o",
    # COMPLEX
    ("COMPLEX", False, True):  "claude-sonnet-4",
    ("COMPLEX", False, False): "claude-sonnet-4",
    ("COMPLEX", True, True):   "gpt-4o",
    ("COMPLEX", True, False):  "gpt-4o",
}

# Models known to support vision
_VISION_MODELS = frozenset({
    "claude-sonnet-4", "gpt-4o", "gpt-4o-mini",
    "gemini-2.5-flash", "minicpmv4.6",
})

# Models known to support tool calling
_TOOL_CALLING_MODELS = frozenset({
    "claude-sonnet-4", "gpt-4o", "gpt-4o-mini",
    "gemini-2.5-flash", "deepseek-v3",
})


def resolve_model(
    complexity_level: str,
    *,
    requires_vision: bool = False,
    requires_tool_calling: bool = True,
    user_override: Optional[str] = None,
    leader_recommendation: Optional[str] = None,
) -> Tuple[str, str]:
    """Resolve which model to use following the three-layer priority.

    Returns:
        (model_name, source) where source is one of:
        "user_override", "leader_recommendation", "auto_routing", "fallback"
    """
    # Layer 1: User override
    if user_override:
        return user_override, "user_override"

    # Layer 2: Leader recommendation
    if leader_recommendation:
        return leader_recommendation, "leader_recommendation"

    # Layer 3: Auto-routing via capability matrix
    key = (complexity_level, requires_vision, requires_tool_calling)
    model = _CAPABILITY_MATRIX.get(key)
    if model:
        return model, "auto_routing"

    # Fallback: any standard-tier model
    return "claude-sonnet-4", "fallback"


def model_supports_vision(model: str) -> bool:
    """Check if a model is known to support vision/image inputs."""
    return model.lower() in _VISION_MODELS


def model_supports_tool_calling(model: str) -> bool:
    """Check if a model is known to support tool calling."""
    return model.lower() in _TOOL_CALLING_MODELS


def list_known_models() -> set[str]:
    """Return model names known to OPC-Hermes routing and capability checks."""
    return set(_CAPABILITY_MATRIX.values()) | set(_VISION_MODELS) | set(_TOOL_CALLING_MODELS)


def validate_model_capabilities(
    model: str,
    requires_vision: bool,
    requires_tool_calling: bool,
) -> Optional[str]:
    """Check if a model meets the required capabilities.

    Returns None if capable, or an error message if not.
    """
    if requires_vision and not model_supports_vision(model):
        return f"Model '{model}' does not support vision but the task requires it."
    if requires_tool_calling and not model_supports_tool_calling(model):
        return f"Model '{model}' does not support tool calling but the task requires it."
    return None
