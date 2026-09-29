"""Database connection and a session helper."""

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from story import config
from story.models import Base


def _fix_postgres_url(url: str) -> str:
    # Some hosts hand out "postgres://" URLs, and SQLAlchemy 2.1 picks the psycopg v3 driver for a
    # bare "postgresql://". We ship psycopg2, so say so explicitly.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]
    return url


def make_engine(url: str):
    url = _fix_postgres_url(url)
    if url.startswith("sqlite"):
        # Background jobs run in worker threads, so SQLite has to allow that.
        return create_engine(url, connect_args={"check_same_thread": False})
    # Supabase's free session pooler allows only a handful of connections, so keep the pool small.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)


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
    if engine.dialect.name == "postgresql":
        lock_tables_from_public_api()


def lock_tables_from_public_api() -> None:
    """Switch on Row Level Security for every table, with no policies.

    Supabase serves the public schema through its REST API to anyone holding the project's
    anon key. RLS with no policies shuts that door, while our backend (connecting as the
    table owner) keeps full access.
    """
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            connection.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))


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
