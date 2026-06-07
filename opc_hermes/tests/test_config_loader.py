import pytest
import yaml

from opc_hermes.config.loader import (
    CONFIG_ROOT_KEY,
    OPCConfigError,
    default_config,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)


def test_load_config_returns_defaults_when_file_is_missing(tmp_path):
    config_path = tmp_path / "missing-config.yaml"

    config = load_config(config_path)

    assert config_path.exists() is False
    assert config["enabled"] is True
    assert config["routing"]["trigger_prefixes"] == ["/opc"]
    assert config["routing"]["auto_route_complex_tasks"] is False
    assert config["evaluator"]["scoring_thresholds"]["overall"] == 0.7
    assert "agent_list_path" in config
    assert "memory_path" in config


def test_default_config_returns_independent_deep_copies():
    first = default_config()
    second = default_config()

    first["routing"]["trigger_prefixes"].append("/changed")
    first["model_preferences"]["agents"]["leader"] = {"model": "test-model"}

    assert second["routing"]["trigger_prefixes"] == ["/opc"]
    assert second["model_preferences"]["agents"] == {}


def test_load_config_create_true_writes_default_wrapped_config(tmp_path):
    config_path = tmp_path / "nested" / "config.yaml"

    config = load_config(config_path, create=True, allow_external_path=True)

    assert config_path.exists()
    written = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert set(written.keys()) == {CONFIG_ROOT_KEY}
    assert written[CONFIG_ROOT_KEY]["enabled"] is True
    assert written[CONFIG_ROOT_KEY]["routing"]["trigger_prefixes"] == ["/opc"]
    assert config["enabled"] is True
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert config_path.parent.stat().st_mode & 0o777 == 0o700


def test_save_config_rejects_external_path_without_explicit_escape_hatch(tmp_path):
    config_path = tmp_path / "config.yaml"

    with pytest.raises(OPCConfigError):
        save_config(default_config(), config_path)


def test_save_config_allows_external_path_with_explicit_escape_hatch(tmp_path):
    config_path = tmp_path / "config.yaml"

    written_path = save_config(
        default_config(),
        config_path,
        allow_external_path=True,
    )

    assert written_path == config_path.resolve(strict=False)
    assert config_path.exists()
    assert config_path.stat().st_mode & 0o777 == 0o600
    assert config_path.parent.stat().st_mode & 0o777 == 0o700


def test_load_config_accepts_top_level_opc_hermes_wrapped_overrides(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                CONFIG_ROOT_KEY: {
                    "enabled": False,
                    "leader_model": "gpt-test",
                    "routing": {
                        "trigger_prefixes": ["/oh"],
                        "auto_route_complex_tasks": True,
                    },
                    "webui": {
                        "enabled": True,
                        "port": 9999,
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["enabled"] is False
    assert config["leader_model"] == "gpt-test"
    assert config["routing"]["trigger_prefixes"] == ["/oh"]
    assert config["routing"]["auto_route_complex_tasks"] is True
    assert config["routing"]["require_approval_for"] == ["MEDIUM", "COMPLEX"]
    assert config["webui"]["enabled"] is True
    assert config["webui"]["host"] == "127.0.0.1"
    assert config["webui"]["port"] == 9999


def test_load_config_accepts_flat_config_overrides(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "enabled": False,
                "allow_external_runtime_paths": True,
                "artifact_path": str(tmp_path / "custom-artifacts"),
                "optimizer": {
                    "enabled": False,
                    "proposal": {
                        "dedupe_window_days": 7,
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["enabled"] is False
    assert config["artifact_path"] == str(tmp_path / "custom-artifacts")
    assert config["optimizer"]["enabled"] is False
    assert config["optimizer"]["cron_interval"] == "1h"
    assert config["optimizer"]["proposal"]["push_to_dashboard"] is True
    assert config["optimizer"]["proposal"]["dedupe_window_days"] == 7


def test_load_config_expands_environment_variables_in_string_values(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("OPC_TEST_ROOT", str(tmp_path / "env-root"))
    config_path.write_text(
        yaml.safe_dump(
            {
                "allow_external_runtime_paths": True,
                "agent_list_path": "${OPC_TEST_ROOT}/agents",
                "leader_model": "${OPC_TEST_MODEL}",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config["agent_list_path"] == str(tmp_path / "env-root" / "agents")
    assert config["leader_model"] == "${OPC_TEST_MODEL}"


def test_load_config_rejects_external_runtime_paths_by_default(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({"artifact_path": str(tmp_path / "outside-artifacts")}),
        encoding="utf-8",
    )

    with pytest.raises(OPCConfigError):
        load_config(config_path)


def test_default_config_uses_current_hermes_home_after_import(monkeypatch, tmp_path):
    hermes_home = tmp_path / "hermes-home"
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    config = default_config()

    assert config["agent_list_path"] == str(hermes_home / "opc" / "agent_list")
    assert config["memory_path"] == str(hermes_home / "opc" / "memory")


def test_dot_key_get_and_set_work_on_nested_config_without_mutating_original():
    config = default_config()

    updated = set_config_value(config, "routing.auto_route_complex_tasks", True)
    updated = set_config_value(updated, "model_preferences.agents.leader.model", "gpt-test")
    updated = set_config_value(updated, "new.section.value", 42)

    assert get_config_value(updated, "routing.auto_route_complex_tasks") is True
    assert get_config_value(updated, "model_preferences.agents.leader.model") == "gpt-test"
    assert get_config_value(updated, "new.section.value") == 42
    assert get_config_value(updated, "missing.value", default="fallback") == "fallback"
    assert config["routing"]["auto_route_complex_tasks"] is False
    assert config["model_preferences"]["agents"] == {}


@pytest.mark.parametrize("dotted_key", ["", ".", ".."])
def test_dot_key_helpers_reject_empty_keys(dotted_key):
    with pytest.raises(OPCConfigError):
        get_config_value({}, dotted_key)

    with pytest.raises(OPCConfigError):
        set_config_value({}, dotted_key, "value")


@pytest.mark.parametrize(
    "yaml_text",
    [
        "- not\n- a\n- mapping\n",
        "just a string\n",
    ],
)
def test_load_config_rejects_non_mapping_yaml(tmp_path, yaml_text):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(OPCConfigError):
        load_config(config_path)


def test_load_config_rejects_non_mapping_top_level_opc_hermes_section(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({CONFIG_ROOT_KEY: ["not", "a", "mapping"]}),
        encoding="utf-8",
    )

    with pytest.raises(OPCConfigError):
        load_config(config_path)


@pytest.mark.parametrize(
    "config",
    [
        {"routing": "bad"},
        {"routing": {"trigger_prefixes": "/opc"}},
        {"evaluator": {"scoring_thresholds": "bad"}},
        {"webui": {"port": "8765"}},
    ],
)
def test_load_config_rejects_invalid_nested_config_types(tmp_path, config):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(OPCConfigError):
        load_config(config_path)


def test_load_config_rejects_invalid_yaml_with_opc_config_error(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("opc_hermes: [unterminated\n", encoding="utf-8")

    with pytest.raises(OPCConfigError):
        load_config(config_path)
