from pathlib import Path
from importlib.resources import files

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULTS_PATH = PACKAGE_ROOT / "agent_list" / "defaults.yaml"
LEADER_CONFIG_PATH = PACKAGE_ROOT / "config" / "leader_default.yaml"
PROMPTS_PATH = PACKAGE_ROOT / "config" / "worker_templates" / "prompts.yaml"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must parse to a YAML mapping"
    return data


def test_phase0_yaml_files_parse_to_expected_top_level_mappings():
    defaults = _load_yaml(DEFAULTS_PATH)
    leader_config = _load_yaml(LEADER_CONFIG_PATH)
    prompts = _load_yaml(PROMPTS_PATH)

    assert isinstance(defaults.get("workers"), list)
    assert isinstance(defaults.get("skills"), list)
    assert defaults["workers"], "defaults.yaml must define at least one worker"
    assert defaults["skills"], "defaults.yaml must define at least one skill"

    assert isinstance(leader_config.get("leader"), dict)
    assert isinstance(prompts, dict)
    assert prompts, "prompts.yaml must define at least one prompt template"


def test_phase0_default_worker_and_skill_entries_have_required_schema():
    defaults = _load_yaml(DEFAULTS_PATH)
    workers = defaults["workers"]
    skills = defaults["skills"]

    worker_ids = [worker.get("id") for worker in workers]
    skill_ids = [skill.get("id") for skill in skills]

    assert len(worker_ids) == len(set(worker_ids)), "worker ids must be unique"
    assert len(skill_ids) == len(set(skill_ids)), "skill ids must be unique"

    required_worker_fields = {
        "id",
        "display_name",
        "description",
        "role",
        "capabilities",
        "skill_ids",
        "default_model",
        "model_tier",
        "toolsets",
        "system_prompt_template",
    }
    required_skill_fields = {
        "id",
        "display_name",
        "description",
        "owner_worker_id",
        "tags",
        "input_schema",
        "output_schema",
    }

    for worker in workers:
        assert required_worker_fields <= worker.keys(), worker.get("id")
        assert worker["role"] in {"leader", "worker", "evaluator"}
        assert worker["model_tier"] in {"budget", "standard", "premium"}
        assert isinstance(worker["capabilities"], list), worker["id"]
        assert isinstance(worker["skill_ids"], list), worker["id"]
        assert isinstance(worker["toolsets"], list), worker["id"]

    for skill in skills:
        assert required_skill_fields <= skill.keys(), skill.get("id")
        assert isinstance(skill["tags"], list), skill["id"]
        assert isinstance(skill["input_schema"], dict), skill["id"]
        assert isinstance(skill["output_schema"], dict), skill["id"]


def test_phase0_leader_config_has_usable_routing_and_workflow_schema():
    leader = _load_yaml(LEADER_CONFIG_PATH)["leader"]

    routing = leader.get("complexity_routing")
    assert isinstance(routing, dict)
    assert {"SIMPLE", "MEDIUM", "COMPLEX"} <= routing.keys()

    for level, rules in routing.items():
        assert rules["recommended_model_tier"] in {"budget", "standard", "premium"}, level
        assert isinstance(rules["max_workers"], int), level
        assert rules["max_workers"] >= 1, level
        assert isinstance(rules["requires_plan_approval"], bool), level
        assert isinstance(rules.get("examples"), list), level

    workflows = leader.get("development_workflows")
    assert isinstance(workflows, dict)
    assert workflows, "development workflows must be configured for Phase 0"

    for workflow_id, workflow in workflows.items():
        assert workflow["mode"] in {"pipeline", "parallel", "sequential", "star"}, workflow_id
        assert isinstance(workflow.get("triggers"), list), workflow_id
        assert workflow["triggers"], workflow_id
        assert isinstance(workflow.get("workers"), list), workflow_id
        assert workflow["workers"], workflow_id


def test_phase0_worker_prompt_templates_are_non_empty_strings():
    prompts = _load_yaml(PROMPTS_PATH)

    empty_templates = [
        template_id
        for template_id, template in prompts.items()
        if not isinstance(template, str) or not template.strip()
    ]

    assert empty_templates == []


def test_phase0_package_data_resources_are_readable():
    package_root = files("opc_hermes")
    required_resources = [
        "agent_list/defaults.yaml",
        "config/leader_default.yaml",
        "config/worker_templates/prompts.yaml",
        "skills/opc-leader.md",
    ]

    for resource_path in required_resources:
        resource = package_root.joinpath(*resource_path.split("/"))
        assert resource.is_file(), resource_path
        assert resource.read_text(encoding="utf-8").strip(), resource_path
