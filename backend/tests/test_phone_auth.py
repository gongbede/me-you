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
    monkeypatch.setenv("ME_YOU_SMS_DEV_LOG", "true")

    with caplog.at_level(logging.INFO, logger="me_you.sms"):
        asyncio.run(provider.send_code(phone_number="+12025550111", code="012345"))
    assert "012345" in caplog.text

    caplog.clear()
    monkeypatch.setenv("ME_YOU_ENV", "production")
    with pytest.raises(HTTPException) as error:
        asyncio.run(provider.send_code(phone_number="+12025550111", code="012345"))
    assert error.value.status_code == 503
    assert "012345" not in caplog.text


def test_console_provider_never_logs_without_explicit_development_opt_in(caplog, monkeypatch):
    provider = ConsoleSMSProvider()
    monkeypatch.setenv("ME_YOU_ENV", "development")
    monkeypatch.delenv("ME_YOU_SMS_DEV_LOG", raising=False)

    with caplog.at_level(logging.INFO, logger="me_you.sms"):
        result = asyncio.run(provider.send_code(phone_number="+12025550111", code="012345"))

    assert result is None
    assert "012345" not in caplog.text
    monkeypatch.setenv("ME_YOU_SMS_DEV_LOG", "false")
    with caplog.at_level(logging.INFO, logger="me_you.sms"):
        asyncio.run(provider.send_code(phone_number="+12025550111", code="678901"))
    assert "678901" not in caplog.text


def test_sms_provider_is_unavailable_in_production_when_unconfigured(monkeypatch):
    monkeypatch.setenv("ME_YOU_ENV", "production")
    monkeypatch.delenv("ME_YOU_SMS_PROVIDER", raising=False)

    with pytest.raises(HTTPException) as error:
        get_sms_provider()
    assert error.value.status_code == 503


@pytest.mark.parametrize("provider_name", ["", "console"])
def test_production_never_falls_back_to_console_sms(provider_name, monkeypatch, caplog):
    monkeypatch.setenv("ME_YOU_ENV", "production")
    monkeypatch.setenv("ME_YOU_SMS_DEV_LOG", "true")
    if provider_name:
        monkeypatch.setenv("ME_YOU_SMS_PROVIDER", provider_name)
    else:
        monkeypatch.delenv("ME_YOU_SMS_PROVIDER", raising=False)

    with caplog.at_level(logging.INFO, logger="me_you.sms"):
        with pytest.raises(HTTPException) as error:
            get_sms_provider()

    assert error.value.status_code == 503
    assert "012345" not in caplog.text


def test_production_real_sms_stub_returns_503_from_both_phone_endpoints(monkeypatch):
    from starlette.requests import Request

    import app.routes.auth_phone as auth_phone

    monkeypatch.setenv("ME_YOU_ENV", "production")
    monkeypatch.setenv("ME_YOU_SMS_PROVIDER", "real")
    provider = get_sms_provider()
    request = Request({
        "type": "http", "method": "POST", "scheme": "https",
        "path": "/auth/phone/request", "raw_path": b"/auth/phone/request",
        "query_string": b"", "headers": [],
        "client": ("192.0.2.10", 1234), "server": ("example.test", 443),
    })

    async def verify():
        with pytest.raises(HTTPException) as request_error:
            await auth_phone.request_phone_code(
                PhoneCodeRequest(phone_number="+12025550111"), request,
                object(), provider, None,
            )
        with pytest.raises(HTTPException) as verify_error:
            await auth_phone.verify_phone_code(
                auth_phone.PhoneCodeVerify(phone_number="+12025550111", code="012345"),
                object(), provider,
            )
        assert request_error.value.status_code == verify_error.value.status_code == 503
        assert "not configured" in str(request_error.value.detail)
        assert "not configured" in str(verify_error.value.detail)

    asyncio.run(verify())


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