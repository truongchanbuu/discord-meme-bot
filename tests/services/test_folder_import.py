"""Local planning, resume and failure handling work without Discord credentials."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from meme_manager.domain.models import MemeInput
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.persistence.database import SQLiteDatabase
from meme_manager.persistence.imports import FolderImportStore
from meme_manager.services.folder_import import FolderImportService, UploadError, scan_folder


def write_media(root: Path, relative: str, content: bytes = b"image") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def uploaded(attachment_id: int = 40) -> MemeInput:
    return MemeInput(
        guild_id=1,
        channel_id=20,
        message_id=30,
        attachment_id=attachment_id,
        author_id=50,
        filename="cat.gif",
        content_type="image/gif",
        file_size=5,
        message_text="",
        channel_name="meo-khoc",
    )


def test_scan_maps_top_level_folders_and_root_files(tmp_path: Path) -> None:
    write_media(tmp_path, "Mèo Khóc/nested/cat.gif")
    write_media(tmp_path, "root.mp4", b"video")
    write_media(tmp_path, "ignore.txt")
    plan = scan_folder(tmp_path)
    assert [(item.relative_path, item.category) for item in plan.files] == [
        ("Mèo Khóc/nested/cat.gif", "meo-khoc"),
        ("root.mp4", "general"),
    ]
    assert plan.skipped == 1
    assert plan.errors == []


def test_scan_override_and_content_deduplication(tmp_path: Path) -> None:
    write_media(tmp_path, "one/cat.gif")
    write_media(tmp_path, "two/copy.png")
    assert len(scan_folder(tmp_path).files) == 2
    plan = scan_folder(tmp_path, "Mèo Khóc")
    assert len(plan.files) == 1
    assert plan.files[0].category == "meo-khoc"
    assert plan.skipped == 1


def test_skips_symlinks_instead_of_importing_outside_folder(tmp_path: Path) -> None:
    outside = write_media(tmp_path, "outside/cat.gif")
    source = tmp_path / "source"
    source.mkdir()
    (source / "link.gif").symlink_to(outside)
    assert scan_folder(source).files == []


def test_invalid_folder_or_category_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Không tìm thấy folder"):
        scan_folder(tmp_path / "missing")
    with pytest.raises(ValueError, match="Tên category"):
        scan_folder(tmp_path, "🎉")


def test_resume_skips_upload_and_preserves_edited_index(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "Mèo Khóc/cat.gif")
    plan = scan_folder(tmp_path)
    store = FolderImportStore(database)
    uploader = Mock(
        upload=AsyncMock(return_value=uploaded()), recover=AsyncMock(return_value=uploaded())
    )
    service = FolderImportService(1, catalog, store, uploader, Mock())
    first = asyncio.run(service.run(plan.files))
    meme = catalog.search(1)[0]
    catalog.update(meme.id, 1, "Edited name", "custom")
    renamed = replace(plan.files[0], relative_path="renamed.gif")
    second = asyncio.run(service.run([renamed]))
    assert first.uploaded == 1
    assert first.indexed == 1
    assert second.uploaded == 0
    assert second.skipped == 1
    assert catalog.get(meme.id, 1).title == "Edited name"
    uploader.upload.assert_awaited_once()
    assert store.get(9, plan.files[0].category, plan.files[0].content_hash) is None


def test_checkpoint_repairs_missing_index_without_reupload(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    store = FolderImportStore(database)
    store.save(source, uploaded())
    uploader = Mock(upload=AsyncMock(), recover=AsyncMock(return_value=uploaded()))
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert result.skipped == 1
    assert result.indexed == 1
    uploader.upload.assert_not_awaited()
    assert len(catalog.search(1)) == 1


def test_missing_original_is_reuploaded_and_checkpoint_is_updated(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    store = FolderImportStore(database)
    store.save(source, uploaded())
    uploader = Mock(
        upload=AsyncMock(return_value=uploaded(41)), recover=AsyncMock(return_value=None)
    )
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert result.uploaded == 1
    assert store.get(1, source.category, source.content_hash).attachment_id == 41


def test_one_file_failure_does_not_stop_later_files(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "first.gif", b"first")
    write_media(tmp_path, "second.gif", b"second")
    sources = scan_folder(tmp_path).files
    store = FolderImportStore(database)
    uploader = Mock(upload=AsyncMock(side_effect=[UploadError("No permission"), uploaded()]))
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run(sources))
    assert result.failed == 1
    assert result.uploaded == 1
    assert store.get(1, sources[0].category, sources[0].content_hash) is None
    assert len(catalog.search(1)) == 1


def test_recovery_permission_error_does_not_create_duplicate_upload(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    store = FolderImportStore(database)
    store.save(source, uploaded())
    uploader = Mock(upload=AsyncMock(), recover=AsyncMock(side_effect=UploadError("Forbidden")))
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert result.failed == 1
    uploader.upload.assert_not_awaited()


def test_checkpoint_survives_catalog_failure_for_next_run(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    store = FolderImportStore(database)
    uploader = Mock(upload=AsyncMock(return_value=uploaded()))
    broken_catalog = Mock(
        add=Mock(side_effect=ValueError("Index failed")),
        iter_search_candidates=Mock(return_value=iter([])),
    )
    result = asyncio.run(
        FolderImportService(1, broken_catalog, store, uploader, Mock()).run([source])
    )
    assert result.failed == 1
    assert store.get(1, source.category, source.content_hash) is not None
    assert catalog.search(1) == []


def test_adopts_upload_from_before_cli_without_posting_again(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    record = replace(uploaded(), channel_name=source.category)
    catalog.add(record)
    store = FolderImportStore(database)
    uploader = Mock(upload=AsyncMock(), match_existing=AsyncMock(return_value=record))
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert result.skipped == 1
    assert result.uploaded == 0
    uploader.match_existing.assert_awaited_once()
    uploader.upload.assert_not_awaited()
    assert store.get(1, source.category, source.content_hash) is not None


def test_missing_attachment_removes_only_its_stale_index(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    record = replace(uploaded(), channel_name=source.category)
    catalog.add(record)
    catalog.add(replace(record, attachment_id=99))
    store = FolderImportStore(database)
    store.save(source, record)
    uploader = Mock(
        upload=AsyncMock(return_value=replace(record, attachment_id=41, message_id=31)),
        recover=AsyncMock(return_value=None),
    )
    result = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert result.uploaded == 1
    assert {item.attachment_id for item in catalog.search(1)} == {41, 99}


def test_unsupported_remote_mime_is_checkpointed_but_not_reported_as_indexed(
    tmp_path: Path, database: SQLiteDatabase, catalog: MemeCatalog
) -> None:
    write_media(tmp_path, "cat.gif")
    source = scan_folder(tmp_path).files[0]
    store = FolderImportStore(database)
    record = replace(uploaded(), content_type="application/pdf")
    uploader = Mock(upload=AsyncMock(return_value=record))
    summary = asyncio.run(FolderImportService(1, catalog, store, uploader, Mock()).run([source]))
    assert summary.failed == 1
    assert summary.indexed == 0
    assert store.get(1, source.category, source.content_hash) is not None
    assert catalog.search(1) == []


def test_unreadable_directory_is_reported(tmp_path: Path) -> None:
    def walk_error(
        path: Path, *, followlinks: bool, onerror: Callable[[OSError], None]
    ) -> list[tuple[str, list[str], list[str]]]:
        onerror(PermissionError("Cannot read subfolder"))
        return []

    with patch("meme_manager.services.folder_import.walk", side_effect=walk_error):
        plan = scan_folder(tmp_path)
    assert plan.files == []
    assert len(plan.errors) == 1
    assert "Cannot read subfolder" in plan.errors[0]
