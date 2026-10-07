import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import record_activity
from ..account_tokens import invalidate_account_email_tokens
from ..database import get_postgres_session
from ..models import User
from ..permissions import ensure_account_can_be_deactivated, require_platform_admin
from ..schemas import PlatformAdminUserResponse
from ..security import get_current_postgres_user
from ..security_audit import record_security_event


router = APIRouter(prefix="/platform-admin", tags=["platform-administration"])


def platform_user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_active": bool(getattr(user, "is_active", True)),
        "is_platform_admin": bool(getattr(user, "is_platform_admin", False)),
        "created_at": user.created_at,
    }


async def set_account_active(
    user_id: uuid.UUID,
    active: bool,
    current_user: User,
    database: AsyncSession,
    request: Request | None = None,
) -> dict:
    require_platform_admin(current_user)
    if not active:
        target_admin_flag = await database.scalar(
            select(User.is_platform_admin).where(User.id == user_id)
        )
        if target_admin_flag is None:
            raise HTTPException(status_code=404, detail="Account not found")
        await ensure_account_can_be_deactivated(
            user_id,
            database,
            is_platform_admin=bool(target_admin_flag),
        )
    target = await database.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if active and getattr(target, "deleted_at", None) is not None:
        raise HTTPException(status_code=409, detail="Deleted accounts cannot be reactivated")

    target.is_active = active
    target.token_version = (getattr(target, "token_version", 0) or 0) + 1
    if not active:
        await invalidate_account_email_tokens(database, target.id)
    if request is not None:
        record_security_event(
            database,
            event_type="account.reactivated" if active else "account.deactivated",
            outcome="SUCCESS",
            request=request,
            actor_user_id=current_user.id,
            target_user_id=target.id,
        )
    await record_activity(
        database,
        event_type="platform.account.activated" if active else "platform.account.deactivated",
        actor_id=current_user.id,
        target_type="user",
        target_id=target.id,
        metadata={"is_active": active},
    )
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return platform_user_response(target)


@router.get("/users", response_model=list[PlatformAdminUserResponse])
async def list_platform_users(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    require_platform_admin(current_user)
    users = list(
        (
            await database.scalars(
                select(User).order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    return [platform_user_response(user) for user in users]


@router.post("/users/{user_id}/deactivate", response_model=PlatformAdminUserResponse)
async def deactivate_platform_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    return await set_account_active(user_id, False, current_user, database, request)


@router.post("/users/{user_id}/activate", response_model=PlatformAdminUserResponse)
async def activate_platform_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    return await set_account_active(user_id, True, current_user, database, request)