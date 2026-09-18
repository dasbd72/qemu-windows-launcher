"""Reading and writing this tool's persisted config.

Config lives under $XDG_CONFIG_HOME/qemu-windows-launcher (falling back to ~/.config),
alongside the managed win_vars.fd file.
"""

import json
import os
from pathlib import Path
from typing import Any, cast

APP_NAME = "qemu-windows-launcher"

type Config = dict[str, Any]


def config_dir() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def win_vars_path() -> Path:
    return config_dir() / "win_vars.fd"


def load_config() -> Config | None:
    path = config_path()
    if not path.exists():
        return None
    with open(path) as f:
        return cast(Config, json.load(f))


def save_config(config: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
