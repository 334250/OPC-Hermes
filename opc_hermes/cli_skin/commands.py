"""
OPC-Hermes CLI Commands

Registers the `opc` subcommand group via the Hermes plugin CLI hook.
Commands:
  - opc list [agents|skills]     — browse registered agents and skills
  - opc status [task_id]         — show active workflow status
  - opc config [key] [value]     — manage OPC configuration
  - opc proposals                — list optimization proposals
  - opc approve <id>             — approve an optimization proposal
  - opc agents                   — interactive agent list browser
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def register_cli(subparsers) -> None:
    """Register the `opc` subcommand group with Hermes CLI argparse.

    Called by Hermes plugin discovery at startup.
    """
    opc_parser = subparsers.add_parser(
        "opc",
        help="OPC-Hermes multi-agent management commands",
        description="Manage OPC-Hermes agents, workflows, and configuration.",
    )
    opc_sub = opc_parser.add_subparsers(dest="opc_action")

    # opc list
    list_parser = opc_sub.add_parser("list", help="List registered agents or skills")
    list_parser.add_argument(
        "what", nargs="?", default="agents",
        choices=["agents", "skills", "workers"],
        help="What to list (default: agents)",
    )

    # opc status
    status_parser = opc_sub.add_parser("status", help="Show active workflow status")
    status_parser.add_argument("task_id", nargs="?", help="Task ID to show status for")

    # opc config
    config_parser = opc_sub.add_parser("config", help="Manage OPC configuration")
    config_parser.add_argument("key", nargs="?", help="Config key to get/set")
    config_parser.add_argument("value", nargs="?", help="Value to set")

    # opc proposals
    proposals_parser = opc_sub.add_parser("proposals", help="List optimization proposals")
    proposals_parser.add_argument(
        "--status", choices=["pending", "approved", "rejected", "applied"],
        default="pending", help="Filter by status",
    )

    # opc approve
    approve_parser = opc_sub.add_parser("approve", help="Approve an optimization proposal")
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve")

    # opc agents (interactive)
    opc_sub.add_parser("agents", help="Interactive agent list browser")


# ── Command Handlers ─────────────────────────────────────────────────────

def handle_list(what: str = "agents") -> str:
    """Handle `opc list` — display registered agents or skills."""
    from opc_hermes.agent_list.registry import get_registry

    registry = get_registry()

    if what in ("agents", "workers"):
        workers = registry.list_workers()
        if not workers:
            return "No agents registered. System defaults should be loaded automatically."

        lines = [f"📋 Registered Agents ({len(workers)})", "=" * 50]
        for w in workers:
            role_emoji = {"leader": "👑", "worker": "🔧", "evaluator": "🔍"}.get(w.role, "❓")
            score = f" ⭐{w.quality_score:.1f}" if w.quality_score else ""
            lines.append(
                f"  {role_emoji} {w.display_name} ({w.id}) [{w.model_tier}{score}]"
            )
            lines.append(f"     Role: {w.role} | Model: {w.default_model or 'default'}")
            lines.append(f"     Skills: {', '.join(w.skill_ids) if w.skill_ids else '(none)'}")
            lines.append("")
        return "\n".join(lines)

    elif what == "skills":
        skills = registry.list_skills()
        if not skills:
            return "No skills registered."

        lines = [f"🛠️  Registered Skills ({len(skills)})", "=" * 50]
        for s in skills:
            tags = f" [{', '.join(s.tags)}]" if s.tags else ""
            lines.append(f"  • {s.display_name} ({s.id}){tags}")
            lines.append(f"    Owner: {s.owner_worker_id} | {s.description[:80]}")
            lines.append("")
        return "\n".join(lines)

    return f"Unknown list target: {what}"


def handle_status(task_id: Optional[str] = None) -> str:
    """Handle `opc status` — show workflow status."""
    from opc_hermes.memory_layer.gated_memory import get_memory_layer

    memory = get_memory_layer()

    if task_id:
        reports = memory.get_progress_reports(task_id)
        protocols = memory.get_all_task_protocols(task_id)

        if not protocols:
            return f"No task found with ID: {task_id}"

        lines = [f"📊 Task Status: {task_id}", "=" * 50]
        for p in protocols:
            worker_reports = [r for r in reports if r.worker_id == p.worker_id]
            latest = worker_reports[-1] if worker_reports else None
            status = latest.status if latest else "not_started"
            status_emoji = {
                "completed": "✅", "in_progress": "🔄",
                "failed": "❌", "blocked": "⏸️",
            }.get(status, "⬜")
            lines.append(f"  {status_emoji} {p.worker_id}: {status}")
            if latest and latest.summary:
                lines.append(f"     {latest.summary[:100]}")
        return "\n".join(lines)

    return "Usage: opc status <task_id>"


def handle_config(key: Optional[str] = None, value: Optional[str] = None) -> str:
    """Handle `opc config` — manage OPC configuration."""
    if key and value:
        return f"[Phase 4] Would set config '{key}' = '{value}'"
    elif key:
        return f"[Phase 4] Would show config '{key}'"
    return "[Phase 4] OPC config management — coming in Phase 4"


def handle_proposals(status: str = "pending") -> str:
    """Handle `opc proposals` — list optimization proposals."""
    from opc_hermes.optimizer import Optimizer

    opt = Optimizer()
    proposals = opt.list_proposals(status=status)

    if not proposals:
        return f"No {status} proposals."

    lines = [f"📈 Optimization Proposals ({status})", "=" * 50]
    for p in proposals:
        lines.append(f"  [{p['id']}] {p['title']}")
        lines.append(f"     Worker: {p['worker_id']} | Risk: {p['risk']}")
        lines.append(f"     {p['description'][:120]}")
        lines.append("")
    return "\n".join(lines)


def handle_approve(proposal_id: str) -> str:
    """Handle `opc approve` — approve a proposal."""
    from opc_hermes.optimizer import Optimizer

    opt = Optimizer()
    ok = opt.approve_proposal(proposal_id)
    if ok:
        return f"✅ Proposal {proposal_id} approved. Apply the change manually via `opc config`."
    return f"❌ Proposal {proposal_id} not found."
