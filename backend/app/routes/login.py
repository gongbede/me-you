from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import User
from ..schemas import LoginRequest, LoginResponse
from ..security import create_access_token, password_hash


router = APIRouter()
AUTHENTICATION_ERROR = "Invalid email or password"


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    database: AsyncSession = Depends(get_postgres_session),
):
    user = await database.scalar(select(User).where(User.email == login_data.email))
    if user is None or not password_hash.verify(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_ERROR,
        )

    return {
        "message": "Login successful",
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
    }
