import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import AUTH_SESSION_COOKIE_NAME, AUTH_SESSION_COOKIE_PATH
from app.main import app
from app.models import AuthIdentity, PhoneLoginCode, User
from app.providers.sms import ConsoleSMSProvider
from app.routes.auth_google import GoogleSignInRequest, google_sign_in
from app.routes.auth_phone import PhoneCodeVerify, hash_phone_code, verify_phone_code
from app.routes.login import login
from app.schemas import LoginRequest
from app.security import create_access_token, decode_access_token, set_auth_cookie


class AuthSession:
    def __init__(self, scalar_values=None, user=None):
        self.scalar_values = list(scalar_values or [])
        self.user = user
        self.added = []
        self.committed = False

    async def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def get(self, _model, _key):
        return self.user

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()
            if isinstance(value, User) and value.is_active is None:
                value.is_active = True

    async def commit(self):
        self.committed = True


class EmptySession:
    async def scalar(self, _statement):
        return None


def make_request(path="/login", headers=None):
    raw_headers = [
        (name.lower().encode("ascii"), value.encode("ascii"))
        for name, value in (headers or {}).items()
    ]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("192.0.2.10", 1234),
        "server": ("testserver", 80),
    })


def cookie_from_response(response):
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    return cookie[AUTH_SESSION_COOKIE_NAME]


def assert_cookie_session(response, body):
    assert "access_token" not in body
    assert "token_type" not in body
    assert body["csrf_token"]
    cookie = cookie_from_response(response)
    assert cookie["httponly"]
    assert cookie["path"] == AUTH_SESSION_COOKIE_PATH
    assert cookie["samesite"] == "lax"
    assert cookie["max-age"] == "1800"
    claims = decode_access_token(cookie.value)
    assert claims["csrf"] == body["csrf_token"]
    assert claims["sub"] == body["id"]


def test_password_login_sets_cookie_without_returning_token_and_keeps_bearer_compatibility():
    user = User(
        id=uuid.uuid4(), username="learner", email="learner@example.test",
        password_hash="stored-hash", token_version=4, is_active=True,
    )
    cookie_response = Response()
    cookie_request = make_request(headers={
        "origin": "http://testserver",
        "x-me-you-session": "cookie",
    })
    with (
        patch("app.routes.login.password_hash.verify", return_value=True),
        patch("app.routes.login.record_security_event"),
    ):
        cookie_body = asyncio.run(login(
            LoginRequest(email=user.email, password="correct-password"),
            AuthSession([user]), None, cookie_request, cookie_response,
        ))
    assert_cookie_session(cookie_response, cookie_body)
    assert decode_access_token(cookie_from_response(cookie_response).value)["ver"] == 4

    bearer_request = make_request()
    with patch("app.routes.login.password_hash.verify", return_value=True):
        bearer_body = asyncio.run(login(
            LoginRequest(email=user.email, password="correct-password"),
            AuthSession([user]), None, bearer_request, Response(),
        ))
    assert bearer_body["access_token"]
    assert bearer_body["token_type"] == "bearer"


def test_password_login_rejects_invalid_credentials_without_setting_cookie():
    response = Response()
    with (
        patch("app.routes.login.password_hash.verify", return_value=False),
        patch("app.routes.login.record_security_event"),
        patch("app.routes.login.RATE_LIMITS", {
            "login_ip": (30, 900), "login_pair": (5, 900), "login_email": (50, 3600),
        }),
    ):
        with __import__("pytest").raises(HTTPException) as error:
            asyncio.run(login(
                LoginRequest(email="missing@example.test", password="wrong-password"),
                AuthSession([None]), None, make_request(), response,
            ))
    assert error.value.status_code == 401
    assert "set-cookie" not in response.headers


def test_google_login_uses_cookie_session_for_verified_existing_identity(monkeypatch):
    monkeypatch.setenv("ME_YOU_GOOGLE_CLIENT_ID", "test-google-client-id")
    user = User(
        id=uuid.uuid4(), username="google-user", email="google@example.test",
        password_hash="stored-hash", token_version=0, is_active=True,
    )
    identity = AuthIdentity(
        id=uuid.uuid4(), user_id=user.id, provider="google", provider_subject="google-subject",
    )
    response = Response()
    request = make_request("/auth/google", {
        "origin": "http://testserver", "x-me-you-session": "cookie",
    })
    with patch("app.routes.auth_google.verify_google_id_token", return_value={
        "sub": "google-subject", "email": user.email, "email_verified": True,
    }):
        body = asyncio.run(google_sign_in(
            GoogleSignInRequest(id_token="verified-provider-credential"),
            AuthSession([identity], user), request, response,
        ))
    assert_cookie_session(response, body)


def test_phone_login_uses_cookie_session_after_code_verification():
    phone_number = "+12025550111"
    code = "123456"
    now = datetime.now(timezone.utc)
    code_record = PhoneLoginCode(
        id=uuid.uuid4(), phone_number=phone_number,
        code_hash=hash_phone_code(phone_number, code), attempts=0,
        created_at=now, expires_at=now + timedelta(minutes=5),
    )
    session = AuthSession([code_record, None, None])
    response = Response()
    request = make_request("/auth/phone/verify", {
        "origin": "http://testserver", "x-me-you-session": "cookie",
    })
    body = asyncio.run(verify_phone_code(
        PhoneCodeVerify(phone_number=phone_number, code=code),
        session, ConsoleSMSProvider(), request, response,
    ))
    assert session.committed
    assert_cookie_session(response, body)


def test_cookie_requests_require_allowed_origin_and_session_bound_csrf(monkeypatch):
    import app.main as app_main

    monkeypatch.setattr(app_main, "CORS_ORIGINS", ("http://testserver",))
    monkeypatch.setattr(app_main, "RATE_LIMIT_ENABLED", False)
    csrf_token = "c" * 43
    cookie_token = create_access_token(uuid.uuid4(), csrf_token=csrf_token)
    with TestClient(app) as client:
        missing_csrf = client.post(
            "/api/v1/not-a-route",
            cookies={AUTH_SESSION_COOKIE_NAME: cookie_token},
            headers={"Origin": "http://testserver"},
        )
        bad_origin = client.post(
            "/api/v1/not-a-route",
            cookies={AUTH_SESSION_COOKIE_NAME: cookie_token},
            headers={"Origin": "https://untrusted.example", "X-CSRF-Token": csrf_token},
        )
        accepted = client.post(
            "/api/v1/not-a-route",
            cookies={AUTH_SESSION_COOKIE_NAME: cookie_token},
            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf_token},
        )
    assert missing_csrf.status_code == 403
    assert bad_origin.status_code == 403
    assert accepted.status_code == 404


def test_cookie_login_requires_allowed_origin_and_expired_cookie_is_cleared(monkeypatch):
    import app.main as app_main

    monkeypatch.setattr(app_main, "CORS_ORIGINS", ("http://testserver",))
    monkeypatch.setattr(app_main, "RATE_LIMIT_ENABLED", False)
    expired_cookie = create_access_token(
        uuid.uuid4(), expires_delta=timedelta(seconds=-1), csrf_token="c" * 43,
    )
    with TestClient(app) as client:
        login_without_origin = client.post(
            "/api/v1/login",
            headers={"X-Me-You-Session": "cookie"},
            json={"email": "person@example.test", "password": "password-value"},
        )
        expired = client.post(
            "/api/v1/not-a-route",
            cookies={AUTH_SESSION_COOKIE_NAME: expired_cookie},
            headers={"Origin": "http://testserver", "X-CSRF-Token": "c" * 43},
        )
    assert login_without_origin.status_code == 403
    assert expired.status_code == 401
    assert "Max-Age=0" in expired.headers["set-cookie"]


def test_production_cookie_is_secure():
    response = Response()
    with patch("app.security.APP_ENV", "production"):
        set_auth_cookie(response, "opaque-session-value")
    cookie = cookie_from_response(response)
    assert cookie["secure"]
    assert cookie["httponly"]
