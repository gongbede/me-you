import json
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Activity


_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")
_SENSITIVE_KEY = re.compile(r"email|password|token|secret|content|message|body|phone|address|grade|score", re.I)


def _validate_name(value: str | None, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not _EVENT_NAME.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase event-style name")
    return value


def _safe_payload(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, Mapping) or len(metadata) > 20:
        raise ValueError("activity metadata must be an object with at most 20 fields")

    payload: dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or len(key) > 64 or _SENSITIVE_KEY.search(key):
            raise ValueError("activity metadata contains an unsafe field name")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError("activity metadata values must be simple scalar values")
        if isinstance(value, str) and len(value) > 200:
            raise ValueError("activity metadata string values must be at most 200 characters")
        payload[key] = value

    if len(json.dumps(payload, allow_nan=False).encode("utf-8")) > 2048:
        raise ValueError("activity metadata must be at most 2048 bytes")
    return payload


async def record_activity(
    database: AsyncSession,
    *,
    event_type: str,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> Activity:
    activity = Activity(
        actor_id=actor_id,
        event_type=_validate_name(event_type, "event_type"),
        target_type=_validate_name(target_type, "target_type", optional=True),
        target_id=target_id,
        payload=_safe_payload(metadata),
        created_at=datetime.now(timezone.utc),
    )
    database.add(activity)
    return activity


async def list_actor_activities(
    actor_id: uuid.UUID,
    database: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 20,
) -> list[Activity]:
    if offset < 0 or limit < 1 or limit > 100:
        raise ValueError("activity pagination is out of range")
    return list(
        (
            await database.scalars(
                select(Activity)
                .where(Activity.actor_id == actor_id)
                .order_by(Activity.created_at.desc(), Activity.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
