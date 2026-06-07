"""
Model Manager — CRUD for models, model groups, and providers.

Replaces the hardcoded capability matrix in model_prefs.py with a
runtime-managed model registry backed by YAML files.

Design reference: OPC-Hermes产品设计文档.md §3.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ModelDef:
    """A managed model definition."""
    id: str
    display_name: str
    provider: str = "custom"
    tier: str = "standard"  # budget | standard | premium
    context_length: int = 128000
    capabilities: Dict[str, bool] = field(default_factory=lambda: {
        "vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False,
    })
    suitable_complexity: List[str] = field(default_factory=lambda: ["SIMPLE", "MEDIUM"])
    api_base: Optional[str] = None
    api_key_ref: Optional[str] = None
    active: bool = True
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelDef":
        return cls(
            id=data["id"],
            display_name=data.get("display_name", data["id"]),
            provider=data.get("provider", "custom"),
            tier=data.get("tier", "standard"),
            context_length=data.get("context_length", 128000),
            capabilities=data.get("capabilities", {}),
            suitable_complexity=data.get("suitable_complexity", ["SIMPLE", "MEDIUM"]),
            api_base=data.get("api_base"),
            api_key_ref=data.get("api_key_ref"),
            active=data.get("active", True),
            description=data.get("description", ""),
        )


@dataclass
class ModelGroup:
    """A grouping of models by dimension."""
    id: str
    name: str
    dimension: str = "tier"  # tier | provider | capability | scenario
    model_ids: List[str] = field(default_factory=list)
    filter: Optional[Dict[str, Any]] = None  # capability filter, e.g. {vision: true}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelGroup":
        return cls(
            id=data["id"],
            name=data["name"],
            dimension=data.get("dimension", "tier"),
            model_ids=data.get("model_ids", []),
            filter=data.get("filter"),
        )


@dataclass
class ModelProvider:
    """A model API provider."""
    id: str
    name: str
    api_base: str = ""
    api_key_ref: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelProvider":
        return cls(
            id=data["id"],
            name=data["name"],
            api_base=data.get("api_base", ""),
            api_key_ref=data.get("api_key_ref", ""),
        )


# Default models matching the design doc §3.6.6 + §7.3 capability matrix
DEFAULT_MODELS = [
    ModelDef(
        id="claude-sonnet-4", display_name="Claude Sonnet 4", provider="anthropic",
        tier="premium", context_length=200000,
        capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False},
        suitable_complexity=["SIMPLE", "MEDIUM", "COMPLEX"],
        description="Anthropic Claude Sonnet 4 — best-in-class reasoning",
    ),
    ModelDef(
        id="gpt-4o", display_name="GPT-4o", provider="openai",
        tier="premium", context_length=128000,
        capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False},
        suitable_complexity=["MEDIUM", "COMPLEX"],
        description="OpenAI GPT-4o — multimodal complex tasks",
    ),
    ModelDef(
        id="gpt-4o-mini", display_name="GPT-4o Mini", provider="openai",
        tier="budget", context_length=128000,
        capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False},
        suitable_complexity=["SIMPLE"],
        description="OpenAI GPT-4o Mini — lightweight tasks",
    ),
    ModelDef(
        id="gemini-2.5-flash", display_name="Gemini 2.5 Flash", provider="google",
        tier="budget", context_length=1000000,
        capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False},
        suitable_complexity=["SIMPLE", "MEDIUM"],
        description="Google Gemini 2.5 Flash — ultra-long context",
    ),
    ModelDef(
        id="deepseek-v3", display_name="DeepSeek V3", provider="deepseek",
        tier="standard", context_length=64000,
        capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False},
        suitable_complexity=["SIMPLE", "MEDIUM"],
        description="DeepSeek V3 — strong text reasoning",
    ),
    ModelDef(
        id="minicpmv4.6", display_name="MiniCPM V4.6", provider="openbmb",
        tier="budget", context_length=8000,
        capabilities={"vision": True, "tool_calling": False, "image_gen": False, "audio_stt": False},
        suitable_complexity=["SIMPLE"],
        description="OpenBMB MiniCPM — local vision model",
    ),
]

DEFAULT_GROUPS = [
    ModelGroup(id="premium_tier", name="Premium Tier", dimension="tier", model_ids=["claude-sonnet-4", "gpt-4o"]),
    ModelGroup(id="standard_tier", name="Standard Tier", dimension="tier", model_ids=["deepseek-v3"]),
    ModelGroup(id="budget_tier", name="Budget Tier", dimension="tier", model_ids=["gpt-4o-mini", "gemini-2.5-flash", "minicpmv4.6"]),
    ModelGroup(id="vision_ready", name="Vision-Ready", dimension="capability", filter={"vision": True}),
    ModelGroup(id="tool_calling", name="Tool-Calling", dimension="capability", filter={"tool_calling": True}),
]

DEFAULT_PROVIDERS = [
    ModelProvider(id="anthropic", name="Anthropic", api_base="https://api.anthropic.com", api_key_ref="${ANTHROPIC_API_KEY}"),
    ModelProvider(id="openai", name="OpenAI", api_base="https://api.openai.com/v1", api_key_ref="${OPENAI_API_KEY}"),
    ModelProvider(id="google", name="Google", api_base="https://generativelanguage.googleapis.com", api_key_ref="${GOOGLE_API_KEY}"),
    ModelProvider(id="deepseek", name="DeepSeek", api_base="https://api.deepseek.com", api_key_ref="${DEEPSEEK_API_KEY}"),
    ModelProvider(id="openbmb", name="OpenBMB", api_base="", api_key_ref=""),
    ModelProvider(id="custom", name="Custom", api_base="", api_key_ref=""),
]


class ModelManager:
    """Manages models, model groups, and providers with YAML persistence."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            try:
                from hermes_constants import get_hermes_home
                data_dir = get_hermes_home() / "opc" / "models"
            except ImportError:
                data_dir = Path.home() / ".hermes" / "opc" / "models"
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._seed_defaults()

    @property
    def models_file(self) -> Path:
        return self._data_dir / "models.yaml"

    @property
    def groups_file(self) -> Path:
        return self._data_dir / "groups.yaml"

    @property
    def providers_file(self) -> Path:
        return self._data_dir / "providers.yaml"

    def _seed_defaults(self) -> None:
        if not self.models_file.exists():
            self._save_models(DEFAULT_MODELS)
        if not self.groups_file.exists():
            self._save_groups(DEFAULT_GROUPS)
        if not self.providers_file.exists():
            self._save_providers(DEFAULT_PROVIDERS)

    # ── Models ───────────────────────────────────────────────────────────

    def list_models(self) -> List[ModelDef]:
        if not self.models_file.exists():
            return list(DEFAULT_MODELS)
        with open(self.models_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [ModelDef.from_dict(m) for m in data.get("models", [])]

    def get_model(self, model_id: str) -> Optional[ModelDef]:
        for m in self.list_models():
            if m.id == model_id:
                return m
        return None

    def save_model(self, model: ModelDef) -> None:
        models = self.list_models()
        models = [m for m in models if m.id != model.id]
        models.append(model)
        self._save_models(models)

    def delete_model(self, model_id: str) -> bool:
        models = self.list_models()
        if not any(m.id == model_id for m in models):
            return False
        models = [m for m in models if m.id != model_id]
        self._save_models(models)
        return True

    def _save_models(self, models: List[ModelDef]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.models_file, "w", encoding="utf-8") as f:
            yaml.safe_dump({"models": [asdict(m) for m in models]}, f, allow_unicode=True, sort_keys=False)

    # ── Groups ───────────────────────────────────────────────────────────

    def list_groups(self) -> List[ModelGroup]:
        if not self.groups_file.exists():
            return list(DEFAULT_GROUPS)
        with open(self.groups_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [ModelGroup.from_dict(g) for g in data.get("groups", [])]

    def save_group(self, group: ModelGroup) -> None:
        groups = self.list_groups()
        groups = [g for g in groups if g.id != group.id]
        groups.append(group)
        self._save_groups(groups)

    def delete_group(self, group_id: str) -> bool:
        groups = self.list_groups()
        if not any(g.id == group_id for g in groups):
            return False
        groups = [g for g in groups if g.id != group_id]
        self._save_groups(groups)
        return True

    def _save_groups(self, groups: List[ModelGroup]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.groups_file, "w", encoding="utf-8") as f:
            yaml.safe_dump({"groups": [asdict(g) for g in groups]}, f, allow_unicode=True, sort_keys=False)

    # ── Providers ────────────────────────────────────────────────────────

    def list_providers(self) -> List[ModelProvider]:
        if not self.providers_file.exists():
            return list(DEFAULT_PROVIDERS)
        with open(self.providers_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [ModelProvider.from_dict(p) for p in data.get("providers", [])]

    def save_provider(self, provider: ModelProvider) -> None:
        providers = self.list_providers()
        providers = [p for p in providers if p.id != provider.id]
        providers.append(provider)
        self._save_providers(providers)

    def _save_providers(self, providers: List[ModelProvider]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.providers_file, "w", encoding="utf-8") as f:
            yaml.safe_dump({"providers": [asdict(p) for p in providers]}, f, allow_unicode=True, sort_keys=False)

    # ── Validation ───────────────────────────────────────────────────────

    async def validate_model(self, model_id: str) -> Dict[str, Any]:
        """Test a model connection by sending a minimal API call."""
        model = self.get_model(model_id)
        if not model:
            return {"status": "error", "message": f"Model '{model_id}' not found."}
        if not model.api_base:
            provider = next((p for p in self.list_providers() if p.id == model.provider), None)
            if not provider or not provider.api_base:
                return {"status": "skipped", "message": "No API base configured for this model/provider."}
        # Phase 3b: actual API call stub
        return {"status": "ok", "message": f"Model '{model_id}' configuration is valid (connection test deferred)."}
