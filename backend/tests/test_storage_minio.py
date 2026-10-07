import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ConnectionClosedError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

from app.providers.storage import S3CompatibleStorageProvider


pytestmark = pytest.mark.minio


def test_s3_compatible_signed_transfer_against_minio():
    endpoint = os.getenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "me_you_local")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "me_you_local_secret")
    bucket = os.getenv("S3_BUCKET", "me-you-media-test")
    storage = S3CompatibleStorageProvider(
        bucket=bucket,
        region=os.getenv("S3_REGION", "us-east-1"),
        endpoint_url=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        session_token=os.getenv("AWS_SESSION_TOKEN"),
    )

    async def verify():
        try:
            data = b"\x89PNG\r\n\x1a\nminio-test-image"
            intent = await storage.create_upload_intent(
                object_key=f"users/{uuid4()}/{uuid4()}",
                content_type="image/png",
                max_bytes=len(data),
                expires_in_seconds=60,
            )
        except (
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            ReadTimeoutError,
        ) as error:
            pytest.skip(f"MinIO is not reachable or configured: {type(error).__name__}")

        async with httpx.AsyncClient() as client:
            uploaded = await client.put(
                intent.upload_url,
                content=data,
                headers=intent.required_headers,
            )
            assert uploaded.status_code == 200
            metadata = await storage.inspect_object(intent.object_key)
            assert metadata is not None
            assert metadata.byte_size == len(data)
            assert metadata.detected_content_type == "image/png"
            download_url = await storage.create_download_url(
                intent.object_key, expires_in_seconds=60
            )
            downloaded = await client.get(download_url)
            assert downloaded.status_code == 200
            assert downloaded.content == data
        await storage.delete_object(intent.object_key)

    asyncio.run(verify())