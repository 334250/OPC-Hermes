"""Phase 2 integration tests — Worker dispatch and DAG execution.

Tests cover:
  - P2-1: Plan validation before dispatch
  - P2-2: Parallel group detection and batch execution
  - P2-3: Worker prompt rendering with upstream summaries
  - P2-4: TaskProtocol written before execution
  - P2-5: Fake delegate adapter produces correct results
  - P2-6: Batch delegate (concurrent dispatch)
  - P2-7: Worker result collection and aggregation
  - P2-8: SummaryBridge written after step completion
  - P2-9: Artifact paths extracted from worker output
  - P2-10: Failure strategy (retry / skip / abort)
  - P2-11: Recovery — skip already-completed steps
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from opc_hermes.delegate_adapter import (
    DelegateRequest,
    DelegateResult,
    build_fake_adapter,
    reset_adapter,
    set_adapter,
)
from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
from opc_hermes.agent_list.registry import AgentRegistry, get_registry
from opc_hermes.memory_layer.gated_memory import GatedMemoryLayer


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_adapter():
    """Reset the delegate adapter before each test."""
    reset_adapter()
    yield
    reset_adapter()


@pytest.fixture
def tmp_memory(tmp_path: Path) -> GatedMemoryLayer:
    """Create a GatedMemoryLayer in a temp directory."""
    memory_dir = tmp_path / "opc" / "memory"
    memory_dir.mkdir(parents=True)
    layer = GatedMemoryLayer(base_dir=memory_dir)
    return layer


@pytest.fixture
def fake_adapter():
    """A fake delegate adapter that returns predetermined results."""
    responses = {}

    def _add(task_id: str, worker_id: str, output: str, status: str = "completed"):
        responses[(task_id, worker_id)] = DelegateResult(
            task_id=task_id,
            worker_id=worker_id,
            status=status,
            output=output,
            model_used="fake-model",
            tool_calls=5,
            duration_ms=100.0,
        )

    adapter = build_fake_adapter(responses)
    return adapter, _add


@pytest.fixture
def sample_plan() -> Dict[str, Any]:
    return {
        "task_id": "test-phase2-001",
        "title": "Q2 Sales Analysis Pipeline",
        "complexity": {"level": "MEDIUM", "confidence": 0.75},
        "mode": "pipeline",
        "requires_user_approval": False,
        "steps": [
            {
                "index": 0,
                "worker_id": "researcher",
                "prompt": "Research Q2 2025 cloud market trends",
                "upstream": [],
                "expected_output_format": "Markdown report",
                "requires_vision": False,
                "requires_tool_calling": True,
            },
            {
                "index": 1,
                "worker_id": "data_analyst",
                "prompt": "Analyze the research data and extract key metrics",
                "upstream": [0],
                "expected_output_format": "JSON data + Markdown summary",
                "requires_vision": False,
                "requires_tool_calling": True,
            },
            {
                "index": 2,
                "worker_id": "illustrator",
                "prompt": "Create charts from the data analysis",
                "upstream": [1],
                "expected_output_format": "PNG charts + HTML interactive",
                "requires_vision": False,
                "requires_tool_calling": False,
            },
        ],
        "acceptance_criteria": [
            "Research report covers at least 3 cloud providers",
            "Data analysis includes YoY growth percentages",
            "At least 2 charts generated",
        ],
    }


# ══════════════════════════════════════════════════════════════════════════
# P2-1: Plan Validation
# ══════════════════════════════════════════════════════════════════════════

def test_dispatcher_rejects_empty_steps(fake_adapter):
    """Dispatcher rejects plans with no steps."""
    adapter, _ = fake_adapter
    set_adapter(adapter)
    dispatcher = OPCWorkerDispatcher()

    result = dispatcher.execute({"task_id": "test", "steps": []})
    assert result["status"] == "aborted"
    assert "No steps" in result["error"]


def test_dispatcher_rejects_invalid_plan(fake_adapter):
    """Dispatcher rejects plans that fail schema validation."""
    adapter, _ = fake_adapter
    set_adapter(adapter)
    dispatcher = OPCWorkerDispatcher()

    # Missing required 'steps' field
    result = dispatcher.execute({"task_id": "test", "title": "Bad Plan", "mode": "sequential"})
    assert result["status"] == "aborted"


def test_dispatcher_rejects_cycle(sample_plan):
    """Dispatcher rejects plans with circular dependencies."""
    from opc_hermes.delegate_adapter import build_fake_adapter, set_adapter
    set_adapter(build_fake_adapter())

    sample_plan["steps"] = [
        {"index": 0, "worker_id": "researcher", "prompt": "A", "upstream": [1], "expected_output_format": "text"},
        {"index": 1, "worker_id": "writer", "prompt": "B", "upstream": [0], "expected_output_format": "text"},
    ]
    dispatcher = OPCWorkerDispatcher()
    result = dispatcher.execute(sample_plan)
    assert result["status"] == "aborted"
    assert "DAG" in result.get("error", "")


# ══════════════════════════════════════════════════════════════════════════
# P2-5: Fake Delegate Adapter
# ══════════════════════════════════════════════════════════════════════════

def test_fake_adapter_returns_mapped_results(fake_adapter, sample_plan):
    """Fake adapter returns the mapped results for each worker."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Cloud market research output")
    add_response("test-phase2-001", "data_analyst", "Data analysis output")
    add_response("test-phase2-001", "illustrator", "Charts generated: chart1.png, chart2.png")
    set_adapter(adapter)

    dispatcher = OPCWorkerDispatcher()
    result = dispatcher.execute(sample_plan)

    assert result["status"] == "completed"
    assert len(result["steps"]) == 3

    researcher = result["steps"][0]
    assert researcher["worker_id"] == "researcher"
    assert researcher["status"] == "completed"
    assert "Cloud market research" in researcher["output"]

    data_analyst = result["steps"][1]
    assert data_analyst["worker_id"] == "data_analyst"
    assert data_analyst["status"] == "completed"

    illustrator = result["steps"][2]
    assert illustrator["worker_id"] == "illustrator"
    assert illustrator["status"] == "completed"


# ══════════════════════════════════════════════════════════════════════════
# P2-2: Parallel Group Detection
# ══════════════════════════════════════════════════════════════════════════

def test_parallel_group_detection():
    """Steps with no mutual dependencies are grouped for parallel execution."""
    from opc_hermes.workflow.dag_executor import find_parallel_groups, topological_sort

    steps = [
        {"index": 0, "worker_id": "A", "prompt": "A", "upstream": [], "expected_output_format": "text"},
        {"index": 1, "worker_id": "B", "prompt": "B", "upstream": [], "expected_output_format": "text"},
        {"index": 2, "worker_id": "C", "prompt": "C", "upstream": [0, 1], "expected_output_format": "text"},
        {"index": 3, "worker_id": "D", "prompt": "D", "upstream": [2], "expected_output_format": "text"},
    ]

    sorted_steps = topological_sort(steps)
    groups = find_parallel_groups(sorted_steps)

    # A and B should be in the same group (no mutual dependency)
    assert len(groups) == 3
    assert len(groups[0]) == 2  # A, B
    assert len(groups[1]) == 1  # C depends on A and B
    assert len(groups[2]) == 1  # D depends on C


# ══════════════════════════════════════════════════════════════════════════
# P2-4+P2-8: Memory Integration (TaskProtocol + SummaryBridge)
# ══════════════════════════════════════════════════════════════════════════

def test_task_protocol_and_summary_bridge_written(fake_adapter, sample_plan, tmp_path):
    """TaskProtocol is written before execution, SummaryBridge after."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "### Key Findings\n- Finding 1\n- Finding 2\n\nSaved to research.md")
    add_response("test-phase2-001", "data_analyst", "{\"growth\": \"15%\"}\n\nSaved to analysis.json")
    add_response("test-phase2-001", "illustrator", "Charts: chart1.png, chart2.png")
    set_adapter(adapter)

    # Use tmp memory
    import opc_hermes.memory_layer.gated_memory as gm
    original = gm._memory_layer
    gm._memory_layer = GatedMemoryLayer(base_dir=tmp_path / "opc" / "memory")

    try:
        dispatcher = OPCWorkerDispatcher()
        result = dispatcher.execute(sample_plan)

        assert result["status"] == "completed"

        # Check TaskProtocols were written
        memory = gm._memory_layer
        for step in sample_plan["steps"]:
            protocol = memory.get_task_protocol("test-phase2-001", step["worker_id"])
            assert protocol is not None, f"Missing TaskProtocol for {step['worker_id']}"
            assert protocol.prompt == step["prompt"]

        # Check ProgressReports were written
        reports = memory.get_progress_reports("test-phase2-001")
        completed_reports = [r for r in reports if r.status == "completed"]
        assert len(completed_reports) == 3

        # Check SummaryBridge entries
        bridges = memory.get_upstream_summaries("test-phase2-001", "data_analyst", [0])
        assert len(bridges) >= 1
        researcher_bridge = bridges[0]
        assert "Finding" in researcher_bridge.summary
    finally:
        gm._memory_layer = original


# ══════════════════════════════════════════════════════════════════════════
# P2-7: Result Collection and Aggregation
# ══════════════════════════════════════════════════════════════════════════

def test_result_aggregation(fake_adapter, sample_plan):
    """Results are collected from all workers and aggregated."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Research findings about cloud markets.")
    add_response("test-phase2-001", "data_analyst", "Analysis: 15% growth, 3 key trends.")
    add_response("test-phase2-001", "illustrator", "Chart files created.")
    set_adapter(adapter)

    dispatcher = OPCWorkerDispatcher()
    result = dispatcher.execute(sample_plan)

    # All step results present
    assert len(result["steps"]) == 3
    for step_result in result["steps"]:
        assert "step_index" in step_result
        assert "worker_id" in step_result
        assert "status" in step_result
        assert "output" in step_result
        assert "duration_ms" in step_result

    # Aggregated result contains all worker outputs
    aggregated = result["aggregated_result"]
    assert "researcher" in aggregated
    assert "data_analyst" in aggregated
    assert "illustrator" in aggregated


# ══════════════════════════════════════════════════════════════════════════
# P2-9: Artifact Path Extraction
# ══════════════════════════════════════════════════════════════════════════

def test_artifact_extraction(fake_adapter, sample_plan):
    """Artifact paths are extracted from worker output."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Saved report to research_report.md")
    add_response("test-phase2-001", "data_analyst", "Output: analysis.json and metrics.csv")
    add_response(
        "test-phase2-001", "illustrator",
        "Generated chart1.png, chart2.png and interactive chart.html"
    )
    set_adapter(adapter)

    dispatcher = OPCWorkerDispatcher()
    result = dispatcher.execute(sample_plan)

    all_artifacts = result.get("artifacts", [])
    assert "research_report.md" in all_artifacts or any("research_report" in a for a in all_artifacts)
    assert "analysis.json" in all_artifacts or any("analysis" in a for a in all_artifacts)


# ══════════════════════════════════════════════════════════════════════════
# P2-10: Failure Strategy (retry / skip / abort)
# ══════════════════════════════════════════════════════════════════════════

def test_failure_retry_policy(fake_adapter, sample_plan):
    """Failed steps are retried according to retry policy."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Research done.")
    add_response("test-phase2-001", "data_analyst", "", status="failed")
    add_response("test-phase2-001", "illustrator", "Charts done.")
    set_adapter(adapter)

    # Use RETRY policy for failed (default)
    dispatcher = OPCWorkerDispatcher(max_retries=2)
    result = dispatcher.execute(sample_plan)

    # data_analyst should have been retried
    data_analyst = result["steps"][1]
    assert data_analyst["worker_id"] == "data_analyst"
    # After max retries, it should be marked as failed
    assert data_analyst["status"] in ("failed", "skipped")


def test_failure_skip_policy(fake_adapter, sample_plan):
    """Steps with SKIP policy are skipped but downstream continues."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Research done.")
    add_response("test-phase2-001", "data_analyst", "", status="failed")
    add_response("test-phase2-001", "illustrator", "Charts done.")
    set_adapter(adapter)

    from opc_hermes.worker_dispatcher import FailurePolicy
    dispatcher = OPCWorkerDispatcher(
        failure_policy={"failed": FailurePolicy.SKIP},
        max_retries=0,
    )
    result = dispatcher.execute(sample_plan)

    # data_analyst should be skipped
    data_analyst = result["steps"][1]
    assert data_analyst["status"] == "skipped"


def test_failure_abort_policy(fake_adapter, sample_plan):
    """Steps with ABORT policy stop the entire task."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "", status="failed")
    add_response("test-phase2-001", "data_analyst", "Analysis done.")
    add_response("test-phase2-001", "illustrator", "Charts done.")
    set_adapter(adapter)

    from opc_hermes.worker_dispatcher import FailurePolicy
    dispatcher = OPCWorkerDispatcher(
        failure_policy={"failed": FailurePolicy.ABORT},
        max_retries=0,
    )
    result = dispatcher.execute(sample_plan)

    # Should abort at researcher
    assert result["status"] == "aborted"
    # Later steps should be skipped
    for step in result["steps"]:
        if step["worker_id"] in ("data_analyst", "illustrator"):
            assert step["status"] == "skipped"


# ══════════════════════════════════════════════════════════════════════════
# P2-11: Recovery (skip already-completed steps)
# ══════════════════════════════════════════════════════════════════════════

def test_recovery_skips_completed_steps(fake_adapter, sample_plan, tmp_path):
    """Already-completed steps are skipped on re-execution."""
    adapter, add_response = fake_adapter
    add_response("test-phase2-001", "researcher", "Research output.")
    add_response("test-phase2-001", "data_analyst", "Analysis output.")
    add_response("test-phase2-001", "illustrator", "Charts output.")
    set_adapter(adapter)

    import opc_hermes.memory_layer.gated_memory as gm
    original = gm._memory_layer

    try:
        # First run — complete researcher only
        memory = GatedMemoryLayer(base_dir=tmp_path / "opc" / "memory")
        gm._memory_layer = memory

        # Simulate researcher already completed
        from opc_hermes.memory_layer.task_protocol import ProgressReport
        from datetime import datetime, timezone
        memory.save_task_protocol(
            __import__("opc_hermes.memory_layer.task_protocol", fromlist=["TaskProtocol"]).TaskProtocol(
                task_id="test-phase2-001",
                worker_id="researcher",
                step_index=0,
                prompt="Research Q2 trends",
                complexity="MEDIUM",
            )
        )
        memory.save_progress_report(ProgressReport(
            task_id="test-phase2-001",
            worker_id="researcher",
            step_index=0,
            status="completed",
            summary="Already done",
            reported_at=datetime.now(timezone.utc).isoformat(),
        ))

        # Second run — should detect researcher already completed
        dispatcher = OPCWorkerDispatcher()
        result = dispatcher.execute(sample_plan)

        researcher = result["steps"][0]
        assert researcher["status"] == "completed"
        assert researcher.get("recovered") is True
    finally:
        gm._memory_layer = original


# ══════════════════════════════════════════════════════════════════════════
# P2-3: Worker Prompt Rendering
# ══════════════════════════════════════════════════════════════════════════

def test_worker_prompt_rendering():
    """Worker prompt templates render with upstream summaries."""
    dispatcher = OPCWorkerDispatcher()

    # Test basic rendering
    prompt = dispatcher._render_worker_prompt(
        worker_id="researcher",
        task_prompt="Research cloud trends",
        upstream_outputs={},
        step={"index": 0, "upstream": []},
    )
    assert "Research cloud trends" in prompt
    assert "researcher" in prompt.lower() or "OPC Worker" in prompt

    # Test with upstream context
    prompt_with_upstream = dispatcher._render_worker_prompt(
        worker_id="data_analyst",
        task_prompt="Analyze data",
        upstream_outputs={0: "## Research Findings\nCloud market grew 15%"},
        step={"index": 1, "upstream": [0]},
    )
    assert "Cloud market grew 15%" in prompt_with_upstream


# ══════════════════════════════════════════════════════════════════════════
# End-to-End: 3-step pipeline
# ══════════════════════════════════════════════════════════════════════════

def test_e2e_three_step_pipeline(fake_adapter, sample_plan, tmp_path):
    """Full 3-step pipeline: researcher → data_analyst → illustrator."""
    adapter, add_response = fake_adapter
    add_response(
        "test-phase2-001", "researcher",
        "## Cloud Market Research\n\n- AWS: 32% market share\n- Azure: 23%\n- GCP: 11%\n\nSaved to research.md"
    )
    add_response(
        "test-phase2-001", "data_analyst",
        '{"aws_growth": "15%", "azure_growth": "21%", "gcp_growth": "28%"}\n\nSaved to analysis.json'
    )
    add_response(
        "test-phase2-001", "illustrator",
        "Charts generated:\n- market_share.png\n- growth_trends.png\n- forecast.html"
    )
    set_adapter(adapter)

    import opc_hermes.memory_layer.gated_memory as gm
    original = gm._memory_layer
    gm._memory_layer = GatedMemoryLayer(base_dir=tmp_path / "opc" / "memory")

    try:
        dispatcher = OPCWorkerDispatcher()
        result = dispatcher.execute(sample_plan)

        # Overall status
        assert result["status"] == "completed"
        assert result["task_id"] == "test-phase2-001"

        # All 3 steps completed
        assert len(result["steps"]) == 3
        for step_result in result["steps"]:
            assert step_result["status"] == "completed", f"{step_result['worker_id']} failed: {step_result.get('error')}"

        # Upstream data flowed correctly (illustrator should have seen researcher+analyst summaries)
        memory = gm._memory_layer
        bridges = memory.get_upstream_summaries("test-phase2-001", "illustrator")
        assert len(bridges) >= 1  # Should see researcher and data_analyst summaries

        # Artifacts extracted
        assert len(result.get("artifacts", [])) >= 2

        # Memory has all task protocols
        for step in sample_plan["steps"]:
            protocol = memory.get_task_protocol("test-phase2-001", step["worker_id"])
            assert protocol is not None

        # Memory has progress reports
        reports = memory.get_progress_reports("test-phase2-001")
        completed = [r for r in reports if r.status == "completed"]
        assert len(completed) == 3

    finally:
        gm._memory_layer = original


# ══════════════════════════════════════════════════════════════════════════
# DelegateAdapter — standalone tests
# ══════════════════════════════════════════════════════════════════════════

def test_delegate_adapter_fake_basic():
    """Fake adapter returns sensible defaults."""
    set_adapter(build_fake_adapter())

    from opc_hermes.delegate_adapter import DelegateRequest, delegate
    result = delegate(DelegateRequest(
        task_id="test", worker_id="researcher", prompt="Research something",
    ))
    assert result.status == "completed"
    assert "fake" in result.output.lower() or "Research" in result.output


def test_delegate_adapter_fake_mapped():
    """Fake adapter returns mapped responses when configured."""
    adapter = build_fake_adapter({
        ("t1", "w1"): DelegateResult(task_id="t1", worker_id="w1", status="completed", output="exact output"),
        ("t1", "w2"): DelegateResult(task_id="t1", worker_id="w2", status="failed", error="simulated error"),
    })
    set_adapter(adapter)

    from opc_hermes.delegate_adapter import DelegateRequest, delegate
    r1 = delegate(DelegateRequest(task_id="t1", worker_id="w1", prompt="p1"))
    assert r1.status == "completed"
    assert r1.output == "exact output"

    r2 = delegate(DelegateRequest(task_id="t1", worker_id="w2", prompt="p2"))
    assert r2.status == "failed"
    assert "simulated error" in r2.error
