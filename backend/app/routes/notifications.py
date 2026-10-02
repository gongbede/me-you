import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Notification, User
from ..schemas import NotificationResponse, NotificationUnreadCountResponse
from ..security import get_current_postgres_user
from .posts import user_summary


router = APIRouter(prefix="/notifications", tags=["notifications"])


def notification_response(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "type": notification.type,
        "title": notification.title,
        "payload": notification.payload,
        "target_type": notification.target_type,
        "target_id": str(notification.target_id) if notification.target_id else None,
        "actor": user_summary(notification.actor) if notification.actor else None,
        "post_id": str(notification.post_id) if notification.post_id else None,
        "comment_id": str(notification.comment_id) if notification.comment_id else None,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


async def get_recipient_notification(
    notification_id: uuid.UUID,
    current_user: User,
    database: AsyncSession,
) -> Notification:
    notification = await database.scalar(
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(
            Notification.id == notification_id,
            Notification.recipient_id == current_user.id,
        )
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.get(
    "",
    response_model=list[NotificationResponse],
    summary="List your notifications",
)
async def list_notifications(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
):
    statement = (
        select(Notification)
        .options(selectinload(Notification.actor))
        .where(Notification.recipient_id == current_user.id)
    )
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    notifications = list(
        (
            await database.scalars(
                statement.order_by(Notification.created_at.desc(), Notification.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return [notification_response(notification) for notification in notifications]


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="Count your unread notifications",
)
async def count_unread_notifications(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    unread_count = await database.scalar(
        select(func.count(Notification.id)).where(
            Notification.recipient_id == current_user.id,
            Notification.read_at.is_(None),
        )
    )
    return {"unread_count": int(unread_count or 0)}


@router.post(
    "/read-all",
    response_model=dict[str, int],
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    result = await database.execute(
        update(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await database.commit()
    return {"updated": result.rowcount}


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark a notification as read",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    notification = await get_recipient_notification(notification_id, current_user, database)
    notification.read_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(notification)
    return notification_response(notification)
