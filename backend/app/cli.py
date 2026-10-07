import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from getpass import getpass, getuser
from typing import Any

from sqlalchemy import select

from .account_tokens import purge_expired_account_email_tokens
from .config import MEDIA_ORPHAN_UPLOAD_HOURS
from .database import PostgresSessionLocal
from .models import MediaAsset, User
from .providers import get_provider_registry, provider_or_503
from .rate_limit import purge_expired_counters
from .security import password_hash
from .security_audit import purge_expired_security_events, record_security_event


def _resolve_session_factory(session_factory: Any = None):
    factory = session_factory or PostgresSessionLocal
    if factory is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    return factory


async def create_platform_admin(session_factory: Any = None) -> str:
    factory = _resolve_session_factory(session_factory)
    email = input("Email: ").strip()
    if not email:
        raise ValueError("Email is required")

    async with factory() as session:
        user = await session.scalar(
            select(User).where(User.email == email).with_for_update()
        )
        created = user is None
        if created:
            username = input("Username: ").strip()
            password = getpass("Password: ")
            confirmation = getpass("Confirm password: ")
            if not username:
                raise ValueError("Username is required for a new account")
            if not password:
                raise ValueError("Password is required for a new account")
            if password != confirmation:
                raise ValueError("Passwords do not match")
            user = User(
                username=username,
                email=email,
                password_hash=password_hash.hash(password),
                is_platform_admin=True,
            )
            session.add(user)
            await session.flush()
        else:
            if user.deleted_at is not None:
                raise ValueError("Deleted accounts cannot be promoted")
            changed = user.is_platform_admin is not True
            user.is_platform_admin = True
        record_security_event(
            session,
            event_type="platform.admin.granted",
            outcome="SUCCESS",
            target_user_id=user.id,
            details={
                "created": created,
                "changed": created or changed,
                "source": "cli",
                "operator": getuser(),
            },
        )
        try:
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return email


async def grant_platform_admin(email: str, session_factory: Any = None) -> bool:
    factory = _resolve_session_factory(session_factory)
    async with factory() as session:
        user = await session.scalar(
            select(User).where(User.email == email).with_for_update()
        )
        if user is None:
            raise ValueError("User not found")
        if user.deleted_at is not None:
            raise ValueError("Deleted accounts cannot be granted platform-admin access")
        changed = user.is_platform_admin is not True
        user.is_platform_admin = True
        record_security_event(
            session,
            event_type="platform.admin.granted",
            outcome="SUCCESS",
            target_user_id=user.id,
            details={"changed": changed, "source": "cli", "operator": getuser()},
        )
        try:
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return changed


async def revoke_platform_admin(email: str, session_factory: Any = None) -> bool:
    factory = _resolve_session_factory(session_factory)
    async with factory() as session:
        user = await session.scalar(
            select(User).where(User.email == email).with_for_update()
        )
        if user is None:
            raise ValueError("User not found")

        changed = user.is_platform_admin is True
        if changed and user.is_active:
            active_admin_ids = list(
                (
                    await session.scalars(
                        select(User.id)
                        .where(
                            User.is_platform_admin.is_(True),
                            User.is_active.is_(True),
                        )
                        .order_by(User.id)
                        .with_for_update()
                    )
                ).all()
            )
            if len(active_admin_ids) <= 1:
                record_security_event(
                    session,
                    event_type="platform.admin.revoke_denied",
                    outcome="FAILURE",
                    target_user_id=user.id,
                    details={
                        "reason": "last_active_admin",
                        "source": "cli",
                        "operator": getuser(),
                    },
                )
                await session.commit()
                raise ValueError("Cannot revoke the last active platform administrator")

        user.is_platform_admin = False
        record_security_event(
            session,
            event_type="platform.admin.revoked",
            outcome="SUCCESS",
            target_user_id=user.id,
            details={"changed": changed, "source": "cli", "operator": getuser()},
        )
        try:
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
    return changed


async def purge_orphan_uploads(
    session_factory: Any = None,
    *,
    older_than_hours: int | None = None,
    storage: Any = None,
) -> int:
    factory = _resolve_session_factory(session_factory)
    storage = storage or provider_or_503(get_provider_registry(), "storage")
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=MEDIA_ORPHAN_UPLOAD_HOURS if older_than_hours is None else older_than_hours
    )
    async with factory() as session:
        assets = list(
            (
                await session.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.status == "UPLOAD_PENDING",
                        MediaAsset.created_at < cutoff,
                    )
                    .order_by(MediaAsset.created_at.asc(), MediaAsset.id.asc())
                )
            ).all()
        )
        for asset in assets:
            await storage.delete_object(asset.storage_key)
            await session.delete(asset)
        await session.commit()
        return len(assets)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create-platform-admin", help="Create or promote the first platform administrator")
    grant_parser = commands.add_parser("grant-platform-admin", help="Grant platform-admin access")
    grant_parser.add_argument("email")
    revoke_parser = commands.add_parser("revoke-platform-admin", help="Revoke platform-admin access")
    revoke_parser.add_argument("email")
    commands.add_parser("purge-expired", help="Delete expired rate-limit counter rows")
    commands.add_parser("purge-orphan-uploads", help="Delete stale, incomplete media uploads")
    commands.add_parser("purge-security-events", help="Delete old security audit events")
    arguments = parser.parse_args()

    try:
        if arguments.command == "create-platform-admin":
            email = asyncio.run(create_platform_admin())
            print(f"Platform administrator created or promoted: {email}")
        elif arguments.command == "grant-platform-admin":
            changed = asyncio.run(grant_platform_admin(arguments.email))
            print(f"Platform-admin access {'granted' if changed else 'already granted'}: {arguments.email}")
        elif arguments.command == "revoke-platform-admin":
            changed = asyncio.run(revoke_platform_admin(arguments.email))
            print(f"Platform-admin access {'revoked' if changed else 'already absent'}: {arguments.email}")
        elif arguments.command == "purge-expired":
            deleted = asyncio.run(purge_expired_counters())
            tokens_deleted = asyncio.run(purge_expired_account_email_tokens())
            print(
                f"Deleted {deleted} expired rate-limit counters and "
                f"{tokens_deleted} expired/consumed account email tokens"
            )
        elif arguments.command == "purge-security-events":
            deleted = asyncio.run(purge_expired_security_events())
            print(f"Deleted {deleted} expired security events")
        elif arguments.command == "purge-orphan-uploads":
            deleted = asyncio.run(purge_orphan_uploads())
            print(f"Deleted {deleted} orphan media uploads")
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()