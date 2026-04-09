from datetime import datetime, timezone
from app.models import Feed, Article, Setting

def test_create_feed(db):
    feed = Feed(
        name="Test Feed",
        url="https://example.com",
        update_interval=60,
        translation_enabled=False,
        ai_provider="openai",
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    assert feed.id is not None
    assert feed.name == "Test Feed"
    assert feed.created_at is not None

def test_create_article(db):
    feed = Feed(name="F", url="https://example.com", update_interval=60,
                translation_enabled=False, ai_provider="openai")
    db.add(feed)
    db.commit()
    article = Article(
        feed_id=feed.id,
        title="Article 1",
        url="https://example.com/1",
        content_original="<p>Hello</p>",
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    assert article.id is not None
    assert article.feed_id == feed.id

def test_article_url_unique_per_feed(db):
    feed = Feed(name="F", url="https://example.com", update_interval=60,
                translation_enabled=False, ai_provider="openai")
    db.add(feed)
    db.commit()
    a1 = Article(feed_id=feed.id, title="A", url="https://example.com/1",
                 content_original="x")
    a2 = Article(feed_id=feed.id, title="B", url="https://example.com/1",
                 content_original="y")
    db.add(a1)
    db.commit()
    db.add(a2)
    import pytest
    with pytest.raises(Exception):
        db.commit()

def test_setting_crud(db):
    s = Setting(key="openai_api_key", value="sk-test")
    db.add(s)
    db.commit()
    result = db.query(Setting).filter_by(key="openai_api_key").first()
    assert result.value == "sk-test"

def test_feed_has_ai_model_and_article_selector(db):
    feed = Feed(
        name="New Feed",
        url="https://example.com",
        update_interval=60,
        translation_enabled=False,
        ai_provider="openai",
        ai_model="gpt-4o-mini",
        article_selector="h3.post-title a",
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    assert feed.ai_model == "gpt-4o-mini"
    assert feed.article_selector == "h3.post-title a"
