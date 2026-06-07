"""
Pipeline Template Manager — CRUD for pipeline templates.

Stores pipeline definitions in ~/.hermes/opc/pipelines/templates.yaml
Each template defines a reusable workflow: which workers, what order,
memory strategy, failure policy, etc.

Design reference: OPC-Hermes产品设计文档.md §3.5.4
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class PipelineStep:
    """A single step in a pipeline template."""
    index: int
    worker_id: str
    prompt_template: str = ""
    expected_output_format: str = "markdown"
    timeout_seconds: int = 600
    model_override: Optional[str] = None
    upstream: List[int] = field(default_factory=list)
    memory_mode: str = "A"  # A/B/C/D

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineStep":
        return cls(
            index=data["index"],
            worker_id=data["worker_id"],
            prompt_template=data.get("prompt_template", ""),
            expected_output_format=data.get("expected_output_format", "markdown"),
            timeout_seconds=data.get("timeout_seconds", 600),
            model_override=data.get("model_override"),
            upstream=data.get("upstream", []),
            memory_mode=data.get("memory_mode", "A"),
        )


@dataclass
class PipelineTemplate:
    """A reusable pipeline template."""
    id: str
    name: str
    description: str = ""
    group_id: Optional[str] = None
    mode: str = "pipeline"  # pipeline | scatter | star | consensus | hierarchy
    default_complexity: str = "auto"
    memory_strategy: Dict[str, str] = field(default_factory=lambda: {"worker_to_worker": "mode_A"})
    failure_policy: str = "retry_then_skip"
    require_approval: str = "medium_and_above"
    steps: List[PipelineStep] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineTemplate":
        steps = [PipelineStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            group_id=data.get("group_id"),
            mode=data.get("mode", "pipeline"),
            default_complexity=data.get("default_complexity", "auto"),
            memory_strategy=data.get("memory_strategy", {"worker_to_worker": "mode_A"}),
            failure_policy=data.get("failure_policy", "retry_then_skip"),
            require_approval=data.get("require_approval", "medium_and_above"),
            steps=steps,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_execution_plan(self, user_request: str) -> Dict[str, Any]:
        """Convert this template into an executable task plan for the dispatcher."""
        return {
            "task_id": f"opc-{uuid.uuid4().hex[:12]}",
            "title": self.name,
            "complexity": {"level": "MEDIUM", "confidence": 0.8},
            "mode": self.mode,
            "requires_user_approval": self.require_approval != "never",
            "steps": [
                {
                    "index": s.index,
                    "worker_id": s.worker_id,
                    "prompt": s.prompt_template.replace("{{ user_request }}", user_request),
                    "upstream": s.upstream,
                    "expected_output_format": s.expected_output_format,
                    "model_override": s.model_override,
                    "timeout_seconds": s.timeout_seconds,
                }
                for s in self.steps
            ],
        }


class PipelineManager:
    """Manages pipeline templates with YAML persistence."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            try:
                from hermes_constants import get_hermes_home
                data_dir = get_hermes_home() / "opc" / "pipelines"
            except ImportError:
                data_dir = Path.home() / ".hermes" / "opc" / "pipelines"
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def templates_file(self) -> Path:
        return self._data_dir / "templates.yaml"

    def load_all(self) -> List[PipelineTemplate]:
        if not self.templates_file.exists():
            return []
        with open(self.templates_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [PipelineTemplate.from_dict(t) for t in data.get("templates", [])]

    def get(self, template_id: str) -> Optional[PipelineTemplate]:
        for t in self.load_all():
            if t.id == template_id:
                return t
        return None

    def save(self, template: PipelineTemplate) -> None:
        templates = self.load_all()
        # Replace if exists
        templates = [t for t in templates if t.id != template.id]
        templates.append(template)
        self._save_all(templates)

    def delete(self, template_id: str) -> bool:
        templates = self.load_all()
        if not any(t.id == template_id for t in templates):
            return False
        templates = [t for t in templates if t.id != template_id]
        self._save_all(templates)
        return True

    def _save_all(self, templates: List[PipelineTemplate]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        data = {
            "templates": [
                {
                    **asdict(t),
                    "steps": [asdict(s) for s in t.steps],
                    "created_at": t.created_at or datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                for t in templates
            ]
        }
        with open(self.templates_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


# Five preset templates from the design doc
PRESET_TEMPLATES = [
    PipelineTemplate(
        id="doc_production_full",
        name="文档制作完整流程",
        description="从调研到最终 PPT 的完整文档制作流水线",
        mode="pipeline",
        steps=[
            PipelineStep(index=0, worker_id="researcher", prompt_template="Research: {{ user_request }}", timeout_seconds=600),
            PipelineStep(index=1, worker_id="writer", prompt_template="Write report based on research: {{ user_request }}", upstream=[0], timeout_seconds=900),
            PipelineStep(index=2, worker_id="illustrator", prompt_template="Create charts for: {{ user_request }}", upstream=[0], timeout_seconds=600),
            PipelineStep(index=3, worker_id="ppt_maker", prompt_template="Build PPT from findings: {{ user_request }}", upstream=[1, 2], timeout_seconds=900),
            PipelineStep(index=4, worker_id="reviewer", prompt_template="Review final output: {{ user_request }}", upstream=[3], timeout_seconds=300),
        ],
    ),
    PipelineTemplate(
        id="quick_research",
        name="快速研究报告",
        description="精简的研究报告流程",
        mode="pipeline",
        steps=[
            PipelineStep(index=0, worker_id="researcher", prompt_template="Research: {{ user_request }}", timeout_seconds=300),
            PipelineStep(index=1, worker_id="writer", prompt_template="Write: {{ user_request }}", upstream=[0], timeout_seconds=600),
            PipelineStep(index=2, worker_id="reviewer", prompt_template="Review: {{ user_request }}", upstream=[1], timeout_seconds=200),
        ],
    ),
    PipelineTemplate(
        id="backend_dev",
        name="后端功能开发",
        description="后端 API 开发完整流程",
        mode="pipeline",
        steps=[
            PipelineStep(index=0, worker_id="software_architect", prompt_template="Design architecture: {{ user_request }}", timeout_seconds=900),
            PipelineStep(index=1, worker_id="backend_engineer", prompt_template="Implement: {{ user_request }}", upstream=[0], timeout_seconds=1200),
            PipelineStep(index=2, worker_id="qa_engineer", prompt_template="Test: {{ user_request }}", upstream=[1], timeout_seconds=600),
            PipelineStep(index=3, worker_id="code_reviewer", prompt_template="Review: {{ user_request }}", upstream=[1], timeout_seconds=600),
        ],
    ),
    PipelineTemplate(
        id="security_audit",
        name="安全审计",
        description="Star Delegation 安全审计流程",
        mode="star",
        memory_strategy={"worker_to_worker": "mode_B"},
        steps=[
            PipelineStep(index=0, worker_id="security_engineer", prompt_template="Security audit: {{ user_request }}", timeout_seconds=1200, memory_mode="B"),
            PipelineStep(index=1, worker_id="code_reviewer", prompt_template="Code review: {{ user_request }}", timeout_seconds=900, memory_mode="B"),
            PipelineStep(index=2, worker_id="qa_engineer", prompt_template="QA verification: {{ user_request }}", timeout_seconds=600, memory_mode="B"),
        ],
    ),
    PipelineTemplate(
        id="data_analysis",
        name="数据分析报告",
        description="数据分析到 PPT 的完整流程",
        mode="pipeline",
        steps=[
            PipelineStep(index=0, worker_id="data_analyst", prompt_template="Analyze data: {{ user_request }}", timeout_seconds=900),
            PipelineStep(index=1, worker_id="illustrator", prompt_template="Visualize: {{ user_request }}", upstream=[0], timeout_seconds=600),
            PipelineStep(index=2, worker_id="ppt_maker", prompt_template="Create presentation: {{ user_request }}", upstream=[0, 1], timeout_seconds=900),
        ],
    ),
]
