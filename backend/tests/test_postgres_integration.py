import asyncio
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import asyncpg
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from starlette.requests import Request

from app.database import get_postgres_session
from app.main import app
from app.models import (
    AuthIdentity,
    ClassSession,
    ClassSessionAttendance,
    Course,
    CourseTeacher,
    Department,
    Enrollment,
    Exercise,
    ExerciseSubmission,
    Faculty,
    Institution,
    InstitutionMembership,
    Lesson,
    MediaAsset,
    MusicCategoryFollow,
    Notification,
    NotificationPreference,
    Playlist,
    PlaylistItem,
    SecurityEvent,
    Student,
    Teacher,
    Track,
    UserBlock,
    User,
    Video,
    VideoComment,
)
import app.routes.institutions as institution_routes
from app.security import get_current_postgres_user
from app.permissions import ensure_account_can_be_deactivated
from app.permissions import require_course_teacher, require_enrolled_student


pytestmark = pytest.mark.postgres
BACKEND = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def disable_global_api_rate_limit_for_isolated_database(monkeypatch):
    monkeypatch.setattr("app.main.RATE_LIMIT_ENABLED", False)


def _alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["ME_YOU_DATABASE_URL"] = database_url
    environment["PYTHONPATH"] = str(BACKEND) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="session")
def postgres_database_url():
    configured_url = os.getenv("ME_YOU_DATABASE_URL")
    if not configured_url:
        pytest.skip("PostgreSQL integration tests require ME_YOU_DATABASE_URL")

    base_url = make_url(configured_url)
    if base_url.drivername != "postgresql+asyncpg":
        pytest.fail("ME_YOU_DATABASE_URL must use the postgresql+asyncpg:// scheme")

    database_name = f"me_you_test_{uuid.uuid4().hex}"
    test_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    admin_connect = {
        "user": base_url.username,
        "password": base_url.password,
        "host": base_url.host,
        "port": base_url.port or 5432,
        "database": "postgres",
    }

    async def create_database():
        connection = await asyncpg.connect(**admin_connect)
        try:
            await connection.execute(f'CREATE DATABASE "{database_name}"')
        finally:
            await connection.close()

    async def drop_database():
        connection = await asyncpg.connect(**admin_connect)
        try:
            await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        finally:
            await connection.close()

    asyncio.run(create_database())
    try:
        result = _alembic(test_url, "upgrade", "head")
        if result.returncode:
            pytest.fail(f"Could not migrate temporary PostgreSQL database:\n{result.stdout}{result.stderr}")
        yield test_url
    finally:
        asyncio.run(drop_database())


@asynccontextmanager
async def database_session(database_url: str):
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


async def create_user(session, *, username: str | None = None, email: str | None = None) -> User:
    suffix = uuid.uuid4().hex
    user = User(
        username=username or f"user-{suffix}",
        email=email or f"{suffix}@example.com",
        password_hash="test-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def create_institution(session, *, name: str | None = None) -> Institution:
    institution = Institution(
        name=name or f"School {uuid.uuid4().hex}",
        institution_type="SCHOOL",
    )
    session.add(institution)
    await session.flush()
    return institution


async def create_learning_records(session):
    user = await create_user(session)
    institution = await create_institution(session)
    faculty = Faculty(institution_id=institution.id, name="Faculty")
    session.add(faculty)
    await session.flush()
    department = Department(faculty_id=faculty.id, name="Department")
    session.add(department)
    await session.flush()
    course = Course(department_id=department.id, code="CS101", name="Computing")
    student = Student(user_id=user.id, institution_id=institution.id)
    session.add_all([course, student])
    await session.flush()
    return user, institution, course, student

def test_database_rejects_duplicate_username_and_email(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            existing = await create_user(session, username="duplicate-name", email="first@example.com")
            existing_username = existing.username
            existing_email = existing.email
            await session.commit()

            session.add(User(username=existing_username, email="other@example.com", password_hash="test-hash"))
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

            session.add(User(username="other-name", email=existing_email, password_hash="test-hash"))
            with pytest.raises(IntegrityError):
                await session.flush()

    asyncio.run(verify())


def test_post_quality_migration_supports_downgrade_and_upgrade(postgres_database_url):
    result = _alembic(postgres_database_url, "downgrade", "0028_music_library")
    assert result.returncode == 0, result.stdout + result.stderr
    result = _alembic(postgres_database_url, "upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr


def test_notification_preferences_and_mark_all_are_user_scoped(postgres_database_url):
    from app.models import Notification, NotificationPreference
    from app.notification_preferences import add_notification

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        user_ids: list[uuid.UUID] = []
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                other = await create_user(session)
                user_ids.extend([owner.id, other.id])
                owner_notification = Notification(
                    recipient_id=owner.id,
                    type="FOLLOW",
                    title="Owner notification",
                )
                other_notification = Notification(
                    recipient_id=other.id,
                    type="FOLLOW",
                    title="Other notification",
                )
                session.add_all([owner_notification, other_notification])
                await session.commit()
                owner_notification_id = owner_notification.id
                other_notification_id = other_notification.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency(request: Request):
                async with session_factory() as session:
                    return await session.get(User, uuid.UUID(request.headers["x-test-user"]))

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                headers = {"x-test-user": str(user_ids[0])}
                defaults = await client.get("/notifications/preferences", headers=headers)
                assert defaults.status_code == 200
                assert defaults.json()["preferences"]
                assert all(defaults.json()["preferences"].values())

                update_response = await client.put(
                    "/notifications/preferences",
                    headers=headers,
                    json={"preferences": {"FOLLOW": False}},
                )
                assert update_response.status_code == 200
                assert update_response.json()["preferences"]["FOLLOW"] is False

                async with session_factory() as session:
                    suppressed = Notification(
                        recipient_id=user_ids[0],
                        type="FOLLOW",
                        title="Suppressed notification",
                    )
                    security_preference = NotificationPreference(
                        user_id=user_ids[0],
                        notification_type="SECURITY_ALERT",
                        enabled=False,
                    )
                    security_notification = Notification(
                        recipient_id=user_ids[0],
                        type="SECURITY_ALERT",
                        title="Security alert",
                    )
                    session.add(security_preference)
                    assert await add_notification(session, suppressed) is False
                    assert await add_notification(session, security_notification) is True
                    await session.commit()
                    assert await session.scalar(
                        select(Notification.id).where(
                            Notification.title == "Suppressed notification"
                        )
                    ) is None
                    assert await session.scalar(
                        select(Notification.id).where(
                            Notification.title == "Security alert"
                        )
                    ) is not None

                marked = await client.post("/notifications/read-all", headers=headers)
                assert marked.status_code == 200
                async with session_factory() as session:
                    owner_read_at = await session.scalar(
                        select(Notification.read_at).where(
                            Notification.id == owner_notification_id
                        )
                    )
                    other_read_at = await session.scalar(
                        select(Notification.read_at).where(
                            Notification.id == other_notification_id
                        )
                    )
                    saved_preference = await session.get(
                        NotificationPreference, (user_ids[0], "FOLLOW")
                    )
                    assert owner_read_at is not None
                    assert other_read_at is None
                    assert saved_preference is not None
                    assert saved_preference.enabled is False
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            if user_ids:
                async with session_factory() as session:
                    for user_id in user_ids:
                        user = await session.get(User, user_id)
                        if user is not None:
                            await session.delete(user)
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_auth_identity_constraints_and_multiple_identities(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            first_user = await create_user(session)
            second_user = await create_user(session)
            second_user_id = second_user.id
            first_user.phone_number = "+12025550111"
            session.add_all(
                [
                    AuthIdentity(
                        user_id=first_user.id,
                        provider="google",
                        provider_subject="google-subject-1",
                    ),
                    AuthIdentity(
                        user_id=first_user.id,
                        provider="phone",
                        provider_subject="+12025550111",
                    ),
                ]
            )
            await session.commit()

            session.add(
                User(
                    username="duplicate-phone",
                    email="duplicate-phone@example.com",
                    password_hash="test-hash",
                    phone_number=first_user.phone_number,
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

            session.add(
                AuthIdentity(
                    user_id=second_user_id,
                    provider="google",
                    provider_subject="google-subject-1",
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()

    asyncio.run(verify())


def test_auth_identity_migration_up_and_down(postgres_database_url):
    base_url = make_url(postgres_database_url)
    database_name = f"me_you_auth_migration_{uuid.uuid4().hex}"
    migration_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    admin_connect = {
        "user": base_url.username,
        "password": base_url.password,
        "host": base_url.host,
        "port": base_url.port or 5432,
        "database": "postgres",
    }

    async def create_database():
        connection = await asyncpg.connect(**admin_connect)
        try:
            await connection.execute(f'CREATE DATABASE "{database_name}"')
        finally:
            await connection.close()

    async def migration_state():
        connection = await asyncpg.connect(**{**admin_connect, "database": database_name})
        try:
            phone_exists = await connection.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'phone_number')"
            )
            identities_exist = await connection.fetchval(
                "SELECT to_regclass('public.auth_identities') IS NOT NULL"
            )
            return phone_exists, identities_exist
        finally:
            await connection.close()

    async def drop_database():
        connection = await asyncpg.connect(**admin_connect)
        try:
            await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        finally:
            await connection.close()

    async def verify():
        await create_database()
        try:
            result = _alembic(migration_url, "upgrade", "0017_media_storage")
            assert result.returncode == 0, result.stdout + result.stderr
            assert await migration_state() == (False, False)

            result = _alembic(migration_url, "upgrade", "head")
            assert result.returncode == 0, result.stdout + result.stderr
            assert await migration_state() == (True, True)

            result = _alembic(migration_url, "downgrade", "0017_media_storage")
            assert result.returncode == 0, result.stdout + result.stderr
            assert await migration_state() == (False, False)
        finally:
            await drop_database()

    asyncio.run(verify())


def test_google_sign_in_creates_user_from_verified_claims(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google
    from app.security import password_hash

    claims = {
        "sub": "google-new-user",
        "email": "New.User@example.com",
        "email_verified": True,
    }
    verifier = Mock(return_value=claims)
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(auth_google.id_token, "verify_oauth2_token", verifier)

    async def verify():
        async with database_session(postgres_database_url) as session:
            response = await auth_google.google_sign_in(
                auth_google.GoogleSignInRequest(id_token="signed-google-token"),
                session,
            )
            user = await session.scalar(
                select(User).where(User.email == "new.user@example.com")
            )
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_subject == "google-new-user",
                )
            )
            assert user is not None
            assert identity is not None
            assert identity.user_id == user.id
            assert user.email_verified_at is not None
            assert response["id"] == str(user.id)
            assert response["token_type"] == "bearer"
            assert not password_hash.verify("", user.password_hash)
            assert verifier.call_args.args[2] == "google-test-client"
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_google_sign_in_uses_existing_identity(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(
        auth_google.id_token,
        "verify_oauth2_token",
        Mock(
            return_value={
                "sub": "google-existing-subject",
                "email": "changed@example.com",
                "email_verified": True,
            }
        ),
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session)
            session.add(
                AuthIdentity(
                    user_id=user.id,
                    provider="google",
                    provider_subject="google-existing-subject",
                )
            )
            await session.commit()
            response = await auth_google.google_sign_in(
                auth_google.GoogleSignInRequest(id_token="signed-google-token"),
                session,
            )
            assert response["id"] == str(user.id)
            assert response["email"] == user.email
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_google_sign_in_links_matching_verified_email(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    claims = {
        "sub": "google-link-subject",
        "email": "EXISTING@example.com",
        "email_verified": True,
    }
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(auth_google.id_token, "verify_oauth2_token", Mock(return_value=claims))

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session, email="existing@example.com")
            user.email_verified_at = datetime.now(timezone.utc)
            original_password_hash = user.password_hash
            await session.commit()
            response = await auth_google.google_sign_in(
                auth_google.GoogleSignInRequest(id_token="signed-google-token"),
                session,
            )
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_subject == "google-link-subject",
                )
            )
            assert response["id"] == str(user.id)
            assert identity is not None and identity.user_id == user.id
            assert user.password_hash == original_password_hash
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_google_sign_in_protects_unverified_matching_account_and_revokes_sessions(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google
    from fastapi.security import HTTPAuthorizationCredentials
    from app.security import create_access_token, get_current_postgres_user, password_hash

    claims = {
        "sub": "google-unverified-account-link",
        "email": "unverified-link@example.com",
        "email_verified": True,
    }
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(auth_google.id_token, "verify_oauth2_token", Mock(return_value=claims))

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session, email="unverified-link@example.com")
            user.password_hash = password_hash.hash("prior-password-value")
            await session.commit()
            original_password_hash = user.password_hash
            old_token = create_access_token(user.id, token_version=user.token_version)

            response = await auth_google.google_sign_in(
                auth_google.GoogleSignInRequest(id_token="signed-google-token"),
                session,
            )
            await session.refresh(user)
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_subject == "google-unverified-account-link",
                )
            )
            event = await session.scalar(
                select(SecurityEvent).where(
                    SecurityEvent.event_type == "auth.google_linked_unverified_account",
                    SecurityEvent.target_user_id == user.id,
                )
            )
            assert response["id"] == str(user.id)
            assert identity is not None and identity.user_id == user.id
            assert user.email_verified_at is not None
            assert user.password_hash != original_password_hash
            assert not password_hash.verify("prior-password-value", user.password_hash)
            assert user.token_version == 1
            assert event is not None and event.details == {}
            with pytest.raises(HTTPException) as error:
                await get_current_postgres_user(
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials=old_token),
                    session,
                )
            assert error.value.status_code == 401
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_google_sign_in_refuses_deactivated_matching_account(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    claims = {
        "sub": "google-deactivated-link",
        "email": "deactivated-link@example.com",
        "email_verified": True,
    }
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(auth_google.id_token, "verify_oauth2_token", Mock(return_value=claims))

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session, email="deactivated-link@example.com")
            user.is_active = False
            await session.commit()
            with pytest.raises(HTTPException) as error:
                await auth_google.google_sign_in(
                    auth_google.GoogleSignInRequest(id_token="signed-google-token"),
                    session,
                )
            assert error.value.status_code == 401
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "google",
                    AuthIdentity.provider_subject == "google-deactivated-link",
                )
            )
            assert identity is None
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_classroom_attendance_paginates_more_students_than_the_default_limit(postgres_database_url):
    from app.routes.classrooms import list_class_session_attendance

    async def verify():
        async with database_session(postgres_database_url) as session:
            teacher_user = await create_user(session)
            institution = await create_institution(session)
            faculty = Faculty(institution_id=institution.id, name="Attendance faculty")
            session.add(faculty)
            await session.flush()
            department = Department(faculty_id=faculty.id, name="Attendance department")
            session.add(department)
            await session.flush()
            course = Course(department_id=department.id, code="ATTEND", name="Attendance")
            teacher = Teacher(user_id=teacher_user.id, institution_id=institution.id)
            session.add_all([course, teacher])
            await session.flush()
            session.add_all([
                InstitutionMembership(user_id=teacher_user.id, institution_id=institution.id, role="TEACHER"),
                CourseTeacher(course_id=course.id, teacher_id=teacher.id),
            ])
            await session.flush()
            students = []
            for index in range(55):
                student_user = await create_user(
                    session,
                    username=f"attendance-{index:03}",
                )
                student = Student(user_id=student_user.id, institution_id=institution.id)
                students.append(student)
                session.add_all([
                    student,
                    InstitutionMembership(user_id=student_user.id, institution_id=institution.id, role="STUDENT"),
                ])
            await session.flush()
            session.add_all([Enrollment(student_id=student.id, course_id=course.id) for student in students])
            value = ClassSession(
                course_id=course.id,
                created_by_id=teacher_user.id,
                title="Attendance pagination",
                starts_at=datetime.now(timezone.utc),
                ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            session.add(value)
            await session.flush()
            await session.commit()

            first_page = await list_class_session_attendance(value.id, teacher_user, session)
            second_page = await list_class_session_attendance(value.id, teacher_user, session, offset=50)

            assert len(first_page) == 50
            assert len(second_page) == 5
            assert len({record["user_id"] for record in first_page + second_page}) == 55
            assert [record["username"] for record in first_page + second_page] == [
                f"attendance-{index:03}" for index in range(55)
            ]

    asyncio.run(verify())


def test_google_sign_in_rejects_bad_audience(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    verifier = Mock(side_effect=ValueError("Audience mismatch"))
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "expected-google-client")
    monkeypatch.setattr(auth_google.id_token, "verify_oauth2_token", verifier)

    async def verify():
        async with database_session(postgres_database_url) as session:
            with pytest.raises(HTTPException) as error:
                await auth_google.google_sign_in(
                    auth_google.GoogleSignInRequest(id_token="wrong-audience-token"),
                    session,
                )
            assert error.value.status_code == 401
            verifier.assert_called_once()
            assert verifier.call_args.args[2] == "expected-google-client"

    asyncio.run(verify())


def test_google_sign_in_rejects_unverified_email(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(
        auth_google.id_token,
        "verify_oauth2_token",
        Mock(
            return_value={
                "sub": "google-unverified-subject",
                "email": "unverified@example.com",
                "email_verified": False,
            }
        ),
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            with pytest.raises(HTTPException) as error:
                await auth_google.google_sign_in(
                    auth_google.GoogleSignInRequest(id_token="unverified-token"),
                    session,
                )
            assert error.value.status_code == 401
            assert "not verified" in error.value.detail

    asyncio.run(verify())


def test_google_sign_in_rejects_expired_token(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "google-test-client")
    monkeypatch.setattr(
        auth_google.id_token,
        "verify_oauth2_token",
        Mock(side_effect=ValueError("Token expired")),
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            with pytest.raises(HTTPException) as error:
                await auth_google.google_sign_in(
                    auth_google.GoogleSignInRequest(id_token="expired-token"),
                    session,
                )
            assert error.value.status_code == 401
            assert "expired" in error.value.detail

    asyncio.run(verify())


def test_google_sign_in_returns_503_when_unconfigured(postgres_database_url, monkeypatch):
    import app.routes.auth_google as auth_google

    monkeypatch.delenv("ME_YOU_GOOGLE_CLIENT_ID", raising=False)

    async def verify():
        async with database_session(postgres_database_url) as session:
            with pytest.raises(HTTPException) as error:
                await auth_google.google_sign_in(
                    auth_google.GoogleSignInRequest(id_token="token"), session
                )
            assert error.value.status_code == 503
            assert "not configured" in error.value.detail

    asyncio.run(verify())


def test_phone_code_request_and_verify_creates_user(postgres_database_url, monkeypatch):
    import app.routes.auth_phone as auth_phone
    from app.models import PhoneLoginCode
    from app.security import decode_access_token, password_hash

    class CapturingSMSProvider:
        def __init__(self):
            self.codes = []

        async def send_code(self, *, phone_number, code):
            self.codes.append((phone_number, code))

    class TestLimiter:
        async def increment(self, _scope, _key, _window_seconds):
            return 1, 60

    provider = CapturingSMSProvider()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/phone/request",
            "raw_path": b"/auth/phone/request",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.41", 1234),
            "server": ("test", 80),
        }
    )
    monkeypatch.setenv("ME_YOU_ENV", "development")

    async def verify():
        async with database_session(postgres_database_url) as session:
            requested = await auth_phone.request_phone_code(
                auth_phone.PhoneCodeRequest(phone_number="+1 (415) 555-2671"),
                request,
                session,
                provider,
                TestLimiter(),
            )
            assert requested["message"] == auth_phone.REQUEST_MESSAGE
            phone_number, code = provider.codes[0]
            stored = await session.scalar(
                select(PhoneLoginCode).where(PhoneLoginCode.phone_number == phone_number)
            )
            assert stored is not None and stored.code_hash != code
            assert stored.code_hash == auth_phone.hash_phone_code(phone_number, code)

        async with database_session(postgres_database_url) as session:
            response = await auth_phone.verify_phone_code(
                auth_phone.PhoneCodeVerify(phone_number=phone_number, code=code),
                session,
                provider,
            )
            user = await session.scalar(
                select(User).where(User.phone_number == phone_number)
            )
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "phone",
                    AuthIdentity.provider_subject == phone_number,
                )
            )
            assert user is not None and identity is not None
            assert identity.user_id == user.id
            assert response["id"] == str(user.id)
            assert decode_access_token(response["access_token"])["sub"] == str(user.id)
            assert not password_hash.verify("", user.password_hash)
            with pytest.raises(HTTPException) as second_verify:
                await auth_phone.verify_phone_code(
                    auth_phone.PhoneCodeVerify(phone_number=phone_number, code=code),
                    session,
                    provider,
                )
            assert second_verify.value.status_code == 401
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_phone_code_verification_reuses_existing_identity(postgres_database_url):
    import app.routes.auth_phone as auth_phone
    from app.models import PhoneLoginCode

    class TestProvider:
        async def send_code(self, *, phone_number, code):
            return None

    phone_number = "+14155552672"
    code = "123456"

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session)
            user.phone_number = phone_number
            session.add(
                AuthIdentity(
                    user_id=user.id,
                    provider="phone",
                    provider_subject=phone_number,
                )
            )
            session.add(
                PhoneLoginCode(
                    phone_number=phone_number,
                    code_hash=auth_phone.hash_phone_code(phone_number, code),
                    attempts=0,
                    created_at=auth_phone.utcnow(),
                    expires_at=auth_phone.utcnow() + timedelta(minutes=10),
                )
            )
            await session.commit()
            user_id = user.id
            response = await auth_phone.verify_phone_code(
                auth_phone.PhoneCodeVerify(phone_number=phone_number, code=code),
                session,
                TestProvider(),
            )
            assert response["id"] == str(user_id)
            assert await session.scalar(
                select(func.count()).select_from(User).where(User.phone_number == phone_number)
            ) == 1
            await session.delete(user)
            await session.commit()

    asyncio.run(verify())


def test_phone_code_request_has_same_response_for_existing_and_new_numbers(
    postgres_database_url,
):
    import app.routes.auth_phone as auth_phone

    class CapturingSMSProvider:
        def __init__(self):
            self.codes = []

        async def send_code(self, *, phone_number, code):
            self.codes.append((phone_number, code))

    class TestLimiter:
        async def increment(self, _scope, _key, _window_seconds):
            return 1, 60

    provider = CapturingSMSProvider()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/phone/request",
            "raw_path": b"/auth/phone/request",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.42", 1234),
            "server": ("test", 80),
        }
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            existing_user = await create_user(session)
            existing_user.phone_number = "+12025550121"
            await session.commit()
            known = await auth_phone.request_phone_code(
                auth_phone.PhoneCodeRequest(phone_number="+12025550121"),
                request,
                session,
                provider,
                TestLimiter(),
            )
            unknown = await auth_phone.request_phone_code(
                auth_phone.PhoneCodeRequest(phone_number="+12025550122"),
                request,
                session,
                provider,
                TestLimiter(),
            )
            assert known == unknown == {"message": auth_phone.REQUEST_MESSAGE}
            assert len(provider.codes) == 2
            await session.delete(existing_user)
            await session.commit()

    asyncio.run(verify())


def test_phone_code_request_cooldown_suppresses_resend(postgres_database_url, monkeypatch):
    import app.routes.auth_phone as auth_phone
    from app.models import PhoneLoginCode

    class CapturingSMSProvider:
        def __init__(self):
            self.codes = []

        async def send_code(self, *, phone_number, code):
            self.codes.append(code)

    class TestLimiter:
        async def increment(self, _scope, _key, _window_seconds):
            return 1, 60

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(auth_phone, "utcnow", lambda: now)
    provider = CapturingSMSProvider()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/auth/phone/request",
            "raw_path": b"/auth/phone/request",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.43", 1234),
            "server": ("test", 80),
        }
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            data = auth_phone.PhoneCodeRequest(phone_number="+12025550131")
            first = await auth_phone.request_phone_code(
                data, request, session, provider, TestLimiter()
            )
            row = await session.scalar(
                select(PhoneLoginCode).where(PhoneLoginCode.phone_number == data.phone_number)
            )
            first_created_at = row.created_at
            second = await auth_phone.request_phone_code(
                data, request, session, provider, TestLimiter()
            )
            assert first == second == {"message": auth_phone.REQUEST_MESSAGE}
            assert len(provider.codes) == 1
            assert row.created_at == first_created_at
            await session.delete(row)
            await session.commit()

    asyncio.run(verify())


def test_phone_code_expires_and_five_wrong_attempts_invalidate(postgres_database_url, monkeypatch):
    import app.routes.auth_phone as auth_phone
    from app.models import PhoneLoginCode

    class TestProvider:
        async def send_code(self, *, phone_number, code):
            return None

    monkeypatch.setattr(
        auth_phone.secrets,
        "randbelow",
        lambda _limit: 12345,
    )
    now = datetime.now(timezone.utc)

    async def verify():
        async with database_session(postgres_database_url) as session:
            expired_number = "+12025550141"
            expired = PhoneLoginCode(
                phone_number=expired_number,
                code_hash=auth_phone.hash_phone_code(expired_number, "012345"),
                attempts=0,
                created_at=now - timedelta(minutes=11),
                expires_at=now - timedelta(minutes=1),
            )
            attempts_number = "+12025550142"
            active = PhoneLoginCode(
                phone_number=attempts_number,
                code_hash=auth_phone.hash_phone_code(attempts_number, "012345"),
                attempts=0,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
            )
            session.add_all([expired, active])
            await session.commit()
            monkeypatch.setattr(auth_phone, "utcnow", lambda: now)

            with pytest.raises(HTTPException) as expiry:
                await auth_phone.verify_phone_code(
                    auth_phone.PhoneCodeVerify(phone_number=expired_number, code="012345"),
                    session,
                    TestProvider(),
                )
            assert expiry.value.status_code == 401
            assert expired.invalidated_at == now

            for _ in range(5):
                with pytest.raises(HTTPException) as invalid:
                    await auth_phone.verify_phone_code(
                        auth_phone.PhoneCodeVerify(phone_number=attempts_number, code="999999"),
                        session,
                        TestProvider(),
                    )
                assert invalid.value.status_code == 401
            assert active.attempts == 5
            assert active.invalidated_at == now
            await session.delete(expired)
            await session.delete(active)
            await session.commit()

    asyncio.run(verify())


def test_seed_demo_is_idempotent(postgres_database_url, monkeypatch):
    from sqlalchemy import delete

    from app.cli import seed_demo
    from app.models import (
        Comment,
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
        Message,
        Notification,
        Post,
        PostLike,
        Student,
        Teacher,
        User,
    )

    monkeypatch.setenv("ME_YOU_ENV", "development")

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                models = (
                    Institution,
                    Faculty,
                    Department,
                    Course,
                    CourseTeacher,
                    Lesson,
                    Exercise,
                    InstitutionMembership,
                    InstitutionMembershipRequest,
                    Teacher,
                    Student,
                    Enrollment,
                    User,
                    Post,
                    PostLike,
                    Comment,
                    Conversation,
                    ConversationMember,
                    Message,
                    Notification,
                )
                before_counts = {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }
            first_credentials = await seed_demo(session_factory)
            async with session_factory() as session:
                enrolled_user_id = select(User.id).where(User.email == "demo.enrolled@example.test")
                await session.execute(
                    update(InstitutionMembership)
                    .where(InstitutionMembership.user_id == enrolled_user_id.scalar_subquery())
                    .values(role="ADMIN")
                )
                await session.commit()
            second_credentials = await seed_demo(session_factory)

            async with session_factory() as session:
                counts = {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }
                enrolled_role = await session.scalar(
                    select(InstitutionMembership.role)
                    .join(User, User.id == InstitutionMembership.user_id)
                    .where(User.email == "demo.enrolled@example.test")
                )

            assert len(first_credentials) == 4
            assert second_credentials == []
            assert enrolled_role == "STUDENT"
            expected_additions = {
                "institutions": 1,
                "faculties": 1,
                "departments": 1,
                "courses": 2,
                "course_teachers": 2,
                "lessons": 8,
                "exercises": 16,
                "institution_memberships": 3,
                "institution_membership_requests": 1,
                "teachers": 1,
                "students": 1,
                "enrollments": 1,
                "users": 4,
                "posts": 3,
                "post_likes": 3,
                "comments": 3,
                "conversations": 2,
                "conversation_members": 5,
                "messages": 5,
                "notifications": 3,
            }
            actual_additions = {name: counts[name] - before_counts[name] for name in counts}
            assert actual_additions == expected_additions

            demo_user_ids = select(User.id).where(
                User.email.in_(
                    [
                        "demo.admin@example.test",
                        "demo.teacher@example.test",
                        "demo.enrolled@example.test",
                        "demo.invited@example.test",
                    ]
                )
            )
            demo_conversation_ids = select(Conversation.id).where(
                Conversation.created_by_id.in_(demo_user_ids)
            )
            async with session_factory() as session:
                await session.execute(
                    delete(Notification).where(Notification.recipient_id.in_(demo_user_ids))
                )
                await session.execute(
                    delete(Conversation).where(Conversation.id.in_(demo_conversation_ids))
                )
                await session.execute(delete(Post).where(Post.content.startswith("Demo:")))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_reset_demo_passwords_changes_only_existing_demo_accounts(postgres_database_url, monkeypatch):
    from app.cli import reset_demo_passwords
    from app.routes.login import login
    from app.schemas import LoginRequest
    from app.security import password_hash

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        demo_emails = (
            "demo.admin@example.test",
            "demo.teacher@example.test",
            "demo.enrolled@example.test",
            "demo.invited@example.test",
        )
        original_demo: dict[str, tuple[uuid.UUID, str, int]] = {}
        new_demo_ids: list[uuid.UUID] = []
        unrelated_ids: list[uuid.UUID] = []
        monkeypatch.setenv("ME_YOU_ENV", "development")
        try:
            async with session_factory() as session:
                existing_demo = list(
                    (await session.scalars(select(User).where(User.email.in_(demo_emails)))).all()
                )
                for user in existing_demo:
                    original_demo[user.email] = (
                        user.id,
                        user.password_hash,
                        user.token_version,
                    )
                demo_user = next(
                    (user for user in existing_demo if user.email == "demo.teacher@example.test"),
                    None,
                )
                if demo_user is None:
                    demo_user = await create_user(session, email="demo.teacher@example.test")
                    new_demo_ids.append(demo_user.id)
                demo_user.password_hash = password_hash.hash("old-demo-password")
                other_demo_domain = await create_user(
                    session, email=f"unrelated-{uuid.uuid4().hex}@example.test"
                )
                outside_demo_domain = await create_user(
                    session, email=f"unrelated-{uuid.uuid4().hex}@example.com"
                )
                unrelated_ids.extend([other_demo_domain.id, outside_demo_domain.id])
                other_demo_domain.password_hash = password_hash.hash("keep-example-password")
                outside_demo_domain.password_hash = password_hash.hash("keep-com-password")
                initial_versions = {
                    demo_user.id: demo_user.token_version,
                    other_demo_domain.id: other_demo_domain.token_version,
                    outside_demo_domain.id: outside_demo_domain.token_version,
                }
                await session.commit()
                demo_user_id = demo_user.id
                other_demo_id = other_demo_domain.id
                outside_demo_id = outside_demo_domain.id
                baseline_demo = {
                    user.email: (user.id, user.password_hash, user.token_version)
                    for user in existing_demo
                }
                baseline_demo[demo_user.email] = (
                    demo_user.id,
                    demo_user.password_hash,
                    demo_user.token_version,
                )

            credentials, missing = await reset_demo_passwords(session_factory)
            expected_emails = set(baseline_demo)
            expected_missing = [email for email in demo_emails if email not in expected_emails]
            assert missing == expected_missing
            assert {email for _, email, _ in credentials} == expected_emails
            new_password = next(
                password for _, email, password in credentials
                if email == "demo.teacher@example.test"
            )
            async with session_factory() as session:
                demo_user = await session.get(User, demo_user_id)
                other_demo_domain = await session.get(User, other_demo_id)
                outside_demo_domain = await session.get(User, outside_demo_id)
                assert demo_user.token_version == initial_versions[demo_user_id] + 1
                assert password_hash.verify(new_password, demo_user.password_hash)
                assert not password_hash.verify("old-demo-password", demo_user.password_hash)
                assert other_demo_domain.token_version == initial_versions[other_demo_id]
                assert password_hash.verify("keep-example-password", other_demo_domain.password_hash)
                assert outside_demo_domain.token_version == initial_versions[outside_demo_id]
                assert password_hash.verify("keep-com-password", outside_demo_domain.password_hash)
                for email, (account_id, original_hash, original_version) in baseline_demo.items():
                    account = await session.get(User, account_id)
                    assert account.token_version == original_version + 1
                    if email == "demo.teacher@example.test":
                        assert not password_hash.verify("old-demo-password", account.password_hash)
                    else:
                        assert account.password_hash != original_hash
                with pytest.raises(HTTPException) as old_password:
                    await login(
                        LoginRequest(email=demo_user.email, password="old-demo-password"),
                        session,
                    )
                assert old_password.value.status_code == 401
                response = await login(
                    LoginRequest(email=demo_user.email, password=new_password),
                    session,
                )
                assert response["id"] == str(demo_user_id)
        finally:
            async with session_factory() as session:
                for account_id, original_hash, original_version in original_demo.values():
                    account = await session.get(User, account_id)
                    if account is not None:
                        account.password_hash = original_hash
                        account.token_version = original_version
                remove_ids = new_demo_ids + unrelated_ids
                if remove_ids:
                    await session.execute(delete(User).where(User.id.in_(remove_ids)))
                if original_demo or remove_ids:
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_database_rejects_duplicate_exercise_submission_number(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            _, _, course, student = await create_learning_records(session)
            lesson = Lesson(course_id=course.id, title="Lesson", content="Content")
            session.add(lesson)
            await session.flush()
            exercise = Exercise(lesson_id=lesson.id, title="Exercise", instructions="Complete", exercise_type="WRITTEN")
            session.add(exercise)
            await session.flush()
            first = ExerciseSubmission(
                exercise_id=exercise.id,
                student_id=student.id,
                attempt_number=1,
                answer_text="First answer",
            )
            session.add(first)
            await session.commit()

            session.add(
                ExerciseSubmission(
                    exercise_id=exercise.id,
                    student_id=student.id,
                    attempt_number=1,
                    answer_text="Duplicate answer",
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()

    asyncio.run(verify())


def test_database_rejects_duplicate_course_enrollment(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            _, _, course, student = await create_learning_records(session)
            session.add(Enrollment(student_id=student.id, course_id=course.id))
            await session.commit()

            session.add(Enrollment(student_id=student.id, course_id=course.id))
            with pytest.raises(IntegrityError):
                await session.flush()

    asyncio.run(verify())


def test_revoked_student_membership_denies_course_access(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            _, institution, course, student = await create_learning_records(session)
            membership = InstitutionMembership(
                user_id=student.user_id,
                institution_id=institution.id,
                role="STUDENT",
            )
            session.add_all(
                [membership, Enrollment(student_id=student.id, course_id=course.id)]
            )
            await session.commit()
            await session.delete(membership)
            await session.commit()

            with pytest.raises(HTTPException) as error:
                await require_enrolled_student(course.id, student.user_id, session)
            assert error.value.status_code == 403
            assert error.value.detail == "Course enrollment required"

    asyncio.run(verify())


def test_revoked_teacher_membership_denies_course_access(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            user, institution, course, _ = await create_learning_records(session)
            teacher = Teacher(user_id=user.id, institution_id=institution.id)
            membership = InstitutionMembership(
                user_id=user.id,
                institution_id=institution.id,
                role="TEACHER",
            )
            session.add_all([teacher, membership])
            await session.flush()
            session.add(CourseTeacher(course_id=course.id, teacher_id=teacher.id))
            await session.commit()
            await session.delete(membership)
            await session.commit()

            with pytest.raises(HTTPException) as error:
                await require_course_teacher(course.id, user.id, session)
            assert error.value.status_code == 403
            assert error.value.detail == "Assigned teacher access required"

    asyncio.run(verify())


def test_foreign_keys_and_delete_cascades_for_users_and_institutions(postgres_database_url):
    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session)
            institution = await create_institution(session)
            user_membership = InstitutionMembership(user_id=user.id, institution_id=institution.id, role="STUDENT")
            session.add(user_membership)
            await session.commit()
            user_id = user.id
            user_membership_id = user_membership.id
            institution_id = institution.id

            session.add(
                InstitutionMembership(
                    user_id=uuid.uuid4(), institution_id=institution_id, role="STUDENT"
                )
            )
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

            await session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
            await session.commit()
            assert await session.scalar(
                select(func.count()).select_from(InstitutionMembership).where(
                    InstitutionMembership.id == user_membership_id
                )
            ) == 0

            institution_user = await create_user(session)
            institution_to_delete = await create_institution(session)
            institution_membership = InstitutionMembership(
                user_id=institution_user.id,
                institution_id=institution_to_delete.id,
                role="ADMIN",
            )
            session.add(institution_membership)
            await session.commit()
            institution_to_delete_id = institution_to_delete.id
            institution_membership_id = institution_membership.id

            await session.execute(
                text("DELETE FROM institutions WHERE id = :institution_id"),
                {"institution_id": institution_to_delete_id},
            )
            await session.commit()
            assert await session.scalar(
                select(func.count()).select_from(InstitutionMembership).where(
                    InstitutionMembership.id == institution_membership_id
                )
            ) == 0

    asyncio.run(verify())


def test_concurrent_admin_demotions_preserve_final_administrator(postgres_database_url):
    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        original_require_admin = institution_routes.require_institution_admin
        try:
            async with session_factory() as session:
                institution = await create_institution(session)
                administrators = [await create_user(session), await create_user(session)]
                memberships = [
                    InstitutionMembership(user_id=user.id, institution_id=institution.id, role="ADMIN")
                    for user in administrators
                ]
                session.add_all(memberships)
                await session.commit()

            users_by_id = {user.id: user for user in administrators}

            async def test_database_dependency():
                async with session_factory() as session:
                    yield session

            async def test_user_dependency(request: Request):
                return users_by_id[uuid.UUID(request.headers["x-test-user"])]

            barrier = None

            async def synchronized_admin_check(user_id, institution_id, database):
                membership = await original_require_admin(user_id, institution_id, database)
                await barrier.wait()
                return membership

            app.dependency_overrides[get_postgres_session] = test_database_dependency
            app.dependency_overrides[get_current_postgres_user] = test_user_dependency
            institution_routes.require_institution_admin = synchronized_admin_check
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                for iteration in range(20):
                    async with session_factory() as session:
                        await session.execute(
                            update(InstitutionMembership)
                            .where(InstitutionMembership.institution_id == institution.id)
                            .values(role="ADMIN")
                        )
                        await session.commit()

                    barrier = asyncio.Barrier(2)
                    responses = await asyncio.wait_for(
                        asyncio.gather(
                            client.patch(
                                f"/institutions/{institution.id}/members/{memberships[1].id}",
                                headers={"x-test-user": str(administrators[0].id)},
                                json={"role": "TEACHER"},
                            ),
                            client.patch(
                                f"/institutions/{institution.id}/members/{memberships[0].id}",
                                headers={"x-test-user": str(administrators[1].id)},
                                json={"role": "TEACHER"},
                            ),
                        ),
                        timeout=10,
                    )

                    async with session_factory() as session:
                        persisted_roles = list(
                            (
                                await session.scalars(
                                    select(InstitutionMembership.role)
                                    .where(InstitutionMembership.institution_id == institution.id)
                                    .order_by(InstitutionMembership.id)
                                )
                            ).all()
                        )
                        active_admin_count = await session.scalar(
                            select(func.count())
                            .select_from(InstitutionMembership)
                            .join(User, User.id == InstitutionMembership.user_id)
                            .where(
                                InstitutionMembership.institution_id == institution.id,
                                InstitutionMembership.role == "ADMIN",
                                User.is_active.is_(True),
                            )
                        )
                    status_codes = sorted(response.status_code for response in responses)
                    assert status_codes == [200, 409], (
                        f"Race {iteration + 1}: responses were "
                        f"{[(response.status_code, response.json()) for response in responses]}"
                    )
                    success = next(response for response in responses if response.status_code == 200)
                    conflict = next(response for response in responses if response.status_code == 409)
                    assert success.json()["role"] == "TEACHER"
                    assert conflict.json()["detail"] == "Final administrator cannot be demoted"
                    assert active_admin_count == 1, (
                        f"Race {iteration + 1}: persisted roles were {persisted_roles}"
                    )
        finally:
            institution_routes.require_institution_admin = original_require_admin
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_active_admin_cannot_demote_remove_or_deactivate_with_inactive_coadmin(postgres_database_url):
    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        try:
            async with session_factory() as session:
                institution = await create_institution(session)
                active_admin = await create_user(session)
                inactive_admin = await create_user(session)
                inactive_admin.is_active = False
                active_membership = InstitutionMembership(
                    user_id=active_admin.id,
                    institution_id=institution.id,
                    role="ADMIN",
                )
                session.add_all(
                    [
                        active_membership,
                        InstitutionMembership(
                            user_id=inactive_admin.id,
                            institution_id=institution.id,
                            role="ADMIN",
                        ),
                    ]
                )
                await session.commit()

            async def test_database_dependency():
                async with session_factory() as session:
                    yield session

            async def test_user_dependency():
                return active_admin

            app.dependency_overrides[get_postgres_session] = test_database_dependency
            app.dependency_overrides[get_current_postgres_user] = test_user_dependency
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                demotion = await client.patch(
                    f"/institutions/{institution.id}/members/{active_membership.id}",
                    json={"role": "TEACHER"},
                )
                removal = await client.delete(
                    f"/institutions/{institution.id}/members/{active_membership.id}"
                )

            assert demotion.status_code == 409
            assert demotion.json()["detail"] == "Final administrator cannot be demoted"
            assert removal.status_code == 409
            assert removal.json()["detail"] == "Final administrator cannot be removed"

            async with session_factory() as session:
                with pytest.raises(HTTPException) as error:
                    await ensure_account_can_be_deactivated(
                        active_admin.id,
                        session,
                        is_platform_admin=False,
                    )
                assert error.value.status_code == 409
                assert error.value.detail == "Transfer institution administration before deactivating this account"
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_z_migration_upgrade_downgrade_round_trip(postgres_database_url):
    downgrade = _alembic(postgres_database_url, "downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    upgrade = _alembic(postgres_database_url, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr


def test_rate_limit_counter_counts_fifty_concurrent_requests_exactly(postgres_database_url):
    from app.models import RateLimitCounter
    from app.rate_limit import PostgresRateLimitStore, hash_rate_limit_key

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = PostgresRateLimitStore(session_factory)
        try:
            counts = await asyncio.gather(
                *(
                    store.increment("concurrency-test", "one-unique-key", 3600)
                    for _ in range(50)
                )
            )
            assert sorted(count for count, _ in counts) == list(range(1, 51))
            async with session_factory() as session:
                rows = list(
                    (
                        await session.scalars(
                            select(RateLimitCounter).where(
                                RateLimitCounter.scope == "concurrency-test",
                                RateLimitCounter.key_hash
                                == hash_rate_limit_key("one-unique-key"),
                            )
                        )
                    ).all()
                )
                assert len(rows) == 1
                assert rows[0].count == 50
                assert rows[0].key_hash == hash_rate_limit_key("one-unique-key")
                assert rows[0].key_hash != "one-unique-key"
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_login_pair_throttle_is_ip_scoped_and_returns_retry_after(postgres_database_url):
    from app.rate_limit import PostgresRateLimitStore
    from app.routes.login import login
    from app.schemas import LoginRequest

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = PostgresRateLimitStore(session_factory)

        def request_for(ip_address):
            return Request(
                {
                    "type": "http",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/login",
                    "raw_path": b"/login",
                    "query_string": b"",
                    "headers": [],
                    "client": (ip_address, 1234),
                    "server": ("test", 80),
                }
            )

        try:
            for attempt in range(5):
                async with session_factory() as session:
                    try:
                        await login(
                            LoginRequest(email="absent@example.com", password="wrong-password"),
                            session,
                            store,
                            request_for("192.0.2.11"),
                        )
                    except HTTPException as error:
                        if attempt < 4:
                            assert error.status_code == 401
                        else:
                            assert error.status_code == 429
                            assert 1 <= int(error.headers["Retry-After"]) <= 900
                    else:
                        pytest.fail("Invalid login unexpectedly succeeded")

            async with session_factory() as session:
                with pytest.raises(HTTPException) as other_ip_error:
                    await login(
                        LoginRequest(email="absent@example.com", password="wrong-password"),
                        session,
                        store,
                        request_for("192.0.2.12"),
                    )
                assert other_ip_error.value.status_code == 401
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_registration_duplicate_fields_return_identical_conflicts(postgres_database_url):
    from app.routes.registration import register
    from app.schemas import UserCreate

    async def verify():
        async with database_session(postgres_database_url) as session:
            existing = await create_user(
                session,
                username="same-username",
                email="same-email@example.com",
            )
            await session.commit()
            existing_username = existing.username
            existing_email = existing.email

        errors = []
        for username, email in (
            (existing_username, "different@example.com"),
            ("different-username", existing_email),
        ):
            async with database_session(postgres_database_url) as session:
                with pytest.raises(HTTPException) as conflict:
                    await register(
                        UserCreate(
                            username=username,
                            email=email,
                            password="valid-registration-password",
                        ),
                        session,
                    )
                errors.append((conflict.value.status_code, conflict.value.detail))
        assert errors[0] == errors[1] == (400, "Username or email already exists")

    asyncio.run(verify())


def test_reports_blocks_direct_message_denial_and_admin_moderation(postgres_database_url):
    from app.models import Conversation, ConversationMember, Notification, Post
    from app.notification_preferences import add_notification
    from app.rate_limit import PostgresRateLimitStore, get_rate_limit_store
    from app.security import get_optional_postgres_user
    from app.security import password_hash

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        identities: dict[str, uuid.UUID] = {}
        try:
            async with session_factory() as session:
                reporter = await create_user(session)
                blocked_user = await create_user(session)
                blocked_user.password_hash = password_hash.hash("valid-test-password")
                blocked_email = blocked_user.email
                admin = await create_user(session)
                admin.is_platform_admin = True
                reporter_post = Post(author_id=reporter.id, content="My public post", visibility="PUBLIC")
                target_post = Post(author_id=blocked_user.id, content="Reported public post", visibility="PUBLIC")
                session.add_all([reporter_post, target_post])
                await session.flush()
                conversation = Conversation(
                    type="DIRECT",
                    direct_key=":".join(sorted((str(reporter.id), str(blocked_user.id)))),
                    created_by_id=reporter.id,
                )
                session.add(conversation)
                await session.flush()
                session.add_all([
                    ConversationMember(conversation_id=conversation.id, user_id=reporter.id),
                    ConversationMember(conversation_id=conversation.id, user_id=blocked_user.id),
                ])
                await session.commit()
                identities.update({
                    "reporter": reporter.id,
                    "blocked": blocked_user.id,
                    "admin": admin.id,
                })
                target_post_id = target_post.id
                reporter_post_id = reporter_post.id
                conversation_id = conversation.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency(request: Request):
                async with session_factory() as session:
                    return await session.get(User, uuid.UUID(request.headers["x-test-user"]))

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            app.dependency_overrides[get_optional_postgres_user] = user_dependency
            app.dependency_overrides[get_rate_limit_store] = lambda: PostgresRateLimitStore(session_factory)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                reporter_headers = {"x-test-user": str(identities["reporter"])}
                blocked_headers = {"x-test-user": str(identities["blocked"])}
                admin_headers = {"x-test-user": str(identities["admin"])}

                report_payload = {
                    "target_type": "POST",
                    "target_id": str(target_post_id),
                    "reason": "SPAM",
                    "details": "Repeated spam",
                }
                created_report = await client.post("/reports", json=report_payload, headers=reporter_headers)
                assert created_report.status_code == 201
                assert (await client.post("/reports", json=report_payload, headers=reporter_headers)).status_code == 409
                self_report = await client.post(
                    "/reports",
                    json={**report_payload, "target_id": str(reporter_post_id)},
                    headers=reporter_headers,
                )
                assert self_report.status_code == 400
                assert (await client.get("/admin/reports", headers=reporter_headers)).status_code == 403
                assert (await client.get("/admin/reports", headers=admin_headers)).status_code == 200

                assert (await client.get(f"/posts/{target_post_id}", headers=reporter_headers)).status_code == 200
                assert (await client.post(f"/users/{identities['blocked']}/block", headers=reporter_headers)).status_code == 200
                assert (await client.get(f"/posts/{target_post_id}", headers=reporter_headers)).status_code == 404
                assert (await client.get(f"/posts/{reporter_post_id}", headers=blocked_headers)).status_code == 404
                assert (await client.post(
                    f"/conversations/{conversation_id}/messages",
                    json={"content": "blocked message"},
                    headers=reporter_headers,
                )).status_code == 404
                assert (await client.post(
                    f"/conversations/{conversation_id}/messages",
                    json={"content": "blocked reply"},
                    headers=blocked_headers,
                )).status_code == 404
                blocked_direct = await client.post(
                    "/conversations/direct",
                    json={"target_user_id": str(identities["reporter"])},
                    headers=blocked_headers,
                )
                nonexistent_direct = await client.post(
                    "/conversations/direct",
                    json={"target_user_id": str(uuid.uuid4())},
                    headers=blocked_headers,
                )
                assert blocked_direct.status_code == nonexistent_direct.status_code == 404
                assert blocked_direct.json()["detail"] == nonexistent_direct.json()["detail"]
                assert (await client.get("/blocks", headers=reporter_headers)).json()[0]["id"] == str(identities["blocked"])

                async with session_factory() as session:
                    assert await add_notification(
                        session,
                        Notification(
                            recipient_id=identities["blocked"],
                            actor_id=identities["reporter"],
                            type="MESSAGE",
                            title="Blocked pair notification",
                        ),
                    ) is False
                    assert await session.scalar(
                        select(func.count(Notification.id)).where(
                            Notification.recipient_id == identities["blocked"],
                            Notification.title == "Blocked pair notification",
                        )
                    ) == 0

                assert (await client.delete(
                    f"/users/{identities['blocked']}/block", headers=reporter_headers
                )).status_code == 200
                hidden = await client.patch(
                    f"/admin/content/POST/{target_post_id}?hidden=true", headers=admin_headers
                )
                assert hidden.status_code == 200
                assert (await client.get(f"/posts/{target_post_id}", headers=reporter_headers)).status_code == 404
                assert (await client.get(f"/posts/{target_post_id}", headers=admin_headers)).status_code == 200
                suspended = await client.post(
                    f"/admin/users/{identities['blocked']}/suspend", headers=admin_headers
                )
                assert suspended.status_code == 200
                denied_login = await client.post(
                    "/login",
                    json={"email": blocked_email, "password": "valid-test-password"},
                )
                assert denied_login.status_code == 401
                assert denied_login.json()["detail"] == "Invalid email or password"
                unsuspended = await client.post(
                    f"/admin/users/{identities['blocked']}/unsuspend", headers=admin_headers
                )
                assert unsuspended.status_code == 200
                reviewed = await client.patch(
                    f"/admin/reports/{created_report.json()['id']}",
                    json={"status": "ACTIONED"},
                    headers=admin_headers,
                )
                assert reviewed.status_code == 200
                async with session_factory() as session:
                    assert await session.scalar(
                        select(func.count(SecurityEvent.id)).where(
                            SecurityEvent.event_type == "moderation.report_status_changed",
                            SecurityEvent.actor_user_id == identities["admin"],
                        )
                    ) == 1
                unhidden = await client.patch(
                    f"/admin/content/POST/{target_post_id}?hidden=false", headers=admin_headers
                )
                assert unhidden.status_code == 200
                assert (await client.get(f"/posts/{target_post_id}", headers=reporter_headers)).status_code == 200
                assert (await client.get(f"/posts/{target_post_id}", headers=admin_headers)).status_code == 200
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            async with session_factory() as session:
                if identities:
                    await session.execute(
                        delete(User).where(User.id.in_(list(identities.values()))),
                    )
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_moderation_migration_up_and_down(postgres_database_url):
    base_url = make_url(postgres_database_url)
    database_name = f"me_you_moderation_migration_{uuid.uuid4().hex}"
    migration_url = base_url.set(database=database_name).render_as_string(hide_password=False)
    admin_connect = {
        "user": base_url.username,
        "password": base_url.password,
        "host": base_url.host,
        "port": base_url.port or 5432,
        "database": "postgres",
    }

    async def run_migrations():
        connection = await asyncpg.connect(**admin_connect)
        try:
            await connection.execute(f'CREATE DATABASE "{database_name}"')
        finally:
            await connection.close()
        engine = create_async_engine(migration_url)
        try:
            assert _alembic(migration_url, "upgrade", "0024_notification_preferences").returncode == 0
            assert _alembic(migration_url, "upgrade", "head").returncode == 0
            async with engine.connect() as connection:
                found = await connection.scalar(text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
                    "AND table_name IN ('reports', 'user_blocks')"
                ))
                assert found == 2
                hidden_columns = await connection.scalar(text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND column_name = 'is_hidden' AND table_name IN ('posts', 'comments')"
                ))
                assert hidden_columns == 2
            assert _alembic(migration_url, "downgrade", "0024_notification_preferences").returncode == 0
            async with engine.connect() as connection:
                found = await connection.scalar(text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
                    "AND table_name IN ('reports', 'user_blocks')"
                ))
                assert found == 0
                hidden_columns = await connection.scalar(text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND column_name = 'is_hidden' AND table_name IN ('posts', 'comments')"
                ))
                assert hidden_columns == 0
        finally:
            await engine.dispose()
            connection = await asyncpg.connect(**admin_connect)
            try:
                await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
            finally:
                await connection.close()

    asyncio.run(run_migrations())


def test_social_search_escapes_wildcards_and_respects_visibility(postgres_database_url):
    from app.models import Post, Profile, UserBlock
    from app.rate_limit import PostgresRateLimitStore, get_rate_limit_store

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        user_ids: list[uuid.UUID] = []
        institution_ids: list[uuid.UUID] = []
        try:
            async with session_factory() as session:
                viewer = await create_user(session)
                user_ids.append(viewer.id)
                literal_user = await create_user(session, username="river%person")
                wildcard_user = await create_user(session, username="riverXperson")
                blocked_user = await create_user(session, username="blockquery-person")
                user_ids.extend([literal_user.id, wildcard_user.id, blocked_user.id])
                session.add_all([
                    Profile(user_id=literal_user.id, display_name="River percent person", visibility="PUBLIC"),
                    Profile(user_id=wildcard_user.id, display_name="River x person", visibility="PUBLIC"),
                    Profile(user_id=blocked_user.id, display_name="Blockquery person", visibility="PUBLIC"),
                    Profile(user_id=viewer.id, display_name="Search viewer", visibility="PUBLIC"),
                ])
                session.add(UserBlock(blocker_id=viewer.id, blocked_id=blocked_user.id))
                listed_school = await create_institution(session, name="Campus-token Listed")
                unlisted_school = await create_institution(session, name="Campus-token Hidden")
                listed_school.is_listed = True
                institution_ids.extend([listed_school.id, unlisted_school.id])
                visible_post = Post(author_id=literal_user.id, content="reelquery visible content", visibility="PUBLIC")
                hidden_post = Post(author_id=literal_user.id, content="reelquery hidden content", visibility="PUBLIC", is_hidden=True)
                session.add_all([visible_post, hidden_post])
                await session.commit()
                viewer_id = viewer.id
                listed_school_id = listed_school.id
                visible_post_id = visible_post.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency(request: Request):
                async with session_factory() as session:
                    return await session.get(User, uuid.UUID(request.headers["x-test-user"]))

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            app.dependency_overrides[get_rate_limit_store] = lambda: PostgresRateLimitStore(session_factory)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                headers = {"x-test-user": str(viewer_id)}
                literal_result = await client.get("/search", params={"query": "river%person"}, headers=headers)
                assert literal_result.status_code == 200
                assert [item["id"] for item in literal_result.json()["items"] if item["resource_type"] == "person"] == [str(literal_user.id)]
                schools = await client.get("/search", params={"query": "campus-token"}, headers=headers)
                assert [item["id"] for item in schools.json()["items"] if item["resource_type"] == "school"] == [str(listed_school_id)]
                posts = await client.get("/search", params={"query": "reelquery"}, headers=headers)
                post_ids = [item["id"] for item in posts.json()["items"] if item["resource_type"] == "post"]
                assert post_ids == [str(visible_post_id)]
                blocked = await client.get("/search", params={"query": "blockquery"}, headers=headers)
                assert not any(item["resource_type"] == "person" for item in blocked.json()["items"])
                first_page = await client.get("/search", params={"query": "river", "limit": 1}, headers=headers)
                assert first_page.status_code == 200
                assert first_page.json()["has_more"] is True
                second_page = await client.get("/search", params={"query": "river", "limit": 1, "offset": 1}, headers=headers)
                assert second_page.status_code == 200
                assert first_page.json()["items"][0]["id"] != second_page.json()["items"][0]["id"]
                assert (await client.get("/search", params={"query": " "}, headers=headers)).status_code == 422
                assert (await client.get("/search", params={"query": "x" * 101}, headers=headers)).status_code == 422
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            async with session_factory() as session:
                if user_ids:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                if institution_ids:
                    await session.execute(delete(Institution).where(Institution.id.in_(institution_ids)))
                await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_auth_security_events_persist_without_secrets(postgres_database_url):
    import json

    from app.models import SecurityEvent
    from app.rate_limit import PostgresRateLimitStore
    from app.routes.login import login
    from app.routes.registration import register
    from app.schemas import LoginRequest, UserCreate
    from app.security import password_hash

    class TestLimiter:
        def __init__(self, counts):
            self.counts = iter(counts)

        async def increment(self, _scope, _key, _window_seconds):
            return next(self.counts), 800

        async def clear(self, _scope, _key):
            return None

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/login",
                "raw_path": b"/login",
                "query_string": b"",
                "headers": [(b"user-agent", b"audit-test-agent" * 30)],
                "client": ("192.0.2.30", 1234),
                "server": ("test", 80),
            }
        )
        correct_password = "correct-audit-test-password"
        wrong_password = "wrong-audit-test-password"
        try:
            async with session_factory() as session:
                user = await register(
                    UserCreate(
                        username=f"audit-{uuid.uuid4().hex[:12]}",
                        email=f"audit-{uuid.uuid4().hex}@example.com",
                        password=correct_password,
                    ),
                    session,
                    request,
                )
            async with session_factory() as session:
                with pytest.raises(HTTPException) as invalid_login:
                    await login(
                        LoginRequest(email=user["email"], password=wrong_password),
                        session,
                        TestLimiter([1, 1, 1]),
                        request,
                    )
                assert invalid_login.value.status_code == 401

            async with session_factory() as session:
                logged_in = await login(
                    LoginRequest(email=user["email"], password=correct_password),
                    session,
                    TestLimiter([1]),
                    request,
                )
                assert logged_in["access_token"]

            async with session_factory() as session:
                with pytest.raises(HTTPException) as throttled:
                    await login(
                        LoginRequest(email="unknown-audit@example.com", password=wrong_password),
                        session,
                        TestLimiter([31]),
                        request,
                    )
                assert throttled.value.status_code == 429
                assert throttled.value.headers["Retry-After"] == "800"

            async with session_factory() as session:
                events = list(
                    (
                        await session.scalars(
                            select(SecurityEvent)
                        )
                    ).all()
                )
                event_types = {event.event_type for event in events}
                assert {
                    "account.registered",
                    "auth.login_failure",
                    "auth.login_success",
                    "auth.login_throttled",
                }.issubset(event_types)
                assert all(len(event.user_agent) <= 200 for event in events if event.user_agent)
                details_text = json.dumps([event.details for event in events])
                for secret in (correct_password, wrong_password, logged_in["access_token"]):
                    assert secret not in details_text
                assert all(event.details == {} for event in events), [
                    (event.event_type, event.details)
                    for event in events
                    if event.details != {}
                ]
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_security_events_are_scoped_to_institution_admin(postgres_database_url):
    from app.models import SecurityEvent

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        active_user = {"value": None}
        try:
            async with session_factory() as session:
                institution_a = await create_institution(session)
                institution_b = await create_institution(session)
                admin_a = await create_user(session)
                admin_b = await create_user(session)
                platform_admin = await create_user(session)
                platform_admin.is_platform_admin = True
                session.add_all(
                    [
                        InstitutionMembership(
                            user_id=admin_a.id,
                            institution_id=institution_a.id,
                            role="ADMIN",
                        ),
                        InstitutionMembership(
                            user_id=admin_b.id,
                            institution_id=institution_b.id,
                            role="ADMIN",
                        ),
                        SecurityEvent(
                            id=uuid.UUID(int=1),
                            event_type="test.institution_a",
                            outcome="SUCCESS",
                            institution_id=institution_a.id,
                            details={},
                        ),
                        SecurityEvent(
                            id=uuid.UUID(int=2),
                            event_type="test.institution_a_second",
                            outcome="SUCCESS",
                            institution_id=institution_a.id,
                            details={},
                        ),
                        SecurityEvent(
                            id=uuid.UUID(int=3),
                            event_type="test.institution_b",
                            outcome="SUCCESS",
                            institution_id=institution_b.id,
                            details={},
                        ),
                    ]
                )
                await session.commit()

            async def test_database_dependency():
                async with session_factory() as session:
                    yield session

            async def test_user_dependency():
                return active_user["value"]

            app.dependency_overrides[get_postgres_session] = test_database_dependency
            app.dependency_overrides[get_current_postgres_user] = test_user_dependency
            active_user["value"] = admin_a
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                page_one = await client.get("/security-events?limit=1")
                assert page_one.status_code == 200
                assert page_one.json()["items"][0]["event_type"] == "test.institution_a_second"
                assert page_one.json()["next_cursor"] == str(uuid.UUID(int=2))

                page_two = await client.get(
                    f"/security-events?limit=1&cursor={page_one.json()['next_cursor']}"
                )
                assert page_two.status_code == 200
                assert page_two.json()["items"][0]["event_type"] == "test.institution_a"

                forbidden = await client.get(
                    f"/security-events?institution_id={institution_b.id}"
                )
                assert forbidden.status_code == 403

                active_user["value"] = platform_admin
                all_events = await client.get("/security-events?event_type=test.institution_b")
                assert all_events.status_code == 200
                assert [item["event_type"] for item in all_events.json()["items"]] == [
                    "test.institution_b"
                ]
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_account_and_institution_mutations_write_security_events(postgres_database_url):
    from types import SimpleNamespace

    from app.models import SecurityEvent
    from app.routes.account import change_my_password, deactivate_account, revoke_account_sessions
    from app.routes.institutions import create_institution, remove_member, update_member_role
    from app.routes.platform_admin import set_account_active
    from app.schemas import PasswordChangeRequest, PasswordConfirmationRequest
    from app.security import password_hash

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/account",
                "raw_path": b"/account",
                "query_string": b"",
                "headers": [(b"user-agent", b"security-event-test")],
                "client": ("192.0.2.45", 1234),
                "server": ("test", 80),
            }
        )
        try:
            async with session_factory() as session:
                account = User(
                    username=f"event-user-{uuid.uuid4().hex[:10]}",
                    email=f"event-user-{uuid.uuid4().hex}@example.com",
                    password_hash=password_hash.hash("initial-account-password"),
                )
                platform_admin = await create_user(session)
                platform_admin.is_platform_admin = True
                session.add(account)
                await session.commit()

                await change_my_password(
                    PasswordChangeRequest(
                        current_password="initial-account-password",
                        new_password="updated-account-password",
                    ),
                    account,
                    session,
                    request,
                )
                await revoke_account_sessions(
                    PasswordConfirmationRequest(current_password="updated-account-password"),
                    account,
                    session,
                    request,
                )
                await deactivate_account(
                    PasswordConfirmationRequest(current_password="updated-account-password"),
                    account,
                    session,
                    request,
                )
                await set_account_active(account.id, True, platform_admin, session, request)

                institution = await create_institution(
                    SimpleNamespace(
                        model_dump=lambda: {
                            "name": f"Audit institution {uuid.uuid4().hex[:8]}",
                            "institution_type": "SCHOOL",
                        }
                    ),
                    account,
                    session,
                    request,
                )
                institution_id = uuid.UUID(institution["id"])

                changed_member = await create_user(session)
                removed_member = await create_user(session)
                membership_to_change = InstitutionMembership(
                    user_id=changed_member.id,
                    institution_id=institution_id,
                    role="STUDENT",
                )
                membership_to_remove = InstitutionMembership(
                    user_id=removed_member.id,
                    institution_id=institution_id,
                    role="TEACHER",
                )
                session.add_all([membership_to_change, membership_to_remove])
                await session.commit()

                await update_member_role(
                    institution_id,
                    membership_to_change.id,
                    {"role": "TEACHER"},
                    account,
                    session,
                    request,
                )
                await remove_member(
                    institution_id,
                    membership_to_remove.id,
                    account,
                    session,
                    request,
                )

            async with session_factory() as session:
                event_types = set(
                    (
                        await session.scalars(
                            select(SecurityEvent.event_type)
                        )
                    ).all()
                )
                assert {
                    "account.password_changed",
                    "account.sessions_revoked",
                    "account.deactivated",
                    "account.reactivated",
                    "institution.created",
                    "institution.membership.role_changed",
                    "institution.membership.removed",
                }.issubset(event_types)
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_security_event_purge_preserves_events_within_retention(postgres_database_url):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch

    from app.models import SecurityEvent
    import app.security_audit as security_audit

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        try:
            async with session_factory() as session:
                session.add_all(
                    [
                        SecurityEvent(
                            event_type="test.old",
                            outcome="SUCCESS",
                            occurred_at=now - timedelta(days=366),
                            details={},
                        ),
                        SecurityEvent(
                            event_type="test.recent",
                            outcome="SUCCESS",
                            occurred_at=now,
                            details={},
                        ),
                    ]
                )
                await session.commit()

            with patch.object(security_audit, "PostgresSessionLocal", session_factory):
                assert await security_audit.purge_expired_security_events() == 1

            async with session_factory() as session:
                event_types = set(
                    (
                        await session.scalars(
                            select(SecurityEvent.event_type).where(
                                SecurityEvent.event_type.in_(
                                    ["test.old", "test.recent"]
                                )
                            )
                        )
                    ).all()
                )
                assert event_types == {"test.recent"}
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_platform_admin_cli_commands_and_last_admin_refusal(postgres_database_url):
    from unittest.mock import patch

    import app.cli as cli
    from app.models import SecurityEvent
    from app.security import password_hash

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                await session.execute(update(User).values(is_platform_admin=False))
                existing_user = await create_user(session)
                await session.commit()
                existing_email = existing_user.email

            with (
                patch("builtins.input", side_effect=[f"bootstrap-{uuid.uuid4().hex}@example.com", "first-admin"]),
                patch("app.cli.getpass", side_effect=["bootstrap-password", "bootstrap-password"]),
            ):
                bootstrap_email = await cli.create_platform_admin(session_factory)

            async with session_factory() as session:
                bootstrap_user = await session.scalar(
                    select(User).where(User.email == bootstrap_email)
                )
                assert bootstrap_user.is_platform_admin is True
                assert password_hash.verify("bootstrap-password", bootstrap_user.password_hash)

            assert await cli.grant_platform_admin(existing_email, session_factory) is True
            assert await cli.grant_platform_admin(existing_email, session_factory) is False
            assert await cli.revoke_platform_admin(existing_email, session_factory) is True
            assert await cli.revoke_platform_admin(existing_email, session_factory) is False

            with patch("builtins.input", side_effect=[existing_email]):
                assert await cli.create_platform_admin(session_factory) == existing_email

            assert await cli.revoke_platform_admin(bootstrap_email, session_factory) is True
            with pytest.raises(ValueError, match="last active platform administrator"):
                await cli.revoke_platform_admin(existing_email, session_factory)

            async with session_factory() as session:
                bootstrap_user = await session.scalar(
                    select(User).where(User.email == bootstrap_email)
                )
                remaining_admin = await session.scalar(
                    select(User).where(User.email == existing_email)
                )
                event_types = list(
                    (await session.scalars(select(SecurityEvent.event_type))).all()
                )
                assert bootstrap_user.is_platform_admin is False
                assert remaining_admin.is_platform_admin is True
                assert "platform.admin.granted" in event_types
                assert "platform.admin.revoked" in event_types
                assert "platform.admin.revoke_denied" in event_types
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_profile_and_post_visibility_modes_are_enforced(postgres_database_url):
    from app.models import Post, Profile
    from app.routes.posts import get_post
    from app.routes.profile import get_user_profile

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                network_viewer = await create_user(session)
                outsider = await create_user(session)
                public_owner = await create_user(session)
                inactive_owner = await create_user(session)
                inactive_owner.is_active = False
                institution = await create_institution(session)
                session.add_all(
                    [
                        InstitutionMembership(
                            user_id=owner.id,
                            institution_id=institution.id,
                            role="STUDENT",
                        ),
                        InstitutionMembership(
                            user_id=network_viewer.id,
                            institution_id=institution.id,
                            role="STUDENT",
                        ),
                        Profile(user_id=owner.id, display_name="Network", visibility="NETWORK"),
                        Profile(user_id=outsider.id, display_name="Private", visibility="PRIVATE"),
                        Profile(user_id=public_owner.id, display_name="Public", visibility="PUBLIC"),
                        Profile(user_id=inactive_owner.id, display_name="Inactive", visibility="PUBLIC"),
                    ]
                )
                public_post = Post(
                    author_id=owner.id,
                    content="public",
                    visibility="PUBLIC",
                )
                authenticated_post = Post(
                    author_id=owner.id,
                    content="authenticated",
                    visibility="AUTHENTICATED",
                )
                network_post = Post(
                    author_id=owner.id,
                    content="network",
                    visibility="NETWORK",
                )
                private_post = Post(
                    author_id=owner.id,
                    content="private",
                    visibility="PRIVATE",
                )
                deactivated_post = Post(
                    author_id=inactive_owner.id,
                    content="hidden after deactivation",
                    visibility="PUBLIC",
                )
                session.add_all(
                    [public_post, authenticated_post, network_post, private_post, deactivated_post]
                )
                await session.commit()
                ids = {
                    "owner": owner.id,
                    "network_viewer": network_viewer.id,
                    "outsider": outsider.id,
                    "public_owner": public_owner.id,
                    "inactive_owner": inactive_owner.id,
                    "public_post": public_post.id,
                    "authenticated_post": authenticated_post.id,
                    "network_post": network_post.id,
                    "private_post": private_post.id,
                    "deactivated_post": deactivated_post.id,
                }

            async with session_factory() as session:
                public_profile = await get_user_profile(
                    ids["public_owner"], None, session
                )
                assert public_profile["visibility"] == "PUBLIC"
                with pytest.raises(HTTPException) as anonymous_network:
                    await get_user_profile(ids["owner"], None, session)
                assert anonymous_network.value.status_code == 404
                owner_user = await session.scalar(
                    select(User).where(User.id == ids["owner"])
                )
                with pytest.raises(HTTPException) as private_profile:
                    await get_user_profile(ids["outsider"], owner_user, session)
                assert private_profile.value.status_code == 404
                outsider_user = await session.scalar(
                    select(User).where(User.id == ids["outsider"])
                )
                private_owner_profile = await get_user_profile(
                    ids["outsider"], outsider_user, session
                )
                assert private_owner_profile["visibility"] == "PRIVATE"
                with pytest.raises(HTTPException) as inactive_profile:
                    await get_user_profile(ids["inactive_owner"], None, session)
                assert inactive_profile.value.status_code == 404
                network_profile = await get_user_profile(
                    ids["owner"],
                    await session.scalar(select(User).where(User.id == ids["network_viewer"])),
                    session,
                )
                assert network_profile["display_name"] == "Network"

                with pytest.raises(HTTPException) as anonymous_authenticated_post:
                    await get_post(ids["authenticated_post"], session, None)
                assert anonymous_authenticated_post.value.status_code == 401
                authenticated_viewer = await session.scalar(
                    select(User).where(User.id == ids["outsider"])
                )
                assert (await get_post(ids["authenticated_post"], session, authenticated_viewer)).visibility == "AUTHENTICATED"
                with pytest.raises(HTTPException) as network_denied:
                    await get_post(ids["network_post"], session, authenticated_viewer)
                assert network_denied.value.status_code == 404
                network_user = await session.scalar(
                    select(User).where(User.id == ids["network_viewer"])
                )
                assert (await get_post(ids["network_post"], session, network_user)).visibility == "NETWORK"
                with pytest.raises(HTTPException) as private_denied:
                    await get_post(ids["private_post"], session, network_user)
                assert private_denied.value.status_code == 404
                owner_user = await session.scalar(select(User).where(User.id == ids["owner"]))
                assert (await get_post(ids["private_post"], session, owner_user)).visibility == "PRIVATE"
                with pytest.raises(HTTPException) as inactive_post:
                    await get_post(ids["deactivated_post"], session, owner_user)
                assert inactive_post.value.status_code == 404
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_feed_query_count_is_bounded_for_twenty_posts(postgres_database_url):
    from sqlalchemy.orm import selectinload

    from app.models import Comment, Post, PostLike
    from app.routes.comments import list_comments
    from app.routes.likes import list_likes
    from app.routes.posts import get_feed

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        statements = []

        def count_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
        try:
            async with session_factory() as session:
                viewer = await create_user(session)
                posts = [
                    Post(author_id=viewer.id, content=f"feed post {index}")
                    for index in range(20)
                ]
                session.add_all(posts)
                await session.flush()
                session.add_all(
                    [
                        value
                        for post in posts
                        for value in (
                            PostLike(post_id=post.id, user_id=viewer.id),
                            Comment(
                                post_id=post.id,
                                author_id=viewer.id,
                                content="one comment",
                            ),
                        )
                    ]
                )
                await session.commit()

                statements.clear()
                legacy_posts = list(
                    (
                        await session.scalars(
                            select(Post)
                            .options(selectinload(Post.author))
                            .where(Post.author_id == viewer.id)
                            .order_by(Post.created_at.desc(), Post.id.desc())
                            .limit(21)
                        )
                    ).all()
                )
                for post in legacy_posts:
                    await list_likes(post.id, viewer, session, limit=100)
                    await list_comments(post.id, viewer, session, limit=100)
                legacy_query_count = len(statements)

                statements.clear()
                one_post_page = await get_feed(viewer, session, offset=0, limit=1)
                one_post_query_count = len(statements)
                statements.clear()
                twenty_post_page = await get_feed(viewer, session, offset=0, limit=20)
                twenty_post_query_count = len(statements)

                assert len(one_post_page["items"]) == 1
                assert len(twenty_post_page["items"]) == 20
                assert legacy_query_count == 142
                assert one_post_query_count == twenty_post_query_count == 5
                assert twenty_post_query_count <= 5
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
            await engine.dispose()

    asyncio.run(verify())


def test_private_profile_avatar_is_not_in_post_author_summary(postgres_database_url):
    from app.models import Post, Profile
    from app.routes.posts import get_post_by_id

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                author = await create_user(session)
                viewer = await create_user(session)
                session.add(
                    Profile(
                        user_id=author.id,
                        display_name="Hidden name",
                        profile_picture_url="https://private.example/avatar.png",
                        visibility="PRIVATE",
                    )
                )
                post = Post(author_id=author.id, content="public post", visibility="PUBLIC")
                session.add(post)
                await session.commit()

                response = await get_post_by_id(post.id, viewer, session)

                assert response["author"]["avatar_url"] is None
                assert response["author"]["display_name"] == author.username
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_institution_join_and_invitation_lifecycle_and_approval_race(postgres_database_url):
    from app.routes.institutions import (
        accept_institution_invitation,
        approve_institution_join_request,
        create_membership_join_request,
        invite_institution_member,
    )
    from app.schemas import InstitutionInvitationCreate

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                institution = await create_institution(session)
                admin = await create_user(session)
                joiner = await create_user(session)
                invitee = await create_user(session)
                unauthorized = await create_user(session)
                session.add(
                    InstitutionMembership(
                        user_id=admin.id,
                        institution_id=institution.id,
                        role="ADMIN",
                    )
                )
                await session.commit()
                institution_id = institution.id
                admin_id = admin.id
                joiner_id = joiner.id
                invitee_id = invitee.id
                unauthorized_id = unauthorized.id

            async with session_factory() as session:
                joiner = await session.get(User, joiner_id)
                join_request = await create_membership_join_request(
                    institution_id, "STUDENT", joiner, session
                )
                request_id = join_request.id

            async with session_factory() as session:
                assert await session.scalar(
                    select(InstitutionMembership.id).where(
                        InstitutionMembership.user_id == joiner_id,
                        InstitutionMembership.institution_id == institution_id,
                    )
                ) is None
                assert await session.scalar(
                    select(Student.id).where(Student.user_id == joiner_id)
                ) is None
                unauthorized_user = await session.get(User, unauthorized_id)
                with pytest.raises(HTTPException) as denied:
                    await approve_institution_join_request(
                        institution_id, request_id, unauthorized_user, session
                    )
                assert denied.value.status_code == 403
                await session.rollback()

            async def approve_once():
                async with session_factory() as session:
                    admin_user = await session.get(User, admin_id)
                    try:
                        await approve_institution_join_request(
                            institution_id, request_id, admin_user, session
                        )
                        return "APPROVED"
                    except HTTPException as error:
                        return error.status_code

            results = await asyncio.gather(approve_once(), approve_once())
            assert sorted(str(result) for result in results) == ["409", "APPROVED"]

            async with session_factory() as session:
                membership = await session.scalar(
                    select(InstitutionMembership).where(
                        InstitutionMembership.user_id == joiner_id,
                        InstitutionMembership.institution_id == institution_id,
                    )
                )
                student = await session.scalar(select(Student).where(Student.user_id == joiner_id))
                assert membership.role == "STUDENT"
                assert student.institution_id == institution_id

            async with session_factory() as session:
                admin_user = await session.get(User, admin_id)
                invitation = await invite_institution_member(
                    institution_id,
                    InstitutionInvitationCreate(user_id=str(invitee_id), role="TEACHER"),
                    admin_user,
                    session,
                )
                invitation_id = uuid.UUID(invitation["id"])

            async with session_factory() as session:
                invitee_user = await session.get(User, invitee_id)
                activated = await accept_institution_invitation(
                    institution_id, invitation_id, invitee_user, session
                )
                assert activated["role"] == "TEACHER"
                assert await session.scalar(
                    select(Teacher.id).where(Teacher.user_id == invitee_id)
                ) is not None
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_database_rejects_cross_institution_learning_links(postgres_database_url):
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.models import (
        Assessment,
        AssessmentResult,
        AssessmentSubmission,
        CourseTeacher,
        Exercise,
        ExerciseSubmission,
        Lesson,
        LessonProgress,
    )

    async def verify():
        async with database_session(postgres_database_url) as session:
            institution_a = await create_institution(session)
            institution_b = await create_institution(session)
            faculty_a = Faculty(institution_id=institution_a.id, name="Faculty A")
            faculty_b = Faculty(institution_id=institution_b.id, name="Faculty B")
            session.add_all([faculty_a, faculty_b])
            await session.flush()
            department_a = Department(faculty_id=faculty_a.id, name="Department A")
            department_b = Department(faculty_id=faculty_b.id, name="Department B")
            session.add_all([department_a, department_b])
            await session.flush()
            course_a = Course(department_id=department_a.id, code="A101", name="Course A")
            course_b = Course(department_id=department_b.id, code="B101", name="Course B")
            session.add_all([course_a, course_b])
            await session.flush()
            user_a = await create_user(session)
            user_b = await create_user(session)
            student_a = Student(user_id=user_a.id, institution_id=institution_a.id)
            student_b = Student(user_id=user_b.id, institution_id=institution_b.id)
            teacher_a = Teacher(user_id=user_a.id, institution_id=institution_a.id)
            teacher_b = Teacher(user_id=user_b.id, institution_id=institution_b.id)
            lesson_a = Lesson(
                course_id=course_a.id,
                title="Lesson A",
                content="Content",
                position=0,
                is_published=True,
            )
            session.add_all([student_a, student_b, teacher_a, teacher_b, lesson_a])
            await session.flush()
            exercise_a = Exercise(
                lesson_id=lesson_a.id,
                title="Exercise A",
                instructions="Do it",
                position=0,
                exercise_type="WRITTEN",
            )
            assessment_a = Assessment(
                course_id=course_a.id,
                title="Assessment A",
                instructions="Answer",
                max_score=Decimal("10.00"),
                is_published=True,
            )
            session.add_all([exercise_a, assessment_a])
            await session.flush()
            valid_submission = AssessmentSubmission(
                assessment_id=assessment_a.id,
                student_id=student_a.id,
                answer_text="valid answer",
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(valid_submission)
            await session.commit()
            values = {
                "student_a": student_a.id,
                "student_b": student_b.id,
                "teacher_b": teacher_b.id,
                "course_a": course_a.id,
                "course_b": course_b.id,
                "exercise_a": exercise_a.id,
                "lesson_a": lesson_a.id,
                "assessment_a": assessment_a.id,
                "submission": valid_submission.id,
                "institution_b": institution_b.id,
            }

        invalid_rows = [
            Enrollment(student_id=values["student_a"], course_id=values["course_b"]),
            CourseTeacher(course_id=values["course_a"], teacher_id=values["teacher_b"]),
            ExerciseSubmission(
                exercise_id=values["exercise_a"],
                student_id=values["student_b"],
                attempt_number=1,
                answer_text="cross institution",
                submitted_at=datetime.now(timezone.utc),
            ),
            AssessmentSubmission(
                assessment_id=values["assessment_a"],
                student_id=values["student_b"],
                answer_text="cross institution",
                status="SUBMITTED",
                submitted_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            LessonProgress(
                student_id=values["student_b"], lesson_id=values["lesson_a"], completed=True
            ),
            AssessmentResult(submission_id=values["submission"], score=Decimal("11.00")),
        ]
        for invalid_row in invalid_rows:
            async with database_session(postgres_database_url) as session:
                session.add(invalid_row)
                with pytest.raises(IntegrityError):
                    await session.flush()
                await session.rollback()

        async with database_session(postgres_database_url) as session:
            valid_result = AssessmentResult(
                submission_id=values["submission"], score=Decimal("8.00")
            )
            session.add(valid_result)
            await session.commit()
            assessment = await session.get(Assessment, values["assessment_a"])
            assessment.max_score = Decimal("7.00")
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()

    asyncio.run(verify())


def test_migration_downgrade_refuses_message_notification_data(postgres_database_url):
    from app.models import Notification

    async def verify():
        async with database_session(postgres_database_url) as session:
            user = await create_user(session)
            notification = Notification(
                recipient_id=user.id,
                type="MESSAGE",
                title="Message",
            )
            session.add(notification)
            await session.commit()
            notification_id = notification.id

        try:
            downgrade = _alembic(
                postgres_database_url,
                "downgrade",
                "0006_institution_memberships",
            )
            assert downgrade.returncode != 0
            assert "Cannot downgrade platform infrastructure while MESSAGE" in (
                downgrade.stdout + downgrade.stderr
            )

            upgrade = _alembic(postgres_database_url, "upgrade", "head")
            assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
        finally:
            async with database_session(postgres_database_url) as session:
                await session.execute(
                    text("DELETE FROM notifications WHERE id = :notification_id"),
                    {"notification_id": notification_id},
                )
                await session.execute(
                    text("DELETE FROM users WHERE id = :user_id"),
                    {"user_id": user.id},
                )
                await session.commit()

    asyncio.run(verify())


def test_demo_class_sessions_are_idempotent_and_visible(postgres_database_url, monkeypatch):
    from app.cli import seed_demo
    from app.routes.classrooms import (
        list_class_session_attendance,
        list_class_sessions,
    )

    monkeypatch.setenv("ME_YOU_ENV", "development")

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await seed_demo(session_factory)
            await seed_demo(session_factory)
            async with session_factory() as session:
                teacher = await session.scalar(
                    select(User).where(User.email == "demo.teacher@example.test")
                )
                student = await session.scalar(
                    select(User).where(User.email == "demo.enrolled@example.test")
                )
                course = await session.scalar(
                    select(Course).where(Course.code == "FOUND-101")
                )
                teacher_sessions = await list_class_sessions(
                    course.id, teacher, session
                )
                student_sessions = await list_class_sessions(
                    course.id, student, session
                )

                assert len(teacher_sessions) == len(student_sessions) == 2
                assert {value["status"] for value in teacher_sessions} == {
                    "LIVE",
                    "SCHEDULED",
                }
                assert {value["id"] for value in teacher_sessions} == {
                    value["id"] for value in student_sessions
                }
                live_session = next(
                    value for value in teacher_sessions if value["status"] == "LIVE"
                )
                attendance = await list_class_session_attendance(
                    uuid.UUID(live_session["id"]), teacher, session
                )
                assert len(attendance) == 1
                assert attendance[0]["username"] == student.username
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_account_email_token_downgrade_preserves_lifecycle_data(postgres_database_url):
    from datetime import datetime, timedelta, timezone

    from app.models import AccountEmailToken

    async def verify():
        now = datetime.now(timezone.utc)
        async with database_session(postgres_database_url) as session:
            user = await create_user(session)
            user.email_verified_at = now
            user.deleted_at = now
            token = AccountEmailToken(
                user_id=user.id,
                purpose="EMAIL_VERIFICATION",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=now + timedelta(hours=1),
            )
            session.add(token)
            await session.commit()
            user_id = user.id
            token_id = token.id

        downgrade = _alembic(
            postgres_database_url,
            "downgrade",
            "0015_education_integrity",
        )
        assert downgrade.returncode != 0
        assert "Cannot downgrade account email token lifecycle" in (
            downgrade.stdout + downgrade.stderr
        )

        async with database_session(postgres_database_url) as session:
            assert await session.get(AccountEmailToken, token_id) is not None
            user = await session.get(User, user_id)
            assert user.email_verified_at is not None
            assert user.deleted_at is not None
            await session.execute(
                text("DELETE FROM account_email_tokens WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            await session.execute(
                text(
                    "UPDATE users SET email_verified_at = NULL, deleted_at = NULL "
                    "WHERE id = :user_id"
                ),
                {"user_id": user_id},
            )
            await session.commit()

        downgrade = _alembic(
            postgres_database_url,
            "downgrade",
            "0015_education_integrity",
        )
        assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
        upgrade = _alembic(postgres_database_url, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

    asyncio.run(verify())


def test_account_email_tokens_logout_and_anonymizing_deletion(postgres_database_url):
    from datetime import datetime, timedelta, timezone
    import hashlib
    import tempfile
    from urllib.parse import parse_qs, urlparse

    from fastapi.security import HTTPAuthorizationCredentials
    from app.models import AccountEmailToken, Comment, Conversation, Message, Post, Profile, SecurityEvent
    from app.providers import LocalDiskStorageProvider
    from app.providers import ProviderRegistry, ProviderSettings
    from app.routes.account import (
        confirm_email_verification,
        confirm_password_recovery,
        delete_account,
        logout_account,
        request_email_verification,
        request_password_recovery,
    )
    from app.schemas import (
        EmailTokenConfirm,
        PasswordConfirmationRequest,
        PasswordRecoveryConfirm,
        PasswordRecoveryRequest,
    )
    from app.security import create_access_token, get_current_postgres_user, password_hash

    class TestEmailProvider:
        def __init__(self):
            self.sent = []

        async def send(self, message):
            self.sent.append(message)
            return f"message-{len(self.sent)}"

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        media_directory = tempfile.TemporaryDirectory()
        storage = LocalDiskStorageProvider(
            media_directory.name, "account-deletion-storage-signing-key"
        )
        email = TestEmailProvider()
        providers = ProviderRegistry(
            settings=ProviderSettings(email="test-adapter", storage="local"),
            email=email,
            storage=storage,
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/account",
                "raw_path": b"/account",
                "query_string": b"",
                "headers": [(b"user-agent", b"account-lifecycle-test")],
                "client": ("192.0.2.80", 1234),
                "server": ("test", 80),
            }
        )
        original_password = "original-lifecycle-password"
        reset_password = "replacement-lifecycle-password"
        try:
            async with session_factory() as session:
                user = User(
                    username=f"lifecycle-{uuid.uuid4().hex[:10]}",
                    email=f"lifecycle-{uuid.uuid4().hex}@example.com",
                    password_hash=password_hash.hash(original_password),
                )
                session.add(user)
                await session.commit()
                user_id = user.id
                old_token = create_access_token(user.id, token_version=0)
                await request_email_verification(user, session, providers)
                prior_verification_raw = parse_qs(
                    urlparse(email.sent[-1].text_body.split()[-1]).query
                )["token"][0]
                await request_password_recovery(
                    PasswordRecoveryRequest(email=user.email), session, providers
                )
                first_reset_raw = parse_qs(urlparse(email.sent[-1].text_body.split()[-1]).query)["token"][0]
                first_reset_hash = hashlib.sha256(first_reset_raw.encode()).hexdigest()
                first_row = await session.scalar(
                    select(AccountEmailToken).where(AccountEmailToken.token_hash == first_reset_hash)
                )
                assert first_row is not None
                assert first_reset_raw not in first_row.token_hash

                await request_password_recovery(
                    PasswordRecoveryRequest(email=user.email), session, providers
                )
                second_reset_raw = parse_qs(urlparse(email.sent[-1].text_body.split()[-1]).query)["token"][0]
                with pytest.raises(HTTPException) as invalidated_reset:
                    await confirm_password_recovery(
                        PasswordRecoveryConfirm(
                            token=first_reset_raw,
                            new_password=reset_password,
                        ),
                        session,
                        request,
                    )
                assert invalidated_reset.value.status_code == 400
                await session.rollback()

                await confirm_password_recovery(
                    PasswordRecoveryConfirm(
                        token=second_reset_raw,
                        new_password=reset_password,
                    ),
                    session,
                    request,
                )
                with pytest.raises(HTTPException) as invalidated_verification:
                    await confirm_email_verification(
                        EmailTokenConfirm(token=prior_verification_raw), session, request
                    )
                assert invalidated_verification.value.status_code == 400
                await session.rollback()
                with pytest.raises(HTTPException) as replayed_reset:
                    await confirm_password_recovery(
                        PasswordRecoveryConfirm(
                            token=second_reset_raw,
                            new_password=original_password,
                        ),
                        session,
                        request,
                    )
                assert replayed_reset.value.status_code == 400
                await session.rollback()

                current_user = await session.get(User, user_id)
                assert password_hash.verify(reset_password, current_user.password_hash)
                assert current_user.token_version == 1
                await request_email_verification(current_user, session, providers)
                verification_raw = parse_qs(
                    urlparse(email.sent[-1].text_body.split()[-1]).query
                )["token"][0]
                await confirm_email_verification(
                    EmailTokenConfirm(token=verification_raw), session, request
                )
                await logout_account(current_user, session, request)
                assert current_user.token_version == 2

                institution = await create_institution(session)
                student = Student(user_id=user_id, institution_id=institution.id)
                session.add(student)
                profile = Profile(user_id=user_id, display_name="Private name")
                post = Post(author_id=user_id, content="private content")
                session.add_all([profile, post])
                await session.flush()
                comment = Comment(
                    post_id=post.id,
                    author_id=user_id,
                    content="private comment",
                )
                conversation = Conversation(
                    type="DIRECT",
                    direct_key="lifecycle-direct-key",
                    created_by_id=user_id,
                )
                session.add_all([comment, conversation])
                await session.flush()
                message = Message(
                    conversation_id=conversation.id,
                    sender_id=user_id,
                    content="private message",
                )
                avatar_key = f"users/{user_id}/{uuid.uuid4()}"
                avatar_intent = await storage.create_upload_intent(
                    object_key=avatar_key,
                    content_type="image/png",
                    max_bytes=12,
                    expires_in_seconds=60,
                )
                avatar_token = urlparse(avatar_intent.upload_url).path.rsplit("/", 1)[-1]

                async def avatar_chunks():
                    yield b"\x89PNG\r\n\x1a\nxxxx"

                await storage.accept_upload(
                    avatar_token, "image/png", avatar_chunks()
                )
                avatar_asset = MediaAsset(
                    owner_id=user_id,
                    purpose="PROFILE_IMAGE",
                    status="READY",
                    storage_provider="local",
                    storage_key=avatar_key,
                    content_type="image/png",
                    byte_size=12,
                    original_filename="avatar.png",
                    upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
                reel_key = f"users/{user_id}/{uuid.uuid4()}"
                reel_bytes = b"\x00\x00\x00\x18ftypisom0000"
                reel_intent = await storage.create_upload_intent(
                    object_key=reel_key,
                    content_type="video/mp4",
                    max_bytes=len(reel_bytes),
                    expires_in_seconds=60,
                )
                reel_token = urlparse(reel_intent.upload_url).path.rsplit("/", 1)[-1]

                async def reel_chunks():
                    yield reel_bytes

                await storage.accept_upload(reel_token, "video/mp4", reel_chunks())
                reel_asset = MediaAsset(
                    owner_id=user_id,
                    purpose="REEL",
                    status="READY",
                    storage_provider="local",
                    storage_key=reel_key,
                    content_type="video/mp4",
                    byte_size=len(reel_bytes),
                    original_filename="reel.mp4",
                    upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
                session.add_all([message, avatar_asset, reel_asset])
                await session.flush()
                reel_post = Post(
                    author_id=user_id,
                    content="Account deletion removes this Reel too",
                    post_type="REEL",
                    media_asset_id=reel_asset.id,
                )
                session.add(reel_post)
                await session.flush()
                profile.avatar_asset_id = avatar_asset.id
                await session.commit()
                comment_id = comment.id
                post_id = post.id
                message_id = message.id
                reel_post_id = reel_post.id
                institution_id = institution.id

                await delete_account(
                    PasswordConfirmationRequest(current_password=reset_password),
                    current_user,
                    session,
                    request,
                    providers,
                )

                assert current_user.deleted_at is not None
                assert current_user.is_active is False
                assert current_user.email.endswith("@deleted.invalid")
                assert current_user.username.startswith("deleted-")
                with pytest.raises(HTTPException) as revoked:
                    await get_current_postgres_user(
                        HTTPAuthorizationCredentials(
                            scheme="Bearer", credentials=old_token
                        ),
                        session,
                    )
                assert revoked.value.status_code == 401

            async with session_factory() as session:
                assert await session.get(Profile, user_id) is None
                assert await session.get(Post, post_id) is None
                assert await session.get(Post, reel_post_id) is None
                assert await session.get(Comment, comment_id) is None
                message = await session.get(Message, message_id)
                assert message.deleted_at is not None
                assert message.content == "[deleted]"
                retained_student = await session.scalar(
                    select(Student).where(
                        Student.user_id == user_id,
                        Student.institution_id == institution_id,
                    )
                )
                assert retained_student is not None
                assert await storage.inspect_object(avatar_key) is None
                assert await storage.inspect_object(reel_key) is None
                events = list(
                    (
                        await session.scalars(
                            select(SecurityEvent).where(
                                SecurityEvent.target_user_id == user_id
                            )
                        )
                    ).all()
                )
                details_text = str([event.details for event in events])
                assert original_password not in details_text
                assert reset_password not in details_text
                assert second_reset_raw not in details_text
                assert verification_raw not in details_text
        finally:
            await engine.dispose()
            media_directory.cleanup()

    asyncio.run(verify())


def test_comment_cursor_pagination_validates_bounds_and_privacy(postgres_database_url):
    from fastapi import FastAPI

    from app.models import Comment, Post
    from app.routes.comments import router as comments_router
    from app.security import get_optional_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(comments_router)
        ids = {}
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                viewer = await create_user(session)
                network_owner = await create_user(session)
                outsider = await create_user(session)
                institution = await create_institution(session)
                other_institution = await create_institution(session)
                session.add_all(
                    [
                        InstitutionMembership(
                            user_id=owner.id,
                            institution_id=institution.id,
                            role="STUDENT",
                        ),
                        InstitutionMembership(
                            user_id=viewer.id,
                            institution_id=institution.id,
                            role="STUDENT",
                        ),
                        InstitutionMembership(
                            user_id=network_owner.id,
                            institution_id=institution.id,
                            role="STUDENT",
                        ),
                        InstitutionMembership(
                            user_id=outsider.id,
                            institution_id=other_institution.id,
                            role="STUDENT",
                        ),
                    ]
                )
                public_post = Post(author_id=owner.id, content="public", visibility="PUBLIC")
                private_post = Post(author_id=owner.id, content="private", visibility="PRIVATE")
                network_post = Post(author_id=network_owner.id, content="network", visibility="NETWORK")
                authenticated_post = Post(
                    author_id=owner.id, content="authenticated", visibility="AUTHENTICATED"
                )
                empty_post = Post(author_id=owner.id, content="empty", visibility="PUBLIC")
                session.add_all([public_post, private_post, network_post, authenticated_post, empty_post])
                await session.flush()
                session.add_all(
                    [
                        Comment(post_id=public_post.id, author_id=owner.id, content=f"comment {index}")
                        for index in range(3)
                    ]
                )
                await session.commit()
                ids = {
                    "public": public_post.id,
                    "private": private_post.id,
                    "network": network_post.id,
                    "authenticated": authenticated_post.id,
                    "empty": empty_post.id,
                    "viewer": viewer.id,
                    "outsider": outsider.id,
                }

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def optional_user_dependency(request: Request):
                user_id = request.headers.get("x-test-user")
                if user_id is None:
                    return None
                async with session_factory() as session:
                    return await session.get(User, uuid.UUID(user_id))

            test_app.dependency_overrides[get_postgres_session] = database_dependency
            test_app.dependency_overrides[get_optional_postgres_user] = optional_user_dependency
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                first = await client.get(f"/posts/{ids['public']}/comments?limit=1")
                assert first.status_code == 200
                assert len(first.json()) == 1
                cursor = first.headers["x-next-cursor"]

                second = await client.get(
                    f"/posts/{ids['public']}/comments?limit=1&cursor={cursor}"
                )
                assert second.status_code == 200
                assert len(second.json()) == 1
                assert first.json()[0]["id"] != second.json()[0]["id"]
                assert second.headers["x-next-cursor"]

                invalid = await client.get(
                    f"/posts/{ids['public']}/comments?cursor=not-a-cursor"
                )
                assert invalid.status_code == 422
                oversized = await client.get(
                    f"/posts/{ids['public']}/comments?limit=101"
                )
                assert oversized.status_code == 422
                empty = await client.get(f"/posts/{ids['private']}/comments")
                assert empty.status_code == 401
                empty_public = await client.get(
                    f"/posts/{ids['empty']}/comments"
                )
                assert empty_public.status_code == 200
                assert empty_public.json() == []

                private = await client.get(f"/posts/{ids['private']}/comments")
                private = await client.get(
                    f"/posts/{ids['private']}/comments",
                    headers={"x-test-user": str(ids["viewer"])},
                )
                assert private.status_code == 404
                authenticated = await client.get(
                    f"/posts/{ids['authenticated']}/comments"
                )
                assert authenticated.status_code == 401
                network_denied = await client.get(
                    f"/posts/{ids['network']}/comments",
                    headers={"x-test-user": str(ids["outsider"])},
                )
                assert network_denied.status_code == 404
                network_allowed = await client.get(
                    f"/posts/{ids['network']}/comments",
                    headers={"x-test-user": str(ids["viewer"])},
                )
                assert network_allowed.status_code == 200
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_message_cursor_pagination_rechecks_conversation_membership(postgres_database_url):
    from fastapi import FastAPI

    from app.models import Conversation, ConversationMember, Message
    from app.routes.messages import router as messages_router
    from app.security import get_current_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(messages_router)
        selected_user = {"id": None}
        try:
            async with session_factory() as session:
                first_user = await create_user(session)
                other_member = await create_user(session)
                outsider = await create_user(session)
                conversation = Conversation(
                    type="DIRECT",
                    direct_key=":".join(sorted((str(first_user.id), str(other_member.id)))),
                    created_by_id=first_user.id,
                )
                session.add(conversation)
                await session.flush()
                session.add_all(
                    [
                        ConversationMember(
                            conversation_id=conversation.id, user_id=first_user.id
                        ),
                        ConversationMember(
                            conversation_id=conversation.id, user_id=other_member.id
                        ),
                    ]
                )
                messages = [
                    Message(
                        conversation_id=conversation.id,
                        sender_id=first_user.id,
                        content=f"message {index}",
                    )
                    for index in range(3)
                ]
                session.add_all(messages)
                await session.commit()
                conversation_id = conversation.id
                first_user_id = first_user.id
                outsider_id = outsider.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected_user["id"])

            test_app.dependency_overrides[get_postgres_session] = database_dependency
            test_app.dependency_overrides[get_current_postgres_user] = user_dependency
            selected_user["id"] = first_user_id
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                first = await client.get(
                    f"/conversations/{conversation_id}/messages?limit=1"
                )
                assert first.status_code == 200
                cursor = first.headers["x-next-cursor"]
                second = await client.get(
                    f"/conversations/{conversation_id}/messages?limit=1&cursor={cursor}"
                )
                assert second.status_code == 200
                assert second.json()[0]["id"] != first.json()[0]["id"]

                malformed = await client.get(
                    f"/conversations/{conversation_id}/messages?cursor=bad-cursor"
                )
                assert malformed.status_code == 422
                maximum = await client.get(
                    f"/conversations/{conversation_id}/messages?limit=101"
                )
                assert maximum.status_code == 422

                selected_user["id"] = outsider_id
                denied = await client.get(
                    f"/conversations/{conversation_id}/messages?limit=1&cursor={cursor}"
                )
                assert denied.status_code == 403
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_search_cursor_pagination_remains_institution_scoped(postgres_database_url):
    from fastapi import FastAPI

    from app.routes.search import router as search_router
    from app.security import get_current_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(search_router)
        active_user = {"id": None}
        try:
            async with session_factory() as session:
                user = await create_user(session)
                outsider = await create_user(session)
                institution_a = await create_institution(session)
                institution_b = await create_institution(session)
                session.add(
                    InstitutionMembership(
                        user_id=user.id,
                        institution_id=institution_a.id,
                        role="STUDENT",
                    )
                )
                faculty_a = Faculty(institution_id=institution_a.id, name="Science")
                faculty_b = Faculty(institution_id=institution_b.id, name="Science")
                session.add_all([faculty_a, faculty_b])
                await session.flush()
                department_a = Department(faculty_id=faculty_a.id, name="Computing")
                department_b = Department(faculty_id=faculty_b.id, name="Computing")
                session.add_all([department_a, department_b])
                await session.flush()
                visible_courses = [
                    Course(department_id=department_a.id, code=f"AL{index}", name=f"Alpha {index}")
                    for index in range(3)
                ]
                hidden_course = Course(
                    department_id=department_b.id, code="ALHIDDEN", name="Alpha hidden"
                )
                session.add_all([*visible_courses, hidden_course])
                await session.commit()
                active_user["id"] = user.id
                outsider_id = outsider.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, active_user["id"])

            test_app.dependency_overrides[get_postgres_session] = database_dependency
            test_app.dependency_overrides[get_current_postgres_user] = user_dependency
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                first = await client.get("/search?query=Alpha&limit=1")
                assert first.status_code == 200
                assert len(first.json()["items"]) == 1
                assert first.json()["next_cursor"]
                assert "hidden" not in first.text

                next_page = await client.get(
                    f"/search?query=Alpha&limit=1&cursor={first.json()['next_cursor']}"
                )
                assert next_page.status_code == 200
                assert len(next_page.json()["items"]) == 1
                assert next_page.json()["items"][0]["id"] != first.json()["items"][0]["id"]
                assert "hidden" not in next_page.text

                invalid = await client.get("/search?query=Alpha&cursor=invalid")
                assert invalid.status_code == 422
                maximum = await client.get("/search?query=Alpha&limit=101")
                assert maximum.status_code == 422

                active_user["id"] = outsider_id
                empty = await client.get("/search?query=Alpha")
                assert empty.status_code == 200
                assert empty.json()["items"] == []
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_institution_discovery_is_opt_in_paginated_and_private_fields_stay_hidden(postgres_database_url):
    from app.security import get_current_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        selected_user = {"id": None}
        try:
            async with session_factory() as session:
                user = await create_user(session)
                listed = [
                    Institution(
                        name=f"Directory Academy {index}",
                        institution_type="SCHOOL",
                        description="PRIVATE DETAIL MUST NOT APPEAR",
                        public_description=f"Public detail {index}",
                        website="https://private.example.test",
                        location="Private Location",
                        is_listed=True,
                    )
                    for index in range(3)
                ]
                unlisted = Institution(
                    name="Directory Academy Hidden",
                    institution_type="SCHOOL",
                    is_listed=False,
                )
                session.add_all([*listed, unlisted])
                await session.commit()
                selected_user["id"] = user.id
                listed_ids = [str(value.id) for value in listed]
                unlisted_id = str(unlisted.id)

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected_user["id"])

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first_page = await client.get(
                    "/institutions/discovery?query=Directory%20Academy&limit=2&offset=0"
                )
                second_page = await client.get(
                    "/institutions/discovery?query=Directory%20Academy&limit=2&offset=2"
                )
                assert first_page.status_code == second_page.status_code == 200
                assert [value["id"] for value in first_page.json()] == listed_ids[:2]
                assert [value["id"] for value in second_page.json()] == [listed_ids[2]]
                assert all(
                    set(value) == {"id", "name", "institution_type", "description"}
                    for value in first_page.json() + second_page.json()
                )
                assert all(
                    "PRIVATE" not in str(value)
                    and "website" not in value
                    and "location" not in value
                    for value in first_page.json() + second_page.json()
                )
                assert unlisted_id not in {
                    value["id"] for value in first_page.json() + second_page.json()
                }
                assert (await client.get(
                    "/institutions/discovery?query=Directory&limit=51"
                )).status_code == 422
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_admin_email_invitations_are_non_enumerating_rate_limited_and_cancellable(
    postgres_database_url, monkeypatch
):
    from app.models import InstitutionMembershipRequest
    from app.rate_limit import get_rate_limit_store

    class MemoryLimiter:
        def __init__(self):
            self.counts = {}

        async def increment(self, scope, key, window_seconds):
            value = (scope, key, window_seconds)
            self.counts[value] = self.counts.get(value, 0) + 1
            return self.counts[value], 23

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        selected = {"admin_id": None}
        limiter = MemoryLimiter()
        try:
            async with session_factory() as session:
                admin = await create_user(session)
                active_target = await create_user(
                    session, email="invite-target@example.test"
                )
                institution = await create_institution(session)
                session.add(
                    InstitutionMembership(
                        user_id=admin.id,
                        institution_id=institution.id,
                        role="ADMIN",
                    )
                )
                await session.commit()
                selected.update(
                    admin_id=admin.id,
                    institution_id=institution.id,
                    target_id=active_target.id,
                )

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected["admin_id"])

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            app.dependency_overrides[get_rate_limit_store] = lambda: limiter
            monkeypatch.setattr(
                institution_routes.config, "INSTITUTION_INVITATION_ADMIN_LIMIT", 2
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                path = f"/institutions/{selected['institution_id']}/invitations/by-email"
                absent = await client.post(
                    path, json={"email": "missing@example.test", "role": "STUDENT"}
                )
                present = await client.post(
                    path,
                    json={"email": "INVITE-TARGET@example.test", "role": "TEACHER"},
                )
                assert absent.status_code == present.status_code == 202
                assert absent.json() == present.json() == {"status": "ACCEPTED"}
                limited = await client.post(
                    path, json={"email": "another@example.test", "role": "STUDENT"}
                )
                assert limited.status_code == 429
                assert limited.headers["retry-after"] == "23"
                assert list(limiter.counts) == [
                    (
                        "institution:invitation:admin",
                        str(selected["admin_id"]),
                        institution_routes.config.INSTITUTION_INVITATION_WINDOW_SECONDS,
                    )
                ]

                invitations = await client.get(
                    f"/institutions/{selected['institution_id']}/invitations?limit=5"
                )
                assert invitations.status_code == 200
                assert len(invitations.json()) == 1
                invitation = invitations.json()[0]
                assert invitation["email"] == "invite-target@example.test"
                assert invitation["role"] == "TEACHER"
                assert (await client.get(
                    f"/institutions/{selected['institution_id']}/invitations?limit=101"
                )).status_code == 422

                events = await client.get(
                    f"/institutions/{selected['institution_id']}/invitations"
                )
                assert events.status_code == 200
                cancelled = await client.delete(
                    f"/institutions/{selected['institution_id']}/invitations/{invitation['id']}"
                )
                assert cancelled.status_code == 204
                assert (await client.get(
                    f"/institutions/{selected['institution_id']}/invitations"
                )).json() == []

            async with session_factory() as session:
                pending = list(
                    (
                        await session.scalars(
                            select(InstitutionMembershipRequest).where(
                                InstitutionMembershipRequest.institution_id
                                == selected["institution_id"]
                            )
                        )
                    ).all()
                )
                assert len(pending) == 1
                assert pending[0].user_id == selected["target_id"]
                assert pending[0].status == "CANCELLED"
                audit_events = list(
                    (
                        await session.scalars(
                            select(SecurityEvent).where(
                                SecurityEvent.event_type
                                == "institution.invitation.email_requested"
                            )
                        )
                    ).all()
                )
                assert len(audit_events) == 2
                assert all(
                    "invite-target@example.test" not in str(event.details)
                    and len(event.details["email_hash"]) == 64
                    for event in audit_events
                )
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_administered_institution_lookup_uses_membership_roles(postgres_database_url):
    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_overrides = app.dependency_overrides.copy()
        selected = {"user_id": None}
        try:
            async with session_factory() as session:
                user = await create_user(session)
                admin_school = await create_institution(session, name="Admin school")
                member_school = await create_institution(session, name="Member school")
                session.add_all([
                    InstitutionMembership(
                        user_id=user.id,
                        institution_id=admin_school.id,
                        role="ADMIN",
                    ),
                    InstitutionMembership(
                        user_id=user.id,
                        institution_id=member_school.id,
                        role="STUDENT",
                    ),
                ])
                await session.commit()
                selected["user_id"] = user.id
                expected_admin_school_id = str(admin_school.id)

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected["user_id"])

            app.dependency_overrides[get_postgres_session] = database_dependency
            app.dependency_overrides[get_current_postgres_user] = user_dependency
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/institutions/administered")
            assert response.status_code == 200
            assert [value["id"] for value in response.json()] == [expected_admin_school_id]
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_reel_create_enforces_asset_rules_and_delete_removes_stored_video(postgres_database_url):
    from fastapi import FastAPI
    from app.models import MediaAsset
    from app.providers import ProviderRegistry, ProviderSettings, get_provider_registry
    from app.routes.reels import router as reels_router

    class ReelStorage:
        name = "test-reels"

        def __init__(self):
            self.deleted = []

        async def create_download_url(self, object_key, *, expires_in_seconds):
            return "https://media.example.test/signed-reel"

        async def delete_object(self, object_key):
            self.deleted.append(object_key)

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(reels_router)
        original_overrides = app.dependency_overrides.copy()
        selected_user = {"id": None}
        storage = ReelStorage()
        providers = ProviderRegistry(settings=ProviderSettings(storage="test-reels"), storage=storage)
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                other = await create_user(session)
                now = datetime.now(timezone.utc)
                assets = {
                    "owned": MediaAsset(
                        owner_id=owner.id, purpose="REEL", status="READY", storage_provider="test",
                        storage_key="reel-owned", content_type="video/mp4", byte_size=1024,
                        original_filename="owned.mp4", upload_expires_at=now,
                    ),
                    "foreign": MediaAsset(
                        owner_id=other.id, purpose="REEL", status="READY", storage_provider="test",
                        storage_key="reel-foreign", content_type="video/mp4", byte_size=1024,
                        original_filename="foreign.mp4", upload_expires_at=now,
                    ),
                    "wrong-purpose": MediaAsset(
                        owner_id=owner.id, purpose="POST_MEDIA", status="READY", storage_provider="test",
                        storage_key="wrong-purpose", content_type="video/mp4", byte_size=1024,
                        original_filename="post.mp4", upload_expires_at=now,
                    ),
                    "pending": MediaAsset(
                        owner_id=owner.id, purpose="REEL", status="UPLOAD_PENDING", storage_provider="test",
                        storage_key="reel-pending", content_type="video/mp4", byte_size=1024,
                        original_filename="pending.mp4", upload_expires_at=now + timedelta(minutes=5),
                    ),
                    "too-large": MediaAsset(
                        owner_id=owner.id, purpose="REEL", status="READY", storage_provider="test",
                        storage_key="reel-too-large", content_type="video/mp4", byte_size=reel_routes_limit() + 1,
                        original_filename="large.mp4", upload_expires_at=now,
                    ),
                }
                session.add_all(assets.values())
                await session.commit()
                selected_user["id"] = owner.id
                asset_ids = {name: str(asset.id) for name, asset in assets.items()}

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected_user["id"])

            test_app.dependency_overrides[get_postgres_session] = database_dependency
            test_app.dependency_overrides[get_current_postgres_user] = user_dependency
            test_app.dependency_overrides[get_provider_registry] = lambda: providers
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                path = "/reels"
                valid = await client.post(path, json={"media_asset_id": asset_ids["owned"], "content": "A short clip"})
                assert valid.status_code == 201
                reel = valid.json()
                assert reel["post_type"] == "REEL"
                assert reel["media_asset_id"] == asset_ids["owned"]
                assert reel["video_url"] == "https://media.example.test/signed-reel"
                assert "reel-owned" not in valid.text

                foreign = await client.post(path, json={"media_asset_id": asset_ids["foreign"], "content": "Clip"})
                wrong_purpose = await client.post(path, json={"media_asset_id": asset_ids["wrong-purpose"], "content": "Clip"})
                pending = await client.post(path, json={"media_asset_id": asset_ids["pending"], "content": "Clip"})
                oversized = await client.post(path, json={"media_asset_id": asset_ids["too-large"], "content": "Clip"})
                assert foreign.status_code == 404
                assert wrong_purpose.status_code == 422
                assert pending.status_code == 409
                assert oversized.status_code == 413

                selected_user["id"] = assets["foreign"].owner_id
                denied_delete = await client.delete(f"/reels/{reel['id']}")
                assert denied_delete.status_code == 404
                selected_user["id"] = assets["owned"].owner_id
                deleted = await client.delete(f"/reels/{reel['id']}")
                assert deleted.status_code == 204
                assert storage.deleted == ["reel-owned"]
        finally:
            test_app.dependency_overrides.clear()
            test_app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def reel_routes_limit():
    from app.routes.reels import REEL_MAX_BYTES

    return REEL_MAX_BYTES


def test_reel_feed_privacy_cursor_pagination_and_query_count_is_bounded(postgres_database_url):
    from fastapi import FastAPI
    from app.models import Follow, MediaAsset, Post
    from app.providers import ProviderRegistry, ProviderSettings, get_provider_registry
    from app.routes.reels import router as reels_router

    class ReelStorage:
        async def create_download_url(self, object_key, *, expires_in_seconds):
            return "https://media.example.test/signed"

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(reels_router)
        original_overrides = app.dependency_overrides.copy()
        selected_user = {"id": None}
        providers = ProviderRegistry(settings=ProviderSettings(storage="test-reels"), storage=ReelStorage())
        statements = []

        def count_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
        try:
            async with session_factory() as session:
                viewer = await create_user(session)
                followed_author = await create_user(session)
                unrelated_author = await create_user(session)
                session.add(Follow(follower_id=viewer.id, following_id=followed_author.id))
                public_reels = []
                for index in range(22):
                    asset = MediaAsset(
                        owner_id=followed_author.id, purpose="REEL", status="READY",
                        storage_provider="test", storage_key=f"feed-reel-{index}",
                        content_type="video/mp4", byte_size=2048, original_filename=f"{index}.mp4",
                        upload_expires_at=datetime.now(timezone.utc),
                    )
                    session.add(asset)
                    await session.flush()
                    reel = Post(
                        author_id=followed_author.id, content=f"Visible reel {index}",
                        post_type="REEL", media_asset_id=asset.id, visibility="PUBLIC",
                    )
                    public_reels.append(reel)
                    session.add(reel)
                hidden_asset = MediaAsset(
                    owner_id=followed_author.id, purpose="REEL", status="READY",
                    storage_provider="test", storage_key="private-reel", content_type="video/webm",
                    byte_size=1024, original_filename="private.webm", upload_expires_at=datetime.now(timezone.utc),
                )
                session.add(hidden_asset)
                await session.flush()
                hidden_reel = Post(
                    author_id=followed_author.id, content="Private reel", post_type="REEL",
                    media_asset_id=hidden_asset.id, visibility="PRIVATE",
                )
                outsider_asset = MediaAsset(
                    owner_id=unrelated_author.id, purpose="REEL", status="READY",
                    storage_provider="test", storage_key="outsider-reel", content_type="video/mp4",
                    byte_size=1024, original_filename="outsider.mp4", upload_expires_at=datetime.now(timezone.utc),
                )
                session.add(outsider_asset)
                await session.flush()
                outsider_reel = Post(
                    author_id=unrelated_author.id, content="Unfollowed reel", post_type="REEL",
                    media_asset_id=outsider_asset.id, visibility="PUBLIC",
                )
                regular_post = Post(author_id=followed_author.id, content="Not a reel", post_type="POST")
                session.add_all([hidden_reel, outsider_reel, regular_post])
                await session.commit()
                selected_user["id"] = viewer.id

            async def database_dependency():
                async with session_factory() as session:
                    yield session

            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected_user["id"])

            test_app.dependency_overrides[get_postgres_session] = database_dependency
            test_app.dependency_overrides[get_current_postgres_user] = user_dependency
            test_app.dependency_overrides[get_provider_registry] = lambda: providers
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                first = await client.get("/reels/feed?limit=2")
                assert first.status_code == 200
                first_payload = first.json()
                assert first_payload["has_more"] is True
                assert len(first_payload["items"]) == 2
                assert all(item["post_type"] == "REEL" and item["video_url"] for item in first_payload["items"])
                second = await client.get(f"/reels/feed?limit=2&cursor={first_payload['next_cursor']}")
                assert second.status_code == 200
                assert not {item["id"] for item in first_payload["items"]} & {item["id"] for item in second.json()["items"]}
                all_visible = await client.get("/reels/feed?limit=20")
                all_visible_text = str(all_visible.json())
                assert "Private reel" not in all_visible_text
                assert "Unfollowed reel" not in all_visible_text
                assert "Not a reel" not in all_visible_text

                statements.clear()
                one_item = await client.get("/reels/feed?limit=1")
                count_one = len(statements)
                statements.clear()
                twenty_items = await client.get("/reels/feed?limit=20")
                count_twenty = len(statements)
                assert len(one_item.json()["items"]) == 1
                assert len(twenty_items.json()["items"]) == 20
                assert count_one == count_twenty
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
            test_app.dependency_overrides.clear()
            test_app.dependency_overrides.update(original_overrides)
            await engine.dispose()

    asyncio.run(verify())


def test_media_download_scope_and_avatar_profile_visibility(postgres_database_url):
    from datetime import datetime, timedelta, timezone
    import tempfile

    from app.models import MediaAsset, Profile
    from app.providers import LocalDiskStorageProvider, ProviderRegistry, ProviderSettings
    from app.routes.media import create_media_download_url
    from app.routes.profile import (
        clear_my_profile_avatar,
        get_user_profile,
        set_my_profile_avatar,
    )
    from app.schemas import MediaAvatarSet

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            with tempfile.TemporaryDirectory() as directory:
                storage = LocalDiskStorageProvider(
                    directory, "integration-storage-signing-key"
                )
                providers = ProviderRegistry(
                    settings=ProviderSettings(storage="local"), storage=storage
                )
                async with session_factory() as session:
                    owner = await create_user(session)
                    same_institution_user = await create_user(session)
                    outsider = await create_user(session)
                    institution_a = await create_institution(session)
                    institution_b = await create_institution(session)
                    session.add_all(
                        [
                            InstitutionMembership(
                                user_id=owner.id,
                                institution_id=institution_a.id,
                                role="TEACHER",
                            ),
                            InstitutionMembership(
                                user_id=same_institution_user.id,
                                institution_id=institution_a.id,
                                role="STUDENT",
                            ),
                            InstitutionMembership(
                                user_id=outsider.id,
                                institution_id=institution_b.id,
                                role="STUDENT",
                            ),
                        ]
                    )
                    now = datetime.now(timezone.utc)
                    profile = Profile(
                        user_id=owner.id,
                        display_name="Media owner",
                        visibility="NETWORK",
                    )
                    avatar = MediaAsset(
                        owner_id=owner.id,
                        purpose="PROFILE_IMAGE",
                        status="READY",
                        storage_provider="local",
                        storage_key=f"users/{owner.id}/{uuid.uuid4()}",
                        content_type="image/png",
                        byte_size=32,
                        original_filename="avatar.png",
                        upload_expires_at=now + timedelta(minutes=5),
                    )
                    course_asset = MediaAsset(
                        owner_id=owner.id,
                        institution_id=institution_a.id,
                        purpose="COURSE_MEDIA",
                        status="READY",
                        storage_provider="local",
                        storage_key=f"users/{owner.id}/{uuid.uuid4()}",
                        content_type="application/pdf",
                        byte_size=64,
                        original_filename="course.pdf",
                        upload_expires_at=now + timedelta(minutes=5),
                    )
                    session.add_all([profile, avatar, course_asset])
                    await session.commit()

                    with pytest.raises(HTTPException) as cross_institution:
                        await create_media_download_url(
                            course_asset.id, outsider, session, providers
                        )
                    assert cross_institution.value.status_code == 404
                    shared_download = await create_media_download_url(
                        course_asset.id, same_institution_user, session, providers
                    )
                    assert shared_download["expires_in_seconds"] == 300

                    with pytest.raises(HTTPException) as private_avatar:
                        await create_media_download_url(
                            avatar.id, outsider, session, providers
                        )
                    assert private_avatar.value.status_code == 404
                    await set_my_profile_avatar(
                        MediaAvatarSet(asset_id=str(avatar.id)),
                        owner,
                        session,
                        providers,
                    )
                    visible_profile = await get_user_profile(
                        owner.id, same_institution_user, session, providers
                    )
                    assert visible_profile["profile_picture_url"].startswith(
                        "/api/v1/media/local-download/"
                    )
                    with pytest.raises(HTTPException):
                        await set_my_profile_avatar(
                            MediaAvatarSet(asset_id=str(avatar.id)),
                            outsider,
                            session,
                            providers,
                        )

                    profile.visibility = "AUTHENTICATED"
                    public_to_authenticated = await create_media_download_url(
                        avatar.id, outsider, session, providers
                    )
                    assert public_to_authenticated["download_url"].startswith(
                        "/api/v1/media/local-download/"
                    )
                    profile.visibility = "PUBLIC"
                    public_avatar = await create_media_download_url(
                        avatar.id, None, session, providers
                    )
                    assert public_avatar["download_url"].startswith(
                        "/api/v1/media/local-download/"
                    )
                    cleared = await clear_my_profile_avatar(owner, session)
                    assert cleared["profile_picture_url"] is None
        finally:
            await engine.dispose()

    asyncio.run(verify())


def test_orphan_upload_purge_and_asset_delete_remove_objects(postgres_database_url):
    import tempfile
    from datetime import datetime, timedelta, timezone
    from urllib.parse import urlparse

    from app.cli import purge_orphan_uploads
    from app.models import MediaAsset
    from app.providers import LocalDiskStorageProvider, ProviderRegistry, ProviderSettings
    from app.routes.media import delete_media_asset

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalDiskStorageProvider(
                directory, "orphan-upload-storage-signing-key"
            )
            providers = ProviderRegistry(
                settings=ProviderSettings(storage="local"), storage=storage
            )
            try:
                async with session_factory() as session:
                    user = await create_user(session)
                    now = datetime.now(timezone.utc)
                    pending_key = f"users/{user.id}/{uuid.uuid4()}"
                    ready_key = f"users/{user.id}/{uuid.uuid4()}"
                    assets = []
                    for key in (pending_key, ready_key):
                        intent = await storage.create_upload_intent(
                            object_key=key,
                            content_type="image/png",
                            max_bytes=12,
                            expires_in_seconds=60,
                        )
                        token = urlparse(intent.upload_url).path.rsplit("/", 1)[-1]

                        async def chunks():
                            yield b"\x89PNG\r\n\x1a\nxxxx"

                        await storage.accept_upload(token, "image/png", chunks())
                    pending = MediaAsset(
                        owner_id=user.id,
                        purpose="PROFILE_IMAGE",
                        status="UPLOAD_PENDING",
                        storage_provider="local",
                        storage_key=pending_key,
                        content_type="image/png",
                        byte_size=12,
                        original_filename="pending.png",
                        upload_expires_at=now - timedelta(hours=1),
                        created_at=now - timedelta(days=2),
                    )
                    ready = MediaAsset(
                        owner_id=user.id,
                        purpose="PROFILE_IMAGE",
                        status="READY",
                        storage_provider="local",
                        storage_key=ready_key,
                        content_type="image/png",
                        byte_size=12,
                        original_filename="ready.png",
                        upload_expires_at=now + timedelta(minutes=5),
                    )
                    session.add_all([pending, ready])
                    await session.commit()
                    user_id = user.id
                    pending_id = pending.id
                    ready_id = ready.id

                assert await purge_orphan_uploads(
                    session_factory, older_than_hours=24, storage=storage
                ) == 1
                assert await storage.inspect_object(pending_key) is None
                async with session_factory() as session:
                    assert await session.get(MediaAsset, pending_id) is None
                    ready = await session.get(MediaAsset, ready_id)
                    user = await session.get(User, user_id)
                    assert ready is not None
                    await delete_media_asset(ready_id, user, session, providers)
                assert await storage.inspect_object(ready_key) is None
                async with session_factory() as session:
                    assert await session.get(MediaAsset, ready_id) is None
            finally:
                await engine.dispose()

    asyncio.run(verify())


def test_notification_preferences_migration_downgrades_and_upgrades(postgres_database_url):
    from app.models import NotificationPreference

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        user_id = None
        try:
            async with session_factory() as session:
                user = await create_user(session)
                user_id = user.id
                session.add(
                    NotificationPreference(
                        user_id=user.id,
                        notification_type="FOLLOW",
                        enabled=False,
                    )
                )
                await session.commit()

            downgrade = _alembic(postgres_database_url, "downgrade", "0023_reels")
            assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
            upgrade = _alembic(postgres_database_url, "upgrade", "head")
            assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

            async with session_factory() as session:
                assert await session.get(NotificationPreference, (user_id, "FOLLOW")) is None
        finally:
            if user_id is not None:
                async with session_factory() as session:
                    user = await session.get(User, user_id)
                    if user is not None:
                        await session.delete(user)
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_profile_visibility_email_change_migration_round_trip(postgres_database_url):
    from app.models import AccountEmailToken, Profile

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        user_id = None
        token_id = uuid.uuid4()
        try:
            async with session_factory() as session:
                user = await create_user(session)
                user_id = user.id
                session.add(Profile(user_id=user.id, display_name="Follower profile", visibility="FOLLOWERS"))
                session.add(
                    AccountEmailToken(
                        id=token_id,
                        user_id=user.id,
                        purpose="EMAIL_CHANGE",
                        token_hash=uuid.uuid4().hex * 2,
                        pending_email="pending@example.test",
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                    )
                )
                await session.commit()

            async with session_factory() as session:
                assert (await session.get(Profile, user_id)).visibility == "FOLLOWERS"
                assert (await session.get(AccountEmailToken, token_id)).pending_email == "pending@example.test"
                await session.delete(await session.get(AccountEmailToken, token_id))
                await session.delete(await session.get(User, user_id))
                await session.commit()

            downgrade = _alembic(postgres_database_url, "downgrade", "0025_reports_blocks_moderation")
            assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
            upgrade = _alembic(postgres_database_url, "upgrade", "head")
            assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
        finally:
            if user_id is not None:
                async with session_factory() as session:
                    user = await session.get(User, user_id)
                    if user is not None:
                        await session.delete(user)
                        await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_email_change_confirms_address_and_revokes_sessions(postgres_database_url):
    from urllib.parse import parse_qs, urlparse

    from starlette.requests import Request
    from starlette.responses import Response

    from app.providers import ProviderRegistry, ProviderSettings
    from app.routes.account import confirm_email_change, request_email_change
    from app.schemas import EmailChangeRequest, EmailTokenConfirm
    from app.security import password_hash

    class EmailProvider:
        def __init__(self):
            self.messages = []

        async def send(self, message):
            self.messages.append(message)

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        user_ids: list[uuid.UUID] = []
        provider = EmailProvider()
        providers = ProviderRegistry(settings=ProviderSettings(), email=provider)
        try:
            async with session_factory() as session:
                user = await create_user(session)
                user.password_hash = password_hash.hash("current-password")
                peer = await create_user(session)
                user_ids.extend([user.id, peer.id])
                peer_email = peer.email
                await session.commit()
                version = user.token_version

                sent = await request_email_change(
                    EmailChangeRequest(email="new-address@example.test", current_password="current-password"),
                    user,
                    session,
                    providers,
                )
                duplicate = await request_email_change(
                    EmailChangeRequest(email=peer_email, current_password="current-password"),
                    user,
                    session,
                    providers,
                )
                assert sent == duplicate == {
                    "message": "If the address is eligible, a confirmation message will be sent"
                }
                assert len(provider.messages) == 1
                confirmation_url = provider.messages[0].text_body.rsplit(" ", 1)[-1]
                token = parse_qs(urlparse(confirmation_url).query)["token"][0]
                scope = {
                    "type": "http",
                    "method": "POST",
                    "path": "/api/v1/account/email-change/confirm",
                    "headers": [],
                    "client": ("127.0.0.1", 1234),
                    "server": ("test", 80),
                    "scheme": "http",
                    "query_string": b"",
                }
                await confirm_email_change(
                    EmailTokenConfirm(token=token),
                    session,
                    Request(scope),
                    Response(),
                )
                assert user.email == "new-address@example.test"
                assert user.email_verified_at is not None
                assert user.token_version == version + 1
                assert provider.messages[0].recipient == "new-address@example.test"
                assert "action=email-change" in provider.messages[0].text_body
                assert await session.scalar(
                    select(func.count()).select_from(SecurityEvent).where(
                        SecurityEvent.event_type == "account.email_changed",
                        SecurityEvent.actor_user_id == user.id,
                    )
                ) == 1
        finally:
            async with session_factory() as session:
                if user_ids:
                    await session.execute(
                        delete(SecurityEvent).where(
                            or_(
                                SecurityEvent.actor_user_id.in_(user_ids),
                                SecurityEvent.target_user_id.in_(user_ids),
                            )
                        )
                    )
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_follower_only_profile_and_content_are_visible_only_to_followers(postgres_database_url):
    from app.models import Follow, Post, Profile
    from app.providers import ProviderRegistry, ProviderSettings
    from app.routes.profile import get_user_profile, list_user_posts

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        user_ids: list[uuid.UUID] = []
        providers = ProviderRegistry(settings=ProviderSettings())
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                follower = await create_user(session)
                outsider = await create_user(session)
                user_ids.extend([owner.id, follower.id, outsider.id])
                session.add(Profile(user_id=owner.id, display_name="Followers only", visibility="FOLLOWERS"))
                session.add(Follow(follower_id=follower.id, following_id=owner.id))
                post = Post(author_id=owner.id, content="private to followers", visibility="PUBLIC")
                session.add(post)
                await session.commit()
                owner_id = owner.id

            async with session_factory() as session:
                follower_profile = await get_user_profile(owner_id, follower, session, providers)
                assert follower_profile["is_following"] is True
                assert follower_profile["post_count"] == 1
                assert follower_profile["reel_count"] == 0
                posts = await list_user_posts(
                    owner_id, follower, session, providers, post_type="POST", limit=20
                )
                assert [post["content"] for post in posts["items"]] == ["private to followers"]
                with pytest.raises(HTTPException) as invisible_profile:
                    await get_user_profile(owner_id, outsider, session, providers)
                assert invisible_profile.value.status_code == 404
                with pytest.raises(HTTPException) as invisible_posts:
                    await list_user_posts(
                        owner_id, outsider, session, providers, post_type="POST", limit=20
                    )
                assert invisible_posts.value.status_code == 404
        finally:
            async with session_factory() as session:
                if user_ids:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_video_and_music_migrations_round_trip_and_cascade_own_rows(postgres_database_url):
    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        user_id = None
        try:
            downgrade = _alembic(postgres_database_url, "downgrade", "0026_profile_email_change")
            assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
            upgrade = _alembic(postgres_database_url, "upgrade", "head")
            assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
            async with session_factory() as session:
                user = await create_user(session)
                user_id = user.id
                video_asset = MediaAsset(
                    owner_id=user.id, purpose="VIDEO", status="READY",
                    storage_provider="local", storage_key=f"users/{user.id}/{uuid.uuid4()}",
                    content_type="video/mp4", byte_size=12, original_filename="video.mp4",
                    upload_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
                audio_asset = MediaAsset(
                    owner_id=user.id, purpose="AUDIO", status="READY",
                    storage_provider="local", storage_key=f"users/{user.id}/{uuid.uuid4()}",
                    content_type="audio/mpeg", byte_size=12, original_filename="audio.mp3",
                    upload_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
                session.add_all([video_asset, audio_asset])
                await session.flush()
                session.add_all([
                    Video(owner_id=user.id, media_asset_id=video_asset.id, title="Test video", category="Education"),
                    Track(owner_id=user.id, media_asset_id=audio_asset.id, title="Test track", artist_name="Artist", category="Jazz"),
                ])
                await session.commit()
            async with session_factory() as session:
                await session.execute(delete(Video).where(Video.owner_id == user_id))
                await session.execute(delete(Track).where(Track.owner_id == user_id))
                await session.execute(delete(MediaAsset).where(MediaAsset.owner_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            async with session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(Video).where(Video.owner_id == user_id)) == 0
                assert await session.scalar(select(func.count()).select_from(Track).where(Track.owner_id == user_id)) == 0
        finally:
            if user_id is not None:
                async with session_factory() as session:
                    await session.execute(delete(Video).where(Video.owner_id == user_id))
                    await session.execute(delete(Track).where(Track.owner_id == user_id))
                    await session.execute(delete(MediaAsset).where(MediaAsset.owner_id == user_id))
                    await session.execute(delete(User).where(User.id == user_id))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_video_track_privacy_ownership_and_playlist_rules(postgres_database_url):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_postgres_session
    from app.models import Follow
    from app.routes.video_music import router as media_router
    from app.security import get_current_postgres_user, get_optional_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(media_router)
        selected = {"id": None}
        user_ids: list[uuid.UUID] = []
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                follower = await create_user(session)
                outsider = await create_user(session)
                blocked = await create_user(session)
                user_ids.extend([owner.id, follower.id, outsider.id, blocked.id])
                session.add(Follow(follower_id=follower.id, following_id=owner.id))
                session.add(UserBlock(blocker_id=owner.id, blocked_id=blocked.id))
                now = datetime.now(timezone.utc)
                assets = [
                    MediaAsset(owner_id=owner.id, purpose="VIDEO", status="READY", storage_provider="test",
                               storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="video/mp4",
                               byte_size=100, original_filename="video.mp4", upload_expires_at=now),
                    MediaAsset(owner_id=owner.id, purpose="AUDIO", status="READY", storage_provider="test",
                               storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="audio/mpeg",
                               byte_size=100, original_filename="track.mp3", upload_expires_at=now),
                ]
                session.add_all(assets)
                await session.flush()
                public_video = Video(owner_id=owner.id, media_asset_id=assets[0].id, title="Public lesson", category="Education")
                private_track = Track(owner_id=owner.id, media_asset_id=assets[1].id, title="Private song",
                                      artist_name="Artist", category="Jazz", visibility="PRIVATE")
                session.add_all([public_video, private_track])
                await session.commit()
                owner_id, follower_id, outsider_id, blocked_id = owner.id, follower.id, outsider.id, blocked.id
                video_id, track_id = public_video.id, private_track.id
            async def db_dependency():
                async with session_factory() as session:
                    yield session
            async def current_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected["id"])
            test_app.dependency_overrides[get_postgres_session] = db_dependency
            test_app.dependency_overrides[get_current_postgres_user] = current_dependency
            test_app.dependency_overrides[get_optional_postgres_user] = current_dependency
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                selected["id"] = outsider_id
                assert (await client.get(f"/videos/{video_id}")).status_code == 200
                assert (await client.put(f"/videos/{video_id}", json={
                    "title": "Hijack", "category": "Education",
                })).status_code == 404
                assert (await client.delete(f"/videos/{video_id}")).status_code == 404
                assert (await client.post(f"/videos/{video_id}/like")).status_code == 204
                assert (await client.post(f"/videos/{video_id}/comments", json={"content": "hello"})).status_code == 201
                selected["id"] = blocked_id
                assert (await client.get(f"/videos/{video_id}")).status_code == 404
                assert (await client.post(f"/videos/{video_id}/like")).status_code == 404
                assert (await client.post(f"/videos/{video_id}/comments", json={"content": "blocked"})).status_code == 404
                selected["id"] = follower_id
                assert (await client.get(f"/tracks?category=Jazz")).json() == []
                selected["id"] = outsider_id
                assert (await client.post(f"/playlists", json={"title": "Public list"})).status_code == 201
                playlist = (await client.get("/playlists")).json()[0]
                assert (await client.post(f"/playlists/{playlist['id']}/tracks/{track_id}")).status_code == 404
                selected["id"] = owner_id
                assert (await client.put(f"/videos/{video_id}", json={
                    "title": "Private lesson", "category": "Education", "visibility": "PRIVATE",
                })).status_code == 200
                selected["id"] = outsider_id
                assert (await client.get(f"/videos/{video_id}")).status_code == 404
                selected["id"] = follower_id
                assert (await client.get(f"/videos/{video_id}")).status_code == 404
                selected["id"] = owner_id
                follow = await client.put("/music/categories/Jazz/follow")
                assert follow.status_code == 204
                unfollow = await client.delete("/music/categories/Jazz/follow")
                assert unfollow.status_code == 204
                async with session_factory() as session:
                    assert await session.get(MusicCategoryFollow, (owner_id, "Jazz")) is None
        finally:
            test_app.dependency_overrides.clear()
            if user_ids:
                async with session_factory() as session:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_media_notifications_respect_visibility_blocks_preferences_and_deduplicate(postgres_database_url):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_postgres_session
    from app.models import Follow
    from app.routes.video_music import router as media_router
    from app.security import get_current_postgres_user

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(media_router)
        selected = {"id": None}
        user_ids: list[uuid.UUID] = []
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                both = await create_user(session)
                category_only = await create_user(session)
                muted = await create_user(session)
                blocked = await create_user(session)
                user_ids.extend([owner.id, both.id, category_only.id, muted.id, blocked.id])
                session.add_all([
                    Follow(follower_id=both.id, following_id=owner.id),
                    Follow(follower_id=muted.id, following_id=owner.id),
                    Follow(follower_id=blocked.id, following_id=owner.id),
                    MusicCategoryFollow(user_id=both.id, category="Jazz"),
                    MusicCategoryFollow(user_id=category_only.id, category="Jazz"),
                    UserBlock(blocker_id=owner.id, blocked_id=blocked.id),
                    NotificationPreference(user_id=muted.id, notification_type="NEW_VIDEO", enabled=False),
                    NotificationPreference(user_id=muted.id, notification_type="NEW_TRACK", enabled=False),
                ])
                now = datetime.now(timezone.utc)
                assets = [
                    MediaAsset(owner_id=owner.id, purpose="VIDEO", status="READY", storage_provider="test",
                               storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="video/mp4",
                               byte_size=100, original_filename="one.mp4", upload_expires_at=now),
                    MediaAsset(owner_id=owner.id, purpose="AUDIO", status="READY", storage_provider="test",
                               storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="audio/mpeg",
                               byte_size=100, original_filename="one.mp3", upload_expires_at=now),
                    MediaAsset(owner_id=owner.id, purpose="AUDIO", status="READY", storage_provider="test",
                               storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="audio/mpeg",
                               byte_size=100, original_filename="private.mp3", upload_expires_at=now),
                ]
                session.add_all(assets)
                await session.commit()
                selected["id"] = owner.id
                asset_ids = [str(asset.id) for asset in assets]
                owner_id, both_id, category_id, muted_id, blocked_id = owner.id, both.id, category_only.id, muted.id, blocked.id

            async def db_dependency():
                async with session_factory() as session:
                    yield session
            async def current_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected["id"])
            test_app.dependency_overrides[get_postgres_session] = db_dependency
            test_app.dependency_overrides[get_current_postgres_user] = current_dependency
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                video = await client.post("/videos", json={
                    "media_asset_id": asset_ids[0], "title": "Public", "category": "Education",
                })
                assert video.status_code == 201
                rejected = await client.post("/tracks", json={
                    "media_asset_id": asset_ids[1], "title": "Rights", "artist_name": "Artist",
                    "category": "Jazz", "rights_confirmed": False,
                })
                assert rejected.status_code == 422
                track = await client.post("/tracks", json={
                    "media_asset_id": asset_ids[1], "title": "Public", "artist_name": "Artist",
                    "category": "Jazz", "rights_confirmed": True,
                })
                assert track.status_code == 201
                private = await client.post("/tracks", json={
                    "media_asset_id": asset_ids[2], "title": "Private", "artist_name": "Artist",
                    "category": "Jazz", "visibility": "PRIVATE", "rights_confirmed": True,
                })
                assert private.status_code == 201

            async with session_factory() as session:
                notifications = (await session.scalars(select(Notification).where(
                    Notification.actor_id == owner_id,
                    Notification.type.in_(["NEW_VIDEO", "NEW_TRACK"]),
                ))).all()
                videos = {notification.recipient_id for notification in notifications if notification.type == "NEW_VIDEO"}
                tracks = {notification.recipient_id for notification in notifications if notification.type == "NEW_TRACK"}
                assert videos == {both_id}
                assert tracks == {both_id, category_id}
                assert muted_id not in videos | tracks
                assert blocked_id not in videos | tracks
                assert sum(notification.type == "NEW_TRACK" and notification.recipient_id == both_id for notification in notifications) == 1
        finally:
            test_app.dependency_overrides.clear()
            if user_ids:
                async with session_factory() as session:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())


def test_media_counters_are_deduplicated_and_rate_limited(postgres_database_url):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from app.database import get_postgres_session
    from app.rate_limit import get_rate_limit_store
    from app.routes.video_music import router as media_router
    from app.security import get_current_postgres_user

    class Limiter:
        def __init__(self):
            self.counts = {}

        async def increment(self, scope, key, window_seconds):
            value = self.counts.get((scope, key), 0) + 1
            self.counts[(scope, key)] = value
            return value, 60

        async def get_count(self, scope, key, window_seconds):
            return self.counts.get((scope, key), 0), 60

        async def clear(self, scope, key):
            self.counts.pop((scope, key), None)

    async def verify():
        engine = create_async_engine(postgres_database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        test_app = FastAPI()
        test_app.include_router(media_router)
        selected = {"id": None}
        user_ids: list[uuid.UUID] = []
        limiter = Limiter()
        try:
            async with session_factory() as session:
                owner = await create_user(session)
                viewer = await create_user(session)
                user_ids.extend([owner.id, viewer.id])
                now = datetime.now(timezone.utc)
                video_asset = MediaAsset(owner_id=owner.id, purpose="VIDEO", status="READY", storage_provider="test",
                    storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="video/mp4", byte_size=100,
                    original_filename="view.mp4", upload_expires_at=now)
                audio_asset = MediaAsset(owner_id=owner.id, purpose="AUDIO", status="READY", storage_provider="test",
                    storage_key=f"users/{owner.id}/{uuid.uuid4()}", content_type="audio/mpeg", byte_size=100,
                    original_filename="play.mp3", upload_expires_at=now)
                session.add_all([video_asset, audio_asset])
                await session.flush()
                video = Video(owner_id=owner.id, media_asset_id=video_asset.id, title="Views", category="Education")
                track = Track(owner_id=owner.id, media_asset_id=audio_asset.id, title="Plays", artist_name="Artist", category="Jazz")
                session.add_all([video, track])
                await session.commit()
                selected["id"] = viewer.id
                video_id, track_id = video.id, track.id
            async def db_dependency():
                async with session_factory() as session:
                    yield session
            async def user_dependency():
                async with session_factory() as session:
                    return await session.get(User, selected["id"])
            test_app.dependency_overrides[get_postgres_session] = db_dependency
            test_app.dependency_overrides[get_current_postgres_user] = user_dependency
            test_app.dependency_overrides[get_rate_limit_store] = lambda: limiter
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
                assert (await client.post(f"/videos/{video_id}/view")).status_code == 204
                assert (await client.post(f"/videos/{video_id}/view")).status_code == 204
                assert (await client.post(f"/tracks/{track_id}/play")).status_code == 204
                assert (await client.post(f"/tracks/{track_id}/play")).status_code == 204
                for _ in range(59):
                    response = await client.post(f"/videos/{video_id}/view")
                assert response.status_code == 429
            async with session_factory() as session:
                assert (await session.get(Video, video_id)).view_count == 1
                assert (await session.get(Track, track_id)).play_count == 1
        finally:
            test_app.dependency_overrides.clear()
            if user_ids:
                async with session_factory() as session:
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                    await session.commit()
            await engine.dispose()

    asyncio.run(verify())
