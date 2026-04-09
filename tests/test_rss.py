from datetime import datetime, timezone
from app.rss import generate_rss_feed


class MockFeed:
    def __init__(self, id=1, name="Test Blog", url="https://example.com",
                 last_fetched_at=None):
        self.id = id
        self.name = name
        self.url = url
        self.last_fetched_at = last_fetched_at or datetime(2026, 1, 1, tzinfo=timezone.utc)


class MockArticle:
    def __init__(self, id, title, url, content_original, content_translated=None,
                 fetched_at=None, published_at=None):
        self.id = id
        self.title = title
        self.url = url
        self.content_original = content_original
        self.content_translated = content_translated
        self.fetched_at = fetched_at
        self.published_at = published_at


def _make_feed():
    return MockFeed()


def _make_article(idx: int, translated: bool = False):
    return MockArticle(
        id=idx,
        title=f"Article {idx}",
        url=f"https://example.com/post/{idx}",
        content_original=f"<p>Original {idx}</p>",
        content_translated=f"<p>翻译 {idx}</p>" if translated else None,
        fetched_at=datetime(2026, 1, idx, tzinfo=timezone.utc),
        published_at=None
    )


def test_rss_contains_feed_title():
    feed = _make_feed()
    articles = [_make_article(1)]
    xml = generate_rss_feed(feed, articles, base_url="http://localhost:8000")
    assert b"Test Blog" in xml


def test_rss_contains_article_entry():
    feed = _make_feed()
    articles = [_make_article(1)]
    xml = generate_rss_feed(feed, articles, base_url="http://localhost:8000")
    assert b"Article 1" in xml
    assert b"example.com/post/1" in xml


def test_rss_bilingual_content():
    feed = _make_feed()
    articles = [_make_article(1, translated=True)]
    xml = generate_rss_feed(feed, articles, base_url="http://localhost:8000")
    assert b"Original 1" in xml
    assert "翻译 1".encode() in xml


def test_rss_original_only_when_no_translation():
    feed = _make_feed()
    articles = [_make_article(1, translated=False)]
    xml = generate_rss_feed(feed, articles, base_url="http://localhost:8000")
    assert b"Original 1" in xml
    assert "翻译".encode() not in xml
