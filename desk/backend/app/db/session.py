"""SQLAlchemy engine + session lifecycle.

Mirrors loft_climate's pattern: file-backed SQLite, WAL mode, threadpool
session_scope context manager. Tables are created via Base.metadata.create_all
on lifespan startup — no Alembic migrations (the desk schema is tiny and
additive-only).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(
        f"sqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _enable_wal(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return eng


def _ensure_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _make_engine(get_settings().db_path)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def reset_engine_for_tests(db_path: Path) -> None:
    """Tests call this to bind to a per-test database file."""
    global _engine, _SessionLocal
    _engine = _make_engine(db_path)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables. Idempotent — safe to call on every startup."""
    _ensure_engine()
    # Import models so SQLAlchemy registers them on Base.
    from app.db import models  # noqa: F401
    assert _engine is not None
    Base.metadata.create_all(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    _ensure_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
