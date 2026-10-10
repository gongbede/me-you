import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import validate_environment, validate_jwt_secret, validate_production_config
from app.database import get_postgres_session
from app.main import app


class OperationsTests(unittest.TestCase):
    def test_environment_validation_accepts_only_supported_values(self):
        for environment in ("development", "test", "production"):
            self.assertEqual(validate_environment(environment), environment)
        for environment in ("", "Development", "prod", "production ", "typo"):
            with self.subTest(environment=environment), self.assertRaisesRegex(ValueError, "ME_YOU_ENV"):
                validate_environment(environment)

    def test_production_jwt_secret_rejects_short_repetitive_and_example_values(self):
        for secret in (
            "short",
            "a" * 48,
            "placeholder-local-development-secret",
            "development-only-me-you-jwt-secret",
        ):
            with self.subTest(secret_length=len(secret)), self.assertRaisesRegex(ValueError, "ME_YOU_JWT_SECRET_KEY"):
                validate_jwt_secret(secret=secret, environment="production")

    def test_production_jwt_secret_accepts_long_diverse_value(self):
        secret = "0123456789abcdefABCDEF!@#$%^&*()_+-="
        self.assertEqual(validate_jwt_secret(secret=secret, environment="production"), secret)

    def test_liveness_and_versioned_alias_return_security_headers(self):
        with TestClient(app) as client:
            response = client.get("/api/v1/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "alive"})
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_readiness_fails_closed_without_database_configuration(self):
        with patch("app.routes.health.postgres_engine", None), TestClient(app) as client:
            response = client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database is not configured")
        self.assertNotIn("exception", response.text.lower())

    def test_validation_errors_do_not_echo_submitted_values(self):
        async def override_database():
            yield object()

        app.dependency_overrides[get_postgres_session] = override_database
        try:
            with patch("app.main.RATE_LIMIT_ENABLED", False), TestClient(app) as client:
                response = client.post(
                    "/register",
                    json={"username": "private-user", "email": "private@example.com"},
                )
        finally:
            app.dependency_overrides.clear()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertNotIn('"input"', response.text)

    def test_production_configuration_requires_db_secret_and_explicit_origins(self):
        validate_production_config(
            environment="production",
            secret="0123456789abcdefABCDEF!@#$%^&*()_+-=",
            database_url="postgresql+asyncpg://user:pass@db/me_you",
            cors_origins=("https://app.example.com",),
            storage_backend="s3",
            s3_bucket="media",
            s3_endpoint_url="https://s3.example.com",
            s3_access_key="access-key",
            s3_secret_key="secret-key",
        )
        for configuration in (
            {"secret": "short", "database_url": "postgresql+asyncpg://db/me_you", "cors_origins": ("https://app.example.com",)},
            {"secret": "a" * 48, "database_url": "", "cors_origins": ("https://app.example.com",)},
            {"secret": "a" * 48, "database_url": "postgresql+asyncpg://db/me_you", "cors_origins": ("*",)},
        ):
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                validate_production_config(environment="production", **configuration)


if __name__ == "__main__":
    unittest.main()