"""Database engine, session factory, and the declarative base.

Synchronous SQLAlchemy 2.0 + psycopg2. The whole v1 flow is synchronous
(sync routes run in FastAPI's threadpool; Pydantic AI agents use run_sync),
which keeps the MVP simple and avoids event-loop pitfalls. Revisit async in
Phase 4 if the queue-driven pipeline needs it.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

engine = create_engine(
    get_settings().database_url,
    echo=False,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
