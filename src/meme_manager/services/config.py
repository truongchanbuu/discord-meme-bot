"""Read named YAML mappings from one configuration directory."""

import re
from pathlib import Path
from typing import Any

import yaml


class ConfigService:
    def __init__(self, directory: Path = Path("config")) -> None:
        self.directory = directory

    def load(self, name: str) -> dict[str, Any]:
        """Load a basename such as 'search'; never interpret a caller-supplied path."""
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
            raise ValueError("Config name must contain only letters, numbers, '_' or '-'")
        path = self.directory / f"{name}.yaml"
        try:
            with path.open(encoding="utf-8") as source:
                values = yaml.safe_load(source)
        except yaml.YAMLError:
            raise ValueError(f"Invalid YAML in config {name}") from None
        if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
            raise ValueError(f"Config {name} must be a mapping with string keys")
        return values
