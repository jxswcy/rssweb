from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app.database import init_db
from app.routers import feeds, rss_feed, settings
from app.routers.auth import router as auth_router, _LoginRequired
from app.scheduler import start_scheduler, stop_scheduler


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
app.include_router(settings.router)
app.include_router(rss_feed.router)
