import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from ..database import get_postgres_session
from ..models import LoginThrottle, User
from ..schemas import LoginRequest, LoginResponse
from ..security import create_access_token, password_hash
from ..config import JWT_SECRET_KEY


router = APIRouter()
AUTHENTICATION_ERROR = "Invalid email or password"
LOGIN_THROTTLE_LIMIT = 5
LOGIN_THROTTLE_WINDOW = timedelta(minutes=15)
DUMMY_PASSWORD_HASH = password_hash.hash("me-you-invalid-account-password")


def login_subject_hash(email: str) -> str:
    return hmac.new(
        JWT_SECRET_KEY.encode("utf-8"),
        email.strip().casefold().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def record_failed_login(database: AsyncSession, subject_hash: str, now: datetime) -> int:
    cutoff = now - LOGIN_THROTTLE_WINDOW
    expired = LoginThrottle.window_started_at < cutoff
    statement = (
        postgres_insert(LoginThrottle)
        .values(
            subject_hash=subject_hash,
            failed_count=1,
            window_started_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[LoginThrottle.subject_hash],
            set_={
                "failed_count": case(
                    (expired, 1),
                    else_=LoginThrottle.failed_count + 1,
                ),
                "window_started_at": case(
                    (expired, now),
                    else_=LoginThrottle.window_started_at,
                ),
                "updated_at": now,
            },
        )
        .returning(LoginThrottle.failed_count)
    )
    failures = await database.scalar(statement)
    await database.commit()
    return int(failures or 1)


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    database: AsyncSession = Depends(get_postgres_session),
):
    now = datetime.now(timezone.utc)
    subject_hash = login_subject_hash(login_data.email)
    throttle = await database.scalar(
        select(LoginThrottle)
        .where(LoginThrottle.subject_hash == subject_hash)
        .with_for_update()
    )
    if (
        throttle is not None
        and throttle.window_started_at > now - LOGIN_THROTTLE_WINDOW
        and throttle.failed_count >= LOGIN_THROTTLE_LIMIT
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Authentication temporarily unavailable; try again later",
            headers={"Retry-After": str(int(LOGIN_THROTTLE_WINDOW.total_seconds()))},
        )

    user = await database.scalar(select(User).where(User.email == login_data.email))
    hash_to_verify = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid_password = password_hash.verify(login_data.password, hash_to_verify)
    if user is None or not valid_password or getattr(user, "is_active", True) is False:
        failures = await record_failed_login(database, subject_hash, now)
        if failures >= LOGIN_THROTTLE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Authentication temporarily unavailable; try again later",
                headers={"Retry-After": str(int(LOGIN_THROTTLE_WINDOW.total_seconds()))},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_ERROR,
        )

    if throttle is not None:
        await database.delete(throttle)
        await database.commit()

    return {
        "message": "Login successful",
        "access_token": create_access_token(
            user.id,
            token_version=getattr(user, "token_version", 0) or 0,
        ),
        "token_type": "bearer",
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
    }
