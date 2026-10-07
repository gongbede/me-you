import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import InstitutionMembership, SecurityEvent, User
from ..security import get_current_postgres_user


router = APIRouter(tags=["security-events"])


@router.get("/security-events")
async def list_security_events(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    cursor: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    event_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    institution_id: uuid.UUID | None = None,
):
    statement = select(SecurityEvent)
    if getattr(current_user, "is_platform_admin", False) is not True:
        admin_institution_ids = set(
            (
                await database.scalars(
                    select(InstitutionMembership.institution_id).where(
                        InstitutionMembership.user_id == current_user.id,
                        InstitutionMembership.role == "ADMIN",
                    )
                )
            ).all()
        )
        if not admin_institution_ids:
            raise HTTPException(status_code=403, detail="Security event access required")
        if institution_id is not None and institution_id not in admin_institution_ids:
            raise HTTPException(status_code=403, detail="Institution administrator access required")
        if institution_id is not None:
            statement = statement.where(SecurityEvent.institution_id == institution_id)
        else:
            statement = statement.where(SecurityEvent.institution_id.in_(admin_institution_ids))
    elif institution_id is not None:
        statement = statement.where(SecurityEvent.institution_id == institution_id)

    if event_type is not None:
        statement = statement.where(SecurityEvent.event_type == event_type)
    if actor_user_id is not None:
        statement = statement.where(SecurityEvent.actor_user_id == actor_user_id)
    if start_at is not None:
        statement = statement.where(SecurityEvent.occurred_at >= start_at)
    if end_at is not None:
        statement = statement.where(SecurityEvent.occurred_at <= end_at)
    if cursor is not None:
        statement = statement.where(SecurityEvent.id < cursor)

    rows = list(
        (
            await database.scalars(
                statement.order_by(SecurityEvent.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [
            {
                "id": str(event.id),
                "occurred_at": event.occurred_at,
                "event_type": event.event_type,
                "outcome": event.outcome,
                "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                "target_user_id": str(event.target_user_id) if event.target_user_id else None,
                "institution_id": str(event.institution_id) if event.institution_id else None,
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "details": event.details,
            }
            for event in page
        ],
        "next_cursor": str(page[-1].id) if has_more and page else None,
    }