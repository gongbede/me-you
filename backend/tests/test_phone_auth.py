import asyncio
import logging

import pytest
from fastapi import HTTPException

from app.providers.sms import ConsoleSMSProvider, get_sms_provider
from app.routes.auth_phone import PhoneCodeRequest, _check_request_limits, hash_phone_code


def test_phone_code_is_hmac_hashed():
    code_hash = hash_phone_code("+12025550111", "012345")

    assert len(code_hash) == 64
    assert code_hash != "012345"
    assert code_hash != hash_phone_code("+12025550112", "012345")


def test_phone_number_is_normalized_to_e164():
    assert PhoneCodeRequest(phone_number="+1 (202) 555-0111").phone_number == "+12025550111"

    with pytest.raises(ValueError):
        PhoneCodeRequest(phone_number="2025550111")


def test_console_provider_only_sends_in_development(caplog, monkeypatch):
    provider = ConsoleSMSProvider()
    monkeypatch.setenv("ME_YOU_ENV", "development")

    with caplog.at_level(logging.INFO, logger="me_you.sms"):
        asyncio.run(provider.send_code(phone_number="+12025550111", code="012345"))
    assert "012345" in caplog.text

    monkeypatch.setenv("ME_YOU_ENV", "production")
    with pytest.raises(HTTPException) as error:
        asyncio.run(provider.send_code(phone_number="+12025550111", code="012345"))
    assert error.value.status_code == 503


def test_sms_provider_is_unavailable_in_production_when_unconfigured(monkeypatch):
    monkeypatch.setenv("ME_YOU_ENV", "production")
    monkeypatch.delenv("ME_YOU_SMS_PROVIDER", raising=False)

    with pytest.raises(HTTPException) as error:
        get_sms_provider()
    assert error.value.status_code == 503


@pytest.mark.parametrize("counts", [(6, 1), (1, 6)])
def test_phone_code_requests_are_limited_by_phone_and_ip(counts):
    class TestLimiter:
        def __init__(self):
            self.counts = iter(counts)
            self.scopes = []

        async def increment(self, scope, _key, _window_seconds):
            self.scopes.append(scope)
            return next(self.counts), 30

    limiter = TestLimiter()
    with pytest.raises(HTTPException) as error:
        asyncio.run(_check_request_limits(limiter, "+12025550111", "192.0.2.1"))
    assert error.value.status_code == 429
    assert limiter.scopes == ["phone:request:number", "phone:request:ip"]