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
    ClassSession,
    ClassSessionAttendance,
    Comment,
    ClassSession,
    ClassSessionAttendance,
    Course,
    CourseTeacher,
    Conversation,
    ConversationMember,
    Department,
    Enrollment,
    Exercise,
    Faculty,
    Institution,
    InstitutionMembership,
    InstitutionMembershipRequest,
    Lesson,
    MediaAsset,
    Message,
    Notification,
    Post,
    PostLike,
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
        institution.is_listed = True
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

        admin_membership = await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": admin_user.id, "institution_id": institution.id},
            {"role": "ADMIN"},
        )
        admin_membership.role = "ADMIN"
        teacher_membership = await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": teacher_user.id, "institution_id": institution.id},
            {"role": "TEACHER"},
        )
        teacher_membership.role = "TEACHER"
        enrolled_membership = await _get_or_create(
            session,
            InstitutionMembership,
            {"user_id": enrolled_user.id, "institution_id": institution.id},
            {"role": "STUDENT"},
        )
        enrolled_membership.role = "STUDENT"
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
        now = datetime.now(timezone.utc)
        live_session = await _get_or_create(
            session,
            ClassSession,
            {"course_id": courses[0].id, "title": "Demo live classroom"},
            {
                "created_by_id": teacher_user.id,
                "description": "A sample live classroom for the demo course.",
                "starts_at": now - timedelta(minutes=5),
                "ends_at": now + timedelta(minutes=55),
                "status": "LIVE",
                "started_at": now - timedelta(minutes=5),
            },
        )
        scheduled_start = now + timedelta(days=1)
        scheduled_session = await _get_or_create(
            session,
            ClassSession,
            {"course_id": courses[0].id, "title": "Demo classroom tomorrow"},
            {
                "created_by_id": teacher_user.id,
                "description": "A sample scheduled classroom for the demo course.",
                "starts_at": scheduled_start,
                "ends_at": scheduled_start + timedelta(hours=1),
                "status": "SCHEDULED",
            },
        )
        for class_session in (live_session, scheduled_session):
            await _get_or_create(
                session,
                ClassSessionAttendance,
                {"session_id": class_session.id, "user_id": enrolled_user.id},
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

        demo_post_specs = (
            (enrolled_user, "Demo: I am trying a short daily review before class.", teacher_user, "Demo reply: A quick review makes it easier to build momentum."),
            (teacher_user, "Demo: What is one idea you want to practice this week?", enrolled_user, "Demo reply: I am working on keeping study sessions focused."),
            (invited_user, "Demo: Looking forward to joining the learning community.", admin_user, "Demo reply: Welcome, we are glad you are here."),
        )
        demo_posts = []
        for author, content, liker, comment_content in demo_post_specs:
            post = await _get_or_create(
                session,
                Post,
                {"author_id": author.id, "content": content},
                {"visibility": "PUBLIC", "post_type": "POST"},
            )
            demo_posts.append(post)
            await _get_or_create(
                session,
                PostLike,
                {"post_id": post.id, "user_id": liker.id},
            )
            await _get_or_create(
                session,
                Comment,
                {"post_id": post.id, "author_id": liker.id, "content": comment_content},
            )

        direct_key = ":".join(sorted((str(enrolled_user.id), str(teacher_user.id))))
        direct_conversation = await _get_or_create(
            session,
            Conversation,
            {"direct_key": direct_key},
            {"type": "DIRECT", "created_by_id": teacher_user.id},
        )
        for member in (enrolled_user, teacher_user):
            await _get_or_create(
                session,
                ConversationMember,
                {"conversation_id": direct_conversation.id, "user_id": member.id},
            )

        group_conversation = await _get_or_create(
            session,
            Conversation,
            {"type": "GROUP", "name": "Demo Study Group", "created_by_id": enrolled_user.id},
            {"description": "A sample group for study plans and questions."},
        )
        group_members = (enrolled_user, teacher_user, invited_user)
        for member in group_members:
            await _get_or_create(
                session,
                ConversationMember,
                {"conversation_id": group_conversation.id, "user_id": member.id},
            )

        for conversation, messages in (
            (direct_conversation, (
                (enrolled_user, "Demo hello from the enrolled student."),
                (teacher_user, "Demo reply from the teacher."),
                (enrolled_user, "Demo thanks, I will try that before the next lesson."),
            )),
            (group_conversation, (
                (enrolled_user, "Demo group: what is everyone studying this week?"),
                (teacher_user, "Demo group: share one useful resource when you find it."),
            )),
        ):
            for sender, content in messages:
                await _get_or_create(
                    session,
                    Message,
                    {"conversation_id": conversation.id, "sender_id": sender.id, "content": content},
                )

        demo_notifications = (
            (enrolled_user, teacher_user, "LIKE", "A teacher liked your post", demo_posts[0].id, demo_posts[0].id),
            (teacher_user, enrolled_user, "COMMENT", "A student commented on your post", demo_posts[1].id, demo_posts[1].id),
            (enrolled_user, teacher_user, "MESSAGE", "New message in your conversation", direct_conversation.id, None),
        )
        for recipient, actor, notification_type, title, target_id, post_id in demo_notifications:
            await _get_or_create(
                session,
                Notification,
                {
                    "recipient_id": recipient.id,
                    "actor_id": actor.id,
                    "type": notification_type,
                    "title": title,
                    "target_type": "post" if post_id else "conversation",
                    "target_id": target_id,
                },
                {"post_id": post_id},
            )

        await session.commit()
    return credentials


async def reset_demo_passwords(
    session_factory: Any = None,
) -> tuple[list[tuple[str, str, str]], list[str]]:
    if os.getenv("ME_YOU_ENV", "").lower() != "development":
        raise ValueError("reset-demo-passwords is available only when ME_YOU_ENV=development")

    factory = _resolve_session_factory(session_factory)
    demo_accounts = (
        ("School admin", "demo.admin@example.test"),
        ("Teacher", "demo.teacher@example.test"),
        ("Enrolled student", "demo.enrolled@example.test"),
        ("Invited student", "demo.invited@example.test"),
    )
    credentials: list[tuple[str, str, str]] = []
    missing: list[str] = []
    async with factory() as session:
        for label, email in demo_accounts:
            user = await session.scalar(
                select(User).where(User.email == email).with_for_update()
            )
            if user is None:
                missing.append(email)
                continue
            password = secrets.token_urlsafe(24)
            user.password_hash = password_hash.hash(password)
            user.token_version = (user.token_version or 0) + 1
            credentials.append((label, email, password))
        await session.commit()
    return credentials, missing


def _write_demo_credentials(path: str, credentials: list[tuple[str, str, str]]) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = -1
            for label, email, password in credentials:
                output.write(f"{label}: {email} / {password}\n")
    finally:
        if descriptor != -1:
            os.close(descriptor)


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
    seed_parser = commands.add_parser("seed-demo", help="Seed development-only school and course demo data")
    seed_parser.add_argument("--output", required=True, metavar="FILE", help="Write generated credentials to FILE")
    reset_demo_parser = commands.add_parser(
        "reset-demo-passwords",
        help="Reset passwords for existing development demo accounts",
    )
    reset_demo_parser.add_argument(
        "--output", required=True, metavar="FILE", help="Write generated credentials to FILE"
    )
    arguments = parser.parse_args()

    try:
        if arguments.command == "seed-demo":
            credentials = asyncio.run(seed_demo())
            _write_demo_credentials(arguments.output, credentials)
            print(arguments.output)
        elif arguments.command == "reset-demo-passwords":
            credentials, missing = asyncio.run(reset_demo_passwords())
            _write_demo_credentials(arguments.output, credentials)
            print(arguments.output)
            for email in missing:
                print(f"Missing demo account {email}; run seed-demo to create demo accounts.")
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