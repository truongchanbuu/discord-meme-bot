"""Relevance and typo matching are independent of Discord and use scoped SQLite data."""

import pytest

from meme_manager.domain.models import Meme, MemeInput
from meme_manager.persistence.catalog import MemeCatalog
from meme_manager.services.search import MemeSearchService


def add_meme(
    catalog: MemeCatalog,
    attachment_id: int,
    title: str,
    *,
    guild_id: int = 1,
    channel_id: int = 2,
    tags: str = "",
    caption: str = "",
    category: str = "reaction",
) -> Meme:
    catalog.add(
        MemeInput(
            guild_id=guild_id,
            channel_id=channel_id,
            message_id=attachment_id,
            attachment_id=attachment_id,
            author_id=50,
            filename=f"{title}.gif",
            content_type="image/gif",
            file_size=100,
            message_text=caption,
            channel_name=category,
        )
    )
    latest = catalog.search(guild_id, limit=1)[0]
    assert catalog.update(latest.id, guild_id, title, tags)
    updated = catalog.get(latest.id, guild_id)
    assert updated is not None
    return updated


def test_exact_name_precedes_newer_keyword_and_fuzzy_results(catalog: MemeCatalog) -> None:
    exact = add_meme(catalog, 1, "Mèo khóc")
    keywords = add_meme(catalog, 2, "Mèo khóc rất nhiều")
    fuzzy = add_meme(catalog, 3, "Mèo khco")
    results = MemeSearchService(catalog).search(1, "meo khoc")
    assert [m.id for m in results] == [exact.id, keywords.id, fuzzy.id]


def test_name_match_precedes_newer_tag_or_caption_matches(catalog: MemeCatalog) -> None:
    named = add_meme(catalog, 1, "Mèo khóc nhiều")
    tagged = add_meme(catalog, 2, "Sad reaction", tags="mèo khóc")
    captioned = add_meme(catalog, 3, "Another reaction", caption="mèo khóc")
    results = MemeSearchService(catalog).search(1, "meo khoc")
    assert results[0].id == named.id
    assert {m.id for m in results} == {named.id, tagged.id, captioned.id}


@pytest.mark.parametrize("query", ["MÈO KHÓC", "meo khco", "meo koc", "khoc meo"])
def test_vietnamese_normalization_typing_errors_and_word_order(
    catalog: MemeCatalog, query: str
) -> None:
    expected = add_meme(catalog, 1, "Mèo khóc")
    assert MemeSearchService(catalog).search(1, query)[0].id == expected.id


def test_typo_inside_longer_video_name(catalog: MemeCatalog) -> None:
    expected = add_meme(catalog, 1, "cat vo tay")
    assert MemeSearchService(catalog).search(1, "cat vo tya")[0].id == expected.id


def test_fuzzy_matching_in_tags_caption_and_category(catalog: MemeCatalog) -> None:
    tagged = add_meme(catalog, 1, "First", tags="gambling")
    captioned = add_meme(catalog, 2, "Second", caption="gambling")
    categorized = add_meme(catalog, 3, "Third", category="gambling")
    results = MemeSearchService(catalog).search(1, "gamblign")
    assert {m.id for m in results} == {tagged.id, captioned.id, categorized.id}


def test_query_can_span_name_and_tags(catalog: MemeCatalog) -> None:
    expected = add_meme(catalog, 1, "Cat", tags="crying")
    assert MemeSearchService(catalog).search(1, "cat cryign")[0].id == expected.id


@pytest.mark.parametrize("query", ["zxqv blrp", "cat xylophone", "cat banana"])
def test_common_word_does_not_admit_unrelated_queries(catalog: MemeCatalog, query: str) -> None:
    add_meme(catalog, 1, "Cat crying")
    assert MemeSearchService(catalog).search(1, query) == []


@pytest.mark.parametrize("query", ["", "   ", "!!!", "🎉", "%", "_", "___"])
def test_empty_or_punctuation_query_returns_no_results(catalog: MemeCatalog, query: str) -> None:
    add_meme(catalog, 1, "Cat crying")
    assert MemeSearchService(catalog).search(1, query) == []


def test_short_queries_keep_literal_matching_without_fuzzy_noise(catalog: MemeCatalog) -> None:
    expected = add_meme(catalog, 1, "Cat", category="memes")
    search = MemeSearchService(catalog)
    assert search.search(1, "ca")[0].id == expected.id
    assert search.search(1, "ct") == []


def test_guild_and_category_are_filtered_before_fuzzy_ranking(catalog: MemeCatalog) -> None:
    allowed = add_meme(catalog, 1, "Mèo khóc", channel_id=2)
    add_meme(catalog, 2, "Mèo khco", channel_id=3)
    add_meme(catalog, 3, "Mèo khco", guild_id=9, channel_id=2)
    search = MemeSearchService(catalog)
    assert [m.id for m in search.search(1, "meo khco", channel_id=2)] == [allowed.id]
    assert search.search(1, "meo khco", channel_id=99) == []


def test_old_match_is_not_lost_beyond_recent_page_or_database_batch(catalog: MemeCatalog) -> None:
    expected = add_meme(catalog, 1, "Cat vo tay")
    for attachment_id in range(2, 253):
        catalog.add(
            MemeInput(
                guild_id=1,
                channel_id=2,
                message_id=attachment_id,
                attachment_id=attachment_id,
                author_id=50,
                filename=f"unrelated-{attachment_id}.gif",
                content_type="image/gif",
                file_size=100,
                message_text="",
            )
        )
    results = MemeSearchService(catalog).search(1, "cat vo tya", limit=1)
    assert [m.id for m in results] == [expected.id]


def test_equal_relevance_is_newest_first_and_limit_is_applied_after_ranking(
    catalog: MemeCatalog,
) -> None:
    add_meme(catalog, 1, "Mèo khóc")
    second = add_meme(catalog, 2, "Mèo khóc")
    newest = add_meme(catalog, 3, "Mèo khóc")
    results = MemeSearchService(catalog).search(1, "meo khoc", limit=2)
    assert [m.id for m in results] == [newest.id, second.id]


def test_edits_and_removals_are_visible_without_restarting_search(catalog: MemeCatalog) -> None:
    original = add_meme(catalog, 1, "Mèo khóc")
    search = MemeSearchService(catalog)
    assert search.search(1, "meo khco")
    catalog.update(original.id, 1, "Dog sleeping", "sleep")
    assert search.search(1, "meo khco") == []
    assert search.search(1, "dog sleping")[0].id == original.id
    catalog.remove(original.id, 1)
    assert search.search(1, "dog sleping") == []


@pytest.mark.parametrize("query", ["votay", "vỗtay", "catvotay", "vỗ tay", "cat votay"])
def test_joined_words_find_spaced_names(catalog: MemeCatalog, query: str) -> None:
    expected = add_meme(catalog, 1, "Cat vỗ tay")
    assert MemeSearchService(catalog).search(1, query)[0].id == expected.id


def test_joined_words_match_tags_caption_and_category(catalog: MemeCatalog) -> None:
    tagged = add_meme(catalog, 1, "First", tags="vỗ tay")
    captioned = add_meme(catalog, 2, "Second", caption="vỗ tay")
    categorized = add_meme(catalog, 3, "Third", category="vo-tay")
    assert {m.id for m in MemeSearchService(catalog).search(1, "votay")} == {
        tagged.id,
        captioned.id,
        categorized.id,
    }


def test_exact_name_still_precedes_newer_space_insensitive_match(catalog: MemeCatalog) -> None:
    exact = add_meme(catalog, 1, "votay")
    add_meme(catalog, 2, "vỗ tay")
    assert MemeSearchService(catalog).search(1, "votay")[0].id == exact.id


def test_joined_words_preserve_guild_and_category_scope(catalog: MemeCatalog) -> None:
    expected = add_meme(catalog, 1, "Cat vỗ tay", channel_id=2)
    add_meme(catalog, 2, "votay", channel_id=3)
    add_meme(catalog, 3, "votay", guild_id=9)
    assert [m.id for m in MemeSearchService(catalog).search(1, "votay", channel_id=2)] == [
        expected.id
    ]


def test_space_insensitive_matching_does_not_join_different_fields(catalog: MemeCatalog) -> None:
    add_meme(catalog, 1, "a", tags="bc", category="memes")
    assert MemeSearchService(catalog).search(1, "abc") == []
