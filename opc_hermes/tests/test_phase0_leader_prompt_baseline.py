from pathlib import Path

from opc_hermes.agent_list.registry import AgentRegistry
from opc_hermes.leader_prompt import build_leader_system_prompt


def test_phase0_leader_prompt_injects_registry_summary_and_default_sections(tmp_path):
    registry = AgentRegistry(data_dir=tmp_path)
    registry.load()

    summary = registry.generate_summary()
    prompt = build_leader_system_prompt(
        "实现一个后端 API 并补充测试",
        agent_list_summary=summary,
    )

    assert "OPC-Hermes Leader Agent" in prompt
    assert "## Available Workers" in prompt
    assert "`backend_engineer`" in prompt
    assert "`qa_engineer`" in prompt
    assert "`code_reviewer`" in prompt
    assert "## Complexity Routing Rules" in prompt
    assert "**SIMPLE**" in prompt
    assert "**MEDIUM**" in prompt
    assert "**COMPLEX**" in prompt
    assert "## Software Development Workflow Hints" in prompt
    assert "**backend_change**" in prompt
    assert "workers=[software_architect, backend_engineer, qa_engineer, code_reviewer]" in prompt
    assert "## Behavior Rules" in prompt
    assert "Always call complexity_rater" in prompt


def test_phase0_leader_prompt_has_safe_fallback_when_agent_summary_is_empty():
    prompt = build_leader_system_prompt("总结这段文字", agent_list_summary="")

    assert "## Agent List" in prompt
    assert "No Agent List summary available" in prompt
    assert "query the Agent List registry" in prompt


def test_phase0_leader_prompt_has_safe_fallback_when_config_is_missing(tmp_path):
    missing_config = Path(tmp_path) / "missing-leader-config.yaml"

    prompt = build_leader_system_prompt(
        "开发一个完整功能",
        agent_list_summary="## Available Workers\n\n- test worker",
        config_path=missing_config,
    )

    assert "OPC-Hermes Leader Agent" in prompt
    assert "## Available Workers" in prompt
    assert "test worker" in prompt
    assert "## Complexity Routing Rules" not in prompt
    assert "## Behavior Rules" not in prompt
