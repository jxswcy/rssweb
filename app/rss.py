from datetime import datetime, timezone
from html import escape as html_escape
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup

from app.constants import TZ_SHANGHAI
from app.models import Feed, Article


def _to_shanghai(dt: datetime) -> datetime:
    """确保时间带有时区信息。入库时间已统一为东8区，只需补上时区标记。"""
    if dt is None:
        return datetime.now(TZ_SHANGHAI)
    if dt.tzinfo is None:
        # 无时区时间标记为东8区（入库时已是东8区时间）
        dt = dt.replace(tzinfo=TZ_SHANGHAI)
    return dt


def _interleave_bilingual(original_html: str, translated_html: str) -> str:
    """将原文和译文按段落交替排列：原文段1 → 译文段1 → 原文段2 → 译文段2..."""
    orig_paras = BeautifulSoup(original_html or "", "html.parser").find_all("p")
    trans_paras = BeautifulSoup(translated_html or "", "html.parser").find_all("p")

    # 无段落结构时退回整块显示
    if not orig_paras:
        return (
            f'<p style="color:#666;font-style:italic;">{original_html}</p>'
            f"<p>{translated_html}</p>"
        )

    orig_style = "color:#555;font-style:italic;margin-top:2px;margin-bottom:14px;"

    def _styled_p(tag) -> str:
        """给 BeautifulSoup <p> 标签追加原文样式"""
        existing = tag.get("style", "")
        tag["style"] = (existing + ";" + orig_style).lstrip(";")
        return str(tag)

    parts = []
    for op, tp in zip(orig_paras, trans_paras):
        parts.append(_styled_p(op))
        parts.append(str(tp))

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

        # 构建正文：标题双语 + 正文内容
        title_html = _build_bilingual_title(article.title, article.title_translated)

        if article.content_translated:
            content = title_html + _interleave_bilingual(article.content_original, article.content_translated)
        else:
            content = title_html + (article.content_original or "")

        fe.content(content, type="html")

    return fg.atom_str(pretty=True)


def _build_bilingual_title(original: str, translated: str | None) -> str:
    """构建双语标题 HTML，原文斜体灰色，译文正常显示。自动转义 HTML 特殊字符。"""
    safe_original = html_escape(original)
    if not translated or translated == original:
        return f"<h1>{safe_original}</h1>"
    safe_translated = html_escape(translated)
    return (
        f'<h1 style="color:#555;font-style:italic;">{safe_original}</h1>'
        f"<h1>{safe_translated}</h1>"
    )
