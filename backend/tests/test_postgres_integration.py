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
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from starlette.requests import Request

from app.database import get_postgres_session
from app.main import app
from app.models import (
    AuthIdentity,
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
    SecurityEvent,
    Student,
    Teacher,
    User,
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
    from app.cli import seed_demo
    from app.models import (
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
                )
                before_counts = {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }
            first_credentials = await seed_demo(session_factory)
            second_credentials = await seed_demo(session_factory)

            async with session_factory() as session:
                counts = {
                    model.__tablename__: await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    for model in models
                }

            assert len(first_credentials) == 4
            assert second_credentials == []
            assert {name: counts[name] - before_counts[name] for name in counts} == {
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
            }
        finally:
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
    from app.models import AccountEmailToken, Comment, Conversation, MediaAsset, Message, Post, Profile, SecurityEvent
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
                session.add_all([message, avatar_asset])
                await session.flush()
                profile.avatar_asset_id = avatar_asset.id
                await session.commit()
                comment_id = comment.id
                post_id = post.id
                message_id = message.id
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
