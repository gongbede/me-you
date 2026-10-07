from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import User
from ..schemas import UserCreate, UserResponse
from ..security_audit import record_security_event
from ..security import password_hash


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=password_hash.hash(user_data.password),
    )

    database.add(user)
    try:
        if request is not None:
            await database.flush()
            record_security_event(
                database,
                event_type="account.registered",
                outcome="SUCCESS",
                request=request,
                target_user_id=user.id,
            )
        await database.commit()
        await database.refresh(user)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        ) from None

    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at,
    }
