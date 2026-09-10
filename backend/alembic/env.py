from __future__ import annotations

import asyncio
from configparser import Error as ConfigParserError
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app import models  # noqa: F401
from app.config import POSTGRESQL_DATABASE_URL
from app.database import Base


try:
    config = context.config
except (AttributeError, NameError):
    from alembic.config import Config

    config = Config()

if config.config_file_name is not None and Path(config.config_file_name).exists():
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    if not POSTGRESQL_DATABASE_URL:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    return POSTGRESQL_DATABASE_URL


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = dict(config.get_section(config.config_ini_section) or {})
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


try:
    offline_mode = context.is_offline_mode()
except (AttributeError, ConfigParserError, NameError):
    offline_mode = None

if offline_mode is not None:
    if offline_mode:
        run_migrations_offline()
    else:
        run_migrations_online()
