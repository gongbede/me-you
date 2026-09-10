from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import User
from ..schemas import UserResponse
from ..security import get_current_postgres_user


router = APIRouter(tags=["account"])


@router.get(
    "/account/me",
    response_model=UserResponse,
    summary="Get the current account",
)
async def get_my_account(
    current_user: User = Depends(get_current_postgres_user),
    _database: AsyncSession = Depends(get_postgres_session),
):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at,
    }