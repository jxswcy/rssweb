import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.scraper import fetch_article_list, fetch_article_content, fetch_articles_concurrently

SAMPLE_LIST_HTML = """
<html><body>
  <ul>
    <li><a class="post-link" href="/post/1">Article One</a></li>
    <li><a class="post-link" href="/post/2">Article Two</a></li>
  </ul>
</body></html>
"""

SAMPLE_CONTENT_HTML = """
<html><body>
  <div class="content"><p>Full article text here.</p></div>
</body></html>
"""


@pytest.mark.asyncio
async def test_fetch_article_list_with_selectors():
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_LIST_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        articles = await fetch_article_list(
            url="https://example.com",
            title_selector="a.post-link",
            link_selector="a.post-link",
            base_url="https://example.com",
        )

    assert len(articles) == 2
    assert articles[0]["title"] == "Article One"
    assert articles[0]["url"] == "https://example.com/post/1"


@pytest.mark.asyncio
async def test_fetch_article_content_with_selector():
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_CONTENT_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        content = await fetch_article_content(
            url="https://example.com/post/1",
            content_selector=".content",
        )

    assert "Full article text here" in content


@pytest.mark.asyncio
async def test_fetch_article_content_fallback_trafilatura():
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_CONTENT_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        with patch("app.scraper.trafilatura.extract", return_value="Extracted text"):
            content = await fetch_article_content(
                url="https://example.com/post/1",
                content_selector=None,
            )

    assert content == "Extracted text"


@pytest.mark.asyncio
async def test_fetch_articles_concurrently_success():
    """多篇文章并发抓取，所有成功"""
    stubs = [
        {"title": "Article 1", "url": "https://example.com/1"},
        {"title": "Article 2", "url": "https://example.com/2"},
    ]
    with patch("app.scraper.fetch_article_content", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = "<p>content</p>"
        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await fetch_articles_concurrently(stubs, content_selector=None)

    assert len(results) == 2
    assert results[0]["content"] == "<p>content</p>"
    assert results[0]["title"] == "Article 1"
    assert results[1]["title"] == "Article 2"


@pytest.mark.asyncio
async def test_fetch_articles_concurrently_partial_failure():
    """单篇失败不影响其他篇"""
    stubs = [
        {"title": "Good", "url": "https://example.com/good"},
        {"title": "Bad", "url": "https://example.com/bad"},
    ]

    async def mock_fetch(url, content_selector):
        if "bad" in url:
            raise Exception("fetch error")
        return "<p>good content</p>"

    with patch("app.scraper.fetch_article_content", side_effect=mock_fetch):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            results = await fetch_articles_concurrently(stubs, content_selector=None)

    assert len(results) == 2
    good = next(r for r in results if r["title"] == "Good")
    bad = next(r for r in results if r["title"] == "Bad")
    assert good["content"] == "<p>good content</p>"
    assert "失败" in bad["content"] or "error" in bad["content"].lower()
