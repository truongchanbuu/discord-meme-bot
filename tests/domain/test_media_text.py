from meme_manager.domain.media import media_kind
from meme_manager.domain.text import default_title, normalize, search_keys


def test_supported_media() -> None:
    assert media_kind("funny.GIF", "image/gif") == "image"
    assert media_kind("reaction.mp4", "video/mp4") == "video"
    assert media_kind("reaction.webp", "video/mp4") is None
    assert media_kind("secret.pdf", None) is None


def test_normalize_vietnamese() -> None:
    assert normalize("Mèo ĐANG khóc!") == "meo dang khoc"
    assert default_title("cat-screaming.jpg") == "cat screaming"


def test_search_key_preserves_accents_separately_from_folding() -> None:
    assert search_keys("ĐẤT_mèo—khóc").accented == "đất mèo khóc"
    assert search_keys("ĐẤT_mèo—khóc").folded == "dat meo khoc"
    assert search_keys("𝐌È𝐎_𝐊𝐇Ó𝐂").accented == "mèo khóc"
    assert search_keys("me\u0300o\u200b_kho\u0301c").accented == "mèo khóc"
