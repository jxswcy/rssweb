from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from app.models import Feed, Article

# 东8区时区
TZ_SHANGHAI = timezone(timedelta(hours=8))


def _to_shanghai(dt: datetime) -> datetime:
    """将时间转换为东8区"""
    if dt is None:
        return datetime.now(TZ_SHANGHAI)
    if dt.tzinfo is None:
        # 假设无时区的时间是 UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ_SHANGHAI)


def _interleave_bilingual(original_html: str, translated_html: str) -> str:
    """将原文和译文按段落交替排列：原文段1 → 译文段1 → 原文段2 → 译文段2..."""
    orig_paras = BeautifulSoup(original_html or "", "html.parser").find_all("p")
    trans_paras = BeautifulSoup(translated_html or "", "html.parser").find_all("p")

    # 无段落结构时退回整块显示
    if not orig_paras:
        return (
            f"<p>{original_html}</p>"
            f'<p style="color:#666;font-style:italic;">{translated_html}</p>'
        )

    trans_style = "color:#555;font-style:italic;margin-top:2px;margin-bottom:14px;"

    def _styled_p(tag) -> str:
        """给 BeautifulSoup <p> 标签追加译文样式"""
        existing = tag.get("style", "")
        tag["style"] = (existing + ";" + trans_style).lstrip(";")
        return str(tag)

    parts = []
    for op, tp in zip(orig_paras, trans_paras):
        parts.append(str(op))
        parts.append(_styled_p(tp))

    for op in orig_paras[len(trans_paras):]:
        parts.append(str(op))
    for tp in trans_paras[len(orig_paras):]:
        parts.append(_styled_p(tp))

    return "\n".join(parts)


def generate_rss_feed(feed: Feed, articles: list[Article], base_url: str) -> bytes:
    """生成 Atom RSS XML，双语内容时按段落交替排列"""
    fg = FeedGenerator()
    fg.id(f"{base_url}/rss/{feed.id}")
    fg.title(feed.name)
    fg.link(href=feed.url, rel="alternate")
    fg.link(href=f"{base_url}/rss/{feed.id}", rel="self")
    fg.language("zh-CN")

    updated_dt = feed.last_fetched_at or getattr(feed, "created_at", None)
    if updated_dt is None:
        updated_dt = datetime.now(TZ_SHANGHAI)
    else:
        updated_dt = _to_shanghai(updated_dt)
    fg.updated(updated_dt)

    for article in articles:
        fe = fg.add_entry(order="append")
        fe.id(article.url)
        fe.title(article.title_translated or article.title)
        fe.link(href=article.url)

        pub = article.published_at or article.fetched_at
        pub = _to_shanghai(pub)
        fe.published(pub)
        fe.updated(pub)

        if article.content_translated:
            content = _interleave_bilingual(article.content_original, article.content_translated)
        else:
            content = article.content_original or ""

        fe.content(content, type="html")

    return fg.atom_str(pretty=True)
