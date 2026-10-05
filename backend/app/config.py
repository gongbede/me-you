import os

from dotenv import load_dotenv


load_dotenv()

APP_ENV = os.getenv("ME_YOU_ENV", "development").lower()
DEVELOPMENT_DEFAULT_SECRET = "development-only-me-you-jwt-secret"
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv("ME_YOU_CORS_ORIGINS", "").split(",")
    if origin.strip()
)


def validate_jwt_secret(secret: str | None = None, environment: str | None = None) -> str:
    env_name = (environment or APP_ENV).lower()
    resolved_secret = secret if secret is not None else os.getenv("ME_YOU_JWT_SECRET_KEY")
    if env_name == "production":
        if (
            not resolved_secret
            or resolved_secret == DEVELOPMENT_DEFAULT_SECRET
            or len(resolved_secret) < 32
        ):
            raise ValueError("ME_YOU_JWT_SECRET_KEY must be at least 32 characters in production")
        return resolved_secret
    return resolved_secret or DEVELOPMENT_DEFAULT_SECRET


def validate_production_config(
    *,
    environment: str | None = None,
    secret: str | None = None,
    database_url: str | None = None,
    cors_origins: tuple[str, ...] | None = None,
) -> None:
    if (environment or APP_ENV).lower() != "production":
        return
    validate_jwt_secret(secret=secret, environment="production")
    resolved_database_url = database_url if database_url is not None else os.getenv("ME_YOU_DATABASE_URL")
    if not resolved_database_url or not resolved_database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("ME_YOU_DATABASE_URL must use postgresql+asyncpg in production")
    resolved_origins = cors_origins if cors_origins is not None else CORS_ORIGINS
    if not resolved_origins or "*" in resolved_origins:
        raise ValueError("ME_YOU_CORS_ORIGINS must contain explicit origins in production")


APP_NAME = "Me&You"
VERSION = "1.0"
DATABASE_URL = "sqlite:///./me_you.db"
POSTGRESQL_DATABASE_URL = os.getenv("ME_YOU_DATABASE_URL")
JWT_SECRET_KEY = validate_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30