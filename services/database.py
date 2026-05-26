from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models.models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


_PENDING_COLUMNS = [
    ("users", "is_admin", "BOOLEAN DEFAULT 0"),
    ("submissions", "hashtags", "TEXT"),
]


async def _apply_sqlite_migrations(conn):
    for table, column, ddl in _PENDING_COLUMNS:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result.fetchall()}
        if column not in existing:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_sqlite_migrations(conn)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
