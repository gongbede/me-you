from fastapi import APIRouter, Depends

from ..models import User
from ..schemas import UserResponse
from ..security import get_current_postgres_user


router = APIRouter()


@router.get(
	"/me",
	response_model=UserResponse,
	summary="Get the current user",
	description="Return the authenticated PostgreSQL account's public information.",
)
async def get_me(current_user: User = Depends(get_current_postgres_user)):
	return {
		"id": str(current_user.id),
		"username": current_user.username,
		"email": current_user.email,
		"created_at": current_user.created_at,
	}