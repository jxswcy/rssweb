import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routers import feeds, reader, rss_feed, settings
from app.routers.auth import router as auth_router, _LoginRequired
from app.scheduler import start_scheduler, stop_scheduler

# 配置日志级别
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="RSS Web", lifespan=lifespan)


@app.exception_handler(_LoginRequired)
async def login_required_handler(request: Request, exc: _LoginRequired):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth_router)
app.include_router(feeds.router)
app.include_router(reader.router)
app.include_router(settings.router)
app.include_router(rss_feed.router)


# ── 首页 ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


# ── 版本信息页面 ───────────────────────────────────────────────────────────

@app.get("/version")
async def version_page(request: Request):
    return templates.TemplateResponse("version.html", {"request": request})
