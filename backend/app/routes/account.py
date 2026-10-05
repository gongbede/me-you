from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import User
from ..permissions import ensure_account_can_be_deactivated
from ..schemas import (
    AccountLifecycleResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    PasswordConfirmationRequest,
    UserResponse,
)
from ..security import get_current_postgres_user, password_hash


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


@router.put(
    "/account/password",
    response_model=PasswordChangeResponse,
    summary="Change the current user's password",
)
async def change_my_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    if not password_hash.verify(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must differ from the current password",
        )

    current_user.password_hash = password_hash.hash(data.new_password)
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Password updated"}


async def confirm_current_password(data: PasswordConfirmationRequest, current_user: User) -> None:
    if not password_hash.verify(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )


@router.post(
    "/account/sessions/revoke",
    response_model=AccountLifecycleResponse,
    summary="Revoke all current account sessions",
)
async def revoke_account_sessions(
    data: PasswordConfirmationRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    await confirm_current_password(data, current_user)
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "All account sessions have been revoked"}


@router.post(
    "/account/deactivate",
    response_model=AccountLifecycleResponse,
    summary="Deactivate the current account",
)
async def deactivate_account(
    data: PasswordConfirmationRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    await confirm_current_password(data, current_user)
    await ensure_account_can_be_deactivated(
        current_user.id,
        database,
        is_platform_admin=bool(getattr(current_user, "is_platform_admin", False)),
    )
    current_user.is_active = False
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Account deactivated"}