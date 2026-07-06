from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings
from app.core.logging import database_logger

# Create database engine with connection pooling config
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5
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
