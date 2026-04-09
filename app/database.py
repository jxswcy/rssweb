import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/feeds.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    poolclass=NullPool,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — ensure models are registered
    Base.metadata.create_all(bind=engine)
    # 幂等 ALTER TABLE：为已有数据库添加新字段
    with engine.connect() as conn:
        for ddl in [
            "ALTER TABLE feeds ADD COLUMN ai_model TEXT",
            "ALTER TABLE feeds ADD COLUMN article_selector TEXT",
            "ALTER TABLE articles ADD COLUMN title_translated TEXT",
            "ALTER TABLE feeds ADD COLUMN feed_type TEXT DEFAULT 'webpage'",
            "ALTER TABLE articles ADD COLUMN published_at DATETIME",
        ]:
            try:
                conn.execute(text(ddl))
                conn.commit()
            except Exception:
                pass  # 字段已存在则忽略

    # 写入默认管理员密码（首次初始化时）
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT value FROM settings WHERE key = 'admin_password_hash'")
        ).fetchone()
        if not row:
            default_hash = _pwd_context.hash("admin")
            conn.execute(
                text("INSERT INTO settings (key, value) VALUES ('admin_password_hash', :h)"),
                {"h": default_hash},
            )
            conn.commit()
