import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY
from .database import get_postgres_session
from .models import User


password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
	subject: int | str,
	expires_delta: timedelta | None = None,
	*,
	token_version: int = 0,
) -> str:
	expires_at = datetime.now(timezone.utc) + (
		expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	)
	payload = {"sub": str(subject), "ver": token_version, "exp": expires_at}
	return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def auth_token_response(user: User) -> dict[str, str]:
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
) -> User:
	user = await get_optional_postgres_user(credentials, database)
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
) -> User | None:
	if credentials is None:
		return None

	payload = decode_access_token(credentials.credentials)
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
