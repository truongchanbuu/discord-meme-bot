"""Validated runtime options, independent of file loading and external adapters."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BotOptions:
    token_env: str
    guild_id_env: str
    category_name: str
    history_default: int
    history_max: int
    page_size: int
    picker_timeout: int
    preview_limit_bytes: int
    log_level: str
    log_format: str


@dataclass(frozen=True, slots=True)
class DatabaseOptions:
    path: str
    path_env: str
    timeout_seconds: int
    search_batch_size: int
    title_length: int
    tags_length: int
    caption_length: int


@dataclass(frozen=True, slots=True)
class SearchOptions:
    max_results: int
    max_query_words: int
    min_fuzzy_query_length: int
    min_fuzzy_word_length: int
    min_fuzzy_score: float
    max_joined_words: int
    long_word_length: int
    short_word_edits: int
    long_word_edits: int
    normalization_cache_entries: int
