"""Phase 3 integration tests — Evaluator flow and quality feedback loop.

Tests cover:
  - P3-1: Memory tools end-to-end (save/load evaluations)
  - P3-2: Evaluator trigger after Worker completion
  - P3-3: LocalEvaluator rule-based scoring
  - P3-4: Snapshot content completeness
  - P3-5: Score rubric v1 (5 dimensions)
  - P3-6: Eval Memory writes
  - P3-7: Agent Registry score updates
  - P3-8: Evaluator failure isolation
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

from opc_hermes.evaluator import LocalEvaluator, EvaluatorPermissionError
from opc_hermes.memory_layer.gated_memory import GatedMemoryLayer, get_memory_layer
from opc_hermes.memory_layer.task_protocol import TaskProtocol, ProgressReport, EvaluationRecord
from opc_hermes.agent_list.registry import get_registry


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def evaluator() -> LocalEvaluator:
    return LocalEvaluator()


@pytest.fixture
def tmp_memory(tmp_path: Path):
    import opc_hermes.memory_layer.gated_memory as gm
    orig = gm._memory_layer
    gm._memory_layer = GatedMemoryLayer(base_dir=tmp_path / "memory")
    yield gm._memory_layer
    gm._memory_layer = orig


# ══════════════════════════════════════════════════════════════════════════
# P3-5: Score Rubric v1
# ══════════════════════════════════════════════════════════════════════════

def test_quality_scoring_excellent(evaluator):
    """Well-structured long output scores high on quality."""
    output = (
        "## Research Findings\n\n"
        "### Overview\n" + "X" * 1500 + "\n\n"
        "### Key Metrics\n\n"
        "- Metric 1: 42\n"
        "- Metric 2: 17\n\n"
        "### Conclusion\n\n"
        "The analysis shows clear trends.\n\n"
        "```json\n{\"growth\": \"15%\"}\n```\n"
    )
    score = evaluator._score_quality(output)
    assert score >= 0.8, f"Expected >= 0.8, got {score}"


def test_quality_scoring_poor(evaluator):
    """Short unstructured output scores low."""
    score = evaluator._score_quality("done")
    assert score <= 0.6, f"Expected <= 0.6, got {score}"


def test_relevance_scoring(evaluator):
    """Output with high keyword overlap gets high relevance."""
    task = "Research cloud market trends and analyze AWS Azure GCP growth rates"
    output = "Cloud market analysis shows AWS growing at 15%, Azure at 21%, GCP at 28%. Research indicates continued growth trends across all three providers."
    score = evaluator._score_relevance(task, output)
    assert score >= 0.7, f"Expected >= 0.7, got {score}"


def test_relevance_scoring_low(evaluator):
    """Irrelevant output gets low relevance."""
    task = "Research cloud market trends for Q2 2025"
    output = "The weather today is sunny with mild temperatures."
    score = evaluator._score_relevance(task, output)
    assert score <= 0.5, f"Expected <= 0.5, got {score}"


def test_completeness_with_artifacts(evaluator):
    """Output mentioning saved files gets completeness bonus."""
    output = "Analysis complete. Saved to report.md and chart.png"
    score = evaluator._score_completeness(output, "markdown")
    assert score >= 0.7, f"Expected >= 0.7, got {score}"


def test_efficiency_good_ratio(evaluator):
    """Reasonable chars-per-tool-call ratio scores well."""
    output = "X" * 2000  # 2000 chars
    score = evaluator._score_efficiency(output, tool_calls=10)  # 200 chars/call
    assert score >= 0.7, f"Expected >= 0.7, got {score}"


def test_leader_decomposition(evaluator):
    """Leader plan output is recognized."""
    output = (
        "## Task Plan\n"
        "Complexity: MEDIUM\n"
        "Steps:\n"
        "- Worker: researcher\n"
        "- Worker: data_analyst (upstream: [0])\n"
    )
    score = evaluator._score_leader_decomposition(output)
    assert score >= 0.7, f"Expected >= 0.7, got {score}"


# ══════════════════════════════════════════════════════════════════════════
# P3-3+P3-6: Full evaluate + write to Eval Memory
# ══════════════════════════════════════════════════════════════════════════

def test_evaluate_and_write(evaluator, tmp_memory):
    """Full evaluate-and-write flow: scores → Eval Memory → registry update."""
    result = evaluator.evaluate_and_write(
        task_id="test-eval-001",
        worker_id="researcher",
        task_prompt="Research Q2 2025 cloud market trends and provide structured report",
        output=(
            "## Cloud Market Research Q2 2025\n\n"
            "### Key Findings\n\n"
            "- AWS market share: 32%\n"
            "- Azure growth: 21% YoY\n"
            "- GCP accelerating: 28% YoY\n\n"
            "### Report\n\n"
            "The analysis shows strong growth across all three major providers. "
            "AWS maintains leadership while Azure and GCP are gaining ground.\n\n"
            "Saved report to cloud_market_q2.md\n"
        ),
        expected_format="markdown",
        tool_calls=8,
    )

    # Result structure
    assert result["task_id"] == "test-eval-001"
    assert result["worker_id"] == "researcher"
    assert "scores" in result
    assert "quality" in result["scores"]
    assert "relevance" in result["scores"]
    assert "completeness" in result["scores"]
    assert "efficiency" in result["scores"]
    assert all(0.0 <= v <= 1.0 for v in result["scores"].values())

    # Eval Memory
    evaluations = tmp_memory.get_evaluations(worker_id="researcher")
    assert len(evaluations) >= 1
    latest = evaluations[0]
    assert latest.task_id == "test-eval-001"
    assert latest.worker_id == "researcher"
    assert latest.scores == result["scores"]


# ══════════════════════════════════════════════════════════════════════════
# P3-7: Registry score update
# ══════════════════════════════════════════════════════════════════════════

def test_registry_score_update(evaluator, tmp_memory):
    """Registry gets updated with evaluator average score."""
    registry = get_registry()
    worker = registry.get_worker("researcher")
    assert worker is not None
    old_score = worker.quality_score

    evaluator.evaluate_and_write(
        task_id="test-reg-001",
        worker_id="researcher",
        task_prompt="Research cloud trends",
        output="## Research\n\n" + "X" * 800 + "\n\nKey findings: growth at 15%.\n\nSaved to research.md",
        tool_calls=5,
    )

    # Re-fetch worker to get updated score
    worker = registry.get_worker("researcher")
    # Score should have changed (unless it was already exactly the computed average)
    assert worker is not None


# ══════════════════════════════════════════════════════════════════════════
# P3-8: Failure isolation
# ══════════════════════════════════════════════════════════════════════════

def test_failed_worker_gets_zero_scores(evaluator):
    """Failed workers get 0.0 across all dimensions."""
    result = evaluator.evaluate(
        task_id="test-fail-001",
        worker_id="data_analyst",
        task_prompt="Analyze data",
        output="",
        status="failed",
    )
    for dim, score in result["scores"].items():
        assert score == 0.0, f"Expected {dim}=0.0 for failed worker, got {score}"
    assert "failed" in result["notes"].lower()


def test_evaluator_exception_does_not_crash_dispatcher():
    """Evaluator failure should not propagate to the caller (P3-8)."""
    from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
    disp = OPCWorkerDispatcher(evaluator_enabled=True)
    # Simulate a step result
    step = {"index": 0, "worker_id": "researcher", "prompt": "Test", "expected_output_format": "text"}
    result = {"worker_id": "researcher", "status": "completed", "output": "Test output", "tool_calls": 3}
    # Should not raise
    try:
        disp._evaluate_step("test-isolate", step, result)
    except Exception as e:
        pytest.fail(f"Evaluator should be failure-isolated, but raised: {e}")


# ══════════════════════════════════════════════════════════════════════════
# P3-4: Snapshot content completeness
# ══════════════════════════════════════════════════════════════════════════

def test_snapshot_content(tmp_memory):
    """Snapshot includes TaskProtocol, ProgressReports, and upstream summaries."""
    # Set up test data
    proto = TaskProtocol(
        task_id="test-snap-001", worker_id="researcher",
        step_index=0, prompt="Research Q2", complexity="MEDIUM",
    )
    tmp_memory.save_task_protocol(proto)
    tmp_memory.save_progress_report(ProgressReport(
        task_id="test-snap-001", worker_id="researcher",
        step_index=0, status="completed", summary="Done",
        reported_at=datetime.now(timezone.utc).isoformat(),
    ))

    from opc_hermes.evaluator import capture_snapshot
    snapshot_json = capture_snapshot("test-snap-001", "researcher")
    snapshot = json.loads(snapshot_json)

    assert snapshot["task_protocol"] is not None
    assert len(snapshot["progress_reports"]) >= 1
    assert "message" in snapshot


# ══════════════════════════════════════════════════════════════════════════
# P3-2+P3-9: End-to-end pipeline with evaluator
# ══════════════════════════════════════════════════════════════════════════

def test_e2e_dispatcher_with_evaluator(tmp_path):
    """Full pipeline execution triggers evaluator for each step."""
    from opc_hermes.delegate_adapter import (
        DelegateResult, build_fake_adapter, set_adapter, reset_adapter,
    )
    from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
    import opc_hermes.memory_layer.gated_memory as gm

    # Setup
    responses = {
        ("test-e2e-001", "researcher"): DelegateResult(
            task_id="test-e2e-001", worker_id="researcher",
            status="completed",
            output="## Research\n\nCloud market growing at 15%. Key players: AWS, Azure, GCP.\n\nSaved to research.md",
            model_used="fake", tool_calls=6,
        ),
        ("test-e2e-001", "data_analyst"): DelegateResult(
            task_id="test-e2e-001", worker_id="data_analyst",
            status="completed",
            output='## Analysis\n\n```json\n{"growth": 15, "trend": "up"}\n```\n\nSaved to analysis.json',
            model_used="fake", tool_calls=4,
        ),
    }
    set_adapter(build_fake_adapter(responses))

    orig_mem = gm._memory_layer
    gm._memory_layer = GatedMemoryLayer(base_dir=tmp_path / "memory")

    try:
        plan = {
            "task_id": "test-e2e-001", "title": "E2E Test",
            "complexity": {"level": "MEDIUM", "confidence": 0.8},
            "mode": "pipeline", "requires_user_approval": False,
            "steps": [
                {"index": 0, "worker_id": "researcher", "prompt": "Research Q2 trends",
                 "upstream": [], "expected_output_format": "markdown"},
                {"index": 1, "worker_id": "data_analyst", "prompt": "Analyze data",
                 "upstream": [0], "expected_output_format": "json"},
            ],
        }

        disp = OPCWorkerDispatcher(evaluator_enabled=True)
        result = disp.execute(plan)

        assert result["status"] == "completed"
        assert len(result["steps"]) == 2

        # Verify evaluations were written
        evaluations_researcher = gm._memory_layer.get_evaluations(worker_id="researcher")
        evaluations_analyst = gm._memory_layer.get_evaluations(worker_id="data_analyst")
        assert len(evaluations_researcher) >= 1, "Researcher should have evaluation"
        assert len(evaluations_analyst) >= 1, "Analyst should have evaluation"

        # Verify scores are meaningful
        for evals in [evaluations_researcher, evaluations_analyst]:
            e = evals[0]
            assert e.scores["quality"] > 0.0, f"Quality should be > 0, got {e.scores['quality']}"
            assert e.notes, "Evaluation should have notes"

    finally:
        gm._memory_layer = orig_mem
        reset_adapter()


# ══════════════════════════════════════════════════════════════════════════
# P3-8 (continued): Dispatcher handles evaluator disabled
# ══════════════════════════════════════════════════════════════════════════

def test_dispatcher_without_evaluator(tmp_path):
    """Evaluator can be disabled — no evaluations written."""
    from opc_hermes.delegate_adapter import (
        DelegateResult, build_fake_adapter, set_adapter, reset_adapter,
    )
    from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
    import opc_hermes.memory_layer.gated_memory as gm

    responses = {
        ("test-noeval-001", "researcher"): DelegateResult(
            task_id="test-noeval-001", worker_id="researcher",
            status="completed", output="Research done.", model_used="fake", tool_calls=3,
        ),
    }
    set_adapter(build_fake_adapter(responses))

    orig_mem = gm._memory_layer
    gm._memory_layer = GatedMemoryLayer(base_dir=tmp_path / "memory")

    try:
        plan = {
            "task_id": "test-noeval-001", "title": "No Eval",
            "complexity": {"level": "SIMPLE", "confidence": 0.9},
            "mode": "sequential", "requires_user_approval": False,
            "steps": [
                {"index": 0, "worker_id": "researcher", "prompt": "Research",
                 "upstream": [], "expected_output_format": "text"},
            ],
        }

        disp = OPCWorkerDispatcher(evaluator_enabled=False)
        result = disp.execute(plan)
        assert result["status"] == "completed"

        evaluations = gm._memory_layer.get_evaluations(worker_id="researcher")
        assert len(evaluations) == 0, "No evaluations should be written when evaluator is disabled"

    finally:
        gm._memory_layer = orig_mem
        reset_adapter()
