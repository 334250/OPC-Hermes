import importlib

import pytest


CORE_MODULES = [
    "opc_hermes",
    "opc_hermes.agent_list",
    "opc_hermes.agent_list.registry",
    "opc_hermes.cli_skin",
    "opc_hermes.cli_skin.commands",
    "opc_hermes.complexity_rater",
    "opc_hermes.config",
    "opc_hermes.evaluator",
    "opc_hermes.knowledge_pipeline",
    "opc_hermes.leader_prompt",
    "opc_hermes.memory_layer",
    "opc_hermes.memory_layer.gated_memory",
    "opc_hermes.memory_layer.summary_bridge",
    "opc_hermes.memory_layer.task_protocol",
    "opc_hermes.memory_layer.tools",
    "opc_hermes.model_prefs",
    "opc_hermes.optimizer",
    "opc_hermes.plugin",
    "opc_hermes.revision_handler",
    "opc_hermes.toolsets",
    "opc_hermes.webui",
    "opc_hermes.worker_dispatcher",
    "opc_hermes.workflow",
    "opc_hermes.workflow.artifact_manager",
    "opc_hermes.workflow.cycle_detector",
    "opc_hermes.workflow.dag_executor",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_phase0_core_modules_are_importable(module_name):
    importlib.import_module(module_name)
