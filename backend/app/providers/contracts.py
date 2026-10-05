from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class ProviderNotConfiguredError(RuntimeError):
    def __init__(self, capability: str):
        self.capability = capability
        super().__init__(f"No provider is configured for {capability}")


@dataclass(frozen=True, slots=True)
class EmailRequest:
    recipient: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailProvider(Protocol):
    async def send(self, request: EmailRequest) -> str: ...


@dataclass(frozen=True, slots=True)
class UploadIntent:
    upload_url: str
    object_key: str
    expires_at: datetime
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class StoredObjectMetadata:
    object_key: str
    content_type: str
    byte_size: int
    checksum_sha256: str | None


class ObjectStorageProvider(Protocol):
    async def create_upload_intent(
        self,
        *,
        object_key: str,
        content_type: str,
        max_bytes: int,
        expires_in_seconds: int,
    ) -> UploadIntent: ...

    async def inspect_object(self, object_key: str) -> StoredObjectMetadata | None: ...

    async def create_download_url(
        self,
        object_key: str,
        *,
        expires_in_seconds: int,
    ) -> str: ...

    async def delete_object(self, object_key: str) -> None: ...


class RealtimeEventProvider(Protocol):
    async def publish(self, *, topic: str, event_type: str, payload: dict[str, Any]) -> None: ...


class MediaProcessingProvider(Protocol):
    async def request_processing(
        self,
        *,
        object_key: str,
        media_type: str,
        callback_id: str,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class ConferenceRoom:
    provider_room_id: str
    join_url: str
    expires_at: datetime | None


class ConferencingProvider(Protocol):
    async def create_room(self, *, room_key: str, title: str) -> ConferenceRoom: ...

    async def close_room(self, provider_room_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class CheckoutRequest:
    customer_id: str
    amount_minor: int
    currency: str
    idempotency_key: str
    success_url: str
    cancel_url: str


class PaymentProvider(Protocol):
    async def create_checkout(self, request: CheckoutRequest) -> str: ...

    async def refund(self, *, provider_payment_id: str, idempotency_key: str) -> str: ...

    async def verify_webhook(self, *, body: bytes, signature: str) -> dict[str, Any]: ...


class AIProvider(Protocol):
    async def generate(
        self,
        *,
        task: str,
        input_text: str,
        options: dict[str, Any],
    ) -> dict[str, Any]: ...