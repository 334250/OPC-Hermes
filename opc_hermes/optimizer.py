"""
OPC Optimizer — automatic improvement engine.

Runs as a periodic cron job that:
  1. Scans Eval Memory for quality trends (worker scores over time)
  2. Detects patterns: declining scores, underperforming models, skill gaps
  3. Generates optimization proposals (model switch, skill update, prompt change)
  4. Pushes proposals to the WebUI Dashboard for human approval
  5. NEVER applies changes automatically — always requires human approval

After human approval and manual switch:
  6. Monitors quality post-switch for regression
  7. If significant quality drop detected → auto-alert + one-click rollback

Design reference: §8 自进化引擎 (opc-hermes-design-v3.0.md)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Thresholds ───────────────────────────────────────────────────────────

QUALITY_DECLINE_THRESHOLD = 0.2    # avg score drop of 0.2 triggers investigation
MIN_EVALUATIONS_FOR_ANALYSIS = 5   # need at least 5 evaluations to analyze a worker
PROPOSAL_SCAN_WINDOW_DAYS = 30     # look at evaluations from the last 30 days

# ── Proposal data structure ──────────────────────────────────────────────

@dataclass
class OptimizationProposal:
    """A single optimization the Optimizer recommends."""
    id: str
    type: str                      # "model_switch" | "skill_update" | "prompt_change" | "worker_retire"
    worker_id: str
    title: str
    description: str
    current_state: Dict[str, Any]  # what we have now
    proposed_state: Dict[str, Any] # what we should switch to
    evidence: Dict[str, Any]       # data backing this proposal
    risk: str = "low"              # low | medium | high
    status: str = "pending"        # pending | approved | rejected | applied | rolled_back
    created_at: str = ""
    approved_at: str = ""
    applied_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


# ── Optimizer Engine ─────────────────────────────────────────────────────

class Optimizer:
    """Scans Eval Memory and generates optimization proposals."""

    def __init__(self, proposals_dir: Optional[Path] = None):
        if proposals_dir is None:
            try:
                from hermes_constants import get_hermes_home
                proposals_dir = get_hermes_home() / "opc" / "proposals"
            except ImportError:
                proposals_dir = Path.home() / ".hermes" / "opc" / "proposals"
        self._proposals_dir = Path(proposals_dir)
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    def scan(self) -> List[OptimizationProposal]:
        """Run a full optimization scan across all workers.

        Returns a list of new proposals (empty if nothing to optimize).
        This is the entry point called by the cron job.
        """
        from opc_hermes.memory_layer.gated_memory import get_memory_layer
        memory = get_memory_layer()

        proposals: List[OptimizationProposal] = []

        # 1. Get all workers from the agent registry
        try:
            from opc_hermes.agent_list.registry import get_registry
            workers = get_registry().list_workers()
        except Exception as e:
            logger.warning("Could not load agent registry: %s", e)
            return proposals

        cutoff = (datetime.now(timezone.utc) - timedelta(days=PROPOSAL_SCAN_WINDOW_DAYS)).isoformat()

        for worker in workers:
            # 2. Get this worker's evaluation trend
            evaluations = memory.get_evaluations(worker_id=worker.id, limit=100)
            recent_evals = [e for e in evaluations if e.evaluated_at >= cutoff]

            if len(recent_evals) < MIN_EVALUATIONS_FOR_ANALYSIS:
                continue

            # 3. Calculate quality trend
            avg_quality = sum(
                e.scores.get("quality", 0.5) for e in recent_evals
            ) / len(recent_evals)

            # 4. Check for decline patterns
            if worker.quality_score > 0 and avg_quality < worker.quality_score - QUALITY_DECLINE_THRESHOLD:
                proposal = self._generate_model_switch_proposal(worker, recent_evals, avg_quality)
                proposals.append(proposal)

            # 5. Check for model-tier mismatch
            if worker.model_tier == "budget" and avg_quality < 0.5:
                proposal = self._generate_tier_upgrade_proposal(worker, recent_evals, avg_quality)
                proposals.append(proposal)

        # 6. Save proposals to disk
        for p in proposals:
            self._save_proposal(p)

        logger.info("Optimizer scan complete: %d proposals generated", len(proposals))
        return proposals

    def _generate_model_switch_proposal(
        self, worker, evaluations: list, current_avg: float
    ) -> OptimizationProposal:
        """Generate a proposal to switch the worker's model."""
        import uuid

        better_models = {
            "budget": "standard",
            "standard": "premium",
            "premium": "premium",  # already top tier
        }
        new_tier = better_models.get(worker.model_tier, "standard")

        return OptimizationProposal(
            id=uuid.uuid4().hex[:12],
            type="model_switch",
            worker_id=worker.id,
            title=f"Upgrade {worker.display_name} model tier",
            description=(
                f"Worker '{worker.display_name}' ({worker.id}) has an average quality "
                f"score of {current_avg:.2f} on {worker.model_tier}-tier model "
                f"'{worker.default_model}'. Consider upgrading to {new_tier}-tier."
            ),
            current_state={"model": worker.default_model, "tier": worker.model_tier},
            proposed_state={"model": "claude-sonnet-4", "tier": new_tier},
            evidence={
                "evaluation_count": len(evaluations),
                "current_avg_quality": round(current_avg, 2),
                "previous_score": worker.quality_score,
                "sample_scores": [e.scores for e in evaluations[:5]],
            },
            risk="low",
        )

    def _generate_tier_upgrade_proposal(
        self, worker, evaluations: list, current_avg: float
    ) -> OptimizationProposal:
        """Generate a proposal to upgrade from budget tier."""
        import uuid

        return OptimizationProposal(
            id=uuid.uuid4().hex[:12],
            type="model_switch",
            worker_id=worker.id,
            title=f"Upgrade {worker.display_name} from budget to standard tier",
            description=(
                f"Worker '{worker.display_name}' is on budget tier but averaging "
                f"only {current_avg:.2f} quality. Standard-tier models may improve output."
            ),
            current_state={"model": worker.default_model, "tier": "budget"},
            proposed_state={"model": "claude-sonnet-4", "tier": "standard"},
            evidence={
                "evaluation_count": len(evaluations),
                "current_avg_quality": round(current_avg, 2),
            },
            risk="low",
        )

    # ── Proposal persistence ─────────────────────────────────────────────

    def _save_proposal(self, proposal: OptimizationProposal) -> None:
        """Save a proposal to disk for the WebUI to display."""
        proposal_file = self._proposals_dir / f"{proposal.id}.json"
        with open(proposal_file, "w", encoding="utf-8") as f:
            json.dump({
                "id": proposal.id,
                "type": proposal.type,
                "worker_id": proposal.worker_id,
                "title": proposal.title,
                "description": proposal.description,
                "current_state": proposal.current_state,
                "proposed_state": proposal.proposed_state,
                "evidence": proposal.evidence,
                "risk": proposal.risk,
                "status": proposal.status,
                "created_at": proposal.created_at,
                "approved_at": proposal.approved_at,
                "applied_at": proposal.applied_at,
            }, f, indent=2, ensure_ascii=False)

    def list_proposals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all proposals, optionally filtered by status."""
        proposals = []
        if self._proposals_dir.exists():
            for f in sorted(self._proposals_dir.glob("*.json"), reverse=True):
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if status is None or data.get("status") == status:
                    proposals.append(data)
        return proposals

    def approve_proposal(self, proposal_id: str) -> bool:
        """Mark a proposal as approved (human action)."""
        return self._update_status(proposal_id, "approved")

    def reject_proposal(self, proposal_id: str) -> bool:
        """Mark a proposal as rejected (human action)."""
        return self._update_status(proposal_id, "rejected")

    def mark_applied(self, proposal_id: str) -> bool:
        """Mark a proposal as applied (after human manually switches)."""
        proposal_file = self._proposals_dir / f"{proposal_id}.json"
        if not proposal_file.exists():
            return False
        with open(proposal_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = "applied"
        data["applied_at"] = datetime.now(timezone.utc).isoformat()
        with open(proposal_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True

    def _update_status(self, proposal_id: str, status: str) -> bool:
        proposal_file = self._proposals_dir / f"{proposal_id}.json"
        if not proposal_file.exists():
            return False
        with open(proposal_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = status
        if status == "approved":
            data["approved_at"] = datetime.now(timezone.utc).isoformat()
        with open(proposal_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True


# ── Cron job entry point ─────────────────────────────────────────────────

def run_optimizer_scan() -> Dict[str, Any]:
    """Entry point for the cron job. Returns a summary dict."""
    optimizer = Optimizer()
    proposals = optimizer.scan()

    return {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "proposals_generated": len(proposals),
        "proposals": [
            {"id": p.id, "title": p.title, "worker_id": p.worker_id}
            for p in proposals
        ],
    }


# ── Rollback monitoring ──────────────────────────────────────────────────

def check_for_regression(worker_id: str, applied_since: str) -> Optional[str]:
    """Check if a worker's quality dropped after an optimization was applied.

    Returns a warning message if regression detected, or None if fine.
    """
    from opc_hermes.memory_layer.gated_memory import get_memory_layer
    memory = get_memory_layer()

    evaluations = memory.get_evaluations(worker_id=worker_id, limit=50)
    pre_switch = [e for e in evaluations if e.evaluated_at < applied_since]
    post_switch = [e for e in evaluations if e.evaluated_at >= applied_since]

    if len(post_switch) < 3:
        return None  # not enough data yet

    pre_avg = sum(e.scores.get("quality", 0.5) for e in pre_switch[-10:]) / max(len(pre_switch[-10:]), 1)
    post_avg = sum(e.scores.get("quality", 0.5) for e in post_switch) / len(post_switch)

    if post_avg < pre_avg - QUALITY_DECLINE_THRESHOLD:
        return (
            f"⚠️ Quality regression detected for {worker_id}: "
            f"pre-switch avg {pre_avg:.2f} → post-switch avg {post_avg:.2f}. "
            f"Consider rolling back."
        )

    return None
