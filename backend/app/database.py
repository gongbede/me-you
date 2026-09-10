import os
from collections.abc import AsyncGenerator, Generator

from pymongo import ASCENDING, AsyncMongoClient, IndexModel
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL, POSTGRESQL_DATABASE_URL


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# PostgreSQL is prepared separately while SQLite remains available for rollback.
postgres_engine = (
    create_async_engine(POSTGRESQL_DATABASE_URL, future=True)
    if POSTGRESQL_DATABASE_URL
    else None
)
PostgresSessionLocal = (
    async_sessionmaker(bind=postgres_engine, class_=AsyncSession, expire_on_commit=False)
    if postgres_engine is not None
    else None
)

MONGODB_URI = os.getenv("ME_YOU_MONGODB_URI")
mongo_client = AsyncMongoClient(MONGODB_URI) if MONGODB_URI else None
mongo_database = mongo_client["me_you"] if mongo_client is not None else None


async def ping_mongodb() -> bool:
    if mongo_client is None:
        raise RuntimeError("ME_YOU_MONGODB_URI is not configured")

    await mongo_client.admin.command("ping")
    return True


async def init_mongodb() -> None:
    if mongo_database is None:
        return

    await mongo_database.users.create_indexes(
        [
            IndexModel([("username", ASCENDING)], unique=True, name="username_unique"),
            IndexModel([("email", ASCENDING)], unique=True, name="email_unique"),
        ]
    )


async def get_mongo_database():
    if mongo_database is None:
        raise RuntimeError("ME_YOU_MONGODB_URI is not configured")

    return mongo_database


def init_db() -> None:
    from . import models

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    if PostgresSessionLocal is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")

    async with PostgresSessionLocal() as session:
        yield session
