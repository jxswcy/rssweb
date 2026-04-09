import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.scraper import fetch_article_list, fetch_article_content

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
