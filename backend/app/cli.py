import argparse
import asyncio
import os
import secrets
from datetime import datetime, timedelta, timezone
from getpass import getpass, getuser
from typing import Any

from sqlalchemy import select

from .account_tokens import purge_expired_account_email_tokens
from .config import MEDIA_ORPHAN_UPLOAD_HOURS
from .database import PostgresSessionLocal
from .models import (
    Course,
    CourseTeacher,
    Department,
    Enrollment,
    Exercise,
    Faculty,
    Institution,
    InstitutionMembership,
    InstitutionMembershipRequest,
    Lesson,
    MediaAsset,
    Student,
    Teacher,
    User,
)
from .providers import get_provider_registry, provider_or_503
from .rate_limit import purge_expired_counters
from .security import password_hash
from .security_audit import purge_expired_security_events, record_security_event


def _resolve_session_factory(session_factory: Any = None):
    factory = session_factory or PostgresSessionLocal
    if factory is None:
        raise RuntimeError("ME_YOU_DATABASE_URL is not configured")
    return factory


async def _get_or_create(session, model, lookup: dict, values: dict | None = None):
    value = await session.scalar(select(model).filter_by(**lookup))
    if value is not None:
        return value
    value = model(**lookup, **(values or {}))
    session.add(value)
    await session.flush()
    return value


async def seed_demo(session_factory: Any = None) -> list[tuple[str, str, str]]:
    if os.getenv("ME_YOU_ENV", "").lower() != "development":
        raise ValueError("seed-demo is available only when ME_YOU_ENV=development")

    factory = _resolve_session_factory(session_factory)
    credentials: list[tuple[str, str, str]] = []
    async with factory() as session:
        institution = await _get_or_create(
            session,
            Institution,
            {"name": "Me & You Demo School"},
            {
                "institution_type": "SCHOOL",
                "description": "A sample school for exploring the student learning experience.",
                "location": "Example City",
            },
        )
        faculty = await _get_or_create(
            session,
            Faculty,
            {"institution_id": institution.id, "name": "Faculty of Learning"},
        )
        department = await _get_or_create(
            session,
            Department,
            {"faculty_id": faculty.id, "name": "Department of Foundations"},
        )

        users = {}
        for username, email, label in (
            ("demo-school-admin", "demo.admin@example.test", "School admin"),
            ("demo-teacher", "demo.teacher@example.test", "Teacher"),
            ("demo-student-enrolled", "demo.enrolled@example.test", "Enrolled student"),
            ("demo-student-invited", "demo.invited@example.test", "Invited student"),
        ):
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                password = secrets.token_urlsafe(18)
                user = User(
                    username=username,
                    email=email,
                    password_hash=password_hash.hash(password),
                )
                session.add(user)
                await session.flush()
                credentials.append((label, email, password))
            users[email] = user

        admin_user = users["demo.admin@example.test"]
        teacher_user = users["demo.teacher@example.test"]
        enrolled_user = users["demo.enrolled@example.test"]
        invited_user = users["demo.invited@example.test"]

        await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": admin_user.id, "institution_id": institution.id},
            {"role": "ADMIN"},
        )
        await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": teacher_user.id, "institution_id": institution.id},
            {"role": "TEACHER"},
        )
        enrolled_membership = await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": enrolled_user.id, "institution_id": institution.id},
            {"role": "STUDENT"},
        )
        teacher = await _get_or_create(
            session,
            Teacher,
            {"user_id": teacher_user.id, "institution_id": institution.id},
        )
        student = await _get_or_create(
            session,
            Student,
            {"user_id": enrolled_user.id, "institution_id": institution.id},
        )

        courses = []
        for code, name, description in (
            ("FOUND-101", "Learning Foundations", "Build strong habits for independent learning."),
            ("STUDY-201", "Study Skills Workshop", "Practice planning, focus, and reflection."),
        ):
            course = await _get_or_create(
                session,
                Course,
                {"department_id": department.id, "code": code},
                {"name": name, "description": description},
            )
            courses.append(course)
            await _get_or_create(
                session,
                CourseTeacher,
                {"course_id": course.id, "teacher_id": teacher.id},
            )
            for lesson_position in range(4):
                lesson_title = f"{code} Lesson {lesson_position + 1}"
                lesson = await _get_or_create(
                    session,
                    Lesson,
                    {"course_id": course.id, "title": lesson_title},
                    {
                        "content": (
                            f"Welcome to {lesson_title}. Read this short guide, "
                            "try the exercises below, and mark the lesson done when ready."
                        ),
                        "position": lesson_position,
                        "is_published": True,
                    },
                )
                for exercise_position in range(2):
                    exercise_title = f"{lesson_title} Practice {exercise_position + 1}"
                    await _get_or_create(
                        session,
                        Exercise,
                        {"lesson_id": lesson.id, "title": exercise_title},
                        {
                            "instructions": "Write a short reflection on one idea from this lesson.",
                            "position": exercise_position,
                            "exercise_type": "WRITTEN",
                        },
                    )

        await _get_or_create(
            session,
            Enrollment,
            {"student_id": student.id, "course_id": courses[0].id},
        )
        invitation = await session.scalar(
            select(InstitutionMembershipRequest).where(
                InstitutionMembershipRequest.institution_id == institution.id,
                InstitutionMembershipRequest.user_id == invited_user.id,
                InstitutionMembershipRequest.request_type == "INVITATION",
            )
        )
        if invitation is None:
            session.add(
                InstitutionMembershipRequest(
                    institution_id=institution.id,
                    user_id=invited_user.id,
                    role="STUDENT",
                    request_type="INVITATION",
                    status="INVITED",
                    created_by_user_id=admin_user.id,
                )
            )

        await session.commit()
    return credentials


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
    commands.add_parser("seed-demo", help="Seed development-only school and course demo data")
    arguments = parser.parse_args()

    try:
        if arguments.command == "seed-demo":
            credentials = asyncio.run(seed_demo())
            print("Demo school and course data is ready.")
            if credentials:
                print("New demo account passwords (shown once):")
                for label, email, password in credentials:
                    print(f"{label}: {email} / {password}")
            else:
                print("No new accounts were created; no passwords were generated.")
        elif arguments.command == "create-platform-admin":
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