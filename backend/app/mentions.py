import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Notification, User
from .notification_preferences import add_notifications


MENTION_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,30})\b")


def mentioned_usernames(content: str) -> set[str]:
    return {match.casefold() for match in MENTION_PATTERN.findall(content)}


async def notify_mentions(
    content: str,
    *,
    actor_id: uuid.UUID,
    post_id: uuid.UUID,
    database: AsyncSession,
    comment_id: uuid.UUID | None = None,
) -> None:
    usernames = mentioned_usernames(content)
    if not usernames:
        return
    recipients = (
        await database.scalars(
            select(User).where(
                func.lower(User.username).in_(usernames),
                User.id != actor_id,
                User.is_active.is_(True),
            )
        )
    ).all()
    await add_notifications(
        database,
        [
            Notification(
                recipient_id=recipient.id,
                actor_id=actor_id,
                type="MENTION",
                title="You were mentioned",
                post_id=post_id,
                comment_id=comment_id,
                target_type="comment" if comment_id else "post",
                target_id=comment_id or post_id,
            )
            for recipient in recipients
        ],
    )