import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import SessionLocal
from app.models import Feed, Article
from app.scraper import fetch_article_list, fetch_articles_concurrently, parse_rss_feed
from app.translator import translate_text

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_fetch_lock = asyncio.Lock()  # 串行化所有 Feed 的抓取+写库，避免 SQLite 并发写冲突


def start_scheduler():
    """启动调度器并为所有已有 Feed 注册任务；过期未抓取则立即补抓"""
    scheduler.start()
    db = SessionLocal()
    try:
        feeds = db.query(Feed).all()
        for feed in feeds:
            _register_feed_job(feed)
            # 从未抓取或上次抓取时间已超过 update_interval 的，立即补抓
            last = feed.last_fetched_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            needs_catchup = (
                last is None
                or (datetime.now(timezone.utc) - last) > timedelta(minutes=feed.update_interval)
            )
            if needs_catchup:
                scheduler.add_job(
                    _run_feed_job,
                    trigger="date",
                    args=[feed.id],
                    id=f"feed_{feed.id}_catchup",
                    replace_existing=True,
                )
    finally:
        db.close()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _register_feed_job(feed: Feed):
    """为指定 Feed 注册/更新定时任务"""
    job_id = f"feed_{feed.id}"
    scheduler.add_job(
        _run_feed_job,
        trigger="interval",
        minutes=feed.update_interval,
        id=job_id,
        args=[feed.id],
        replace_existing=True,
    )
    logger.info("Registered job %s every %d minutes", job_id, feed.update_interval)


def register_feed(feed: Feed, run_immediately: bool = False):
    """公开接口：注册或更新 Feed 的定时任务。run_immediately=True 时立即触发一次抓取。"""
    _register_feed_job(feed)
    if run_immediately:
        scheduler.add_job(
            _run_feed_job,
            trigger="date",
            args=[feed.id],
            id=f"feed_{feed.id}_initial",
            replace_existing=True,
        )
        logger.info("Scheduled immediate fetch for new feed %d", feed.id)


def remove_feed_job(feed_id: int):
    """公开接口：删除 Feed 的定时任务"""
    job_id = f"feed_{feed_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Removed job %s", job_id)


async def run_feed_now(feed_id: int):
    """手动立即触发一次抓取"""
    await _run_feed_job(feed_id)


async def retranslate_feed(feed_id: int):
    """对 feed 中所有 content_translated IS NULL 的文章逐篇补做翻译，翻译一篇立即写库"""
    # 不使用 _fetch_lock：retranslate 只更新已有文章，与 fetch 插入新文章不冲突
    # ── 阶段 1：读取配置和待翻译文章列表（读完即关 session）──────────────
    db = SessionLocal()
    try:
        feed = db.query(Feed).filter(Feed.id == feed_id).first()
        if not feed or not feed.translation_enabled:
            logger.info("Feed %d: retranslate skipped — translation not enabled", feed_id)
            return

        ai_provider = feed.ai_provider
        if ai_provider == "google_free":
            api_key = ""
        else:
            key_name = f"{ai_provider}_api_key"
            api_key = _get_setting(db, key_name)
            if not api_key:
                logger.warning("Feed %d: retranslate skipped — %s not set", feed_id, key_name)
                return
        ai_model          = feed.ai_model
        raw               = _get_setting(db, f"{ai_provider}_base_url")
        provider_base_url = raw if raw else None
        translate_lang    = _get_setting(db, "translate_target_lang") or "zh-CN"

        pending = [
            {"id": a.id, "title": a.title, "content": a.content_original,
             "has_title_trans": a.title_translated is not None}
            for a in db.query(Article)
            .filter(Article.feed_id == feed_id, Article.content_translated.is_(None))
            .all()
            if a.content_original
        ]
    finally:
        db.close()

    if not pending:
        logger.info("Feed %d: retranslate — no untranslated articles", feed_id)
        return

    logger.info("Feed %d: retranslating %d articles (one-by-one)", feed_id, len(pending))
    done = 0

    # ── 阶段 2：逐篇翻译（标题+正文），每篇完成立即写库 ─────────────────
    for item in pending:
        update: dict = {}

        # 翻译标题（如尚未翻译）
        if not item["has_title_trans"]:
            try:
                t = await translate_text(
                    text=item["title"],
                    provider=ai_provider, api_key=api_key,
                    model=ai_model or None, target_lang=translate_lang,
                    base_url=provider_base_url,
                )
                if t and t != item["title"]:
                    update["title_translated"] = t
            except Exception as exc:
                logger.error("Feed %d: retranslate title article %d failed: %s", feed_id, item["id"], exc)

        # 翻译正文
        try:
            result = await translate_text(
                text=item["content"],
                provider=ai_provider, api_key=api_key,
                model=ai_model or None, target_lang=translate_lang,
                base_url=provider_base_url,
            )
            if result and result != item["content"]:
                update["content_translated"] = result
        except Exception as exc:
            logger.error("Feed %d: retranslate article %d failed: %s", feed_id, item["id"], exc)

        if not update:
            continue

        db = SessionLocal()
        try:
            db.query(Article).filter(Article.id == item["id"]).update(update)
            db.commit()
            done += 1
            logger.info("Feed %d: retranslated article %d (%d/%d)", feed_id, item["id"], done, len(pending))
        except Exception as exc:
            db.rollback()
            logger.error("Feed %d: write article %d failed: %s", feed_id, item["id"], exc)
        finally:
            db.close()

    logger.info("Feed %d: retranslate done %d / %d", feed_id, done, len(pending))


async def _run_feed_job(feed_id: int):
    async with _fetch_lock:
        try:
            await _fetch_and_store(feed_id)
        except Exception as exc:
            logger.error("Feed %d job failed: %s", feed_id, exc)
            try:
                db = SessionLocal()
                try:
                    _update_feed_error(db, feed_id, str(exc))
                finally:
                    db.close()
            except Exception as write_exc:
                logger.error("Failed to write error status for feed %d: %s", feed_id, write_exc)


async def _fetch_and_store(feed_id: int):
    from urllib.parse import urlparse

    # ── 阶段 1：读取配置（短暂打开 DB，读完即关）──────────────────────────
    db = SessionLocal()
    try:
        feed = db.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return
        # 提取所有需要的字段，避免 session 关闭后 lazy-load
        feed_id_      = feed.id
        feed_url      = feed.url
        article_sel   = feed.article_selector
        title_sel     = feed.title_selector
        link_sel      = feed.link_selector
        content_sel   = feed.content_selector
        trans_enabled = feed.translation_enabled
        ai_provider   = feed.ai_provider
        ai_model      = feed.ai_model
        feed_type     = feed.feed_type  # 新增：读取 feed 类型

        existing_urls = {
            row[0] for row in db.query(Article.url).filter(Article.feed_id == feed_id_).all()
        }
        translate_lang = _get_setting(db, "translate_target_lang") or "zh-CN"
        api_key: Optional[str] = None
        provider_base_url: Optional[str] = None
        if trans_enabled:
            if ai_provider == "google_free":
                api_key = ""  # google_free 无需 API Key
            else:
                key_name = f"{ai_provider}_api_key"
                api_key = _get_setting(db, key_name)
                if not api_key:
                    logger.warning(
                        "Feed %d: translation_enabled but %s is not set in settings, skipping translation",
                        feed_id_, key_name,
                    )
            raw = _get_setting(db, f"{ai_provider}_base_url")
            provider_base_url = raw if raw else None
    finally:
        db.close()  # ← 读完即关，不持有 session 做 I/O

    # ── 阶段 2：网络抓取 + AI 翻译（纯 async I/O，不持有 DB）──────────────
    if feed_type == "rss_source":
        stubs = await parse_rss_feed(feed_url)
    else:
        base_url = f"{urlparse(feed_url).scheme}://{urlparse(feed_url).netloc}"
        stubs = await fetch_article_list(
            url=feed_url,
            article_selector=article_sel,
            title_selector=title_sel,
            link_selector=link_sel,
            base_url=base_url,
        )
    new_stubs = [s for s in stubs if s["url"] not in existing_urls]

    if not new_stubs:
        db = SessionLocal()
        try:
            _update_feed_fetched(db, feed_id_)
            db.commit()
        finally:
            db.close()
        return

    articles_data = await fetch_articles_concurrently(new_stubs, content_sel)

    # ── 阶段 3：逐篇翻译（标题+正文）+立即写库 ──────────────────────────
    saved = 0
    for data in articles_data:
        content_original   = data.get("content", "")
        content_translated: Optional[str] = None
        title_translated:   Optional[str] = None

        if trans_enabled and (api_key is not None):
            # 翻译标题（短文本，单独调用）
            try:
                title_translated = await translate_text(
                    text=data["title"],
                    provider=ai_provider,
                    api_key=api_key,
                    model=ai_model or None,
                    target_lang=translate_lang,
                    base_url=provider_base_url,
                )
                if title_translated == data["title"]:
                    title_translated = None  # 翻译无效则忽略
            except Exception as exc:
                logger.error("Feed %d: translate title '%s' failed: %s", feed_id_, data["title"], exc)

            # 翻译正文
            if content_original:
                try:
                    content_translated = await translate_text(
                        text=content_original,
                        provider=ai_provider,
                        api_key=api_key,
                        model=ai_model or None,
                        target_lang=translate_lang,
                        base_url=provider_base_url,
                    )
                except Exception as exc:
                    logger.error("Feed %d: translate content '%s' failed: %s", feed_id_, data["title"], exc)

        db = SessionLocal()
        try:
            stmt = sqlite_insert(Article).values(
                feed_id=feed_id_,
                title=data["title"],
                title_translated=title_translated,
                url=data["url"],
                content_original=content_original,
                content_translated=content_translated,
                published_at=data.get("published_at"),  # 新增：rss_source 类型携带此字段
            ).on_conflict_do_nothing(index_elements=["feed_id", "url"])
            db.execute(stmt)
            db.commit()
            saved += 1
        except Exception as exc:
            db.rollback()
            logger.error("Feed %d: save article '%s' failed: %s", feed_id_, data["title"], exc)
        finally:
            db.close()

    db = SessionLocal()
    try:
        _update_feed_fetched(db, feed_id_)
        db.commit()
    finally:
        db.close()
    logger.info("Feed %d: stored %d / %d new articles", feed_id_, saved, len(articles_data))


def _get_setting(db: Session, key: str) -> Optional[str]:
    from app.models import Setting
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else None


def _update_feed_fetched(db: Session, feed_id: int):
    db.query(Feed).filter(Feed.id == feed_id).update(
        {"last_fetched_at": datetime.now(timezone.utc), "last_error": None}
    )
    # commit 由调用方负责


def _update_feed_error(db: Session, feed_id: int, error: str):
    db.query(Feed).filter(Feed.id == feed_id).update({"last_error": error})
    db.commit()
