from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import User
from ..schemas import UserCreate, UserResponse
from ..security import password_hash


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    database: AsyncSession = Depends(get_postgres_session),
):
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=password_hash.hash(user_data.password),
    )

    database.add(user)
    try:
        await database.commit()
        await database.refresh(user)
    except IntegrityError:
        await database.rollback()
        username_exists = await database.scalar(
            select(User.id).where(User.username == user_data.username)
        )
        if username_exists is not None:
            detail = "Username already exists"
        elif await database.scalar(
            select(User.id).where(User.email == user_data.email)
        ) is not None:
            detail = "Email already exists"
        else:
            detail = "Username or email already exists"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from None

    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }
