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


SAMPLE_ARTICLE_LIST_HTML = """
<html><body>
  <ul>
    <li class="post">
      <h3><a href="/post/1">Article One Title</a></h3>
      <p>summary...</p>
    </li>
    <li class="post">
      <h3><a href="/post/2">Article Two Title</a></h3>
      <p>summary...</p>
    </li>
  </ul>
</body></html>
"""

SAMPLE_DIRECT_ANCHOR_HTML = """
<html><body>
  <ul>
    <li><a class="post-link" href="/post/1">Article One</a></li>
    <li><a class="post-link" href="/post/2">Article Two</a></li>
  </ul>
</body></html>
"""

SAMPLE_CONTAINER_WITH_LINKS_HTML = """
<html><body>
  <article class="post">
    <span class="date">2026-01-01</span>
    <a href="/post/1">Long Article Title Here</a>
    <a href="/tag/foo">foo</a>
  </article>
  <article class="post">
    <span class="date">2026-01-02</span>
    <a href="/post/2">Another Long Title</a>
    <a href="/tag/bar">bar</a>
  </article>
</body></html>
"""


@pytest.mark.asyncio
async def test_article_selector_heading_anchor():
    """路径 2：li 容器内含 h3 a，提取标题锚点"""
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_ARTICLE_LIST_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        articles = await fetch_article_list(
            url="https://example.com",
            article_selector="li.post",
            title_selector=None,
            link_selector=None,
            base_url="https://example.com",
        )

    assert len(articles) == 2
    assert articles[0]["title"] == "Article One Title"
    assert articles[0]["url"] == "https://example.com/post/1"


@pytest.mark.asyncio
async def test_article_selector_direct_anchor():
    """路径 1：selector 直接指向 <a> 元素"""
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_DIRECT_ANCHOR_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        articles = await fetch_article_list(
            url="https://example.com",
            article_selector="a.post-link",
            title_selector=None,
            link_selector=None,
            base_url="https://example.com",
        )

    assert len(articles) == 2
    assert articles[0]["title"] == "Article One"
    assert articles[0]["url"] == "https://example.com/post/1"


@pytest.mark.asyncio
async def test_article_selector_longest_anchor():
    """路径 3：容器内有多个 <a>，取文字最长的那个"""
    with patch("app.scraper.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.text = SAMPLE_CONTAINER_WITH_LINKS_HTML
        mock_response.raise_for_status = MagicMock()
        MockClient.return_value.__aenter__ = AsyncMock(return_value=MockClient.return_value)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value.get = AsyncMock(return_value=mock_response)

        articles = await fetch_article_list(
            url="https://example.com",
            article_selector="article.post",
            title_selector=None,
            link_selector=None,
            base_url="https://example.com",
        )

    assert len(articles) == 2
    assert articles[0]["title"] == "Long Article Title Here"
    assert articles[0]["url"] == "https://example.com/post/1"
