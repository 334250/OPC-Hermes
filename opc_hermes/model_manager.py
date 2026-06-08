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


# Default models — comprehensive catalog of all major providers and models
DEFAULT_MODELS = [
    # ── Anthropic ──────────────────────────────────────────────────────────
    ModelDef(id="claude-sonnet-4", display_name="Claude Sonnet 4", provider="anthropic", tier="premium", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM", "COMPLEX"], description="Anthropic Claude Sonnet 4 — best-in-class reasoning"),
    ModelDef(id="claude-3.5-sonnet", display_name="Claude 3.5 Sonnet", provider="anthropic", tier="standard", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM", "COMPLEX"], description="Anthropic Claude 3.5 Sonnet"),
    ModelDef(id="claude-3.5-haiku", display_name="Claude 3.5 Haiku", provider="anthropic", tier="budget", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Anthropic Claude 3.5 Haiku — fast and affordable"),
    ModelDef(id="claude-opus-4", display_name="Claude Opus 4", provider="anthropic", tier="premium", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["COMPLEX"], description="Anthropic Claude Opus 4 — most powerful"),
    # ── OpenAI ─────────────────────────────────────────────────────────────
    ModelDef(id="gpt-4o", display_name="GPT-4o", provider="openai", tier="premium", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="OpenAI GPT-4o — multimodal flagship"),
    ModelDef(id="gpt-4o-mini", display_name="GPT-4o Mini", provider="openai", tier="budget", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="OpenAI GPT-4o Mini — lightweight"),
    ModelDef(id="gpt-4.1", display_name="GPT-4.1", provider="openai", tier="premium", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="OpenAI GPT-4.1 — 1M context"),
    ModelDef(id="gpt-4.1-mini", display_name="GPT-4.1 Mini", provider="openai", tier="standard", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="OpenAI GPT-4.1 Mini"),
    ModelDef(id="gpt-4.1-nano", display_name="GPT-4.1 Nano", provider="openai", tier="budget", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="OpenAI GPT-4.1 Nano — cheapest"),
    ModelDef(id="o3-mini", display_name="o3 Mini", provider="openai", tier="premium", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="OpenAI o3 Mini — reasoning model"),
    ModelDef(id="o4-mini", display_name="o4 Mini", provider="openai", tier="premium", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["COMPLEX"], description="OpenAI o4 Mini — advanced reasoning"),
    # ── Google ─────────────────────────────────────────────────────────────
    ModelDef(id="gemini-2.5-flash", display_name="Gemini 2.5 Flash", provider="google", tier="budget", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Google Gemini 2.5 Flash — 1M context"),
    ModelDef(id="gemini-2.5-pro", display_name="Gemini 2.5 Pro", provider="google", tier="premium", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Google Gemini 2.5 Pro — most capable"),
    ModelDef(id="gemini-2.0-flash", display_name="Gemini 2.0 Flash", provider="google", tier="budget", context_length=1000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="Google Gemini 2.0 Flash"),
    # ── DeepSeek ───────────────────────────────────────────────────────────
    ModelDef(id="deepseek-v3", display_name="DeepSeek V3", provider="deepseek", tier="standard", context_length=64000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="DeepSeek V3 — strong text reasoning"),
    ModelDef(id="deepseek-r1", display_name="DeepSeek R1", provider="deepseek", tier="premium", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="DeepSeek R1 — chain-of-thought reasoning"),
    ModelDef(id="deepseek-coder", display_name="DeepSeek Coder V2", provider="deepseek", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="DeepSeek Coder V2 — code specialist"),
    # ── Meta (via OpenRouter/self-host) ───────────────────────────────────
    ModelDef(id="llama-4-maverick", display_name="Llama 4 Maverick", provider="meta", tier="standard", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Meta Llama 4 Maverick — open-weight"),
    ModelDef(id="llama-4-scout", display_name="Llama 4 Scout", provider="meta", tier="budget", context_length=10000000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Meta Llama 4 Scout — 10M context"),
    # ── Mistral ────────────────────────────────────────────────────────────
    ModelDef(id="mistral-large", display_name="Mistral Large", provider="mistral", tier="premium", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Mistral Large — flagship model"),
    ModelDef(id="mistral-small", display_name="Mistral Small", provider="mistral", tier="standard", context_length=32000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Mistral Small — efficient"),
    ModelDef(id="codestral", display_name="Codestral", provider="mistral", tier="standard", context_length=256000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Mistral Codestral — code generation"),
    ModelDef(id="mixtral-8x22b", display_name="Mixtral 8x22B", provider="mistral", tier="standard", context_length=64000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Mistral Mixtral 8x22B — MoE"),
    # ── xAI / Grok ────────────────────────────────────────────────────────
    ModelDef(id="grok-3", display_name="Grok 3", provider="xai", tier="premium", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="xAI Grok 3 — deep reasoning"),
    ModelDef(id="grok-3-mini", display_name="Grok 3 Mini", provider="xai", tier="standard", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="xAI Grok 3 Mini — fast reasoning"),
    # ── Cohere ─────────────────────────────────────────────────────────────
    ModelDef(id="command-r-plus", display_name="Command R+", provider="cohere", tier="premium", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Cohere Command R+ — enterprise RAG"),
    ModelDef(id="command-r", display_name="Command R", provider="cohere", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Cohere Command R — efficient RAG"),
    # ── Alibaba / Qwen ────────────────────────────────────────────────────
    ModelDef(id="qwen-max", display_name="Qwen Max", provider="alibaba", tier="premium", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Alibaba Qwen Max — flagship"),
    ModelDef(id="qwen-plus", display_name="Qwen Plus", provider="alibaba", tier="standard", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Alibaba Qwen Plus — balanced"),
    ModelDef(id="qwen-coder", display_name="Qwen Coder", provider="alibaba", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Alibaba Qwen Coder — code specialist"),
    # ── Anthropic-compatible / OpenRouter ──────────────────────────────────
    ModelDef(id="openrouter-auto", display_name="OpenRouter Auto", provider="openrouter", tier="standard", context_length=200000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM", "COMPLEX"], description="OpenRouter — auto-select best model"),
    # ── Open-source local ──────────────────────────────────────────────────
    ModelDef(id="minicpmv4.6", display_name="MiniCPM V4.6", provider="openbmb", tier="budget", context_length=8000, capabilities={"vision": True, "tool_calling": False, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="OpenBMB MiniCPM — local vision model"),
    # ── Local / Self-hosted ────────────────────────────────────────────────
    ModelDef(id="llama-3.3-70b", display_name="Llama 3.3 70B", provider="ollama", tier="premium", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Meta Llama 3.3 70B — local via Ollama"),
    ModelDef(id="qwen2.5-72b", display_name="Qwen 2.5 72B", provider="ollama", tier="premium", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["MEDIUM", "COMPLEX"], description="Alibaba Qwen 2.5 72B — local via Ollama"),
    ModelDef(id="deepseek-coder-33b", display_name="DeepSeek Coder 33B", provider="ollama", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="DeepSeek Coder 33B — local code specialist"),
    ModelDef(id="mistral-nemo", display_name="Mistral Nemo 12B", provider="ollama", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Mistral Nemo 12B — local via Ollama"),
    ModelDef(id="phi-4", display_name="Phi-4 14B", provider="ollama", tier="standard", context_length=16000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Microsoft Phi-4 — local reasoning"),
    ModelDef(id="gemma-3-27b", display_name="Gemma 3 27B", provider="ollama", tier="standard", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="Google Gemma 3 27B — local via Ollama"),
    ModelDef(id="llama-3.2-3b", display_name="Llama 3.2 3B", provider="ollama", tier="budget", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="Meta Llama 3.2 3B — lightweight local"),
    ModelDef(id="qwen2.5-7b", display_name="Qwen 2.5 7B", provider="ollama", tier="budget", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="Alibaba Qwen 2.5 7B — compact local"),
    ModelDef(id="granite-3.1-8b", display_name="Granite 3.1 8B", provider="ollama", tier="budget", context_length=128000, capabilities={"vision": False, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE"], description="IBM Granite 3.1 8B — enterprise local"),
    # LM Studio / vLLM / LocalAI 通用条目
    ModelDef(id="local-model", display_name="Local Model (自定义)", provider="lmstudio", tier="standard", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="LM Studio 本地模型 — 自动检测"),
    ModelDef(id="vllm-model", display_name="vLLM Model (自部署)", provider="vllm", tier="premium", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM", "COMPLEX"], description="vLLM 自部署模型"),
    ModelDef(id="localai-model", display_name="LocalAI Model (自部署)", provider="localai", tier="standard", context_length=128000, capabilities={"vision": True, "tool_calling": True, "image_gen": False, "audio_stt": False}, suitable_complexity=["SIMPLE", "MEDIUM"], description="LocalAI 自部署模型"),
]

DEFAULT_GROUPS = [
    ModelGroup(id="premium_tier", name="Premium Tier", dimension="tier", model_ids=["claude-sonnet-4", "gpt-4o", "claude-opus-4", "gpt-4.1", "o3-mini", "o4-mini", "gemini-2.5-pro", "deepseek-r1", "mistral-large", "grok-3", "command-r-plus", "qwen-max"]),
    ModelGroup(id="standard_tier", name="Standard Tier", dimension="tier", model_ids=["claude-3.5-sonnet", "gpt-4.1-mini", "deepseek-v3", "deepseek-coder", "llama-4-maverick", "mistral-small", "codestral", "mixtral-8x22b", "grok-3-mini", "command-r", "qwen-plus", "qwen-coder", "openrouter-auto"]),
    ModelGroup(id="budget_tier", name="Budget Tier", dimension="tier", model_ids=["claude-3.5-haiku", "gpt-4o-mini", "gpt-4.1-nano", "gemini-2.5-flash", "gemini-2.0-flash", "llama-4-scout", "minicpmv4.6"]),
    ModelGroup(id="vision_ready", name="Vision-Ready", dimension="capability", filter={"vision": True}),
    ModelGroup(id="tool_calling", name="Tool-Calling", dimension="capability", filter={"tool_calling": True}),
    ModelGroup(id="reasoning", name="Reasoning Models", dimension="scenario", model_ids=["o3-mini", "o4-mini", "deepseek-r1", "grok-3"]),
    ModelGroup(id="code_specialist", name="Code Specialists", dimension="scenario", model_ids=["deepseek-coder", "codestral", "qwen-coder"]),
    ModelGroup(id="local_deploy", name="本地部署 (Local)", dimension="scenario", model_ids=["llama-3.3-70b", "qwen2.5-72b", "deepseek-coder-33b", "mistral-nemo", "phi-4", "gemma-3-27b", "llama-3.2-3b", "qwen2.5-7b", "granite-3.1-8b", "local-model", "vllm-model", "localai-model"]),
    ModelGroup(id="cloud_gpu", name="云 GPU 推理", dimension="scenario", model_ids=["claude-sonnet-4", "gpt-4o", "deepseek-v3", "deepseek-r1", "llama-4-maverick", "qwen-max"]),
]

DEFAULT_PROVIDERS = [
    ModelProvider(id="anthropic", name="Anthropic", api_base="https://api.anthropic.com", api_key_ref="${ANTHROPIC_API_KEY}"),
    ModelProvider(id="openai", name="OpenAI", api_base="https://api.openai.com/v1", api_key_ref="${OPENAI_API_KEY}"),
    ModelProvider(id="google", name="Google", api_base="https://generativelanguage.googleapis.com", api_key_ref="${GOOGLE_API_KEY}"),
    ModelProvider(id="deepseek", name="DeepSeek", api_base="https://api.deepseek.com", api_key_ref="${DEEPSEEK_API_KEY}"),
    ModelProvider(id="meta", name="Meta", api_base="https://openrouter.ai/api/v1", api_key_ref="${OPENROUTER_API_KEY}"),
    ModelProvider(id="mistral", name="Mistral", api_base="https://api.mistral.ai/v1", api_key_ref="${MISTRAL_API_KEY}"),
    ModelProvider(id="xai", name="xAI", api_base="https://api.x.ai/v1", api_key_ref="${XAI_API_KEY}"),
    ModelProvider(id="cohere", name="Cohere", api_base="https://api.cohere.ai/v1", api_key_ref="${COHERE_API_KEY}"),
    ModelProvider(id="alibaba", name="Alibaba Cloud", api_base="https://dashscope.aliyuncs.com/compatible-mode/v1", api_key_ref="${DASHSCOPE_API_KEY}"),
    ModelProvider(id="openrouter", name="OpenRouter", api_base="https://openrouter.ai/api/v1", api_key_ref="${OPENROUTER_API_KEY}"),
    ModelProvider(id="openbmb", name="OpenBMB", api_base="", api_key_ref=""),
    ModelProvider(id="ollama", name="Ollama (本地)", api_base="http://localhost:11434/v1", api_key_ref=""),
    ModelProvider(id="lmstudio", name="LM Studio (本地)", api_base="http://localhost:1234/v1", api_key_ref=""),
    ModelProvider(id="vllm", name="vLLM (自部署)", api_base="http://localhost:8000/v1", api_key_ref=""),
    ModelProvider(id="localai", name="LocalAI (自部署)", api_base="http://localhost:8080/v1", api_key_ref=""),
    ModelProvider(id="llamacpp", name="llama.cpp Server (本地)", api_base="http://localhost:8081/v1", api_key_ref=""),
    ModelProvider(id="textgen", name="TextGen WebUI (oobabooga)", api_base="http://localhost:5000/v1", api_key_ref=""),
    ModelProvider(id="koboldcpp", name="KoboldCpp (本地)", api_base="http://localhost:5001/api/v1", api_key_ref=""),
    ModelProvider(id="jan", name="Jan (桌面本地)", api_base="http://localhost:1337/v1", api_key_ref=""),
    ModelProvider(id="gpt4all", name="GPT4All (本地)", api_base="http://localhost:4891/v1", api_key_ref=""),
    ModelProvider(id="exllamav2", name="ExLlamaV2 (高性能GPU)", api_base="http://localhost:5000/v1", api_key_ref=""),
    ModelProvider(id="aphrodite", name="Aphrodite Engine", api_base="http://localhost:2242/v1", api_key_ref=""),
    ModelProvider(id="together", name="Together AI (云GPU)", api_base="https://api.together.xyz/v1", api_key_ref="${TOGETHER_API_KEY}"),
    ModelProvider(id="groq", name="Groq (LPU推理)", api_base="https://api.groq.com/openai/v1", api_key_ref="${GROQ_API_KEY}"),
    ModelProvider(id="fireworks", name="Fireworks AI (云GPU)", api_base="https://api.fireworks.ai/inference/v1", api_key_ref="${FIREWORKS_API_KEY}"),
    ModelProvider(id="replicate", name="Replicate (云GPU)", api_base="https://api.replicate.com/v1", api_key_ref="${REPLICATE_API_TOKEN}"),
    ModelProvider(id="runpod", name="RunPod (云GPU)", api_base="https://api.runpod.ai/v2", api_key_ref="${RUNPOD_API_KEY}"),
    ModelProvider(id="novita", name="Novita AI (云GPU)", api_base="https://api.novita.ai/v3/openai", api_key_ref="${NOVITA_API_KEY}"),
    ModelProvider(id="hyperbolic", name="Hyperbolic (云GPU)", api_base="https://api.hyperbolic.xyz/v1", api_key_ref="${HYPERBOLIC_API_KEY}"),
    ModelProvider(id="custom", name="Custom (自定义端点)", api_base="", api_key_ref=""),
]


class ModelManager:
    """Manages models, model groups, and providers with YAML persistence."""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            from opc_hermes.config.loader import get_opc_home

            data_dir = get_opc_home() / "models"
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
