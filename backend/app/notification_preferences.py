from collections.abc import Iterable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Notification, NotificationPreference
from .schemas.social import NotificationType


NOTIFICATION_PREFERENCE_TYPES = tuple(notification_type.value for notification_type in NotificationType)
SECURITY_NOTIFICATION_TYPES = frozenset({"ACCOUNT_SECURITY", "SECURITY_ALERT"})


async def add_notification(
    database: AsyncSession,
    notification: Notification,
) -> bool:
    if notification.type not in SECURITY_NOTIFICATION_TYPES:
        enabled = await database.scalar(
            select(NotificationPreference.enabled).where(
                NotificationPreference.user_id == notification.recipient_id,
                NotificationPreference.notification_type == notification.type,
            )
        )
        if enabled is False:
            return False
    database.add(notification)
    return True


async def add_notifications(
    database: AsyncSession,
    notifications: Iterable[Notification],
) -> None:
    batch = list(notifications)
    if not batch:
        return
    preferences = (
        await database.scalars(
            select(NotificationPreference).where(
                NotificationPreference.user_id.in_(
                    {notification.recipient_id for notification in batch}
                ),
                NotificationPreference.notification_type.in_(
                    {notification.type for notification in batch}
                    - SECURITY_NOTIFICATION_TYPES
                ),
                NotificationPreference.enabled.is_(False),
            )
        )
    ).all()
    disabled = {(preference.user_id, preference.notification_type) for preference in preferences}
    database.add_all(
        notification
        for notification in batch
        if notification.type in SECURITY_NOTIFICATION_TYPES
        or (notification.recipient_id, notification.type) not in disabled
    )


def default_notification_preferences() -> dict[str, bool]:
    return {notification_type: True for notification_type in NOTIFICATION_PREFERENCE_TYPES}
