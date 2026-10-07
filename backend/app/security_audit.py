from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from .config import SECURITY_EVENT_RETENTION_DAYS
from .database import PostgresSessionLocal
from .models.security_event import SecurityEvent
from .rate_limit import client_ip


_DETAIL_KEYS_BY_EVENT = {
    "account.sessions_revoked": {"source"},
    "account.deleted": {"policy"},
    "institution.membership.requested": {"role"},
    "institution.membership.request_approved": {"role"},
    "institution.membership.request_rejected": {"role"},
    "institution.membership.invited": {"role"},
    "institution.membership.invitation_accepted": {"role"},
    "institution.membership.invitation_declined": set(),
    "institution.membership.role_changed": {"previous_role", "new_role"},
    "institution.membership.removed": {"role"},
    "platform.admin.granted": {"created", "changed", "source", "operator"},
    "platform.admin.revoked": {"changed", "source", "operator"},
    "platform.admin.revoke_denied": {"reason", "source", "operator"},
}
_ROLES = {"ADMIN", "TEACHER", "STUDENT"}


def sanitize_security_details(
    event_type: str,
    details: dict[str, Any] | None,
) -> dict[str, Any]:
    if not details:
        return {}
    allowed_keys = _DETAIL_KEYS_BY_EVENT.get(event_type, set())
    safe_details: dict[str, Any] = {}
    for key, value in details.items():
        if key not in allowed_keys:
            continue
        if key in {"role", "previous_role", "new_role"} and isinstance(value, str) and value in _ROLES:
            safe_details[key] = value
        elif key in {"created", "changed"} and isinstance(value, bool):
            safe_details[key] = value
        elif key == "source" and isinstance(value, str) and value in {"cli", "logout"}:
            safe_details[key] = value
        elif key == "operator" and isinstance(value, str) and value.isprintable():
            safe_details[key] = value[:80]
        elif key == "reason" and value == "last_active_admin":
            safe_details[key] = value
        elif key == "policy" and value == "anonymized_retention":
            safe_details[key] = value
    return safe_details


def record_security_event(
    database: AsyncSession,
    *,
    event_type: str,
    outcome: str,
    request: Request | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    institution_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SecurityEvent:
    if request is not None:
        ip_address = client_ip(request)
        user_agent = request.headers.get("user-agent")
    event = SecurityEvent(
        event_type=event_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        institution_id=institution_id,
        ip_address=ip_address,
        user_agent=user_agent[:200] if user_agent else None,
        details=sanitize_security_details(event_type, details),
    )
    database.add(event)
    return event


async def purge_expired_security_events() -> int:
    if PostgresSessionLocal is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    retention_cutoff = datetime.now(timezone.utc) - timedelta(
        days=SECURITY_EVENT_RETENTION_DAYS
    )
    async with PostgresSessionLocal() as session:
        result = await session.execute(
            delete(SecurityEvent).where(SecurityEvent.occurred_at < retention_cutoff)
        )
        await session.commit()
        return int(result.rowcount or 0)