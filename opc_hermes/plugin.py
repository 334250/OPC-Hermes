"""
OPC-Hermes Plugin Entry Point

Registers itself as a Hermes Agent plugin. When loaded by Hermes
(either via ``~/.hermes/plugins/`` or pip entry point), this module:

1. Registers OPC-specific tools (complexity_rater, memory tools, etc.)
2. Registers lifecycle hooks (pre_gateway_dispatch, pre_llm_call, etc.)
3. Registers CLI subcommands (opc list/status/config)
4. Registers cron jobs (optimizer periodic scan)
5. Injects Leader prompt when appropriate

All integration goes through Hermes Agent's existing plugin surface —
no Hermes source files are modified.
"""

from __future__ import annotations

import logging
import hashlib
import json
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Plugin metadata ──────────────────────────────────────────────────────
PLUGIN_NAME = "opc-hermes"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = (
    "OPC-Hermes: multi-agent management layer — Leader/Worker orchestration, "
    "gated memory, complexity routing, quality evaluation, and auto-optimization."
)
LEADER_PROMPT_MARKER = "<!-- opc-hermes-leader-prompt:v1 -->"
MAX_GATEWAY_MESSAGE_CHARS = 20000
_PENDING_PLANS: Dict[str, Dict[str, Any]] = {}


def register(ctx: Any) -> None:
    """Plugin entry point called by Hermes PluginManager at discovery time.

    ``ctx`` is a PluginContext with methods:
      - register_tool(name, handler, schema, toolset, ...)
      - register_hook(hook_name, callback)
      - register_cli_command(name, handler, help_text, ...)
      - register_toolset(name, description, tools)
    """
    logger.info("OPC-Hermes plugin v%s initializing", PLUGIN_VERSION)

    # ── 1. Register OPC tools ────────────────────────────────────────────
    _register_tools(ctx)

    # ── 2. Register lifecycle hooks ──────────────────────────────────────
    _register_hooks(ctx)

    # ── 3. Register CLI subcommands ──────────────────────────────────────
    _register_cli_commands(ctx)

    # ── 4. Register cron jobs ────────────────────────────────────────────
    _register_cron_jobs()

    logger.info("OPC-Hermes plugin registered successfully")


# ══════════════════════════════════════════════════════════════════════════
# Tool Registration
# ══════════════════════════════════════════════════════════════════════════

def _register_tools(ctx: Any) -> None:
    """Register OPC-Hermes tools into Hermes Agent's tool registry.

    Each tool is registered into an OPC-specific toolset so users can
    enable/disable the OPC surface independently.
    """
    from opc_hermes.complexity_rater import (
        register as _register_complexity_rater,
    )
    from opc_hermes.toolsets import register_opc_toolsets

    register_opc_toolsets(ctx)
    _register_complexity_rater(ctx)
    _register_leader_tools(ctx)

    # Memory tools (Phase 2 — registered here for forward-compat)
    _register_memory_tools(ctx)

    # Evaluator tools (Phase 3 — registered here for forward-compat)
    _register_evaluator_tools(ctx)


def _register_leader_tools(ctx: Any) -> None:
    """Register Leader orchestration tools."""
    try:
        ctx.register_tool(
            name="opc_register_pending_plan",
            handler=_register_pending_plan_tool,
            schema={
                "name": "opc_register_pending_plan",
                "description": (
                    "Validate and register a Leader task plan that requires "
                    "explicit user approval before Worker dispatch."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_plan": {"type": "object", "description": "Leader-generated task plan."},
                    },
                    "required": ["task_plan"],
                },
            },
            toolset="opc-leader",
        )
        ctx.register_tool(
            name="opc_dispatch_workers",
            handler=_dispatch_workers_tool,
            schema={
                "name": "opc_dispatch_workers",
                "description": (
                    "Dispatch an approved Leader task plan to OPC Workers. "
                    "Plans marked requires_user_approval must have a matching "
                    "pending-plan hash and approval payload."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_plan": {"type": "object", "description": "Validated task plan."},
                    },
                    "required": ["task_plan"],
                },
            },
            toolset="opc-leader",
        )
    except AttributeError:
        logger.debug("Tool registration not supported in this Hermes version")


def _register_memory_tools(ctx: Any) -> None:
    """Register OPC memory-layer tools (opc_ prefix).

    These tools are the primary API through which Worker agents interact
    with the OPC gated-memory layer. All have the ``opc_`` prefix to
    avoid collisions with core Hermes memory tooling.
    """
    # Stub registrations — full implementations land in Phase 2.
    # Tool schemas are defined in opc_hermes/memory_layer/tools.py.
    try:
        from opc_hermes.memory_layer import tools as mem_tools
        mem_tools.register_all(ctx)
    except Exception as exc:
        logger.warning("OPC memory tools were not registered: %s", exc)


def _register_evaluator_tools(ctx: Any) -> None:
    """Register evaluator-capture tools (opc_eval_ prefix).

    These tools allow the Evaluator agent to snapshot worker outputs and
    write structured evaluations to Eval Memory.
    """
    try:
        from opc_hermes import evaluator

        evaluator.register_all(ctx)
    except Exception as exc:
        logger.warning("OPC evaluator tools were not registered: %s", exc)


# ══════════════════════════════════════════════════════════════════════════
# Lifecycle Hooks
# ══════════════════════════════════════════════════════════════════════════

def _register_hooks(ctx: Any) -> None:
    """Register OPC lifecycle hooks.

    Hooks modify agent behavior without changing Hermes source:
      - pre_gateway_dispatch: intercept incoming messages, route to Leader
      - pre_llm_call: inject OPC-specific context into the system prompt
      - post_tool_call: capture tool results for evaluator snapshots
      - on_session_start: initialize OPC memory partitions
      - on_session_end: flush summary bridges, archive completed tasks
    """
    try:
        ctx.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)
        ctx.register_hook("pre_llm_call", _on_pre_llm_call)
        ctx.register_hook("post_tool_call", _on_post_tool_call)
        ctx.register_hook("on_session_start", _on_session_start)
        ctx.register_hook("on_session_end", _on_session_end)
    except AttributeError:
        logger.debug("Hook registration not supported in this Hermes version")


def _on_pre_gateway_dispatch(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Intercept incoming gateway messages before agent dispatch.

    When the message starts with ``/opc`` or matches OPC task patterns,
    routes to the Leader Agent instead of the default agent.
    """
    if not _is_user_gateway_event(event):
        return None

    message = _extract_event_message(event)
    if not message:
        return None
    if len(message) > MAX_GATEWAY_MESSAGE_CHARS:
        return None
    if _looks_like_quoted_or_code_block(message):
        return None

    config = _load_runtime_config(fail_closed=True)
    if not config.get("enabled", True):
        return None

    prefix = _matched_trigger_prefix(message, config)
    if prefix is None:
        return None

    stripped_message = message.lstrip()
    stripped = stripped_message[len(prefix):].strip()
    if not stripped:
        stripped = message.strip()

    return {
        "handled": True,
        "route_to": "opc_leader",
        "mode": "leader_plan",
        "message": stripped,
        "metadata": {
            "trigger": prefix,
            "requires_plan": True,
            "original_message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            "original_message_length": len(message),
            "opc_session": True,
            "opc_internal_flag": True,
        },
    }


def _on_pre_llm_call(messages: list, agent_context: Dict[str, Any]) -> list:
    """Inject OPC-specific context before the LLM call.

    When the active agent is a Leader, injects:
      - Agent List summary (available workers + capabilities)
      - Recent task status (from Project Memory)
      - Complexity routing rules (from model_prefs)
    """
    if not _is_opc_leader_context(agent_context):
        return messages
    if _has_leader_prompt_marker(messages):
        return messages

    user_message = _latest_user_message(messages)
    agent_list_summary = agent_context.get("agent_list_summary")
    if not agent_list_summary:
        try:
            from opc_hermes.agent_list.registry import get_registry

            agent_list_summary = get_registry().generate_summary()
        except Exception:
            agent_list_summary = ""

    leader_prompt = f"{LEADER_PROMPT_MARKER}\n{get_leader_prompt(user_message, agent_list_summary)}"
    injected = list(messages or [])
    system_message = {"role": "system", "content": leader_prompt}

    if injected and injected[0].get("role") == "system":
        injected[0] = {
            "role": "system",
            "content": f"{leader_prompt}\n\n## Base System Prompt\n\n{injected[0].get('content', '')}",
        }
    else:
        injected.insert(0, system_message)

    return injected


def _on_post_tool_call(
    tool_name: str, tool_args: Dict[str, Any], result: str, task_id: Optional[str]
) -> None:
    """Capture tool call results for evaluator snapshots.

    If the active session has an evaluator watching, forward tool results
    to the evaluator's capture buffer.
    """
    # Phase 3 stub.
    pass


def _on_session_start(session_id: str, platform: str) -> None:
    """Initialize OPC memory partitions for a new session."""
    # Phase 2 stub.
    pass


def _on_session_end(session_id: str) -> None:
    """Flush summary bridges and archive completed tasks."""
    # Phase 2 stub.
    pass


# ══════════════════════════════════════════════════════════════════════════
# CLI Subcommands
# ══════════════════════════════════════════════════════════════════════════

def _register_cli_commands(ctx: Any) -> None:
    """Register `opc` CLI subcommand group.

    Commands:
      - hermes opc list [agents|skills]  — browse registered agents/skills
      - hermes opc status [task_id]      — show active workflow status
      - hermes opc config [key] [value]  — manage OPC configuration
    """
    # Phase 4 — CLI commands land with the full WebUI.
    pass


# ══════════════════════════════════════════════════════════════════════════
# Cron Jobs
# ══════════════════════════════════════════════════════════════════════════

def _register_cron_jobs() -> None:
    """Register OPC periodic cron jobs via Hermes cron API.

    Jobs:
      - opc-optimizer-scan: periodic Eval Memory scan → generate proposals
      - opc-knowledge-crawl: periodic knowledge base refresh
    """
    # Phase 3 — optimizer cron job.
    # Registered via cron.jobs.create_job() API (no source modification).
    pass


# ══════════════════════════════════════════════════════════════════════════
# Public API — for direct embedding (non-plugin usage)
# ══════════════════════════════════════════════════════════════════════════

def get_leader_prompt(user_message: str, agent_list_summary: str = "") -> str:
    """Build a Leader Agent system prompt for the given user message.

    This is the entry point used when OPC is embedded directly (not
    through the plugin system). It produces the full system prompt the
    Leader needs to parse intent, query Agent List, and produce a plan.
    """
    from opc_hermes.leader_prompt import build_leader_system_prompt
    return build_leader_system_prompt(user_message, agent_list_summary)


def should_route_to_leader(message: str, config: Optional[Dict[str, Any]] = None) -> bool:
    """Return true when a user message should enter OPC Leader planning."""
    if not message:
        return False
    cfg = config if config is not None else _load_runtime_config(fail_closed=True)
    if not cfg.get("enabled", True):
        return False
    return _matched_trigger_prefix(message, cfg) is not None


def dispatch_workers(task_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a task plan by dispatching to Worker agents.

    ``task_plan`` is the structured plan produced by the Leader Agent.
    Returns collected results from all workers.
    """
    from opc_hermes.agent_list.registry import get_registry
    from opc_hermes.plan_schema import validate_task_plan

    registry = get_registry()
    allowed_workers = {worker.id for worker in registry.list_workers()}
    allowed_models = _allowed_model_names(registry)
    plan_without_approval = {k: v for k, v in task_plan.items() if k != "approval"}
    validate_task_plan(
        plan_without_approval,
        allowed_worker_ids=allowed_workers,
        allowed_models=allowed_models,
    )
    if plan_without_approval.get("requires_user_approval") is True:
        expected_hash = calculate_plan_hash(plan_without_approval)
        pending = _PENDING_PLANS.get(plan_without_approval["task_id"])
        if pending is None or pending.get("plan_hash") != expected_hash:
            return {
                "task_id": task_plan.get("task_id", "unknown"),
                "status": "blocked",
                "error": "Plan is not registered as a pending plan.",
                "plan_hash": expected_hash,
            }
        if pending.get("status") != "approved":
            return {
                "task_id": task_plan.get("task_id", "unknown"),
                "status": "blocked",
                "error": "Pending plan has not been confirmed by a trusted user action.",
                "plan_hash": expected_hash,
            }
        pending["status"] = "dispatched"

    from opc_hermes.worker_dispatcher import OPCWorkerDispatcher
    dispatcher = OPCWorkerDispatcher()
    return dispatcher.execute(plan_without_approval)


def _register_pending_plan_tool(args: Dict[str, Any], **kw: Any) -> str:
    _require_leader_tool_call(kw)
    task_plan = args.get("task_plan") if isinstance(args, dict) else None
    if not isinstance(task_plan, dict):
        return json.dumps({"status": "error", "error": "task_plan must be an object."})
    return json.dumps(register_pending_plan(task_plan), ensure_ascii=False)


def _dispatch_workers_tool(args: Dict[str, Any], **kw: Any) -> str:
    _require_leader_tool_call(kw)
    task_plan = args.get("task_plan") if isinstance(args, dict) else None
    if not isinstance(task_plan, dict):
        return json.dumps({"status": "error", "error": "task_plan must be an object."})
    return json.dumps(dispatch_workers(task_plan), ensure_ascii=False)


def register_pending_plan(task_plan: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and register a user-approval-gated plan before dispatch."""
    from opc_hermes.agent_list.registry import get_registry
    from opc_hermes.plan_schema import render_plan_summary, validate_task_plan

    registry = get_registry()
    allowed_workers = {worker.id for worker in registry.list_workers()}
    allowed_models = _allowed_model_names(registry)
    plan_without_approval = {k: v for k, v in task_plan.items() if k != "approval"}
    validate_task_plan(
        plan_without_approval,
        allowed_worker_ids=allowed_workers,
        allowed_models=allowed_models,
    )
    if plan_without_approval.get("requires_user_approval") is not True:
        return {
            "task_id": plan_without_approval["task_id"],
            "status": "not_required",
            "plan_hash": calculate_plan_hash(plan_without_approval),
            "summary": render_plan_summary(plan_without_approval),
        }

    plan_hash = calculate_plan_hash(plan_without_approval)
    _PENDING_PLANS[plan_without_approval["task_id"]] = {
        "plan_hash": plan_hash,
        "plan": plan_without_approval,
        "status": "pending",
    }
    return {
        "task_id": plan_without_approval["task_id"],
        "status": "pending",
        "plan_hash": plan_hash,
        "summary": render_plan_summary(plan_without_approval),
    }


def confirm_pending_plan(
    task_id: str,
    plan_hash: str,
    *,
    user_confirmed: bool,
    confirmer_type: str,
) -> Dict[str, Any]:
    """Approve a pending plan from a trusted UI, CLI, or gateway path.

    This API is intentionally not registered as an LLM-callable tool. Leader
    tools can register and dispatch plans, but cannot mark their own plans
    user-approved.
    """
    if not user_confirmed or confirmer_type not in {"user", "cli", "webui", "gateway"}:
        return {
            "task_id": task_id,
            "status": "blocked",
            "error": "Pending plan confirmation requires a trusted user action.",
        }

    pending = _PENDING_PLANS.get(task_id)
    if pending is None or pending.get("plan_hash") != plan_hash:
        return {
            "task_id": task_id,
            "status": "blocked",
            "error": "Pending plan hash does not match.",
        }
    if pending.get("status") != "pending":
        return {
            "task_id": task_id,
            "status": "blocked",
            "error": f"Pending plan is already {pending.get('status')}.",
        }

    pending["status"] = "approved"
    pending["confirmed_by"] = confirmer_type
    return {
        "task_id": task_id,
        "status": "approved",
        "plan_hash": plan_hash,
    }


def calculate_plan_hash(task_plan: Dict[str, Any]) -> str:
    """Return a stable hash for an approved plan payload."""
    payload = json.dumps(task_plan, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_runtime_config(*, fail_closed: bool = False) -> Dict[str, Any]:
    try:
        from opc_hermes.config import load_config

        return load_config()
    except Exception as exc:
        logger.warning("Could not load OPC config: %s", exc)
        from opc_hermes.config import default_config

        config = default_config()
        if fail_closed:
            config["enabled"] = False
            config.setdefault("routing", {})["trigger_prefixes"] = []
        return config


def _allowed_model_names(registry: Any) -> set[str]:
    from opc_hermes.model_prefs import list_known_models

    models = list_known_models()
    for worker in registry.list_workers():
        if worker.default_model:
            models.add(worker.default_model)
    return models


def _require_leader_tool_call(metadata: Dict[str, Any]) -> None:
    agent_id = metadata.get("agent_id") or metadata.get("caller_agent_id")
    if agent_id != "opc_leader" or metadata.get("opc_internal_flag") is not True:
        raise PermissionError("OPC Leader tools require trusted leader context.")


def _extract_event_message(event: Dict[str, Any]) -> str:
    for key in ("message", "text", "content"):
        value = event.get(key)
        if isinstance(value, str):
            return value.strip()
    nested = event.get("message")
    if isinstance(nested, dict):
        for key in ("text", "content"):
            value = nested.get(key)
            if isinstance(value, str):
                return value.strip()
    return ""


def _is_user_gateway_event(event: Dict[str, Any]) -> bool:
    role = event.get("role") or event.get("message_role")
    if role != "user":
        return False
    source = event.get("source") or event.get("message_source")
    if source is not None and source not in {"user", "gateway", "chat"}:
        return False
    if event.get("tool_name") or event.get("tool_call_id"):
        return False
    return True


def _looks_like_quoted_or_code_block(message: str) -> bool:
    stripped = message.lstrip()
    if stripped.startswith((">", "```")):
        return True
    first_line = stripped.splitlines()[0] if stripped.splitlines() else stripped
    return first_line.startswith(("    ", "\t"))


def _matched_trigger_prefix(message: str, config: Dict[str, Any]) -> Optional[str]:
    routing = config.get("routing", {})
    prefixes = routing.get("trigger_prefixes", ["/opc"])
    if not isinstance(prefixes, list):
        prefixes = ["/opc"]
    stripped = message.lstrip()
    for prefix in sorted((p for p in prefixes if isinstance(p, str) and p), key=len, reverse=True):
        if stripped == prefix or stripped.startswith(f"{prefix} "):
            return prefix
    return None


def _is_opc_leader_context(agent_context: Dict[str, Any]) -> bool:
    if not isinstance(agent_context, dict):
        return False
    if agent_context.get("opc_internal_flag") is True and agent_context.get("agent_id") == "opc_leader":
        return True
    metadata = agent_context.get("metadata")
    if (
        isinstance(metadata, dict)
        and metadata.get("opc_internal_flag") is True
        and agent_context.get("agent_id") == "opc_leader"
    ):
        return True
    return False


def _latest_user_message(messages: List[Dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _has_leader_prompt_marker(messages: List[Dict[str, Any]]) -> bool:
    for message in messages or []:
        if message.get("role") == "system" and LEADER_PROMPT_MARKER in str(message.get("content", "")):
            return True
    return False
