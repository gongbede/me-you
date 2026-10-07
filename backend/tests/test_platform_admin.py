import unittest
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_postgres_session
from app.models import Activity, User
from app.permissions import require_platform_admin
from app.routes.platform_admin import list_platform_users, router, set_account_active


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class AdminSession:
    def __init__(self, scalar_values=None, scalar_rows=None, commit_error=None):
        self.scalar_values = list(scalar_values or [])
        self.scalar_rows = list(scalar_rows or [])
        self.commit_error = commit_error
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return None

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, statement):
        self.statements.append(statement)
        return Rows(self.scalar_rows.pop(0) if self.scalar_rows else [])

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class PlatformAdminTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.platform_admin = User(
            id=uuid.uuid4(), username="global", email="global@example.com",
            password_hash="hash", is_platform_admin=True, is_active=True,
            token_version=0, created_at=now,
        )
        self.institution_admin = User(
            id=uuid.uuid4(), username="school-admin", email="school@example.com",
            password_hash="hash", is_platform_admin=False, is_active=True,
            token_version=0, created_at=now,
        )
        self.user = User(
            id=uuid.uuid4(), username="member", email="member@example.com",
            password_hash="hash", is_platform_admin=False, is_active=True,
            token_version=0, created_at=now,
        )

    async def test_institution_admin_and_normal_user_are_not_platform_admins(self):
        for user in (self.user, self.institution_admin):
            with self.subTest(user=user.username), self.assertRaises(HTTPException) as error:
                require_platform_admin(user)
            self.assertEqual(error.exception.status_code, 403)
        self.assertIs(require_platform_admin(self.platform_admin), self.platform_admin)

    async def test_platform_admin_has_global_user_scope_without_institution_filter(self):
        session = AdminSession(scalar_rows=[[self.user, self.institution_admin]])
        response = await list_platform_users(self.platform_admin, session, offset=0, limit=10)
        self.assertEqual({row["id"] for row in response}, {str(self.user.id), str(self.institution_admin.id)})
        statement = str(session.statements[0].compile())
        self.assertNotIn("institution_memberships", statement)

    async def test_institution_admin_cannot_access_platform_user_list(self):
        session = AdminSession()
        with self.assertRaises(HTTPException) as error:
            await list_platform_users(self.institution_admin, session)
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(session.statements, [])

    async def test_platform_deactivation_revokes_sessions_and_records_activity(self):
        session = AdminSession([False, self.user], [[]])
        result = await set_account_active(self.user.id, False, self.platform_admin, session)
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.token_version, 1)
        self.assertFalse(result["is_active"])
        self.assertTrue(session.committed)
        event = next(value for value in session.added if isinstance(value, Activity))
        self.assertEqual(event.event_type, "platform.account.deactivated")
        self.assertEqual(event.target_id, self.user.id)

    async def test_platform_admin_cannot_deactivate_final_platform_admin(self):
        session = AdminSession(
            [True, self.platform_admin],
            [[], [self.platform_admin.id]],
        )
        with self.assertRaises(HTTPException) as error:
            await set_account_active(self.platform_admin.id, False, self.platform_admin, session)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(session.committed)
        self.assertEqual(session.added, [])

    async def test_account_deactivation_requires_group_owner_transfer(self):
        group_id = uuid.uuid4()
        session = AdminSession(
            [False, self.user.id],
            [[], [group_id]],
        )
        with self.assertRaises(HTTPException) as error:
            await set_account_active(self.user.id, False, self.platform_admin, session)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("Transfer group ownership", error.exception.detail)
        self.assertFalse(session.committed)

    async def test_commit_failure_rolls_back_admin_activity_and_status_change(self):
        session = AdminSession(
            [False, self.user],
            [[]],
            commit_error=RuntimeError("database failure"),
        )
        with self.assertRaises(RuntimeError):
            await set_account_active(self.user.id, False, self.platform_admin, session)
        self.assertTrue(session.rolled_back)

    async def test_platform_admin_endpoint_requires_authentication(self):
        app = FastAPI()
        app.include_router(router)

        async def override_session():
            yield AdminSession()

        app.dependency_overrides[get_postgres_session] = override_session
        with TestClient(app) as client:
            response = client.get("/platform-admin/users")
        app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()