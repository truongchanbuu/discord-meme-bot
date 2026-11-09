"""Attachment policy shared by folder imports, gateway indexing and search filters."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileType:
    name: str
    kind: str
    extensions: tuple[str, ...]
    enabled: bool


@dataclass(frozen=True, slots=True)
class MediaPolicy:
    default_category: str
    types: tuple[FileType, ...]

    def extensions_for(self, name: str | None) -> tuple[str, ...] | None:
        if name is None:
            return None
        for file_type in self.types:
            if name == file_type.name or name.lower().lstrip(".") in file_type.extensions:
                return file_type.extensions
        raise ValueError(f"Unknown file type: {name}")


def media_kind(filename: str, content_type: str | None, policy: MediaPolicy) -> str | None:
    extension = Path(filename).suffix.lower().lstrip(".")
    for file_type in policy.types:
        if not file_type.enabled or extension not in file_type.extensions:
            continue
        if content_type and not content_type.startswith(f"{file_type.kind}/"):
            return None
        return file_type.kind
    return None
