from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .config import APP_PUBLIC_BASE_URL
from .models import AccountEmailToken, User
from .providers import EmailProvider, EmailRequest


TOKEN_LIFETIMES = {
    "EMAIL_VERIFICATION": timedelta(hours=24),
    "PASSWORD_RESET": timedelta(minutes=30),
}
INVALID_TOKEN_DETAIL = "This account action token is invalid or expired"


def account_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_account_email_token(
    database: AsyncSession,
    provider: EmailProvider,
    user: User,
    purpose: str,
) -> None:
    lifetime = TOKEN_LIFETIMES[purpose]
    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(32)
    token = AccountEmailToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=account_token_hash(raw_token),
        expires_at=now + lifetime,
        created_at=now,
    )
    await database.execute(
        update(AccountEmailToken)
        .where(
            AccountEmailToken.user_id == user.id,
            AccountEmailToken.purpose == purpose,
            AccountEmailToken.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    database.add(token)
    await database.commit()

    path = "verify-email" if purpose == "EMAIL_VERIFICATION" else "reset-password"
    subject = "Verify your Me&You email" if purpose == "EMAIL_VERIFICATION" else "Reset your Me&You password"
    await provider.send(
        EmailRequest(
            recipient=user.email,
            subject=subject,
            text_body=f"Use this single-use link before it expires: {APP_PUBLIC_BASE_URL}/{path}?token={raw_token}",
        )
    )


async def invalidate_account_email_tokens(
    database: AsyncSession,
    user_id: uuid.UUID,
    *,
    purposes: set[str] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    statement = update(AccountEmailToken).where(
        AccountEmailToken.user_id == user_id,
        AccountEmailToken.consumed_at.is_(None),
    )
    if purposes is not None:
        statement = statement.where(AccountEmailToken.purpose.in_(purposes))
    await database.execute(statement.values(consumed_at=now))


async def purge_expired_account_email_tokens() -> int:
    from .database import PostgresSessionLocal

    if PostgresSessionLocal is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    now = datetime.now(timezone.utc)
    async with PostgresSessionLocal() as session:
        result = await session.execute(
            delete(AccountEmailToken).where(
                (AccountEmailToken.expires_at <= now)
                | AccountEmailToken.consumed_at.is_not(None)
            )
        )
        await session.commit()
        return int(result.rowcount or 0)


async def lock_valid_account_token(
    database: AsyncSession,
    raw_token: str,
    purpose: str,
) -> tuple[AccountEmailToken, User]:
    now = datetime.now(timezone.utc)
    token = await database.scalar(
        select(AccountEmailToken)
        .where(
            AccountEmailToken.token_hash == account_token_hash(raw_token),
            AccountEmailToken.purpose == purpose,
            AccountEmailToken.consumed_at.is_(None),
            AccountEmailToken.expires_at > now,
        )
        .with_for_update()
    )
    if token is None:
        raise HTTPException(status_code=400, detail=INVALID_TOKEN_DETAIL)
    user = await database.scalar(
        select(User)
        .where(
            User.id == token.user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=400, detail=INVALID_TOKEN_DETAIL)
    return token, user