from meme_manager.domain.media import media_kind
from meme_manager.domain.text import default_title, normalize


def test_supported_media():
    assert media_kind("funny.GIF", "image/gif") == "image"
    assert media_kind("reaction.mp4", "video/mp4") == "video"
    assert media_kind("reaction.webp", "video/mp4") is None
    assert media_kind("secret.pdf", None) is None


def test_normalize_vietnamese():
    assert normalize("Mèo ĐANG khóc!") == "meo dang khoc"
    assert default_title("cat-screaming.jpg") == "cat screaming"
