"""
Delegate Adapter — bridges OPC Worker Dispatcher to Hermes delegate_task.

This adapter exists so OPC-Hermes can be tested without requiring a full
Hermes Agent runtime. In production, it wraps the real ``delegate_task``
from Hermes' ``tools/delegate_tool.py``. In tests, it can be replaced
with a fake that returns predetermined results.

Design:
  - ``set_adapter(adapter)`` — global swap for testing
  - ``get_adapter()`` — returns current adapter (lazy-inits to real on first call)
  - ``DelegateResult`` — standardized result shape regardless of backend
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DelegateResult:
    """Standardized result from a delegate_task call."""
    task_id: str
    worker_id: str
    status: str                     # "completed" | "failed" | "timeout" | "cancelled"
    output: str = ""
    error: str = ""
    tool_calls: int = 0
    duration_ms: float = 0.0
    model_used: str = ""
    raw_result: Optional[Dict[str, Any]] = None  # original result for debugging

    def is_success(self) -> bool:
        return self.status == "completed"


@dataclass
class DelegateRequest:
    """Standardized request to delegate_task."""
    task_id: str
    worker_id: str
    prompt: str                        # the worker's task prompt
    system_prompt: str = ""            # rendered from worker template
    provider: str = ""                 # provider override ("" = inherit)
    model: str = ""                    # model override ("" = use worker default)
    toolsets: Optional[List[str]] = None
    max_iterations: int = 60
    timeout_seconds: int = 600
    context: Optional[str] = None      # upstream summaries (rendered)
    parent_agent: Any = None           # the Hermes AIAgent instance (for real delegate)
    extra_kwargs: Dict[str, Any] = field(default_factory=dict)


# ── Adapter protocol ─────────────────────────────────────────────────────

AdapterFn = Callable[[DelegateRequest], DelegateResult]

_adapter: Optional[AdapterFn] = None


def set_adapter(adapter: AdapterFn) -> None:
    """Replace the global delegate adapter (for testing)."""
    global _adapter
    _adapter = adapter


def reset_adapter() -> None:
    """Reset to default (lazy-init real delegate)."""
    global _adapter
    _adapter = None


def get_adapter() -> AdapterFn:
    """Return the current delegate adapter, lazy-initializing to real."""
    global _adapter
    if _adapter is None:
        _adapter = _build_real_adapter()
    return _adapter


def delegate(request: DelegateRequest) -> DelegateResult:
    """Execute a single Worker task through the configured adapter."""
    adapter = get_adapter()
    t0 = time.monotonic()
    try:
        result = adapter(request)
    except Exception as exc:
        logger.exception("Delegate adapter raised: %s", exc)
        return DelegateResult(
            task_id=request.task_id,
            worker_id=request.worker_id,
            status="failed",
            error=f"Delegate adapter error: {exc}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
    # Ensure duration is set
    if result.duration_ms == 0.0:
        result.duration_ms = (time.monotonic() - t0) * 1000
    return result


# ── Real adapter (Hermes delegate_task) ──────────────────────────────────

def _build_real_adapter() -> AdapterFn:
    """Build an adapter that calls the real Hermes delegate_task tool.

    The import is deferred so tests can set a fake adapter without ever
    importing Hermes internals.
    """
    try:
        from tools.delegate_tool import delegate_task as _real_delegate

        def _real_adapter(request: DelegateRequest) -> DelegateResult:
            t0 = time.monotonic()
            parent = getattr(request, 'parent_agent', None)
            try:
                raw = _real_delegate(
                    goal=request.prompt,
                    role="leaf",
                    context=request.context or None,
                    toolsets=request.toolsets,
                    provider=request.provider or None,
                    model=request.model or None,
                    max_iterations=request.max_iterations,
                    parent_agent=parent,
                )
                duration = (time.monotonic() - t0) * 1000
                if isinstance(raw, dict):
                    return DelegateResult(
                        task_id=request.task_id,
                        worker_id=request.worker_id,
                        status="completed" if raw.get("success") else "failed",
                        output=raw.get("output", raw.get("result", "")),
                        error=raw.get("error", ""),
                        tool_calls=raw.get("tool_calls", 0),
                        duration_ms=duration,
                        model_used=raw.get("model", request.model),
                        raw_result=raw,
                    )
                return DelegateResult(
                    task_id=request.task_id,
                    worker_id=request.worker_id,
                    status="completed",
                    output=str(raw),
                    duration_ms=duration,
                    model_used=request.model,
                )
            except Exception as exc:
                duration = (time.monotonic() - t0) * 1000
                return DelegateResult(
                    task_id=request.task_id,
                    worker_id=request.worker_id,
                    status="failed",
                    error=f"{type(exc).__name__}: {exc}",
                    duration_ms=duration,
                )

        return _real_adapter

    except ImportError:
        logger.warning(
            "Could not import tools.delegate_tool. "
            "Delegate adapter will fail until a real or fake adapter is set."
        )

        def _unavailable_adapter(request: DelegateRequest) -> DelegateResult:
            return DelegateResult(
                task_id=request.task_id,
                worker_id=request.worker_id,
                status="failed",
                error="Hermes delegate_task is not available. Set a fake adapter for testing.",
            )

        return _unavailable_adapter


# ── Test helper: build a fake adapter from a mapping ─────────────────────

def build_fake_adapter(
    responses: Optional[Dict[str, DelegateResult]] = None,
    *,
    default_result: Optional[DelegateResult] = None,
) -> AdapterFn:
    """Build a fake adapter for testing.

    Args:
        responses: Mapping from ``(task_id, worker_id)`` → DelegateResult.
        default_result: Fallback result when no mapping matches.

    Returns:
        A callable suitable for ``set_adapter()``.
    """
    mapping = dict(responses or {})
    fallback = default_result or DelegateResult(
        task_id="unknown",
        worker_id="unknown",
        status="completed",
        output="[fake delegate output]",
    )

    def _fake_adapter(request: DelegateRequest) -> DelegateResult:
        key = (request.task_id, request.worker_id)
        if key in mapping:
            result = mapping[key]
            # Override task_id/worker_id on the stored result
            result.task_id = request.task_id
            result.worker_id = request.worker_id
            return result
        return DelegateResult(
            task_id=request.task_id,
            worker_id=request.worker_id,
            status=fallback.status,
            output=f"[fake] {request.worker_id}: {request.prompt[:100]}",
            model_used=request.model or "fake-model",
            tool_calls=3,
        )

    return _fake_adapter
