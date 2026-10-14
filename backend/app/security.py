import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import (
	ACCESS_TOKEN_EXPIRE_MINUTES,
	APP_ENV,
	AUTH_SESSION_COOKIE_MAX_AGE,
	AUTH_SESSION_COOKIE_NAME,
	AUTH_SESSION_COOKIE_PATH,
	AUTH_SESSION_COOKIE_SAMESITE,
	AUTH_SESSION_MODE_HEADER,
	JWT_ALGORITHM,
	JWT_SECRET_KEY,
)
from .database import get_postgres_session
from .models import User


password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def cookie_session_requested(request: Request | None) -> bool:
	return bool(
		request
		and request.headers.get(AUTH_SESSION_MODE_HEADER, "").strip().lower() == "cookie"
	)


def create_access_token(
	subject: int | str,
	expires_delta: timedelta | None = None,
	*,
	token_version: int = 0,
	csrf_token: str | None = None,
) -> str:
	expires_at = datetime.now(timezone.utc) + (
		expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	)
	payload = {"sub": str(subject), "ver": token_version, "exp": expires_at}
	if csrf_token is not None:
		payload["csrf"] = csrf_token
	return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def set_auth_cookie(response: Response, token: str) -> None:
	response.set_cookie(
		key=AUTH_SESSION_COOKIE_NAME,
		value=token,
		max_age=AUTH_SESSION_COOKIE_MAX_AGE,
		path=AUTH_SESSION_COOKIE_PATH,
		secure=APP_ENV == "production",
		httponly=True,
		samesite=AUTH_SESSION_COOKIE_SAMESITE,
	)


def clear_auth_cookie(response: Response, *, session_invalidated: bool = False) -> None:
	response.delete_cookie(
		key=AUTH_SESSION_COOKIE_NAME,
		path=AUTH_SESSION_COOKIE_PATH,
		secure=APP_ENV == "production",
		httponly=True,
		samesite=AUTH_SESSION_COOKIE_SAMESITE,
	)
	if session_invalidated:
		response.headers["X-Session-Invalidated"] = "true"


def auth_token_response(
	user: User,
	response: Response | None = None,
	*,
	cookie_session: bool = False,
) -> dict[str, str]:
	csrf_token = secrets.token_urlsafe(32) if cookie_session else None
	access_token = create_access_token(
		user.id,
		token_version=getattr(user, "token_version", 0) or 0,
		csrf_token=csrf_token,
	)
	if cookie_session:
		if response is None:
			raise RuntimeError("A response is required for cookie-based sessions")
		assert csrf_token is not None
		set_auth_cookie(response, access_token)
		return {
			"message": "Login successful",
			"id": str(user.id),
			"username": user.username,
			"email": user.email,
			"csrf_token": csrf_token,
		}
	return {
		"message": "Login successful",
		"access_token": access_token,
		"token_type": "bearer",
		"id": str(user.id),
		"username": user.username,
		"email": user.email,
	}


def decode_access_token(token: str) -> dict:
	try:
		return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
	except jwt.InvalidTokenError as exc:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		) from exc


async def get_current_postgres_user(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	database: AsyncSession = Depends(get_postgres_session),
	request: Request = None,
) -> User:
	user = await get_optional_postgres_user(credentials, database, request)
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Not authenticated",
			headers={"WWW-Authenticate": "Bearer"},
		)
	return user


async def get_optional_postgres_user(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	database: AsyncSession = Depends(get_postgres_session),
	request: Request = None,
) -> User | None:
	cookie_token = request.cookies.get(AUTH_SESSION_COOKIE_NAME) if request is not None else None
	if cookie_token:
		token = cookie_token
		auth_scheme = "cookie"
	elif credentials is not None:
		token = credentials.credentials
		auth_scheme = "bearer"
	else:
		return None

	payload = decode_access_token(token)
	if auth_scheme == "cookie":
		csrf_token = payload.get("csrf")
		if not isinstance(csrf_token, str) or len(csrf_token) < 32:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="Invalid or expired access token",
				headers={"WWW-Authenticate": "Bearer"},
			)
		if request is not None:
			request.state.csrf_token = csrf_token
			request.state.auth_scheme = auth_scheme
	elif request is not None:
		request.state.auth_scheme = auth_scheme
	subject = payload.get("sub")
	if not isinstance(subject, str):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	try:
		user_id = uuid.UUID(subject)
	except ValueError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		) from None

	user = await database.scalar(select(User).where(User.id == user_id))
	if (
		user is None
		or getattr(user, "is_active", True) is False
		or getattr(user, "deleted_at", None) is not None
		or payload.get("ver", 0) != (getattr(user, "token_version", 0) or 0)
	):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	return user
