from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, status

from .contracts import (
    AIProvider,
    ConferencingProvider,
    EmailProvider,
    MediaProcessingProvider,
    ObjectStorageProvider,
    PaymentProvider,
    ProviderNotConfiguredError,
    RealtimeEventProvider,
)


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    email: str | None = None
    storage: str | None = None
    media_processing: str | None = None
    realtime: str | None = None
    conferencing: str | None = None
    payments: str | None = None
    ai: str | None = None
    storage_backend: str = "local"

    @classmethod
    def from_environment(cls) -> ProviderSettings:
        return cls(
            email=os.getenv("ME_YOU_EMAIL_PROVIDER"),
            storage=os.getenv("ME_YOU_STORAGE_PROVIDER"),
            media_processing=os.getenv("ME_YOU_MEDIA_PROCESSOR"),
            realtime=os.getenv("ME_YOU_REALTIME_PROVIDER"),
            conferencing=os.getenv("ME_YOU_CONFERENCING_PROVIDER"),
            payments=os.getenv("ME_YOU_PAYMENT_PROVIDER"),
            ai=os.getenv("ME_YOU_AI_PROVIDER"),
            storage_backend=os.getenv("STORAGE_BACKEND", "local").strip().lower(),
        )


@dataclass(slots=True)
class ProviderRegistry:
    settings: ProviderSettings
    email: EmailProvider | None = None
    storage: ObjectStorageProvider | None = None
    media_processing: MediaProcessingProvider | None = None
    realtime: RealtimeEventProvider | None = None
    conferencing: ConferencingProvider | None = None
    payments: PaymentProvider | None = None
    ai: AIProvider | None = None


def get_provider_registry() -> ProviderRegistry:
    settings = ProviderSettings.from_environment()
    from ..config import JWT_SECRET_KEY, S3_BUCKET, S3_ENDPOINT_URL, S3_REGION, STORAGE_LOCAL_DIR
    from .storage import LocalDiskStorageProvider, S3CompatibleStorageProvider

    storage: ObjectStorageProvider | None = None
    if settings.storage_backend == "local":
        storage = LocalDiskStorageProvider(STORAGE_LOCAL_DIR, JWT_SECRET_KEY)
    elif settings.storage_backend == "s3":
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        if access_key and secret_key and S3_BUCKET:
            storage = S3CompatibleStorageProvider(
                bucket=S3_BUCKET,
                region=S3_REGION,
                endpoint_url=S3_ENDPOINT_URL,
                access_key=access_key,
                secret_key=secret_key,
                session_token=os.getenv("AWS_SESSION_TOKEN"),
            )
    return ProviderRegistry(settings=settings, storage=storage)


def require_provider(registry: ProviderRegistry, capability: str):
    provider = getattr(registry, capability, None)
    if provider is None:
        raise ProviderNotConfiguredError(capability)
    return provider


def provider_or_503(registry: ProviderRegistry, capability: str):
    try:
        return require_provider(registry, capability)
    except ProviderNotConfiguredError:
        configured_provider = getattr(registry.settings, capability, None)
        message = (
            f"The configured {capability} provider adapter is unavailable"
            if configured_provider
            else f"The {capability} provider is not configured"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": message, "code": "provider_not_configured"},
            headers={"Retry-After": "300"},
        ) from None


def provider_not_configured_http_error(capability: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": f"The {capability} provider is not configured",
            "code": "provider_not_configured",
        },
        headers={"Retry-After": "300"},
    )