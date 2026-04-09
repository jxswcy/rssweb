import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Feed, Article
from app.scraper import fetch_article_list, fetch_articles_concurrently
from app.translator import translate_text

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    """启动调度器并为所有已有 Feed 注册任务；过期未抓取则立即补抓"""
    scheduler.start()
    db = SessionLocal()
    try:
        feeds = db.query(Feed).all()
        for feed in feeds:
            _register_feed_job(feed)
            # 从未抓取或上次抓取时间已超过 update_interval 的，立即补抓
            if feed.last_fetched_at is None:
                scheduler.add_job(
                    _run_feed_job, args=[feed.id],
                    id=f"feed_{feed.id}_catchup",
                    replace_existing=True,
                )
            else:
                elapsed = datetime.now(timezone.utc) - feed.last_fetched_at
                if elapsed > timedelta(minutes=feed.update_interval):
                    scheduler.add_job(
                        _run_feed_job, args=[feed.id],
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
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        _run_feed_job,
        trigger="interval",
        minutes=feed.update_interval,
        id=job_id,
        args=[feed.id],
        replace_existing=True,
    )
    logger.info("Registered job %s every %d minutes", job_id, feed.update_interval)


def register_feed(feed: Feed):
    """公开接口：注册或更新 Feed 的定时任务"""
    _register_feed_job(feed)


def remove_feed_job(feed_id: int):
    """公开接口：删除 Feed 的定时任务"""
    job_id = f"feed_{feed_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("Removed job %s", job_id)


async def run_feed_now(feed_id: int):
    """手动立即触发一次抓取"""
    await _run_feed_job(feed_id)


async def _run_feed_job(feed_id: int):
    db = SessionLocal()
    try:
        feed = db.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return
        await _fetch_and_store(feed, db)
    except Exception as exc:
        logger.error("Feed %d job failed: %s", feed_id, exc)
        db.rollback()
        _update_feed_error(db, feed_id, str(exc))
    finally:
        db.close()


async def _fetch_and_store(feed: Feed, db: Session):
    from urllib.parse import urlparse
    base_url = f"{urlparse(feed.url).scheme}://{urlparse(feed.url).netloc}"

    # 获取文章列表
    stubs = await fetch_article_list(
        url=feed.url,
        title_selector=feed.title_selector,
        link_selector=feed.link_selector,
        base_url=base_url,
    )

    # 去重（Article.url 已与 feed_id 建联合唯一索引）
    existing_urls = {
        row[0] for row in db.query(Article.url).filter(Article.feed_id == feed.id).all()
    }
    new_stubs = [s for s in stubs if s["url"] not in existing_urls]

    if not new_stubs:
        _update_feed_fetched(db, feed.id)
        return

    # 并发抓取正文
    articles_data = await fetch_articles_concurrently(new_stubs, feed.content_selector)

    # 获取翻译配置
    translate_lang = _get_setting(db, "translate_target_lang") or "zh-CN"
    api_key: Optional[str] = None
    if feed.translation_enabled:
        key_name = f"{feed.ai_provider}_api_key"
        api_key = _get_setting(db, key_name)

    for data in articles_data:
        content_original = data.get("content", "")
        content_translated: Optional[str] = None

        if feed.translation_enabled and api_key and content_original:
            content_translated = await translate_text(
                text=content_original,
                provider=feed.ai_provider,
                api_key=api_key,
                target_lang=translate_lang,
            )

        article = Article(
            feed_id=feed.id,
            title=data["title"],
            url=data["url"],
            content_original=content_original,
            content_translated=content_translated,
        )
        db.add(article)

    _update_feed_fetched(db, feed.id)
    db.commit()
    logger.info("Feed %d: stored %d new articles", feed.id, len(articles_data))


def _get_setting(db: Session, key: str) -> Optional[str]:
    from app.models import Setting
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else None


def _update_feed_fetched(db: Session, feed_id: int):
    db.query(Feed).filter(Feed.id == feed_id).update(
        {"last_fetched_at": datetime.now(timezone.utc), "last_error": None}
    )
    db.commit()


def _update_feed_error(db: Session, feed_id: int, error: str):
    db.query(Feed).filter(Feed.id == feed_id).update({"last_error": error})
    db.commit()
