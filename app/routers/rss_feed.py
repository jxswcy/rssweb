from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Article, Feed
from app.rss import generate_rss_feed

router = APIRouter()


@router.get("/rss/{feed_id}")
async def get_rss(feed_id: int, request: Request, db: Session = Depends(get_db)):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    query = db.query(Article).filter(Article.feed_id == feed_id)
    # 双语翻译开启时，只输出已完成翻译的文章，避免 RSS 客户端将纯原文版本标记为已读
    if feed.translation_enabled:
        query = query.filter(Article.content_translated.isnot(None))
    articles = query.order_by(Article.fetched_at.desc()).limit(50).all()

    base_url = str(request.base_url).rstrip("/")
    xml_bytes = generate_rss_feed(feed, articles, base_url=base_url)
    return Response(
        content=xml_bytes,
        media_type="application/atom+xml; charset=utf-8",
    )
