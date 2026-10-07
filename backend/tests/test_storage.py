import asyncio
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from moto import mock_aws

from app.providers.storage import (
    LocalDiskStorageProvider,
    S3CompatibleStorageProvider,
    StorageObjectTooLarge,
    StorageTokenError,
    sniff_content_type,
)


class LocalDiskStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.storage = LocalDiskStorageProvider(
            self.temporary_directory.name, "test-signing-key-long-enough"
        )
        self.object_key = f"users/{uuid4()}/{uuid4()}"

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    async def test_signed_upload_streams_to_safe_key_and_inspects_real_metadata(self):
        intent = await self.storage.create_upload_intent(
            object_key=self.object_key,
            content_type="image/png",
            max_bytes=64,
            expires_in_seconds=60,
        )
        token = urlparse(intent.upload_url).path.rsplit("/", 1)[-1]
        image = b"\x89PNG\r\n\x1a\n" + b"image-bytes"

        async def chunks():
            yield image[:5]
            yield image[5:]

        self.assertEqual(
            await self.storage.accept_upload(token, "image/png", chunks()),
            (self.object_key, len(image)),
        )
        metadata = await self.storage.inspect_object(self.object_key)
        self.assertEqual(metadata.byte_size, len(image))
        self.assertEqual(metadata.detected_content_type, "image/png")
        self.assertTrue((Path(self.temporary_directory.name) / self.object_key.split("/")[1] / self.object_key.split("/")[2]).is_file())

    async def test_upload_rejects_oversize_and_wrong_declared_type(self):
        intent = await self.storage.create_upload_intent(
            object_key=self.object_key,
            content_type="image/png",
            max_bytes=4,
            expires_in_seconds=60,
        )
        token = urlparse(intent.upload_url).path.rsplit("/", 1)[-1]

        async def oversized():
            yield b"12345"

        with self.assertRaises(StorageObjectTooLarge):
            await self.storage.accept_upload(token, "image/png", oversized())
        with self.assertRaises(StorageTokenError):
            await self.storage.accept_upload(token, "image/jpeg", oversized())

    async def test_paths_and_expired_download_tokens_are_rejected(self):
        with self.assertRaises(StorageTokenError):
            await self.storage.inspect_object("../../etc/passwd")
        expired_url = await self.storage.create_download_url(
            self.object_key, expires_in_seconds=-1
        )
        token = urlparse(expired_url).path.rsplit("/", 1)[-1]
        with self.assertRaises(StorageTokenError):
            await self.storage.resolve_download(token)

    def test_content_type_sniffer_recognizes_and_rejects_signatures(self):
        self.assertEqual(sniff_content_type(b"\xff\xd8\xffrest"), "image/jpeg")
        self.assertEqual(sniff_content_type(b"RIFF0000WEBP"), "image/webp")
        self.assertIsNone(sniff_content_type(b"not-an-image"))


def test_s3_adapter_presigns_inspects_and_deletes_with_moto():
    with mock_aws():
        storage = S3CompatibleStorageProvider(
            bucket="media-test",
            region="us-east-1",
            endpoint_url=None,
            access_key="test-access-key",
            secret_key="test-secret-key",
        )

        async def verify():
            object_key = f"users/{uuid4()}/{uuid4()}"
            intent = await storage.create_upload_intent(
                object_key=object_key,
                content_type="image/png",
                max_bytes=512,
                expires_in_seconds=60,
            )
            assert "X-Amz-Signature" in intent.upload_url
            assert "X-Amz-Expires=60" in intent.upload_url
            image = b"\x89PNG\r\n\x1a\nmock-image"
            storage.client.put_object(
                Bucket="media-test",
                Key=object_key,
                Body=image,
                ContentType="image/png",
            )
            metadata = await storage.inspect_object(object_key)
            assert metadata.byte_size == len(image)
            assert metadata.content_type == "image/png"
            assert metadata.detected_content_type == "image/png"
            download_url = await storage.create_download_url(
                object_key, expires_in_seconds=45
            )
            assert "X-Amz-Signature" in download_url
            assert "X-Amz-Expires=45" in download_url
            await storage.delete_object(object_key)
            assert await storage.inspect_object(object_key) is None

        asyncio.run(verify())


if __name__ == "__main__":
    unittest.main()