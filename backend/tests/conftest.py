import os


# Set these before test modules import app.config, which loads backend/.env.
os.environ["ME_YOU_ENV"] = "test"
os.environ["ME_YOU_CORS_ORIGINS"] = ""
os.environ["ME_YOU_TRUSTED_ORIGINS"] = ""
os.environ["ME_YOU_JWT_SECRET_KEY"] = "test-only-me-you-jwt-secret-key-2026"
