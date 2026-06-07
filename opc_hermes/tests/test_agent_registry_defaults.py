from pathlib import Path

import yaml

from opc_hermes.agent_list.registry import AgentRegistry
from opc_hermes.toolsets import OPC_TOOLSETS


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HERMES_TOOLSETS_USED_BY_DEFAULTS = {
    "browser",
    "debugging",
    "file",
    "image_gen",
    "search",
    "terminal",
    "vision",
    "web",
}


def test_default_workers_reference_existing_skills_and_templates(tmp_path):
    registry = AgentRegistry(data_dir=tmp_path)
    registry.load()

    workers = {worker.id: worker for worker in registry.list_workers()}
    skills = {skill.id: skill for skill in registry.list_skills()}

    prompts_path = PACKAGE_ROOT / "config" / "worker_templates" / "prompts.yaml"
    prompts = yaml.safe_load(prompts_path.read_text(encoding="utf-8"))

    missing_skills = []
    missing_templates = []
    for worker in workers.values():
        for skill_id in worker.skill_ids:
            if skill_id not in skills:
                missing_skills.append((worker.id, skill_id))
        if worker.system_prompt_template not in prompts:
            missing_templates.append((worker.id, worker.system_prompt_template))

    assert missing_skills == []
    assert missing_templates == []


def test_default_skills_reference_existing_owner_workers(tmp_path):
    registry = AgentRegistry(data_dir=tmp_path)
    registry.load()

    worker_ids = {worker.id for worker in registry.list_workers()}
    missing_owners = [
        (skill.id, skill.owner_worker_id)
        for skill in registry.list_skills()
        if skill.owner_worker_id not in worker_ids
    ]

    assert missing_owners == []


def test_development_workflows_reference_registered_workers(tmp_path):
    registry = AgentRegistry(data_dir=tmp_path)
    registry.load()
    worker_ids = {worker.id for worker in registry.list_workers()}

    leader_config_path = PACKAGE_ROOT / "config" / "leader_default.yaml"
    leader_config = yaml.safe_load(leader_config_path.read_text(encoding="utf-8"))
    workflows = leader_config["leader"]["development_workflows"]

    missing_workers = []
    for workflow_id, workflow in workflows.items():
        for worker_id in workflow.get("workers", []):
            if worker_id not in worker_ids:
                missing_workers.append((workflow_id, worker_id))

    assert missing_workers == []


def test_default_workers_reference_known_toolsets(tmp_path):
    registry = AgentRegistry(data_dir=tmp_path)
    registry.load()

    known_toolsets = set(OPC_TOOLSETS) | HERMES_TOOLSETS_USED_BY_DEFAULTS
    unknown_toolsets = [
        (worker.id, toolset)
        for worker in registry.list_workers()
        for toolset in worker.toolsets
        if toolset not in known_toolsets
    ]

    assert unknown_toolsets == []
