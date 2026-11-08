"""Validate startup configuration without binding the rest of the app to environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    guild_id: int
    database_path: Path

    @classmethod
    def from_environment(cls) -> Settings:
        load_dotenv()
        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Set DISCORD_BOT_TOKEN in .env")

        return cls(
            token=token,
            guild_id=_required_positive_int("DISCORD_GUILD_ID"),
            database_path=Path(os.getenv("MEME_DB_PATH", "data/memes.sqlite3")),
        )


def _required_positive_int(name: str) -> int:
    raw_value = os.getenv(name, "")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
