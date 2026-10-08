import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import phonenumbers
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import JWT_SECRET_KEY
from ..database import get_postgres_session
from ..models import AuthIdentity, PhoneLoginCode, User
from ..providers.sms import RealSMSProvider, SMSProvider, get_sms_provider
from ..rate_limit import RateLimitStore, client_ip, get_rate_limit_store
from ..schemas import LoginResponse
from ..security import auth_token_response, password_hash
from ..providers.registry import provider_not_configured_http_error


router = APIRouter(prefix="/auth/phone", tags=["authentication"])
CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODE_ATTEMPTS = 5
REQUEST_MESSAGE = "If the number can receive messages, a sign-in code has been sent."
INVALID_CODE_MESSAGE = "Invalid or expired phone sign-in code"


class PhoneCodeRequest(BaseModel):
    phone_number: str = Field(min_length=3, max_length=40)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone_number(cls, value: str) -> str:
        try:
            parsed = phonenumbers.parse(value, None)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("Enter a valid international phone number") from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Enter a valid international phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class PhoneCodeVerify(PhoneCodeRequest):
    code: str = Field(pattern=r"^\d{6}$")


class PhoneCodeRequestResponse(BaseModel):
    message: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_phone_code(phone_number: str, code: str) -> str:
    message = f"{phone_number}:{code}".encode("utf-8")
    return hmac.new(JWT_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _generic_code_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=INVALID_CODE_MESSAGE,
    )


def _ensure_sms_provider_configured(sms_provider: SMSProvider) -> None:
    if isinstance(sms_provider, RealSMSProvider):
        raise provider_not_configured_http_error("sms")


async def _check_request_limits(
    limiter: RateLimitStore | None,
    phone_number: str,
    ip_address: str,
) -> None:
    if limiter is None or not hasattr(limiter, "increment"):
        return
    limit = max(1, int(os.getenv("PHONE_LOGIN_REQUEST_LIMIT", "5")))
    window = max(1, int(os.getenv("PHONE_LOGIN_REQUEST_WINDOW_SECONDS", "3600")))
    phone_count, phone_retry = await limiter.increment(
        "phone:request:number", phone_number, window
    )
    ip_count, ip_retry = await limiter.increment("phone:request:ip", ip_address, window)
    if phone_count > limit or ip_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many code requests; try again later",
            headers={"Retry-After": str(max(phone_retry, ip_retry))},
        )


@router.post(
    "/request",
    response_model=PhoneCodeRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_phone_code(
    data: PhoneCodeRequest,
    request: Request,
    database: AsyncSession = Depends(get_postgres_session),
    sms_provider: SMSProvider = Depends(get_sms_provider),
    limiter: RateLimitStore | None = Depends(get_rate_limit_store),
):
    phone_number = data.phone_number
    _ensure_sms_provider_configured(sms_provider)
    await _check_request_limits(limiter, phone_number, client_ip(request))
    now = utcnow()
    code_record = await database.scalar(
        select(PhoneLoginCode)
        .where(PhoneLoginCode.phone_number == phone_number)
        .with_for_update()
    )
    if code_record is not None and now - code_record.created_at < RESEND_COOLDOWN:
        return {"message": REQUEST_MESSAGE}

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hash_phone_code(phone_number, code)
    if code_record is None:
        code_record = PhoneLoginCode(
            phone_number=phone_number,
            code_hash=code_hash,
            attempts=0,
            created_at=now,
            expires_at=now + CODE_TTL,
        )
        database.add(code_record)
    else:
        code_record.code_hash = code_hash
        code_record.attempts = 0
        code_record.created_at = now
        code_record.expires_at = now + CODE_TTL
        code_record.invalidated_at = None
    await database.commit()

    await sms_provider.send_code(phone_number=phone_number, code=code)
    return {"message": REQUEST_MESSAGE}


@router.post("/verify", response_model=LoginResponse)
async def verify_phone_code(
    data: PhoneCodeVerify,
    database: AsyncSession = Depends(get_postgres_session),
    _sms_provider: SMSProvider = Depends(get_sms_provider),
):
    phone_number = data.phone_number
    _ensure_sms_provider_configured(_sms_provider)
    now = utcnow()
    code_record = await database.scalar(
        select(PhoneLoginCode)
        .where(PhoneLoginCode.phone_number == phone_number)
        .with_for_update()
    )
    if code_record is None or code_record.invalidated_at is not None:
        raise _generic_code_error()
    if code_record.expires_at <= now or code_record.attempts >= MAX_CODE_ATTEMPTS:
        code_record.invalidated_at = now
        await database.commit()
        raise _generic_code_error()
    if not hmac.compare_digest(code_record.code_hash, hash_phone_code(phone_number, data.code)):
        code_record.attempts += 1
        if code_record.attempts >= MAX_CODE_ATTEMPTS:
            code_record.invalidated_at = now
        await database.commit()
        raise _generic_code_error()

    code_record.invalidated_at = now
    identity = await database.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == "phone",
            AuthIdentity.provider_subject == phone_number,
        )
    )
    user = await database.get(User, identity.user_id) if identity is not None else None
    if user is None:
        user = await database.scalar(
            select(User).where(User.phone_number == phone_number)
        )
    if user is None:
        suffix = uuid.uuid4().hex
        digits = re.sub(r"\D", "", phone_number)
        user = User(
            username=f"phone-{digits[-10:]}-{suffix[:8]}",
            email=f"phone-{suffix}@phone.invalid",
            password_hash=password_hash.hash(secrets.token_urlsafe(48)),
            phone_number=phone_number,
        )
        database.add(user)
        await database.flush()
    elif user.phone_number is None:
        user.phone_number = phone_number

    if identity is None:
        database.add(
            AuthIdentity(
                user_id=user.id,
                provider="phone",
                provider_subject=phone_number,
            )
        )
    if not user.is_active or user.deleted_at is not None:
        await database.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phone sign-in is not available for this account",
        )
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        raise _generic_code_error() from None
    return auth_token_response(user)