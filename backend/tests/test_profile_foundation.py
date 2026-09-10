import uuid
from datetime import datetime, timedelta, timezone
import unittest

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pwdlib import PasswordHash

from app.models import Profile, User
from app.routes.account import get_my_account
from app.routes.login import login
from app.routes.me import get_me
from app.routes.profile import create_profile, get_my_profile, update_my_profile
from app.routes.registration import register
from app.schemas import CreateProfile, LoginRequest, UpdateProfile, UserCreate
from app.security import create_access_token, decode_access_token, get_current_postgres_user


class FakeSession:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [])
        self.pending = None
        self.profiles = {}
        self.rollback_count = 0

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add(self, value):
        self.pending = value

    async def commit(self):
        if self.pending is not None:
            if hasattr(self.pending, "id") and getattr(self.pending, "id", None) is None:
                self.pending.id = uuid.uuid4()
            now = datetime.now(timezone.utc)
            if getattr(self.pending, "created_at", None) is None:
                self.pending.created_at = now
            if hasattr(self.pending, "updated_at") and self.pending.updated_at is None:
                self.pending.updated_at = now
            if hasattr(self.pending, "user_id"):
                self.profiles[self.pending.user_id] = self.pending

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rollback_count += 1


class ProfileFoundationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(
            id=uuid.uuid4(),
            username="mentor",
            email="mentor@example.com",
            password_hash=PasswordHash.recommended().hash("correct-password"),
        )

    async def test_registration_and_login_remain_postgres_backed(self):
        registration_session = FakeSession([None])
        registered = await register(
            UserCreate(
                username="new-user",
                email="new-user@example.com",
                password="correct-password",
            ),
            registration_session,
        )
        self.assertEqual(registered["username"], "new-user")
        self.assertNotIn("password_hash", registered)
        self.assertNotEqual(registration_session.pending.password_hash, "correct-password")

        login_response = await login(
            LoginRequest(email=self.user.email, password="correct-password"),
            FakeSession([self.user]),
        )
        self.assertEqual(login_response["token_type"], "bearer")
        self.assertEqual(login_response["id"], str(self.user.id))
        self.assertEqual(decode_access_token(login_response["access_token"])["sub"], str(self.user.id))

    async def test_authentication_accepts_valid_token_and_rejects_missing_or_invalid(self):
        valid_session = FakeSession([self.user])
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token(self.user.id),
        )
        authenticated = await get_current_postgres_user(credentials, valid_session)
        self.assertIs(authenticated, self.user)

        with self.assertRaises(HTTPException) as missing_error:
            await get_current_postgres_user(None, valid_session)
        self.assertEqual(missing_error.exception.status_code, 401)

        invalid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid-token",
        )
        with self.assertRaises(HTTPException) as invalid_error:
            await get_current_postgres_user(invalid_credentials, valid_session)
        self.assertEqual(invalid_error.exception.status_code, 401)

    async def test_authentication_rejects_expired_invalid_uuid_and_missing_user(self):
        expired_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token(self.user.id, timedelta(seconds=-1)),
        )
        with self.assertRaises(HTTPException) as expired_error:
            await get_current_postgres_user(expired_credentials, FakeSession([self.user]))
        self.assertEqual(expired_error.exception.status_code, 401)

        invalid_uuid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token("not-a-uuid"),
        )
        with self.assertRaises(HTTPException) as uuid_error:
            await get_current_postgres_user(invalid_uuid_credentials, FakeSession())
        self.assertEqual(uuid_error.exception.status_code, 401)

        missing_user_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token(self.user.id),
        )
        with self.assertRaises(HTTPException) as missing_user_error:
            await get_current_postgres_user(missing_user_credentials, FakeSession([None]))
        self.assertEqual(missing_user_error.exception.status_code, 401)

    async def test_me_returns_the_authenticated_postgres_user_safely(self):
        response = await get_me(self.user)
        self.assertEqual(response["id"], str(self.user.id))
        self.assertEqual(response["username"], self.user.username)
        self.assertEqual(response["email"], self.user.email)
        self.assertEqual(response["created_at"], self.user.created_at)
        self.assertNotIn("password_hash", response)

    async def test_profile_creation_and_duplicate_are_handled(self):
        session = FakeSession([None])
        created = await create_profile(
            CreateProfile(display_name="Mentor"),
            self.user,
            session,
        )
        self.assertEqual(created["user_id"], str(self.user.id))
        self.assertEqual(created["display_name"], "Mentor")
        self.assertNotIn("password_hash", created)

        duplicate_session = FakeSession([session.pending])
        with self.assertRaises(HTTPException) as duplicate_error:
            await create_profile(CreateProfile(display_name="Other"), self.user, duplicate_session)
        self.assertEqual(duplicate_error.exception.status_code, 409)

    async def test_profile_retrieval_and_missing_profile(self):
        profile = Profile(user_id=self.user.id, display_name="Mentor")
        found = await get_my_profile(self.user, FakeSession([profile]))
        self.assertEqual(found["display_name"], "Mentor")
        self.assertNotIn("password_hash", found)

        with self.assertRaises(HTTPException) as missing_error:
            await get_my_profile(self.user, FakeSession([None]))
        self.assertEqual(missing_error.exception.status_code, 404)

    async def test_profile_partial_update_changes_updated_at(self):
        old_timestamp = datetime.now(timezone.utc) - timedelta(minutes=1)
        profile = Profile(
            user_id=self.user.id,
            display_name="Mentor",
            bio="Original bio",
            created_at=old_timestamp,
            updated_at=old_timestamp,
        )
        updated = await update_my_profile(
            UpdateProfile(bio="Updated bio"),
            self.user,
            FakeSession([profile]),
        )
        self.assertEqual(updated["display_name"], "Mentor")
        self.assertEqual(updated["bio"], "Updated bio")
        self.assertGreater(updated["updated_at"], old_timestamp)

    async def test_profile_update_cannot_change_account_fields(self):
        profile = Profile(user_id=self.user.id, display_name="Mentor")
        original_password_hash = self.user.password_hash
        update_data = UpdateProfile.model_validate(
            {
                "id": str(uuid.uuid4()),
                "user_id": str(uuid.uuid4()),
                "username": "changed",
                "email": "changed@example.com",
                "password": "changed-password",
                "created_at": datetime.now(timezone.utc),
            }
        )
        await update_my_profile(update_data, self.user, FakeSession([profile]))
        self.assertEqual(self.user.id, profile.user_id)
        self.assertEqual(self.user.username, "mentor")
        self.assertEqual(self.user.email, "mentor@example.com")
        self.assertEqual(self.user.password_hash, original_password_hash)
        self.assertNotIn("username", update_data.model_dump())
        self.assertNotIn("email", update_data.model_dump())
        self.assertNotIn("id", update_data.model_dump())
        self.assertNotIn("user_id", update_data.model_dump())
        self.assertNotIn("password", update_data.model_dump())
        self.assertNotIn("created_at", update_data.model_dump())

    async def test_account_response_is_public_only(self):
        response = await get_my_account(self.user, FakeSession())
        self.assertEqual(response["id"], str(self.user.id))
        self.assertEqual(response["username"], self.user.username)
        self.assertEqual(response["email"], self.user.email)
        self.assertNotIn("password_hash", response)
        self.assertNotIn("JWT_SECRET_KEY", response)


if __name__ == "__main__":
    unittest.main()
