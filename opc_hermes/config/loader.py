"""Configuration loading for OPC-Hermes.

OPC-Hermes intentionally uses its own config file instead of adding keys
to Hermes Agent's config parser. The default location is:

    ~/.hermes/opc/config.yaml

The public loader returns the inner ``opc_hermes`` section merged with
defaults, so callers do not need to handle missing files or partial user
overrides.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Iterable, MutableMapping, Optional

import yaml


CONFIG_ROOT_KEY = "opc_hermes"


class OPCConfigError(ValueError):
    """Raised when an OPC-Hermes config file is malformed."""


def get_opc_home() -> Path:
    """Return the OPC-Hermes runtime home directory."""
    try:
        from hermes_constants import get_hermes_home

        hermes_home = Path(get_hermes_home())
    except ImportError:
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

    hermes_home = hermes_home.expanduser()
    if not hermes_home.is_absolute():
        raise OPCConfigError("HERMES_HOME must resolve to an absolute path.")
    if ".." in hermes_home.parts:
        raise OPCConfigError("HERMES_HOME must not contain '..' path segments.")
    return hermes_home / "opc"


def get_default_config_path() -> Path:
    """Return the default OPC config path."""
    return get_opc_home() / "config.yaml"


DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "allow_external_runtime_paths": False,
    "agent_list_path": None,
    "memory_path": None,
    "artifact_path": None,
    "proposal_path": None,
    "log_path": None,
    "leader_model": "${HERMES_DEFAULT_MODEL}",
    "routing": {
        "trigger_prefixes": ["/opc"],
        "auto_route_complex_tasks": False,
        "require_approval_for": ["MEDIUM", "COMPLEX"],
    },
    "model_preferences": {
        "global": {
            "preferred_provider": None,
            "max_cost_per_call": None,
        },
        "agents": {},
        "skills": {},
        "workflows": {},
    },
    "evaluator": {
        "enabled": True,
        "model": "claude-sonnet-4",
        "scoring_thresholds": {
            "overall": 0.7,
            "accuracy": 0.8,
            "leader_decomposition": 0.6,
        },
    },
    "optimizer": {
        "enabled": True,
        "cron_interval": "1h",
        "proposal": {
            "push_to_dashboard": True,
            "dedupe_window_days": 30,
        },
    },
    "knowledge_pipeline": {
        "enabled": False,
        "use_chromadb": False,
        "crawl_interval": "24h",
    },
    "webui": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 8765,
    },
}


PATH_KEYS = (
    "agent_list_path",
    "memory_path",
    "artifact_path",
    "proposal_path",
    "log_path",
)


def default_config() -> Dict[str, Any]:
    """Return a deep copy of the default OPC config."""
    return _build_default_config(get_opc_home())


def load_config(
    config_path: Optional[Path] = None,
    *,
    create: bool = False,
    allow_external_path: bool = False,
) -> Dict[str, Any]:
    """Load OPC config and merge it with defaults.

    Args:
        config_path: Optional config path. Defaults to ``~/.hermes/opc/config.yaml``.
        create: If true, write a default config when the file does not exist.
        allow_external_path: Allow ``create=True`` to write outside OPC home.
            This is mainly for tests and explicit administrative tooling.

    Returns:
        The merged inner ``opc_hermes`` config section.

    Raises:
        OPCConfigError: If the YAML file is not a mapping.
    """
    path = Path(config_path).expanduser() if config_path else get_default_config_path()

    if not path.exists():
        config = default_config()
        if create:
            save_config(config, path, allow_external_path=allow_external_path)
        return resolve_config_paths(expand_env_values(config))

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise OPCConfigError(f"Could not parse OPC config YAML: {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise OPCConfigError(f"Config file must contain a mapping: {path}")

    user_config = raw.get(CONFIG_ROOT_KEY, raw)
    if not isinstance(user_config, dict):
        raise OPCConfigError(f"'{CONFIG_ROOT_KEY}' must be a mapping in {path}")

    merged = _deep_merge(default_config(), user_config)
    _validate_config_types(merged, path)
    return resolve_config_paths(expand_env_values(merged))


def save_config(
    config: Dict[str, Any],
    config_path: Optional[Path] = None,
    *,
    allow_external_path: bool = False,
) -> Path:
    """Persist an OPC config using the standard top-level key."""
    path = _normalize_path(Path(config_path) if config_path else get_default_config_path())
    if not allow_external_path:
        _ensure_within(path, get_opc_home(), "Config path")

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass

    data = {CONFIG_ROOT_KEY: config}
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def resolve_config_paths(config: Dict[str, Any]) -> Dict[str, Any]:
    """Expand user-relative path values for well-known path keys."""
    resolved = copy.deepcopy(config)
    allow_external = bool(resolved.get("allow_external_runtime_paths"))
    opc_home = get_opc_home()
    for key in PATH_KEYS:
        value = resolved.get(key)
        if isinstance(value, str):
            path = _normalize_path(Path(value))
            if not allow_external:
                _ensure_within(path, opc_home, key)
            resolved[key] = str(path)
    return resolved


def expand_env_values(config: Dict[str, Any], key_path: tuple[str, ...] = ()) -> Dict[str, Any]:
    """Expand environment variables inside string config values."""
    if isinstance(config, dict):
        return {k: expand_env_values(v, (*key_path, k)) for k, v in config.items()}
    if isinstance(config, list):
        return [expand_env_values(v, key_path) for v in config]
    if isinstance(config, str):
        key = key_path[-1] if key_path else ""
        if key in (*PATH_KEYS, "leader_model"):
            return os.path.expandvars(config)
        return config
    return config


def get_config_value(config: Dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    """Read a nested config value using dot notation."""
    current: Any = config
    for part in _split_key(dotted_key):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_config_value(config: Dict[str, Any], dotted_key: str, value: Any) -> Dict[str, Any]:
    """Set a nested config value using dot notation and return a copy."""
    updated = copy.deepcopy(config)
    current: MutableMapping[str, Any] = updated
    parts = _split_key(dotted_key)
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value
    return updated


def _split_key(dotted_key: str) -> Iterable[str]:
    parts = [p for p in dotted_key.split(".") if p]
    if not parts:
        raise OPCConfigError("Config key must not be empty.")
    return parts


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _build_default_config(opc_home: Path) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["agent_list_path"] = str(opc_home / "agent_list")
    config["memory_path"] = str(opc_home / "memory")
    config["artifact_path"] = str(opc_home / "artifacts")
    config["proposal_path"] = str(opc_home / "proposals")
    config["log_path"] = str(opc_home / "logs")
    return config


def _normalize_path(path: Path) -> Path:
    return Path(os.path.expandvars(str(path.expanduser()))).resolve(strict=False)


def _ensure_within(path: Path, parent: Path, label: str) -> None:
    parent = parent.resolve(strict=False)
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise OPCConfigError(f"{label} must be inside OPC home ({parent}): {path}") from exc


def _validate_config_types(config: Dict[str, Any], path: Path) -> None:
    expected = {
        "enabled": bool,
        "allow_external_runtime_paths": bool,
        "agent_list_path": str,
        "memory_path": str,
        "artifact_path": str,
        "proposal_path": str,
        "log_path": str,
        "leader_model": str,
        "routing": dict,
        "model_preferences": dict,
        "evaluator": dict,
        "optimizer": dict,
        "knowledge_pipeline": dict,
        "webui": dict,
    }
    for key, expected_type in expected.items():
        if not isinstance(config.get(key), expected_type):
            raise OPCConfigError(
                f"Config key '{key}' in {path} must be {expected_type.__name__}."
            )

    nested_expected = {
        ("routing", "trigger_prefixes"): list,
        ("routing", "auto_route_complex_tasks"): bool,
        ("routing", "require_approval_for"): list,
        ("evaluator", "enabled"): bool,
        ("evaluator", "model"): str,
        ("evaluator", "scoring_thresholds"): dict,
        ("optimizer", "enabled"): bool,
        ("optimizer", "cron_interval"): str,
        ("optimizer", "proposal"): dict,
        ("knowledge_pipeline", "enabled"): bool,
        ("knowledge_pipeline", "use_chromadb"): bool,
        ("knowledge_pipeline", "crawl_interval"): str,
        ("webui", "enabled"): bool,
        ("webui", "host"): str,
        ("webui", "port"): int,
    }
    for key_path, expected_type in nested_expected.items():
        value = get_config_value(config, ".".join(key_path))
        if not isinstance(value, expected_type):
            dotted = ".".join(key_path)
            raise OPCConfigError(
                f"Config key '{dotted}' in {path} must be {expected_type.__name__}."
            )
