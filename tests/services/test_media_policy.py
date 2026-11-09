"""One media policy controls ingest and scoped browse/fuzzy search filtering."""

from dataclasses import replace
from pathlib import Path

from meme_manager.config import RuntimeConfig
from meme_manager.domain.models import MemeInput
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.services.folder_import import scan_folder
from meme_manager.services.search import MemeSearchService


def item(attachment_id: int, filename: str, guild: int = 1, channel: int = 2) -> MemeInput:
    return MemeInput(
        guild, channel, attachment_id, attachment_id, 50, filename, None, 10, "", "cat"
    )


def test_extension_filters_before_ranking_with_scope(
    catalog: MemeCatalog, config: RuntimeConfig
) -> None:
    for record in [
        item(1, "mèo khóc.PNG"),
        item(2, "mèo khóc.gif"),
        item(3, "mèo khóc.jpg"),
        item(4, "mèo khóc.JPEG"),
        item(5, "mèo khóc.mp4"),
        item(6, "mèo khóc.png", guild=99),
        item(7, "mèo khóc.png", channel=99),
    ]:
        assert catalog.add(record)
    service = MemeSearchService(catalog, config.search)
    for name, expected in [("png", {1}), ("gif", {2}), ("jpg", {3, 4}), ("video", {5})]:
        extensions = config.media.extensions_for(name)
        assert {
            m.attachment_id for m in catalog.search(1, channel_id=2, extensions=extensions)
        } == expected
        assert {
            m.attachment_id
            for m in service.search(1, "meo khco", channel_id=2, extensions=extensions)
        } == expected
    assert config.media.extensions_for(".jpeg") == ("jpg", "jpeg")
    assert catalog.search(1, extensions=()) == []
    assert service.search(1, "meo", extensions=()) == []


def test_disabled_format_is_skipped_but_old_records_remain_searchable(
    tmp_path: Path,
    database: SQLiteDatabase,
    catalog: MemeCatalog,
    config: RuntimeConfig,
) -> None:
    assert catalog.add(item(1, "cat.gif"))
    policy = replace(
        config.media,
        types=tuple(
            replace(t, enabled=False) if t.name == "gif" else t for t in config.media.types
        ),
    )
    restricted = MemeCatalog(database, policy, config.search)
    assert not restricted.add(item(2, "new.gif"))
    (tmp_path / "cat.gif").write_bytes(b"gif")
    (tmp_path / "cat.png").write_bytes(b"png")
    plan = scan_folder(tmp_path, media=policy)
    assert [f.path.name for f in plan.files] == ["cat.png"]
    assert plan.skipped >= 1
    assert len(restricted.search(1, extensions=policy.extensions_for("gif"))) == 1


def test_runtime_search_limits_are_used(catalog: MemeCatalog, config: RuntimeConfig) -> None:
    for i in range(1, 5):
        catalog.add(item(i, f"mèo khóc {i}.gif"))
    options = replace(config.search, max_results=2, normalization_cache_entries=3)
    service = MemeSearchService(catalog, options)
    assert len(service.search(1, "meokhoc", limit=99)) == 2
    assert service._search_keys.cache_info().maxsize == 3
    strict = MemeSearchService(catalog, replace(options, min_fuzzy_score=100.0))
    assert strict.search(1, "meo khco") == []


def test_custom_default_folder_category(tmp_path: Path, config: RuntimeConfig) -> None:
    (tmp_path / "cat.png").write_bytes(b"png")
    policy = replace(config.media, default_category="new-default")
    assert scan_folder(tmp_path, media=policy).files[0].category == "new-default"
