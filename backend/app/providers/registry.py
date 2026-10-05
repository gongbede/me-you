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
    return ProviderRegistry(settings=ProviderSettings.from_environment())


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