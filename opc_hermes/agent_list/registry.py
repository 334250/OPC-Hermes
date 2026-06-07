"""
Agent + Skill Global Registry for OPC-Hermes.

The registry is the single source of truth for:
  - Which Worker agents are available
  - What capabilities each Worker has
  - Which Skills are registered and which Worker owns each
  - Quality scores for agents (updated by Evaluator)

Storage:
  - defaults.yaml  — system defaults shipped with the package
  - workers.yaml   — user-registered workers (~/.hermes/opc/agent_list/workers.yaml)
  - skills.yaml    — user-registered skills  (~/.hermes/opc/agent_list/skills.yaml)

API:
  - search(query)       — full-text search across agents + skills
  - match(capability)   — find agents matching a required capability
  - register(agent)     — register a new agent
  - update_score(id, score) — update agent quality score
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class SkillDef:
    """A reusable capability with defined input/output contracts."""
    id: str
    display_name: str
    description: str
    owner_worker_id: str       # which worker "owns" this skill
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillDef":
        return cls(
            id=data["id"],
            display_name=data.get("display_name", data["id"]),
            description=data.get("description", ""),
            owner_worker_id=data.get("owner_worker_id", ""),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            tags=data.get("tags", []),
        )


@dataclass
class WorkerDef:
    """A role-specialized worker agent."""
    id: str
    display_name: str
    description: str
    role: str                       # "worker" | "leader" | "evaluator"
    capabilities: List[str] = field(default_factory=list)  # what this worker can do
    skill_ids: List[str] = field(default_factory=list)     # skills this worker owns
    default_model: str = ""         # preferred model for this worker
    model_tier: str = "standard"    # budget | standard | premium
    toolsets: List[str] = field(default_factory=list)      # toolset names
    system_prompt_template: str = ""  # jinja2 template for system prompt
    quality_score: float = 0.0      # updated by Evaluator
    total_tasks: int = 0
    successful_tasks: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerDef":
        return cls(
            id=data["id"],
            display_name=data.get("display_name", data["id"]),
            description=data.get("description", ""),
            role=data.get("role", "worker"),
            capabilities=data.get("capabilities", []),
            skill_ids=data.get("skill_ids", []),
            default_model=data.get("default_model", ""),
            model_tier=data.get("model_tier", "standard"),
            toolsets=data.get("toolsets", []),
            system_prompt_template=data.get("system_prompt_template", ""),
            quality_score=data.get("quality_score", 0.0),
            total_tasks=data.get("total_tasks", 0),
            successful_tasks=data.get("successful_tasks", 0),
        )

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.successful_tasks / self.total_tasks


# ══════════════════════════════════════════════════════════════════════════
# AgentRegistry
# ══════════════════════════════════════════════════════════════════════════

class AgentRegistry:
    """In-memory + YAML-backed registry of all OPC agents and skills.

    Loads system defaults first, then overlays user registrations.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or self._default_data_dir()
        self._workers: Dict[str, WorkerDef] = {}
        self._skills: Dict[str, SkillDef] = {}
        self._loaded = False

    # ── Initialization ───────────────────────────────────────────────────

    @staticmethod
    def _default_data_dir() -> Path:
        """Resolve the OPC data directory relative to Hermes home."""
        try:
            from opc_hermes.config.loader import get_opc_home

            return get_opc_home() / "agent_list"
        except ImportError:
            return Path.home() / ".hermes" / "opc" / "agent_list"

    @property
    def workers_file(self) -> Path:
        return self._data_dir / "workers.yaml"

    @property
    def skills_file(self) -> Path:
        return self._data_dir / "skills.yaml"

    @property
    def defaults_file(self) -> Any:
        """Path-like handle to the shipped defaults.yaml (inside the package)."""
        return files("opc_hermes.agent_list").joinpath("defaults.yaml")

    def load(self) -> None:
        """Load system defaults + user registrations into memory.

        Idempotent — safe to call multiple times.
        """
        if self._loaded:
            return

        # 1. Load system defaults
        if self.defaults_file.exists():
            self._load_yaml_into(self.defaults_file, is_default=True)

        # 2. Overlay user workers
        if self.workers_file.exists():
            self._load_yaml_into(self.workers_file, is_default=False)

        # 3. Overlay user skills
        if self.skills_file.exists():
            self._load_yaml_into(self.skills_file, is_default=False)

        self._loaded = True
        logger.info(
            "AgentRegistry loaded: %d workers, %d skills",
            len(self._workers), len(self._skills),
        )

    def _load_yaml_into(self, path: Any, *, is_default: bool) -> None:
        """Parse a YAML file and merge its entries into the registry."""
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for w_data in data.get("workers", []):
            worker = WorkerDef.from_dict(w_data)
            if worker.id not in self._workers or not is_default:
                self._workers[worker.id] = worker

        for s_data in data.get("skills", []):
            skill = SkillDef.from_dict(s_data)
            if skill.id not in self._skills or not is_default:
                self._skills[skill.id] = skill

    # ── Query API ────────────────────────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Full-text search across worker names, descriptions, and capabilities.

        Returns a list of matching entries with ``type`` (worker/skill) and
        the entry's fields.
        """
        self.load()
        q = query.lower()
        results: List[Dict[str, Any]] = []

        for w in self._workers.values():
            if (
                q in w.id.lower()
                or q in w.display_name.lower()
                or q in w.description.lower()
                or any(q in c.lower() for c in w.capabilities)
            ):
                results.append({"type": "worker", **asdict(w)})

        for s in self._skills.values():
            if (
                q in s.id.lower()
                or q in s.display_name.lower()
                or q in s.description.lower()
                or any(q in t.lower() for t in s.tags)
            ):
                results.append({"type": "skill", **asdict(s)})

        return results

    def match(self, capability: str) -> List[WorkerDef]:
        """Find workers that can fulfill a required capability.

        ``capability`` is a short string like "data_analysis", "chart_drawing",
        "ppt_generation", etc. Matches against worker capabilities and skill tags.
        """
        self.load()
        cap_lower = capability.lower().strip()
        matched: List[WorkerDef] = []

        for w in self._workers.values():
            # Direct capability match
            if any(cap_lower in c.lower() or c.lower() in cap_lower for c in w.capabilities):
                matched.append(w)
                continue
            # Skill tag match
            for sid in w.skill_ids:
                skill = self._skills.get(sid)
                if skill and any(cap_lower in t.lower() for t in skill.tags):
                    matched.append(w)
                    break

        return matched

    def get_worker(self, worker_id: str) -> Optional[WorkerDef]:
        """Get a worker by ID."""
        self.load()
        return self._workers.get(worker_id)

    def get_skill(self, skill_id: str) -> Optional[SkillDef]:
        """Get a skill by ID."""
        self.load()
        return self._skills.get(skill_id)

    def list_workers(self, role: Optional[str] = None) -> List[WorkerDef]:
        """List all workers, optionally filtered by role."""
        self.load()
        workers = list(self._workers.values())
        if role:
            workers = [w for w in workers if w.role == role]
        return workers

    def list_skills(self) -> List[SkillDef]:
        """List all registered skills."""
        self.load()
        return list(self._skills.values())

    # ── Mutation API ─────────────────────────────────────────────────────

    def register_worker(self, worker: WorkerDef) -> None:
        """Register a new worker (or update an existing one). Saves to disk."""
        self.load()
        self._workers[worker.id] = worker
        self._save_workers()

    def register_skill(self, skill: SkillDef) -> None:
        """Register a new skill (or update an existing one). Saves to disk."""
        self.load()
        self._skills[skill.id] = skill
        self._save_skills()

    def update_score(self, worker_id: str, score: float) -> None:
        """Update a worker's quality score (called by Evaluator)."""
        self.load()
        worker = self._workers.get(worker_id)
        if worker:
            worker.quality_score = score
            self._save_workers()

    def record_task_outcome(self, worker_id: str, success: bool) -> None:
        """Record a task completion outcome for a worker."""
        self.load()
        worker = self._workers.get(worker_id)
        if worker:
            worker.total_tasks += 1
            if success:
                worker.successful_tasks += 1
            self._save_workers()

    # ── Persistence ──────────────────────────────────────────────────────

    def _save_workers(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = {"workers": [asdict(w) for w in self._workers.values()]}
        with open(self.workers_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def _save_skills(self) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = {"skills": [asdict(s) for s in self._skills.values()]}
        with open(self.skills_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def generate_summary(self) -> str:
        """Generate a compact Agent List summary for injection into the Leader prompt.

        The Leader sees this summary so it knows which workers are available
        without querying the registry at every turn.
        """
        self.load()
        lines = ["## Available Workers", ""]
        for w in sorted(self._workers.values(), key=lambda x: x.display_name):
            caps = ", ".join(w.capabilities) if w.capabilities else "(general)"
            skills = ", ".join(w.skill_ids) if w.skill_ids else "(none)"
            score_str = f" score={w.quality_score:.1f}" if w.quality_score else ""
            lines.append(
                f"- **{w.display_name}** (`{w.id}`) [{w.model_tier}{score_str}] "
                f"— {w.description[:100]}"
            )
            lines.append(f"  capabilities: {caps}")
            lines.append(f"  skills: {skills}")

        if self._skills:
            lines.append("")
            lines.append("## Available Skills")
            for s in sorted(self._skills.values(), key=lambda x: x.display_name):
                tags = f" ({', '.join(s.tags)})" if s.tags else ""
                lines.append(f"- **{s.display_name}** (`{s.id}`){tags} — {s.description[:80]}")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# Module-level convenience instance
# ══════════════════════════════════════════════════════════════════════════

_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Return the module-level AgentRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        _registry.load()
    return _registry
