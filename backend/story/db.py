"""Database connection and a session helper."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from story import config
from story.models import Base


def _fix_postgres_url(url: str) -> str:
    # Render hands out "postgres://" URLs; SQLAlchemy wants "postgresql://".
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def make_engine(url: str):
    url = _fix_postgres_url(url)
    if url.startswith("sqlite"):
        # Background jobs run in worker threads, so SQLite has to allow that.
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(config.DATABASE_URL)
SessionMaker = sessionmaker(bind=engine, expire_on_commit=False)


def use_database(url: str) -> None:
    """Point the app at a different database (tests use an in-memory one)."""
    global engine
    engine = make_engine(url)
    SessionMaker.configure(bind=engine)
    create_tables()


def create_tables() -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """Open a session, commit if everything went fine, roll back if not."""
    session: Session = SessionMaker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
