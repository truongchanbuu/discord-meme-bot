"""Plan local imports and checkpoint uploads before indexing their Discord references."""

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import file_digest
from os import walk
from pathlib import Path
from typing import Protocol

from meme_manager.domain.media import media_kind
from meme_manager.domain.models import ImportedFile, LocalMeme, Meme, MemeInput
from meme_manager.domain.repositories import FolderImportRepository, MemeRepository
from meme_manager.domain.text import meme_channel_name


class UploadError(Exception):
    """An expected Discord upload/recovery failure for an individual file."""


class FolderUploader(Protocol):
    async def upload(self, source: LocalMeme) -> MemeInput: ...

    async def recover(self, reference: ImportedFile) -> MemeInput | None: ...

    async def match_existing(self, source: LocalMeme, candidate: Meme) -> MemeInput | None: ...


@dataclass(slots=True)
class FolderPlan:
    files: list[LocalMeme] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped: int = 0


@dataclass(slots=True)
class ImportSummary:
    uploaded: int = 0
    indexed: int = 0
    skipped: int = 0
    failed: int = 0


def scan_folder(folder: Path, category: str | None = None) -> FolderPlan:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"Không tìm thấy folder: {folder}")
    override = meme_channel_name(category) if category is not None else None
    plan = FolderPlan()
    seen: set[tuple[str, str]] = set()
    paths: list[Path] = []
    for current, _, filenames in walk(
        folder, followlinks=False, onerror=lambda error: plan.errors.append(str(error))
    ):
        paths.extend(Path(current) / name for name in filenames)
    for path in sorted(paths):
        if path.is_symlink():
            plan.skipped += 1
            continue
        if not path.is_file():
            continue
        if media_kind(path.name, None) is None:
            plan.skipped += 1
            continue
        relative = path.relative_to(folder)
        try:
            name = override or meme_channel_name(
                relative.parts[0] if len(relative.parts) > 1 else "general"
            )
            with path.open("rb") as media:
                digest = file_digest(media, "sha256").hexdigest()
            size = path.stat().st_size
        except (OSError, ValueError) as error:
            plan.errors.append(f"{relative}: {error}")
            continue
        key = (name, digest)
        if key in seen:
            plan.skipped += 1
            continue
        seen.add(key)
        plan.files.append(LocalMeme(path, relative.as_posix(), name, digest, size))
    return plan


class FolderImportService:
    def __init__(
        self,
        guild_id: int,
        catalog: MemeRepository,
        imports: FolderImportRepository,
        uploader: FolderUploader,
        report: Callable[[str], None],
    ) -> None:
        self.guild_id = guild_id
        self.catalog = catalog
        self.imports = imports
        self.uploader = uploader
        self.report = report

    async def run(self, files: list[LocalMeme]) -> ImportSummary:
        summary = ImportSummary()
        existing: dict[tuple[str, int], list[Meme]] = {}
        indexed = {
            candidate.attachment_id: candidate
            for candidate in self.catalog.iter_search_candidates(self.guild_id)
        }
        for candidate in indexed.values():
            if not candidate.channel_name:
                continue
            try:
                key = (meme_channel_name(candidate.channel_name), candidate.file_size)
            except ValueError:
                continue
            existing.setdefault(key, []).append(candidate)
        for source in files:
            try:
                reference = self.imports.get(self.guild_id, source.category, source.content_hash)
                record = await self.uploader.recover(reference) if reference else None
                if reference is None:
                    for candidate in existing.get((source.category, source.file_size), []):
                        record = await self.uploader.match_existing(source, candidate)
                        if record is not None:
                            break
                if record is not None:
                    if record.guild_id != self.guild_id:
                        raise UploadError("File khôi phục thuộc server khác cấu hình")
                    self.imports.save(source, record)
                    added = self._index(record)
                    summary.indexed += int(added)
                    summary.skipped += 1
                    self.report(f"SKIP {source.relative_path}: đã upload, đã kiểm tra file gốc")
                    continue
                if reference is not None:
                    stale = indexed.get(reference.attachment_id)
                    if stale is not None:
                        self.catalog.remove(stale.id, self.guild_id)
                self.report(f"UPLOAD #{source.category}: {source.relative_path}")
                record = await self.uploader.upload(source)
                if record.guild_id != self.guild_id:
                    raise UploadError("File upload thuộc server khác cấu hình")
                self.report(
                    f"UPLOADED {source.relative_path}: https://discord.com/channels/"
                    f"{record.guild_id}/{record.channel_id}/{record.message_id}"
                )
                # Save the remote reference first; a retry can repair an unfinished catalog write.
                self.imports.save(source, record)
                summary.uploaded += 1
                summary.indexed += int(self._index(record))
            except (OSError, ValueError, UploadError) as error:
                summary.failed += 1
                self.report(f"ERROR {source.relative_path}: {error}")
        return summary

    def _index(self, record: MemeInput) -> bool:
        # add() also returns False for duplicates; unsupported remote MIME must report failure.
        if media_kind(record.filename, record.content_type) is None:
            raise UploadError("Discord trả về file không thuộc định dạng ảnh/video được hỗ trợ")
        return self.catalog.add(record)
