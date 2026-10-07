import unittest
import uuid
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.database import get_postgres_session
from app.models import MediaAsset, User
from app.providers import (
    LocalDiskStorageProvider,
    ProviderRegistry,
    ProviderSettings,
    StoredObjectMetadata,
    UploadIntent,
    get_provider_registry,
)
from app.routes.media import (
    complete_media_upload,
    create_media_download_url,
    create_media_upload_intent,
    router,
)
from app.schemas import MediaUploadIntentCreate


class Rows:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class MediaSession:
    def __init__(self, scalar_values=None, commit_error=None):
        self.scalar_values = list(scalar_values or [])
        self.commit_error = commit_error
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _statement):
        return Rows([])

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        if self.commit_error:
            raise self.commit_error
        self.committed = True

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rolled_back = True


class FakeStorage:
    def __init__(self):
        self.object_key = None
        self.expected_size = None
        self.detected_content_type = "image/png"

    async def create_upload_intent(self, *, object_key, content_type, max_bytes, expires_in_seconds):
        self.object_key = object_key
        return UploadIntent(
            upload_url="https://storage.example.test/upload",
            object_key=object_key,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds - 1),
            required_headers={"Content-Type": content_type},
        )

    async def inspect_object(self, object_key):
        return StoredObjectMetadata(
            object_key=object_key,
            content_type="image/png",
            byte_size=self.expected_size or 512,
            checksum_sha256="a" * 64,
            detected_content_type=self.detected_content_type,
        )

    async def create_download_url(self, object_key, *, expires_in_seconds):
        return "https://storage.example.test/download"

    async def delete_object(self, object_key):
        return None


class MediaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = User(id=uuid.uuid4(), username="owner", email="owner@example.com", password_hash="hash")
        self.other = User(id=uuid.uuid4(), username="other", email="other@example.com", password_hash="hash")
        self.storage = FakeStorage()
        self.providers = ProviderRegistry(settings=ProviderSettings(storage="fake"), storage=self.storage)
        self.request = MediaUploadIntentCreate(
            purpose="PROFILE_IMAGE",
            content_type="image/png",
            byte_size=512,
            original_filename="avatar.png",
        )

    async def test_upload_intent_uses_provider_and_creates_private_asset(self):
        session = MediaSession()
        response = await create_media_upload_intent(
            self.request, self.user, session, self.providers
        )
        self.assertEqual(response["upload_url"], "https://storage.example.test/upload")
        asset = session.added[0]
        self.assertIsInstance(asset, MediaAsset)
        self.assertEqual(asset.owner_id, self.user.id)
        self.assertEqual(asset.status, "UPLOAD_PENDING")
        self.assertTrue(session.committed)
        self.assertNotIn("storage_key", response["asset"])

    async def test_content_type_size_and_filename_are_validated(self):
        invalid_type = MediaUploadIntentCreate(
            purpose="PROFILE_IMAGE",
            content_type="image/svg+xml",
            byte_size=512,
            original_filename="avatar.svg",
        )
        with self.assertRaises(HTTPException) as content_type_error:
            await create_media_upload_intent(
                invalid_type, self.user, MediaSession(), self.providers
            )
        self.assertEqual(content_type_error.exception.status_code, 422)
        with self.assertRaises(ValidationError):
            MediaUploadIntentCreate(
                purpose="PROFILE_IMAGE",
                content_type="image/png",
                byte_size=512,
                original_filename="../avatar.png",
            )
        request = MediaUploadIntentCreate(
            purpose="PROFILE_IMAGE",
            content_type="image/png",
            byte_size=11_000_000,
            original_filename="avatar.png",
        )
        with self.assertRaises(HTTPException) as error:
            await create_media_upload_intent(request, self.user, MediaSession(), self.providers)
        self.assertEqual(error.exception.status_code, 413)

    async def test_user_storage_quota_is_enforced_before_upload_intent_creation(self):
        with patch("app.routes.media.MEDIA_USER_QUOTA_BYTES", 100):
            with self.assertRaises(HTTPException) as error:
                await create_media_upload_intent(
                    self.request, self.user, MediaSession(), self.providers
                )
        self.assertEqual(error.exception.status_code, 413)
        self.assertIn("quota", error.exception.detail)

    async def test_unconfigured_storage_fails_with_503_without_creating_asset(self):
        session = MediaSession()
        with self.assertRaises(HTTPException) as error:
            await create_media_upload_intent(
                self.request,
                self.user,
                session,
                ProviderRegistry(settings=ProviderSettings()),
            )
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(session.added, [])

    async def test_completion_checks_actual_provider_metadata_before_ready(self):
        asset = MediaAsset(
            id=uuid.uuid4(), owner_id=self.user.id, purpose="PROFILE_IMAGE",
            status="UPLOAD_PENDING", storage_provider="fake", storage_key="object-key",
            content_type="image/png", byte_size=512, original_filename="avatar.png",
            upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        session = MediaSession([asset])
        response = await complete_media_upload(asset.id, self.user, session, self.providers)
        self.assertEqual(response["status"], "READY")
        self.assertEqual(asset.checksum_sha256, "a" * 64)
        self.assertTrue(session.committed)

    async def test_completion_rejects_spoofed_image_content(self):
        self.storage.detected_content_type = "image/jpeg"
        asset = MediaAsset(
            id=uuid.uuid4(), owner_id=self.user.id, purpose="PROFILE_IMAGE",
            status="UPLOAD_PENDING", storage_provider="fake", storage_key="object-key",
            content_type="image/png", byte_size=512, original_filename="avatar.png",
            upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        session = MediaSession([asset])
        with self.assertRaises(HTTPException) as error:
            await complete_media_upload(asset.id, self.user, session, self.providers)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(asset.status, "FAILED")

    async def test_cross_owner_lookup_is_hidden_and_ready_asset_download_is_signed(self):
        asset = MediaAsset(
            id=uuid.uuid4(), owner_id=self.user.id, purpose="PROFILE_IMAGE",
            status="READY", storage_provider="fake", storage_key="object-key",
            content_type="image/png", byte_size=512, original_filename="avatar.png",
            upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with self.assertRaises(HTTPException) as error:
            await create_media_download_url(asset.id, self.other, MediaSession([None]), self.providers)
        self.assertEqual(error.exception.status_code, 404)

        response = await create_media_download_url(
            asset.id, self.user, MediaSession([asset]), self.providers
        )
        self.assertEqual(response["download_url"], "https://storage.example.test/download")
        self.assertEqual(response["expires_in_seconds"], 300)

    async def test_media_endpoint_requires_authentication(self):
        app = FastAPI()
        app.include_router(router)

        async def override_session():
            yield MediaSession()

        app.dependency_overrides[get_postgres_session] = override_session
        with TestClient(app) as client:
            response = client.get("/media")
        app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 401)

    async def test_local_signed_upload_and_expired_download_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = LocalDiskStorageProvider(directory, "a-long-test-key-for-local-media")
            registry = ProviderRegistry(
                settings=ProviderSettings(storage="local"), storage=storage
            )
            app = FastAPI()
            app.include_router(router)
            app.dependency_overrides[get_provider_registry] = lambda: registry
            upload = await storage.create_upload_intent(
                object_key=f"users/{self.user.id}/{uuid.uuid4()}",
                content_type="image/png",
                max_bytes=128,
                expires_in_seconds=60,
            )
            token = urlparse(upload.upload_url).path.rsplit("/", 1)[-1]
            expired_url = await storage.create_download_url(
                upload.object_key, expires_in_seconds=-1
            )
            expired_token = urlparse(expired_url).path.rsplit("/", 1)[-1]
            with TestClient(app) as client:
                response = client.put(
                    f"/media/local-upload/{token}",
                    content=b"not-a-png",
                    headers={"Content-Type": "image/png"},
                )
                expired = client.get(f"/media/local-download/{expired_token}")
            metadata = await storage.inspect_object(upload.object_key)
            app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(metadata.detected_content_type)
        self.assertEqual(expired.status_code, 403)


if __name__ == "__main__":
    unittest.main()