import asyncio
import logging
from urllib.parse import urljoin, urlparse
from typing import Optional

import httpx
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; RSSWeb/1.0; +https://github.com/rssweb)"
    )
}
MAX_CONCURRENCY = 3
DELAY_BETWEEN_REQUESTS = 1.0


async def fetch_article_list(
    url: str,
    article_selector: Optional[str] = None,
    title_selector: Optional[str] = None,
    link_selector: Optional[str] = None,
    base_url: str = "",
) -> list[dict]:
    """抓取文章列表页，返回 [{"title": ..., "url": ...}, ...]"""
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    soup = BeautifulSoup(html, "html.parser")

    # 优先：单 selector 模式
    if article_selector:
        return _extract_from_article_selector(soup, article_selector, base_url)

    if title_selector and link_selector:
        title_tags = soup.select(title_selector)
        link_tags = soup.select(link_selector)
        if len(title_tags) != len(link_tags):
            logger.warning(
                "title_selector matched %d elements but link_selector matched %d; "
                "extra elements will be ignored",
                len(title_tags), len(link_tags),
            )
        results = []
        for t, l in zip(title_tags, link_tags):
            href = l.get("href", "")
            full_url = urljoin(base_url, href) if href else ""
            if full_url:
                results.append({"title": t.get_text(strip=True), "url": full_url})
        return results

    # 启发式：寻找包含文章链接的 <a> 标签
    return _heuristic_extract(soup, base_url)


def _extract_from_article_selector(
    soup: BeautifulSoup, article_selector: str, base_url: str
) -> list[dict]:
    """
    用单个 selector 匹配文章元素，自动提取标题和链接。
    提取优先级：
      1. 元素本身是 <a> → 直接取文字和 href
      2. 元素内有 h1/h2/h3/h4 a → 取第一个标题锚点
      3. 元素内有任意 <a> → 取文字最长的那个
      4. 都无 → 跳过
    """
    elements = soup.select(article_selector)
    results = []
    seen: set[str] = set()

    for el in elements:
        anchor = None

        if el.name == "a":
            # 路径 1：selector 直接指向 <a>
            anchor = el
        else:
            # 路径 2：容器内有标题锚点
            for heading in ("h1", "h2", "h3", "h4"):
                heading_anchor = el.select_one(f"{heading} a")
                if heading_anchor:
                    anchor = heading_anchor
                    break

            if anchor is None:
                # 路径 3：取文字最长的 <a>
                all_anchors = el.find_all("a", href=True)
                if all_anchors:
                    anchor = max(all_anchors, key=lambda a: len(a.get_text(strip=True)))

        if anchor is None:
            continue

        href = anchor.get("href", "")
        if not href:
            continue
        full_url = urljoin(base_url, href)
        title = anchor.get_text(strip=True)
        if not title or full_url in seen:
            continue
        seen.add(full_url)
        results.append({"title": title, "url": full_url})

    return results


def _heuristic_extract(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """简单启发式：提取页面中最多的同域链接"""
    parsed_base = urlparse(base_url)
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc == parsed_base.netloc and parsed.path not in ("", "/"):
            title = a.get_text(strip=True)
            if title:
                candidates.append({"title": title, "url": full_url})
    # 去重保序
    seen = set()
    unique = []
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)
    return unique


async def fetch_article_content(
    url: str,
    content_selector: Optional[str],
) -> str:
    """抓取单篇文章正文，返回 HTML 字符串"""
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    if content_selector:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.select_one(content_selector)
        if tag:
            return str(tag)
        logger.warning("content_selector %r matched nothing for %s, falling back to trafilatura", content_selector, url)

    # 降级：trafilatura 自动提取（output_format="html" 保留段落换行结构）
    extracted = trafilatura.extract(html, output_format="html", include_formatting=True)
    return extracted or ""


async def fetch_articles_concurrently(
    article_stubs: list[dict],
    content_selector: Optional[str],
) -> list[dict]:
    """并发抓取多篇文章正文，限制 MAX_CONCURRENCY 并发，每篇间隔 DELAY_BETWEEN_REQUESTS 秒"""
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _fetch_one(stub: dict) -> dict:
        async with semaphore:
            try:
                content = await fetch_article_content(stub["url"], content_selector)
            except Exception as e:
                content = f"<p>内容提取失败：{e}</p>"
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
            return {**stub, "content": content}

    tasks = [_fetch_one(s) for s in article_stubs]
    results = await asyncio.gather(*tasks)
    return list(results)
