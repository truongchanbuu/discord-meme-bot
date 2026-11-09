"""Load and validate named YAML settings and environment-backed credentials at startup."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import get_type_hints

from dotenv import load_dotenv

from meme_manager.domain.media import FileType, MediaPolicy
from meme_manager.domain.options import BotOptions, DatabaseOptions, SearchOptions
from meme_manager.domain.text import meme_channel_name
from meme_manager.services.config import ConfigService


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    bot: BotOptions
    database: DatabaseOptions
    search: SearchOptions
    media: MediaPolicy

    @classmethod
    def load(cls, directory: Path | None = None) -> RuntimeConfig:
        service = ConfigService(directory or Path(os.getenv("MEME_CONFIG_DIR", "config")))
        bot = _options(service, "bot", BotOptions)
        database = _options(service, "database", DatabaseOptions)
        search = _options(service, "search", SearchOptions)
        if bot.page_size > 25 or bot.history_default > bot.history_max:
            raise ValueError("bot: page_size must be <=25 and history_default <= history_max")
        if bot.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("bot.log_level is invalid")
        if len(bot.category_name) > 100:
            raise ValueError("bot.category_name exceeds Discord's 100 character limit")
        if search.min_fuzzy_score > 100:
            raise ValueError("search.min_fuzzy_score must be <=100")
        for name in (bot.token_env, bot.guild_id_env, database.path_env):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError("Environment variable names must be valid identifiers")
        return cls(bot, database, search, _media(service))


def _options[Options: (BotOptions, DatabaseOptions, SearchOptions)](
    service: ConfigService, name: str, model: type[Options]
) -> Options:
    values = service.load(name)
    hints = get_type_hints(model)
    if values.keys() != hints.keys():
        raise ValueError(f"config {name}: expected keys {', '.join(hints)}")
    for field in fields(model):
        value = values[field.name]
        expected = hints[field.name]
        valid = type(value) is expected or (expected is float and type(value) is int)
        if not valid:
            raise ValueError(f"{name}.{field.name}: expected {expected.__name__}")
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{name}.{field.name} cannot be empty")
        if isinstance(value, (int, float)) and (value <= 0 or not math.isfinite(value)):
            raise ValueError(f"{name}.{field.name} must be positive")
    return model(**values)


def _media(service: ConfigService) -> MediaPolicy:
    values = service.load("media")
    if values.keys() != {"default_category", "types"}:
        raise ValueError("media: expected default_category and types")
    category = values["default_category"]
    if not isinstance(category, str):
        raise ValueError("media.default_category must be a string")
    category = meme_channel_name(category)
    groups = values["types"]
    if not isinstance(groups, dict) or not 1 <= len(groups) <= 25:
        raise ValueError("media.types must contain 1 to 25 file types")
    result: list[FileType] = []
    seen: set[str] = set()
    for name, group in groups.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,24}", name):
            raise ValueError("media type names must be lowercase identifiers, up to 25 characters")
        if not isinstance(group, dict) or group.keys() != {"kind", "extensions", "enabled"}:
            raise ValueError(f"media.{name}: expected kind, extensions, enabled")
        if group["kind"] not in ("image", "video") or type(group["enabled"]) is not bool:
            raise ValueError(f"media.{name}: invalid kind or enabled")
        extensions = group["extensions"]
        if not isinstance(extensions, list) or not extensions:
            raise ValueError(f"media.{name}.extensions must be a nonempty list")
        for extension in extensions:
            if not isinstance(extension, str) or not re.fullmatch(r"[a-z0-9]+", extension):
                raise ValueError(f"media.{name}: extensions must be lowercase without a dot")
            if extension in seen:
                raise ValueError("Each extension must belong to exactly one media type")
            seen.add(extension)
        result.append(FileType(name, group["kind"], tuple(extensions), group["enabled"]))
    if any(item.name in seen and item.name not in item.extensions for item in result):
        raise ValueError("Media names cannot shadow extensions of another group")
    return MediaPolicy(category, tuple(result))


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    guild_id: int
    database_path: Path
    config: RuntimeConfig

    @classmethod
    def from_environment(cls, config: RuntimeConfig | None = None) -> Settings:
        load_dotenv()
        config = config or RuntimeConfig.load()
        token = os.getenv(config.bot.token_env, "").strip()
        if not token:
            raise ValueError(f"Set {config.bot.token_env} in .env")
        return cls(
            token,
            _required_positive_int(config.bot.guild_id_env),
            Path(os.getenv(config.database.path_env, config.database.path)),
            config,
        )


def _required_positive_int(name: str) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        raise ValueError(f"{name} must be a positive integer") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
