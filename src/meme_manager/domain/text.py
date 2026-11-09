"""Human-friendly search for short English and Vietnamese phrases."""

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Lowercase, remove accents, and collapse spacing for robust simple matching."""
    without_accents = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in without_accents if not unicodedata.combining(char))
    without_marks = without_marks.replace("đ", "d")
    return " ".join(re.findall(r"[\w]+", without_marks, flags=re.UNICODE))


def default_title(filename: str) -> str:
    """Produce a readable name from the original file name."""
    stem = filename.rsplit(".", maxsplit=1)[0]
    return stem.replace("_", " ").replace("-", " ").strip() or "Untitled meme"


def meme_channel_name(name: str) -> str:
    """Use the same canonical name for Discord channels and duplicate checks."""
    channel_name = "-".join(normalize(name).replace("_", " ").split())
    if not channel_name or len(channel_name) > 100:
        raise ValueError("Tên category phải có chữ hoặc số và dài tối đa 100 ký tự sau chuẩn hóa.")
    return channel_name


@dataclass(frozen=True, slots=True)
class SearchKeys:
    accented: str
    folded: str


def search_keys(text: str) -> SearchKeys:
    """Build both search forms per text, without changing display or persisted legacy keys."""
    visible = "".join(char for char in text if unicodedata.category(char) != "Cf")
    canonical = unicodedata.normalize("NFKC", visible)
    canonical = unicodedata.normalize("NFKC", canonical.casefold())
    accented = " ".join(re.findall(r"[^\W_]+", canonical, flags=re.UNICODE))
    return SearchKeys(accented, normalize(accented))
