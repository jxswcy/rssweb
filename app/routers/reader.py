from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case

from app.constants import TZ_SHANGHAI
from app.database import get_db
from app.models import Article, Feed, ReadStatus
from app.routers.auth import require_login
from app.rss import _interleave_bilingual, _build_bilingual_title

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _get_unread_counts(db: Session) -> dict:
    """获取各订阅源的未读文章数（单次查询优化）"""
    # 使用 LEFT JOIN 一次查询获取所有 feed 的未读数
    # 未读 = 文章没有对应的 ReadStatus 记录，或 is_read 为 False
    # 注意：需要先检查 Article.id IS NOT NULL，否则无文章的 Feed 会产生错误的未读数
    result = db.query(
        Feed.id,
        func.count(Article.id).label("total"),
        func.coalesce(
            func.sum(
                case(
                    (Article.id == None, 0),  # 无文章时返回 0
                    (ReadStatus.is_read == False, 1),
                    (ReadStatus.is_read == None, 1),
                    else_=0
                )
            ), 0
        ).label("unread")
    ).outerjoin(
        Article, Feed.id == Article.feed_id
    ).outerjoin(
        ReadStatus, Article.id == ReadStatus.article_id
    ).group_by(Feed.id).all()

    return {feed_id: int(unread) for feed_id, total, unread in result}


@router.get("/reader", response_class=HTMLResponse)
async def reader_page(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
):
    """阅读器主页面"""
    feeds = db.query(Feed).order_by(Feed.name).all()
    unread_counts = _get_unread_counts(db)
    return templates.TemplateResponse(
        "reader.html",
        {"request": request, "feeds": feeds, "unread_counts": unread_counts},
    )


@router.get("/reader/feeds", response_class=HTMLResponse)
async def get_feed_list(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
):
    """HTMX：获取订阅源列表（含未读计数）"""
    feeds = db.query(Feed).order_by(Feed.name).all()
    unread_counts = _get_unread_counts(db)
    return templates.TemplateResponse(
        "partials/feed_list.html",
        {"request": request, "feeds": feeds, "unread_counts": unread_counts},
    )


@router.get("/reader/feeds/{feed_id}/articles", response_class=HTMLResponse)
async def get_article_list(
    feed_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
    unread_only: bool = True,
):
    """HTMX：获取文章列表"""
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        return HTMLResponse('<div class="empty-state"><p>订阅源不存在</p></div>', status_code=404)

    query = db.query(Article).options(
        joinedload(Article.read_status)
    ).filter(Article.feed_id == feed_id)

    if unread_only:
        # 过滤已读文章
        read_ids = db.query(ReadStatus.article_id).filter(ReadStatus.is_read == True)
        query = query.filter(~Article.id.in_(read_ids))

    articles = query.order_by(
        Article.published_at.desc().nullslast(),
        Article.fetched_at.desc()
    ).limit(100).all()

    return templates.TemplateResponse(
        "partials/article_list.html",
        {
            "request": request,
            "feed": feed,
            "articles": articles,
            "unread_only": unread_only,
        },
    )


@router.get("/reader/articles/{article_id}", response_class=HTMLResponse)
async def get_article_detail(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
):
    """HTMX：获取文章详情（自动标记为已读）"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return HTMLResponse('<div class="empty-state"><p>文章不存在</p></div>', status_code=404)

    # 自动标记为已读
    existing = db.query(ReadStatus).filter(ReadStatus.article_id == article_id).first()
    if not existing:
        db.add(ReadStatus(article_id=article_id, is_read=True))
        db.commit()
    elif not existing.is_read:
        existing.is_read = True
        existing.read_at = datetime.now(TZ_SHANGHAI)
        db.commit()

    # 生成双语内容（包含双语标题）
    bilingual_content = ""
    if article.content_translated and article.content_original:
        # 添加双语标题
        title_html = _build_bilingual_title(article.title, article.title_translated)
        bilingual_content = title_html + _interleave_bilingual(
            article.content_original, article.content_translated
        )

    return templates.TemplateResponse(
        "partials/article_detail.html",
        {
            "request": request,
            "article": article,
            "bilingual_content": bilingual_content,
        },
    )


@router.post("/reader/articles/{article_id}/unread", response_class=HTMLResponse)
async def mark_article_unread(
    article_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
):
    """标记文章为未读"""
    existing = db.query(ReadStatus).filter(ReadStatus.article_id == article_id).first()
    if existing:
        existing.is_read = False
        db.commit()
    return HTMLResponse('<span style="color:var(--stone);font-size:12px;">已标记为未读</span>')


@router.post("/reader/feeds/{feed_id}/mark-all-read", response_class=HTMLResponse)
async def mark_all_read(
    feed_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_login),
):
    """标记订阅源所有文章为已读"""
    articles = db.query(Article).filter(Article.feed_id == feed_id).all()
    for article in articles:
        existing = db.query(ReadStatus).filter(ReadStatus.article_id == article.id).first()
        if not existing:
            db.add(ReadStatus(article_id=article.id, is_read=True))
        elif not existing.is_read:
            existing.is_read = True
            existing.read_at = datetime.now(TZ_SHANGHAI)
    db.commit()
    return HTMLResponse('<span style="color:var(--stone);font-size:12px;">已全部标记为已读</span>')
