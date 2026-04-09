from datetime import timezone
from feedgen.feed import FeedGenerator
from app.models import Feed, Article


def generate_rss_feed(feed: Feed, articles: list[Article], base_url: str) -> bytes:
    """生成 Atom RSS XML，双语内容时原文在前、译文在后"""
    fg = FeedGenerator()
    fg.id(f"{base_url}/rss/{feed.id}")
    fg.title(feed.name)
    fg.link(href=feed.url, rel="alternate")
    fg.link(href=f"{base_url}/rss/{feed.id}", rel="self")
    fg.language("zh-CN")

    if feed.last_fetched_at:
        updated = feed.last_fetched_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        fg.updated(updated)

    for article in articles:
        fe = fg.add_entry(order="append")
        fe.id(article.url)
        fe.title(article.title)
        fe.link(href=article.url)

        pub = article.published_at or article.fetched_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        fe.published(pub)
        fe.updated(pub)

        if article.content_translated:
            content = (
                f"<div><h3>原文</h3>{article.content_original}</div>"
                f"<hr/>"
                f"<div><h3>译文</h3>{article.content_translated}</div>"
            )
        else:
            content = article.content_original or ""

        fe.content(content, type="html")

    return fg.atom_str(pretty=True)
