from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash

from .config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET_KEY


password_hash = PasswordHash.recommended()


def create_access_token(subject: int | str, expires_delta: timedelta | None = None) -> str:
	expires_at = datetime.now(timezone.utc) + (
		expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
	)
	payload = {"sub": str(subject), "exp": expires_at}
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
