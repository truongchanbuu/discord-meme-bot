"""Catalog behavior is tested without Discord, tokens, or network access."""

import sqlite3
from dataclasses import replace

import pytest

from meme_manager.domain.models import MemeInput
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.channels import ChannelRegistry


def input_file(
    attachment_id: int = 11, filename: str = "Cat_Crying.gif", message_text: str = "sad"
) -> MemeInput:
    return MemeInput(
        guild_id=1,
        channel_id=2,
        message_id=3,
        attachment_id=attachment_id,
        author_id=4,
        filename=filename,
        content_type="image/gif",
        file_size=1000,
        message_text=message_text,
    )


def test_indexes_supported_file_only_once(catalog: MemeCatalog) -> None:
    assert catalog.add(input_file()) is True
    assert catalog.add(input_file()) is False
    assert len(catalog.search(1)) == 1


def test_search_matches_accent_insensitive_words(catalog: MemeCatalog) -> None:
    catalog.add(input_file(message_text="Mèo khóc quá trời"))
    assert len(catalog.search(1, "meo khoc")) == 1
    assert len(catalog.search(1, "cat sad")) == 0


def test_search_respects_guild_boundary(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    assert catalog.search(999, "cat") == []


def test_edit_tags_then_remove(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    meme = catalog.search(1)[0]
    assert catalog.update(meme.id, 1, "Mèo hết cứu", "cat, reaction")
    assert catalog.search(1, "reaction")[0].id == meme.id
    assert catalog.remove(meme.id, 1)
    assert catalog.search(1) == []


def test_like_metacharacters_are_not_sql_wildcards(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    assert catalog.search(1, "%") == []
    assert catalog.search(1, "_no_match") == []


def test_remove_message_clears_source(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    assert catalog.remove_message(1, 2, 3) == 1
    assert catalog.search(1) == []


def test_rejects_unsupported_extension(catalog: MemeCatalog) -> None:
    assert catalog.add(input_file(filename="malware.exe")) is False


def test_channel_category_remains_searchable_after_edit_and_reimport(catalog: MemeCatalog) -> None:
    upload = replace(input_file(), channel_name="mèo-khóc")
    assert catalog.add(upload)
    meme = catalog.search(1, "meo khoc")[0]
    assert catalog.update(meme.id, 1, "New title", "custom-tag")
    assert catalog.search(1, "meo khoc custom-tag")
    assert catalog.add(replace(upload, channel_name="reaction")) is False
    updated = catalog.search(1, "reaction custom-tag")[0]
    assert updated.title == "New title"
    assert updated.tags == "custom-tag"
    assert catalog.search(1, "meo khoc") == []
    assert len(catalog.search(1)) == 1


def test_upgrades_existing_database_without_losing_entries(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    meme = catalog.search(1)[0]
    catalog.update(meme.id, 1, "Edited title", "saved-tag")
    with sqlite3.connect(catalog.database.path) as connection:
        connection.execute("ALTER TABLE memes DROP COLUMN channel_name")
    catalog.database.initialize()
    catalog.database.initialize()
    restored = catalog.search(1, "saved-tag")[0]
    assert restored.title == "Edited title"
    assert restored.channel_name == ""


def test_normalized_name_is_updated_without_reimport_overwriting_it(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    meme = catalog.search(1)[0]
    assert meme.name_index == "cat crying"
    assert catalog.update(meme.id, 1, "Mèo Hết Cứu!", "reaction")
    assert catalog.get(meme.id, 1).name_index == "meo het cuu"
    assert not catalog.add(input_file())
    assert catalog.get(meme.id, 1).name_index == "meo het cuu"


def test_category_filter_combines_with_query_and_guild(catalog: MemeCatalog) -> None:
    catalog.add(input_file())
    catalog.add(replace(input_file(12), channel_id=5))
    catalog.add(replace(input_file(13), guild_id=9, channel_id=5))
    matches = catalog.search(1, "cat", channel_id=5)
    assert [m.attachment_id for m in matches] == [12]
    assert len(catalog.search(1, channel_id=2)) == 1
    assert catalog.search(1, channel_id=99) == []


def test_migration_backfills_name_and_preserves_metadata_and_channel_mapping(
    catalog: MemeCatalog,
    channels: ChannelRegistry,
) -> None:
    catalog.add(input_file())
    meme = catalog.search(1)[0]
    catalog.update(meme.id, 1, "Mèo khóc", "saved-tag")
    channels.set_meme_category_id(1, 20)
    channels.set_meme_channel_id(1, "reaction", 2)
    with sqlite3.connect(catalog.database.path) as connection:
        connection.execute("DROP INDEX idx_memes_guild_name")
        connection.execute("ALTER TABLE memes DROP COLUMN name_index")
    catalog.database.initialize()
    catalog.database.initialize()
    restored = catalog.search(1, "saved-tag")[0]
    assert restored.name_index == "meo khoc"
    assert restored.title == "Mèo khóc"
    assert restored.attachment_id == meme.attachment_id
    assert channels.get_meme_category_id(1) == 20
    assert channels.get_meme_channel_id(1, "reaction") == 2


@pytest.mark.parametrize(
    ("query", "expected_index"),
    [
        (
            "SELECT id FROM memes WHERE guild_id = 1 AND name_index = 'cat crying' ORDER BY id DESC",
            "idx_memes_guild_name",
        ),
        (
            "SELECT id FROM memes WHERE guild_id = 1 AND channel_id = 2 ORDER BY id DESC",
            "idx_memes_guild_channel",
        ),
        (
            "DELETE FROM memes WHERE guild_id = 1 AND channel_id = 2 AND message_id = 3",
            "idx_memes_source_message",
        ),
    ],
)
def test_indexes_support_name_category_and_source_queries(
    catalog: MemeCatalog, query: str, expected_index: str
) -> None:
    with sqlite3.connect(catalog.database.path) as connection:
        plan = connection.execute("EXPLAIN QUERY PLAN " + query).fetchall()
    assert any(expected_index in str(step) for step in plan)
