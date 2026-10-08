from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import RATE_LIMITS
from ..database import get_postgres_session
from ..models import User
from ..rate_limit import RateLimitStore, client_ip, get_rate_limit_store, hash_rate_limit_key
from ..schemas import LoginRequest, LoginResponse
from ..security_audit import record_security_event
from ..security import auth_token_response, password_hash


router = APIRouter()
AUTHENTICATION_ERROR = "Invalid email or password"
DUMMY_PASSWORD_HASH = password_hash.hash("me-you-invalid-account-password")


def login_subject_hash(email: str) -> str:
    return hash_rate_limit_key(email.strip().casefold())


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    database: AsyncSession = Depends(get_postgres_session),
    limiter: RateLimitStore | None = Depends(get_rate_limit_store),
    request: Request = None,
):
    ip_address = client_ip(request) if request is not None else "unknown"
    pair_key = f"{login_data.email.strip().casefold()}\0{ip_address}"
    throttled_retry_after = None
    if not hasattr(limiter, "increment"):
        limiter = None
    if limiter is not None:
        ip_limit, ip_window = RATE_LIMITS["login_ip"]
        if hasattr(limiter, "get_count"):
            ip_attempts, retry_after = await limiter.get_count(
                "login:ip", ip_address, ip_window
            )
            if ip_attempts >= ip_limit:
                throttled_retry_after = retry_after
            else:
                ip_attempts, retry_after = await limiter.increment(
                    "login:ip", ip_address, ip_window
                )
                if ip_attempts > ip_limit:
                    throttled_retry_after = retry_after
        else:
            ip_attempts, retry_after = await limiter.increment(
                "login:ip", ip_address, ip_window
            )
            if ip_attempts > ip_limit:
                throttled_retry_after = retry_after
        if hasattr(limiter, "get_count"):
            pair_limit, pair_window = RATE_LIMITS["login_pair"]
            email_limit, email_window = RATE_LIMITS["login_email"]
            pair_failures, pair_retry_after = await limiter.get_count(
                "login:pair", pair_key, pair_window
            )
            email_failures, email_retry_after = await limiter.get_count(
                "login:email", login_data.email.strip().casefold(), email_window
            )
            if throttled_retry_after is None and (
                pair_failures >= pair_limit or email_failures >= email_limit
            ):
                throttled_retry_after = (
                    pair_retry_after
                    if pair_failures >= pair_limit
                    else email_retry_after
                )

    user = await database.scalar(select(User).where(User.email == login_data.email))
    hash_to_verify = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid_password = password_hash.verify(login_data.password, hash_to_verify)
    if user is None or not valid_password or getattr(user, "is_active", True) is False:
        if limiter is not None and throttled_retry_after is None:
            pair_limit, pair_window = RATE_LIMITS["login_pair"]
            email_limit, email_window = RATE_LIMITS["login_email"]
            pair_failures, pair_retry_after = await limiter.increment(
                "login:pair", pair_key, pair_window
            )
            email_failures, email_retry_after = await limiter.increment(
                "login:email", login_data.email.strip().casefold(), email_window
            )
            if pair_failures >= pair_limit:
                throttled_retry_after = pair_retry_after
            elif email_failures >= email_limit:
                throttled_retry_after = email_retry_after
        if request is not None:
            record_security_event(
                database,
                event_type="auth.login_failure",
                outcome="FAILURE",
                request=request,
                target_user_id=user.id if user is not None else None,
            )
            if throttled_retry_after is not None:
                record_security_event(
                    database,
                    event_type="auth.login_throttled",
                    outcome="FAILURE",
                    request=request,
                    target_user_id=user.id if user is not None else None,
                )
            await database.commit()
        if throttled_retry_after is not None:
            raise login_throttled(throttled_retry_after)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_ERROR,
        )

    if limiter is not None:
        await limiter.clear("login:pair", pair_key)
    if request is not None:
        record_security_event(
            database,
            event_type="auth.login_success",
            outcome="SUCCESS",
            request=request,
            actor_user_id=user.id,
        )
        await database.commit()

    return auth_token_response(user)


def login_throttled(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Authentication temporarily unavailable; try again later",
        headers={"Retry-After": str(retry_after)},
    )
