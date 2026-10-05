import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY
from .database import get_mongo_database, get_postgres_session
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


def decode_access_token(token: str) -> dict:
	try:
		return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
	except jwt.InvalidTokenError as exc:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		) from exc


async def get_current_user(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	database=Depends(get_mongo_database),
) -> dict:
	if credentials is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Not authenticated",
			headers={"WWW-Authenticate": "Bearer"},
		)

	payload = decode_access_token(credentials.credentials)
	subject = payload.get("sub")
	if not isinstance(subject, str) or not subject:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	user = await database["users"].find_one({"_id": subject})
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	return {
		"id": user["_id"],
		"username": user["username"],
		"email": user["email"],
		"created_at": user["created_at"],
	}


async def get_current_postgres_user(
	credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
	database: AsyncSession = Depends(get_postgres_session),
) -> User:
	if credentials is None:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Not authenticated",
			headers={"WWW-Authenticate": "Bearer"},
		)

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
		or payload.get("ver", 0) != (getattr(user, "token_version", 0) or 0)
	):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Invalid or expired access token",
			headers={"WWW-Authenticate": "Bearer"},
		)

	return user
