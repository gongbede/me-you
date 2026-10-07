import hashlib
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as app_main
from app.rate_limit import client_ip, fixed_window_start, hash_rate_limit_key


def make_request(forwarded_for=None):
    headers = []
    if forwarded_for:
        headers.append((b"x-forwarded-for", forwarded_for.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": headers,
            "client": ("192.0.2.10", 1234),
            "server": ("test", 80),
        }
    )


def test_rate_limit_keys_are_sha256_and_windows_are_aligned():
    assert hash_rate_limit_key("person@example.com") == hashlib.sha256(
        b"person@example.com"
    ).hexdigest()
    now = datetime.fromtimestamp(1_700_000_123, timezone.utc)
    assert fixed_window_start(now, 60) == datetime.fromtimestamp(1_700_000_100, timezone.utc)


def test_client_ip_ignores_forwarded_header_unless_proxy_hops_are_trusted():
    request = make_request("198.51.100.7, 203.0.113.8")
    with patch("app.rate_limit.TRUSTED_PROXY_COUNT", 0):
        assert client_ip(request) == "192.0.2.10"
    with patch("app.rate_limit.TRUSTED_PROXY_COUNT", 1):
        assert client_ip(request) == "203.0.113.8"
    with patch("app.rate_limit.TRUSTED_PROXY_COUNT", 2):
        assert client_ip(request) == "198.51.100.7"


def test_api_rate_limit_returns_retry_after_and_exempts_health_routes():
    class MemoryLimiter:
        def __init__(self):
            self.counts = {}

        async def increment(self, scope, key, window_seconds):
            index = (scope, key)
            self.counts[index] = self.counts.get(index, 0) + 1
            return self.counts[index], 17

    limiter = MemoryLimiter()
    limits = dict(app_main.RATE_LIMITS)
    limits["api_ip"] = (1, 60)
    with (
        patch.object(app_main, "RATE_LIMITS", limits),
        patch.object(app_main, "RATE_LIMIT_ENABLED", True),
        patch.object(app_main, "get_rate_limit_store", return_value=limiter),
        TestClient(app_main.app) as client,
    ):
        health = client.get("/api/v1/health/live")
        assert health.status_code == 200
        assert limiter.counts == {}

        assert client.get("/api/v1/not-a-route").status_code == 404
        limited = client.get("/api/v1/not-a-route")
        assert limited.status_code == 429
        assert limited.headers["retry-after"] == "17"
        assert limited.headers["x-request-id"]
        assert limited.headers["x-content-type-options"] == "nosniff"
        assert limited.headers["x-frame-options"] == "DENY"


def test_already_locked_login_skips_argon2_verification():
    import asyncio
    import uuid
    from unittest.mock import Mock

    import pytest
    from fastapi import HTTPException

    from app.models import User
    from app.routes.login import login
    from app.schemas import LoginRequest

    class LockedLimiter:
        async def get_count(self, scope, _key, _window_seconds):
            return (5, 27) if scope == "login:pair" else (0, 60)

        def __init__(self):
            self.increments = []
            self.cleared = []

        async def increment(self, scope, _key, _window_seconds):
            self.increments.append(scope)
            return 1, 60

        async def clear(self, scope, key):
            self.cleared.append((scope, key))

    class AuditSession:
        def __init__(self):
            self.added = []
            self.committed = False
            self.user = User(
                id=uuid.uuid4(),
                username="locked-user",
                email="locked@example.com",
                password_hash="not-verified-by-mock",
                is_active=True,
            )

        async def scalar(self, _statement):
            return self.user

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            self.committed = True

    database = AuditSession()
    limiter = LockedLimiter()
    with patch("app.routes.login.password_hash.verify", new=Mock(return_value=True)) as verify:
        with patch("app.rate_limit.TRUSTED_PROXY_COUNT", 0):
            login_response = asyncio.run(
                login(
                    LoginRequest(email="locked@example.com", password="correct-password"),
                    database,
                    limiter,
                    make_request(),
                )
            )
    assert login_response["token_type"] == "bearer"
    verify.assert_called_once()
    assert limiter.cleared[0][0] == "login:pair"

    failed_database = AuditSession()
    failed_limiter = LockedLimiter()
    with patch("app.routes.login.password_hash.verify", new=Mock(return_value=False)):
        with patch("app.rate_limit.TRUSTED_PROXY_COUNT", 0):
            with pytest.raises(HTTPException) as error:
                asyncio.run(
                    login(
                        LoginRequest(email="locked@example.com", password="wrong-password"),
                        failed_database,
                        failed_limiter,
                        make_request(),
                    )
                )
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "27"
    assert failed_limiter.increments == ["login:ip"]
    assert failed_database.committed