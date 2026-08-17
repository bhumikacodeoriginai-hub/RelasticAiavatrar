"""
Database connection and session management.
Uses SQLAlchemy async engine with MySQL (aiomysql driver).
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import structlog

from config import settings

logger = structlog.get_logger()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create async engine for MySQL
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Create all tables from ORM models
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully")


async def close_db():
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")


async def check_db_health() -> bool:
    """Check database connectivity."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return False
