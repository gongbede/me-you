import asyncio
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from starlette.requests import Request

from app.database import get_postgres_session
from app.main import app
from app.models import (
    Course,
    Department,
    Enrollment,
    Exercise,
    ExerciseSubmission,
    Faculty,
    Institution,
    InstitutionMembership,
    Lesson,
    Student,
    User,
)
from app.security import get_current_postgres_user


pytestmark = pytest.mark.postgres
BACKEND = Path(__file__).parents[1]


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

            app.dependency_overrides[get_postgres_session] = test_database_dependency
            app.dependency_overrides[get_current_postgres_user] = test_user_dependency
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                responses = await asyncio.gather(
                    *(
                        client.patch(
                            f"/institutions/{institution.id}/members/{memberships[index].id}",
                            headers={"x-test-user": str(administrators[index].id)},
                            json={"role": "TEACHER"},
                        )
                        for index in range(2)
                    )
                )

            async with session_factory() as session:
                persisted_roles = list(
                    (
                        await session.scalars(
                            select(InstitutionMembership.role).where(
                                InstitutionMembership.institution_id == institution.id,
                            )
                        )
                    ).all()
                )
                remaining_admins = persisted_roles.count("ADMIN")
            status_codes = sorted(response.status_code for response in responses)
            assert status_codes == [200, 409] and remaining_admins == 1, (
                f"Concurrent demotions returned HTTP {status_codes}; "
                f"roles returned {[response.json().get('role') for response in responses]}; "
                f"persisted roles are {persisted_roles}"
            )
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
