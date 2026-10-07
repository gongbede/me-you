from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterable
from uuid import UUID

from .contracts import StoredObjectMetadata, UploadIntent


class StorageTokenError(ValueError):
    pass


class StorageObjectTooLarge(ValueError):
    pass


def sniff_content_type(prefix: bytes) -> str | None:
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return "image/webp"
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if len(prefix) >= 8 and prefix[4:8] == b"ftyp":
        return "video/mp4"
    if prefix.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if prefix.startswith(b"OggS"):
        return "audio/ogg"
    if prefix.startswith(b"ID3") or (
        len(prefix) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0
    ):
        return "audio/mpeg"
    return None


class LocalDiskStorageProvider:
    name = "local"
    _key_pattern = re.compile(
        r"^users/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
    )

    def __init__(self, root: str | Path, signing_key: str):
        if len(signing_key) < 16:
            raise ValueError("Local storage signing key must be at least 16 characters")
        self.root = Path(root).expanduser().resolve()
        self.signing_key = signing_key.encode("utf-8")

    def _object_path(self, object_key: str) -> Path:
        match = self._key_pattern.fullmatch(object_key)
        if match is None or str(UUID(match.group(1))) != match.group(1) or str(UUID(match.group(2))) != match.group(2):
            raise StorageTokenError("Invalid storage object key")
        path = (self.root / match.group(1) / match.group(2)).resolve()
        if not path.is_relative_to(self.root):
            raise StorageTokenError("Invalid storage object key")
        return path

    def _token(self, purpose: str, object_key: str, expires_at: datetime, **values: object) -> str:
        payload = {
            "purpose": purpose,
            "object_key": object_key,
            "expires_at": int(expires_at.timestamp()),
            **values,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        signature = hmac.new(self.signing_key, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _decode_token(self, token: str, expected_purpose: str) -> dict:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = hmac.new(
                self.signing_key, encoded.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise StorageTokenError("Invalid storage URL")
            payload = json.loads(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            )
            self._object_path(payload["object_key"])
            if payload["purpose"] != expected_purpose:
                raise StorageTokenError("Invalid storage URL")
            if int(payload["expires_at"]) <= int(datetime.now(timezone.utc).timestamp()):
                raise StorageTokenError("Storage URL has expired")
            return payload
        except StorageTokenError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StorageTokenError("Invalid storage URL") from error

    async def create_upload_intent(
        self,
        *,
        object_key: str,
        content_type: str,
        max_bytes: int,
        expires_in_seconds: int,
    ) -> UploadIntent:
        self._object_path(object_key)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        token = self._token(
            "upload", object_key, expires_at, content_type=content_type, max_bytes=max_bytes
        )
        return UploadIntent(
            upload_url=f"/api/v1/media/local-upload/{token}",
            object_key=object_key,
            expires_at=expires_at,
            required_headers={"Content-Type": content_type},
        )

    async def accept_upload(
        self,
        token: str,
        content_type: str,
        chunks: AsyncIterable[bytes],
    ) -> tuple[str, int]:
        payload = self._decode_token(token, "upload")
        expected_type = str(payload["content_type"])
        max_bytes = int(payload["max_bytes"])
        if content_type.split(";", 1)[0].strip().lower() != expected_type:
            raise StorageTokenError("Content type does not match the upload intent")

        target = self._object_path(payload["object_key"])
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
        total = 0
        digest = hashlib.sha256()
        prefix = bytearray()
        try:
            with os.fdopen(descriptor, "wb") as output:
                async for chunk in chunks:
                    total += len(chunk)
                    if total > max_bytes:
                        raise StorageObjectTooLarge("Uploaded object exceeds its size limit")
                    if len(prefix) < 32:
                        prefix.extend(chunk[: 32 - len(prefix)])
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if total == 0:
                raise StorageTokenError("Uploaded object is empty")
            os.replace(temporary_name, target)
            metadata_path = target.with_suffix(".json")
            metadata_tmp = metadata_path.with_suffix(".json.tmp")
            metadata_tmp.write_text(
                json.dumps(
                    {
                        "content_type": expected_type,
                        "byte_size": total,
                        "checksum_sha256": digest.hexdigest(),
                        "detected_content_type": sniff_content_type(bytes(prefix)),
                    }
                ),
                encoding="utf-8",
            )
            os.replace(metadata_tmp, metadata_path)
            return str(payload["object_key"]), total
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    async def inspect_object(self, object_key: str) -> StoredObjectMetadata | None:
        target = self._object_path(object_key)
        if not target.is_file():
            return None
        metadata_path = target.with_suffix(".json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise StorageTokenError("Stored object metadata is unavailable") from error
        return StoredObjectMetadata(
            object_key=object_key,
            content_type=metadata["content_type"],
            byte_size=target.stat().st_size,
            checksum_sha256=metadata["checksum_sha256"],
            detected_content_type=metadata.get("detected_content_type"),
        )

    async def create_download_url(
        self,
        object_key: str,
        *,
        expires_in_seconds: int,
    ) -> str:
        self._object_path(object_key)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        token = self._token("download", object_key, expires_at)
        return f"/api/v1/media/local-download/{token}"

    async def resolve_download(self, token: str) -> tuple[Path, StoredObjectMetadata]:
        payload = self._decode_token(token, "download")
        object_key = str(payload["object_key"])
        metadata = await self.inspect_object(object_key)
        if metadata is None:
            raise FileNotFoundError(object_key)
        return self._object_path(object_key), metadata

    async def delete_object(self, object_key: str) -> None:
        target = self._object_path(object_key)
        for path in (target, target.with_suffix(".json")):
            try:
                await asyncio.to_thread(path.unlink)
            except FileNotFoundError:
                pass


class S3CompatibleStorageProvider:
    name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: str | None,
        access_key: str,
        secret_key: str,
        session_token: str | None = None,
    ):
        if not access_key or not secret_key:
            raise ValueError("S3 credentials must be supplied through environment variables")
        import boto3
        from botocore.config import Config

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            request = {"Bucket": self.bucket}
            region = self.client.meta.region_name
            if region and region != "us-east-1":
                request["CreateBucketConfiguration"] = {
                    "LocationConstraint": region
                }
            self.client.create_bucket(**request)

    async def create_upload_intent(
        self,
        *,
        object_key: str,
        content_type: str,
        max_bytes: int,
        expires_in_seconds: int,
    ) -> UploadIntent:
        await asyncio.to_thread(self._ensure_bucket)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "ContentType": content_type,
                "ContentLength": max_bytes,
            },
            ExpiresIn=expires_in_seconds,
        )
        return UploadIntent(
            upload_url=url,
            object_key=object_key,
            expires_at=expires_at,
            required_headers={"Content-Type": content_type},
        )

    def _inspect(self, object_key: str) -> StoredObjectMetadata | None:
        from botocore.exceptions import ClientError

        try:
            head = self.client.head_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        content_type = head.get("ContentType", "application/octet-stream").split(";", 1)[0].lower()
        result = self.client.get_object(
            Bucket=self.bucket,
            Key=object_key,
            Range="bytes=0-31",
        )
        prefix = result["Body"].read(32)
        result["Body"].close()
        return StoredObjectMetadata(
            object_key=object_key,
            content_type=content_type,
            byte_size=int(head["ContentLength"]),
            checksum_sha256=None,
            detected_content_type=sniff_content_type(prefix),
        )

    async def inspect_object(self, object_key: str) -> StoredObjectMetadata | None:
        return await asyncio.to_thread(self._inspect, object_key)

    async def create_download_url(
        self,
        object_key: str,
        *,
        expires_in_seconds: int,
    ) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=expires_in_seconds,
        )

    async def delete_object(self, object_key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.bucket, Key=object_key
        )