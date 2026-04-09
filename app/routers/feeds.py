import asyncio
import html
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Article, Feed
from app.scheduler import register_feed, remove_feed_job, run_feed_now, retranslate_feed
from app.scraper import fetch_article_list, fetch_article_content

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    feeds = db.query(Feed).order_by(Feed.created_at.desc()).all()
    feed_stats = []
    for feed in feeds:
        count = db.query(Article).filter(Article.feed_id == feed.id).count()
        untranslated = (
            db.query(Article)
            .filter(Article.feed_id == feed.id, Article.content_translated.is_(None))
            .count()
            if feed.translation_enabled else 0
        )
        feed_stats.append({
            "feed": feed,
            "article_count": count,
            "untranslated_count": untranslated,
        })
    return templates.TemplateResponse(
        "index.html", {"request": request, "feed_stats": feed_stats}
    )


@router.get("/feeds/new", response_class=HTMLResponse)
async def new_feed_form(request: Request):
    return templates.TemplateResponse(
        "feed_form.html", {"request": request, "feed": None, "error": None}
    )


@router.get("/feeds/{feed_id}/edit", response_class=HTMLResponse)
async def edit_feed_form(
    feed_id: int, request: Request, db: Session = Depends(get_db)
):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    return templates.TemplateResponse(
        "feed_form.html", {"request": request, "feed": feed, "error": None}
    )


@router.post("/feeds", response_class=RedirectResponse)
async def create_feed(
    name: str = Form(...),
    url: str = Form(...),
    article_selector: Optional[str] = Form(None),
    content_selector: Optional[str] = Form(None),
    translation_enabled: bool = Form(False),
    ai_provider: str = Form("openai"),
    ai_model: Optional[str] = Form(None),
    update_interval: int = Form(60),
    feed_type: str = Form("webpage"),
    db: Session = Depends(get_db),
):
    feed = Feed(
        name=name,
        url=url,
        article_selector=article_selector or None,
        content_selector=content_selector or None,
        translation_enabled=translation_enabled,
        ai_provider=ai_provider,
        ai_model=ai_model or None,
        update_interval=update_interval,
        feed_type=feed_type,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    register_feed(feed, run_immediately=True)
    return RedirectResponse(url="/", status_code=303)


@router.post("/feeds/preview")
async def preview_feed(
    request: Request,
    url: str = Form(...),
    article_selector: Optional[str] = Form(None),
):
    """HTMX 预览端点：返回提取到的文章列表 HTML 片段"""
    try:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        articles = await fetch_article_list(
            url=url,
            article_selector=article_selector or None,
            title_selector=None,
            link_selector=None,
            base_url=base_url,
        )
        items_html = "".join(
            f'<li><a href="{html.escape(a["url"], quote=True)}" target="_blank">'
            f'{html.escape(a["title"])}</a></li>'
            for a in articles[:20]
        )
        return HTMLResponse(
            f'<ul class="preview-list">{items_html}</ul>'
            if items_html
            else '<p class="preview-empty">未找到文章，请检查 URL 或 Selector</p>'
        )
    except Exception as exc:
        return HTMLResponse(
            f'<p class="preview-error">预览失败：{html.escape(str(exc))}</p>',
            status_code=200,
        )


@router.post("/feeds/preview-content")
async def preview_content(
    article_url: str = Form(...),
    content_selector: Optional[str] = Form(None),
):
    """HTMX 正文预览端点：抓取指定 URL 的正文并返回 HTML 片段"""
    try:
        content = await fetch_article_content(
            url=article_url,
            content_selector=content_selector or None,
        )
        if not content:
            return HTMLResponse('<p class="preview-empty">未提取到正文，请检查 URL 或 Selector</p>')
        # 截取前 3000 字符避免预览过长
        preview = content[:3000]
        truncated = len(content) > 3000
        suffix = '<p style="color:#86868b;font-size:0.8rem;margin-top:0.5rem;">…（仅显示前 3000 字符）</p>' if truncated else ""
        return HTMLResponse(
            f'<div class="content-preview">{preview}</div>{suffix}'
        )
    except Exception as exc:
        return HTMLResponse(
            f'<p class="preview-error">预览失败：{html.escape(str(exc))}</p>',
            status_code=200,
        )


@router.post("/feeds/{feed_id}", response_class=RedirectResponse)
async def update_feed(
    feed_id: int,
    name: str = Form(...),
    url: str = Form(...),
    article_selector: Optional[str] = Form(None),
    content_selector: Optional[str] = Form(None),
    translation_enabled: bool = Form(False),
    ai_provider: str = Form("openai"),
    ai_model: Optional[str] = Form(None),
    update_interval: int = Form(60),
    feed_type: str = Form("webpage"),
    db: Session = Depends(get_db),
):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    feed.name = name
    feed.url = url
    feed.article_selector = article_selector or None
    feed.content_selector = content_selector or None
    feed.translation_enabled = translation_enabled
    feed.ai_provider = ai_provider
    feed.ai_model = ai_model or None
    feed.update_interval = update_interval
    feed.feed_type = feed_type
    db.commit()
    register_feed(feed)
    return RedirectResponse(url="/", status_code=303)


@router.post("/feeds/{feed_id}/delete", response_class=RedirectResponse)
async def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    remove_feed_job(feed_id)
    db.delete(feed)
    db.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/feeds/{feed_id}/refresh", response_class=RedirectResponse)
async def refresh_feed(feed_id: int, db: Session = Depends(get_db)):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    asyncio.create_task(run_feed_now(feed_id))  # 后台执行，立即返回
    return RedirectResponse(url="/", status_code=303)


@router.post("/feeds/{feed_id}/retranslate", response_class=RedirectResponse)
async def retranslate(feed_id: int, db: Session = Depends(get_db)):
    feed = db.query(Feed).filter(Feed.id == feed_id).first()
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    asyncio.create_task(retranslate_feed(feed_id))  # 后台执行，立即返回
    return RedirectResponse(url="/", status_code=303)


