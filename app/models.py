from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class Feed(Base):
    __tablename__ = "feeds"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    title_selector = Column(Text, nullable=True)
    link_selector = Column(Text, nullable=True)
    content_selector = Column(Text, nullable=True)
    translation_enabled = Column(Boolean, nullable=False, default=False)
    ai_provider = Column(Text, nullable=False, default="openai")
    update_interval = Column(Integer, nullable=False, default=60)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    articles = relationship("Article", back_populates="feed",
                            cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("feed_id", "url", name="uq_feed_url"),
    )

    id = Column(Integer, primary_key=True, index=True)
    feed_id = Column(Integer, ForeignKey("feeds.id"), nullable=False)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    content_original = Column(Text, nullable=True)
    content_translated = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    published_at = Column(DateTime(timezone=True), nullable=True)

    feed = relationship("Feed", back_populates="articles")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(Text, primary_key=True)
    value = Column(Text, nullable=True)
