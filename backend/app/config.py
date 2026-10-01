import os

from dotenv import load_dotenv


load_dotenv()

APP_ENV = os.getenv("ME_YOU_ENV", "development").lower()
DEVELOPMENT_DEFAULT_SECRET = "development-only-me-you-jwt-secret"


def validate_jwt_secret(secret: str | None = None, environment: str | None = None) -> str:
    env_name = (environment or APP_ENV).lower()
    resolved_secret = secret if secret is not None else os.getenv("ME_YOU_JWT_SECRET_KEY")
    if env_name == "production":
        if not resolved_secret or resolved_secret == DEVELOPMENT_DEFAULT_SECRET:
            raise ValueError("ME_YOU_JWT_SECRET_KEY must be set to a non-default value in production")
        return resolved_secret
    return resolved_secret or DEVELOPMENT_DEFAULT_SECRET


APP_NAME = "Me&You"
VERSION = "1.0"
DATABASE_URL = "sqlite:///./me_you.db"
POSTGRESQL_DATABASE_URL = os.getenv("ME_YOU_DATABASE_URL")
JWT_SECRET_KEY = validate_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30