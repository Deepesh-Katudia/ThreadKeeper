"""Database connection and a session helper."""

import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from story import config
from story.models import Base

log = logging.getLogger(__name__)


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
    add_missing_columns()
    if engine.dialect.name == "postgresql":
        try:
            lock_tables_from_public_api()
        except OperationalError as error:
            # Hardening, not a reason to refuse to start: the next start will try again.
            log.warning("couldn't switch on row level security this time: %s", error)


def add_missing_columns() -> None:
    """A tiny migration: add columns that exist in the models but not yet in the database.

    create_all only creates missing tables, so a column added to an existing table (like
    directives.beat_changes) would otherwise never reach a database created earlier.
    New columns must be nullable for this to work on tables that already have rows.
    """
    existing_tables = set(inspect(engine).get_table_names())
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {column["name"] for column in inspect(connection).get_columns(table.name)}
            for column in table.columns:
                if column.name not in have:
                    column_type = column.type.compile(dialect=engine.dialect)
                    connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))


def lock_tables_from_public_api() -> None:
    """Switch on Row Level Security for every table, with no policies.

    Supabase serves the public schema through its REST API to anyone holding the project's
    anon key. RLS with no policies shuts that door, while our backend (connecting as the
    table owner) keeps full access.

    Only tables that don't have RLS yet are touched. ALTER TABLE takes an exclusive lock, and
    during a zero-downtime deploy the old server is still reading these tables, so running it
    on every start deadlocked (and crashed) the new server.
    """
    with engine.begin() as connection:
        unlocked = set(connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND NOT rowsecurity"
        )).scalars())
        # Never queue behind the live server's locks for long; give up and retry next start.
        connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        for table in Base.metadata.sorted_tables:
            if table.name in unlocked:
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
