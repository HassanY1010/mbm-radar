from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import settings
from app.core.logging import database_logger

# Use NullPool when connecting through PgBouncer (Supabase pooler).
# NullPool does NOT hold persistent connections — it creates a new one
# per request and releases it immediately after, preventing EMAXCONNSESSION
# errors from Supabase's session-mode limit of 15 clients.
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,  # Required for PgBouncer transaction mode
    }
)

# Async session maker
async_session = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Declarative base for models
Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection helper for FastAPI endpoints"""
    async with async_session() as session:
        try:
            yield session
        except Exception as e:
            database_logger.error(f"Database session error: {str(e)}")
            await session.rollback()
            raise
        finally:
            await session.close()
