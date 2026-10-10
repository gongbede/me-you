from __future__ import annotations

import logging
import os
from typing import Protocol

from fastapi import HTTPException, status

from .contracts import ProviderNotConfiguredError


logger = logging.getLogger("me_you.sms")


class SMSProvider(Protocol):
    async def send_code(self, *, phone_number: str, code: str) -> None: ...


class ConsoleSMSProvider:
    async def send_code(self, *, phone_number: str, code: str) -> None:
        if os.getenv("ME_YOU_ENV", "").lower() != "development":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Console SMS is available only in development",
            )
        if os.getenv("ME_YOU_SMS_DEV_LOG", "false").strip().lower() == "true":
            logger.info("Development SMS code for %s: %s", phone_number, code)


class RealSMSProvider:
    async def send_code(self, *, phone_number: str, code: str) -> None:
        raise ProviderNotConfiguredError("sms")


def get_sms_provider() -> SMSProvider:
    environment = os.getenv("ME_YOU_ENV", "development").lower()
    provider = os.getenv("ME_YOU_SMS_PROVIDER", "").strip().lower()
    if not provider and environment == "development":
        provider = "console"
    if provider == "console":
        if environment != "development":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Console SMS is available only in development",
            )
        return ConsoleSMSProvider()
    if provider == "real":
        return RealSMSProvider()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="SMS sign-in is not configured",
    )