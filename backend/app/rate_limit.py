from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from fastapi import Request
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from .config import TRUSTED_PROXY_COUNT
from .database import PostgresSessionLocal
from .models.rate_limit_counter import RateLimitCounter


class RateLimitStore(Protocol):
    async def increment(self, scope: str, key: str, window_seconds: int) -> tuple[int, int]: ...

    async def get_count(self, scope: str, key: str, window_seconds: int) -> tuple[int, int]: ...

    async def clear(self, scope: str, key: str) -> None: ...


def hash_rate_limit_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def fixed_window_start(now: datetime, window_seconds: int) -> datetime:
    timestamp = int(now.timestamp())
    return datetime.fromtimestamp(timestamp - timestamp % window_seconds, timezone.utc)


@dataclass
class PostgresRateLimitStore:
    session_factory: object

    async def get_count(self, scope: str, key: str, window_seconds: int) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        window_start = fixed_window_start(now, window_seconds)
        async with self.session_factory() as session:
            count = await session.scalar(
                select(func.coalesce(func.max(RateLimitCounter.count), 0)).where(
                    RateLimitCounter.scope == scope,
                    RateLimitCounter.key_hash == hash_rate_limit_key(key),
                    RateLimitCounter.window_start == window_start,
                )
            )
        retry_after = max(
            1,
            int((window_start + timedelta(seconds=window_seconds) - now).total_seconds()),
        )
        return int(count or 0), retry_after

    async def increment(self, scope: str, key: str, window_seconds: int) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        window_start = fixed_window_start(now, window_seconds)
        statement = (
            insert(RateLimitCounter)
            .values(
                scope=scope,
                key_hash=hash_rate_limit_key(key),
                window_start=window_start,
                count=1,
                window_seconds=window_seconds,
            )
            .on_conflict_do_update(
                index_elements=[
                    RateLimitCounter.scope,
                    RateLimitCounter.key_hash,
                    RateLimitCounter.window_start,
                ],
                set_={"count": RateLimitCounter.count + 1},
            )
            .returning(RateLimitCounter.count)
        )
        async with self.session_factory() as session:
            count = int(await session.scalar(statement) or 1)
            await session.commit()
        retry_after = max(1, int((window_start + timedelta(seconds=window_seconds) - now).total_seconds()))
        return count, retry_after

    async def clear(self, scope: str, key: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                delete(RateLimitCounter).where(
                    RateLimitCounter.scope == scope,
                    RateLimitCounter.key_hash == hash_rate_limit_key(key),
                )
            )
            await session.commit()


def get_rate_limit_store() -> RateLimitStore | None:
    if PostgresSessionLocal is None:
        return None
    return PostgresRateLimitStore(PostgresSessionLocal)


def client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client is not None else "unknown"
    if TRUSTED_PROXY_COUNT <= 0:
        return direct_ip
    forwarded_for = request.headers.get("x-forwarded-for")
    if not forwarded_for:
        return direct_ip
    forwarded_addresses = [address.strip() for address in forwarded_for.split(",") if address.strip()]
    if len(forwarded_addresses) < TRUSTED_PROXY_COUNT:
        return direct_ip
    return forwarded_addresses[-TRUSTED_PROXY_COUNT]


async def purge_expired_counters() -> int:
    if PostgresSessionLocal is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    async with PostgresSessionLocal() as session:
        result = await session.execute(
            delete(RateLimitCounter).where(
                text("window_start + window_seconds * INTERVAL '1 second' < now()")
            )
        )
        await session.commit()
        return int(result.rowcount or 0)