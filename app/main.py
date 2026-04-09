from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import feeds, rss_feed, settings
from app.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="RSS Web", lifespan=lifespan)

app.include_router(feeds.router)
app.include_router(settings.router)
app.include_router(rss_feed.router)
