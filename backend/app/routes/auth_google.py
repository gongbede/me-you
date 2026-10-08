import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..database import get_postgres_session
from ..models import AuthIdentity, User
from ..schemas import LoginResponse
from ..security import auth_token_response, password_hash


router = APIRouter(prefix="/auth", tags=["authentication"])


class GoogleSignInRequest(BaseModel):
    id_token: str = Field(min_length=1, max_length=10000)


def verify_google_id_token(token: str, audience: str) -> dict:
    try:
        claims = id_token.verify_oauth2_token(token, GoogleRequest(), audience)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Google ID token",
        ) from exc

    if claims.get("email_verified") is not True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified",
        )
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("email"), str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token is missing required account claims",
        )
    return claims


@router.get("/google/config")
async def google_sign_in_config():
    client_id = os.getenv("ME_YOU_GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )
    return {"client_id": client_id}


@router.post("/google", response_model=LoginResponse)
async def google_sign_in(
    data: GoogleSignInRequest,
    database: AsyncSession = Depends(get_postgres_session),
):
    client_id = os.getenv("ME_YOU_GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    claims = await run_in_threadpool(verify_google_id_token, data.id_token, client_id)
    email = claims["email"].strip().casefold()
    if not email or len(email) > 255:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token contains an invalid email",
        )

    identity = await database.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == "google",
            AuthIdentity.provider_subject == claims["sub"],
        )
    )
    user = None
    if identity is not None:
        user = await database.get(User, identity.user_id)
    else:
        user = await database.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if user is None:
            username_prefix = re.sub(r"[^a-z0-9_-]", "-", email.partition("@")[0])
            username = f"{username_prefix[:36] or 'google-user'}-{uuid.uuid4().hex[:8]}"
            user = User(
                username=username,
                email=email,
                password_hash=password_hash.hash(secrets.token_urlsafe(48)),
                email_verified_at=datetime.now(timezone.utc),
            )
            database.add(user)
            await database.flush()
        database.add(
            AuthIdentity(
                user_id=user.id,
                provider="google",
                provider_subject=claims["sub"],
            )
        )
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            identity = await database.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_subject == claims["sub"],
                )
            )
            user = await database.get(User, identity.user_id) if identity else None

    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account is not available",
        )

    return auth_token_response(user)