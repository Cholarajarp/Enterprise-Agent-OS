"""Async SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session scoped to a single request.

    Commits on success, rolls back on exception, and always closes.

    Yields:
        An ``AsyncSession`` bound to the application engine.
    """
    session = async_session_factory()
    try:
        org_id = getattr(request.state, "org_id", None)
        if org_id is not None:
            await session.execute(
                text("SET LOCAL app.current_org_id = :org_id"),
                {"org_id": str(org_id)},
            )
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
