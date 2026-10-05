import unittest
from datetime import datetime, timezone

from fastapi import HTTPException

from app.providers import (
    EmailRequest,
    ProviderNotConfiguredError,
    ProviderRegistry,
    ProviderSettings,
    UploadIntent,
    provider_or_503,
    require_provider,
)


class FakeEmailProvider:
    def __init__(self):
        self.requests = []

    async def send(self, request):
        self.requests.append(request)
        return "fake-message-id"


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_provider_is_explicit_and_never_falls_back_to_fake(self):
        registry = ProviderRegistry(settings=ProviderSettings())
        with self.assertRaises(ProviderNotConfiguredError):
            require_provider(registry, "email")
        with self.assertRaises(HTTPException) as error:
            provider_or_503(registry, "storage")
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail["code"], "provider_not_configured")
        self.assertEqual(error.exception.headers["Retry-After"], "300")

    async def test_configured_provider_name_without_adapter_fails_explicitly(self):
        registry = ProviderRegistry(settings=ProviderSettings(storage="s3"))
        with self.assertRaises(HTTPException) as error:
            provider_or_503(registry, "storage")
        self.assertIn("adapter is unavailable", error.exception.detail["message"])

    async def test_injected_fake_satisfies_email_contract(self):
        provider = FakeEmailProvider()
        registry = ProviderRegistry(settings=ProviderSettings(), email=provider)
        result = await require_provider(registry, "email").send(
            EmailRequest(
                recipient="person@example.test",
                subject="Account notice",
                text_body="A deterministic test message",
            )
        )
        self.assertEqual(result, "fake-message-id")
        self.assertEqual(len(provider.requests), 1)

    def test_storage_contract_types_are_provider_neutral(self):
        intent = UploadIntent(
            upload_url="https://storage.invalid/upload",
            object_key="opaque-key",
            expires_at=datetime.now(timezone.utc),
            required_headers={"Content-Type": "image/png"},
        )
        self.assertEqual(intent.object_key, "opaque-key")
        self.assertEqual(intent.required_headers["Content-Type"], "image/png")


if __name__ == "__main__":
    unittest.main()