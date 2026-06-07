"""OPC-Hermes configuration templates.

Uses INDEPENDENT config files (not Hermes config.yaml) so OPC-Hermes
survives Hermes Agent upgrades without migration.

Config location: ~/.hermes/opc/config.yaml
"""

from opc_hermes.config.loader import (
    CONFIG_ROOT_KEY,
    DEFAULT_CONFIG,
    OPCConfigError,
    default_config,
    get_config_value,
    get_default_config_path,
    get_opc_home,
    load_config,
    save_config,
    set_config_value,
)

__all__ = [
    "CONFIG_ROOT_KEY",
    "DEFAULT_CONFIG",
    "OPCConfigError",
    "default_config",
    "get_config_value",
    "get_default_config_path",
    "get_opc_home",
    "load_config",
    "save_config",
    "set_config_value",
]
