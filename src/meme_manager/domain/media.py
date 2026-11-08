"""Attachment-type validation without depending on Discord SDK objects."""

from pathlib import Path

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov"})


def media_kind(filename: str, content_type: str | None) -> str | None:
    """Return 'image' or 'video' only for intended, supported meme formats."""
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        if content_type and not content_type.startswith("image/"):
            return None
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        if content_type and not content_type.startswith("video/"):
            return None
        return "video"
    return None
