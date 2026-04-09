"""
路由集成测试
使用 TestClient（同步），通过 dependency_override 替换数据库，
mock scheduler 避免实际启动 APScheduler。
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from app.database import Base, get_db

# 使用内存 SQLite，StaticPool 保证所有连接共享同一内存数据库
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    """创建测试客户端，mock scheduler，使用内存 DB"""
    import app.models  # noqa: F401 — register all models with Base.metadata
    Base.metadata.create_all(bind=engine)

    with (
        patch("app.scheduler.start_scheduler"),
        patch("app.scheduler.stop_scheduler"),
        patch("app.routers.feeds.register_feed"),
        patch("app.routers.feeds.remove_feed_job"),
        patch("app.routers.feeds.run_feed_now"),
        patch("app.database.init_db"),  # skip production DB creation in lifespan
    ):
        # app.main 必须在 patch() 块内部 import，确保 scheduler mock 在
        # FastAPI lifespan 绑定 start_scheduler/stop_scheduler 之前生效
        from app.main import app
        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
        app.dependency_overrides.clear()

    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def sample_feed(client):
    """创建一个共享的测试 Feed，整个模块测试期间可用"""
    resp = client.post(
        "/feeds",
        data={
            "name": "Sample Feed",
            "url": "https://sample.example.com",
            "update_interval": "60",
            "ai_provider": "openai",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db = TestingSessionLocal()
    from app.models import Feed
    feed = db.query(Feed).filter(Feed.name == "Sample Feed").first()
    feed_id = feed.id
    db.close()
    return feed_id


# ── 首页 ──────────────────────────────────────────────────────────────────────

def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "RSS" in response.text


# ── 新建 Feed 表单 ─────────────────────────────────────────────────────────────

def test_new_feed_form(client):
    response = client.get("/feeds/new")
    assert response.status_code == 200
    assert "form" in response.text.lower()


# ── 创建 Feed ─────────────────────────────────────────────────────────────────

def test_create_feed_and_list(client):
    response = client.post(
        "/feeds",
        data={
            "name": "Test Blog",
            "url": "https://example.com",
            "update_interval": "60",
            "ai_provider": "openai",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Test Blog" in response.text


# ── 编辑 Feed ─────────────────────────────────────────────────────────────────

def test_edit_feed_form(client, sample_feed):
    response = client.get(f"/feeds/{sample_feed}/edit")
    assert response.status_code == 200
    assert "Sample Feed" in response.text


def test_edit_feed_404(client):
    response = client.get("/feeds/9999/edit")
    assert response.status_code == 404


# ── Settings ──────────────────────────────────────────────────────────────────

def test_settings_page(client):
    response = client.get("/settings")
    assert response.status_code == 200
    assert "API" in response.text


def test_save_settings(client):
    response = client.post(
        "/settings",
        data={"translate_target_lang": "zh-CN"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "设置已保存" in response.text  # 验证 saved=True 的提示


# ── RSS 输出 ──────────────────────────────────────────────────────────────────

def test_rss_404_for_unknown_feed(client):
    response = client.get("/rss/9999")
    assert response.status_code == 404


def test_rss_returns_atom_xml(client, sample_feed):
    response = client.get(f"/rss/{sample_feed}")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "atom" in content_type or "xml" in content_type
    assert b"Sample Feed" in response.content


# ── 删除 Feed ─────────────────────────────────────────────────────────────────

def test_delete_feed(client):
    # 先创建一个 feed 专门用于删除测试
    client.post(
        "/feeds",
        data={
            "name": "To Delete",
            "url": "https://todelete.example.com",
            "update_interval": "60",
            "ai_provider": "openai",
        },
        follow_redirects=True,
    )

    db = TestingSessionLocal()
    from app.models import Feed
    feed = db.query(Feed).filter(Feed.name == "To Delete").first()
    feed_id = feed.id
    db.close()

    response = client.post(f"/feeds/{feed_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "To Delete" not in response.text


def test_save_deepseek_api_key(client):
    response = client.post(
        "/settings",
        data={"deepseek_api_key": "sk-deepseek-test", "translate_target_lang": "zh-CN"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "设置已保存" in response.text


def test_settings_shows_deepseek_key_set(client):
    # 先写入 key
    client.post(
        "/settings",
        data={"deepseek_api_key": "sk-deepseek-test", "translate_target_lang": "zh-CN"},
        follow_redirects=True,
    )
    response = client.get("/settings")
    assert response.status_code == 200
    # 模板中 deepseek_key_set=True 时显示「已设置」
    assert "DeepSeek" in response.text


def test_create_rss_source_feed(client):
    """创建 rss_source 类型的 Feed，验证 DB 写入 feed_type 正确"""
    response = client.post(
        "/feeds",
        data={
            "name": "RSS Test Feed",
            "url": "https://example.com/feed.rss",
            "update_interval": "60",
            "ai_provider": "openrouter",
            "feed_type": "rss_source",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    db = TestingSessionLocal()
    from app.models import Feed
    feed = db.query(Feed).filter(Feed.name == "RSS Test Feed").first()
    assert feed is not None
    assert feed.feed_type == "rss_source"
    db.close()


def test_edit_rss_source_feed_shows_type(client):
    """编辑 rss_source Feed 时，响应页面包含该 feed_type 的值"""
    # 先创建
    client.post(
        "/feeds",
        data={
            "name": "RSS Edit Feed",
            "url": "https://example.com/feed2.rss",
            "update_interval": "60",
            "ai_provider": "openrouter",
            "feed_type": "rss_source",
        },
        follow_redirects=True,
    )
    db = TestingSessionLocal()
    from app.models import Feed
    feed = db.query(Feed).filter(Feed.name == "RSS Edit Feed").first()
    feed_id = feed.id
    db.close()

    response = client.get(f"/feeds/{feed_id}/edit")
    assert response.status_code == 200
    assert "rss_source" in response.text
