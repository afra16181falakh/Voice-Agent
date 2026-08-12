import structlog
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

logger = structlog.get_logger(__name__)

# Base class for SQLAlchemy declarative models
Base = declarative_base()

# Create async engine
engine = create_async_engine(
    settings.db.async_url,
    echo=False,  # Set to True for debugging SQL queries
    pool_size=settings.db.pool_size,
    max_overflow=settings.db.max_overflow,
)

# Async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("db_session_exception", error=str(e))
            raise
        finally:
            await session.close()

async def init_db() -> None:
    """
    Initializes database tables.
    """
    logger.info("initializing_database_tables")
    try:
        async with engine.begin() as conn:
            # Optionally create pgvector extension if we want to support it natively
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                logger.info("pgvector_extension_initialized")
            except Exception as e:
                logger.warning(
                    "pgvector_extension_failed_to_create", 
                    detail="pgvector might not be installed. Falling back to array-based/no-vector if necessary.",
                    error=str(e)
                )
            
            # Create all tables defined in models/schema
            await conn.run_sync(Base.metadata.create_all)
            logger.info("database_tables_created_successfully")

            # create_all() only creates missing TABLES -- it never alters an
            # already-existing table to add new columns. There's no
            # migration framework in this project, so new columns added to
            # an ORM model (like UserORM.google_id) need an explicit,
            # idempotent patch here to reach tables that already existed
            # before the column was added. Safe to run on every startup.
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id VARCHAR(100)"))
                await conn.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))
                await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE"))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_id ON users (google_id) WHERE google_id IS NOT NULL"
                ))
            except Exception as e:
                logger.warning("schema_patch_failed", error=str(e))
    except Exception as e:
        logger.error("database_initialization_failed", error=str(e))
        # Do not block app startup in local mode if PostgreSQL is not running yet,
        # but log a warning.
