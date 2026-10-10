import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

DEVELOPMENT_DEFAULT_SECRET = "development-only-me-you-jwt-secret"
ALLOWED_ENVIRONMENTS = {"development", "test", "production"}


def validate_environment(environment: str) -> str:
    if environment not in ALLOWED_ENVIRONMENTS:
        allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        raise ValueError(f"ME_YOU_ENV must be one of: {allowed}")
    return environment


APP_ENV = validate_environment(os.getenv("ME_YOU_ENV", "development"))
CORS_ORIGINS = tuple(
    origin.strip()
    for origin in os.getenv("ME_YOU_CORS_ORIGINS", "").split(",")
    if origin.strip()
)


def validate_jwt_secret(secret: str | None = None, environment: str | None = None) -> str:
    env_name = validate_environment(environment or APP_ENV)
    resolved_secret = secret if secret is not None else os.getenv("ME_YOU_JWT_SECRET_KEY")
    if env_name == "production":
        example_secrets = {DEVELOPMENT_DEFAULT_SECRET}
        example_path = Path(__file__).resolve().parents[1] / ".env.example"
        if example_path.exists():
            for line in example_path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator and key.strip() == "ME_YOU_JWT_SECRET_KEY":
                    example_secrets.add(value.strip().strip("\"'"))
        if (
            not resolved_secret
            or len(resolved_secret) < 32
            or len(set(resolved_secret)) < 16
            or resolved_secret in example_secrets
        ):
            raise ValueError(
                "ME_YOU_JWT_SECRET_KEY in production must be at least 32 characters, "
                "contain at least 16 distinct characters, and not be a placeholder"
            )
        return resolved_secret
    return resolved_secret or DEVELOPMENT_DEFAULT_SECRET


def validate_production_config(
    *,
    environment: str | None = None,
    secret: str | None = None,
    database_url: str | None = None,
    cors_origins: tuple[str, ...] | None = None,
    storage_backend: str | None = None,
    s3_bucket: str | None = None,
    s3_endpoint_url: str | None = None,
    s3_access_key: str | None = None,
    s3_secret_key: str | None = None,
) -> None:
    env_name = validate_environment(environment or APP_ENV)
    if env_name != "production":
        return
    validate_jwt_secret(secret=secret, environment="production")
    if not RATE_LIMIT_ENABLED:
        raise ValueError("RATE_LIMIT_ENABLED must be true in production")
    for name, (limit, window_seconds) in RATE_LIMITS.items():
        if limit <= 0 or window_seconds <= 0:
            raise ValueError(f"{name} rate-limit limit and window must be positive in production")
    resolved_database_url = database_url if database_url is not None else os.getenv("ME_YOU_DATABASE_URL")
    if not resolved_database_url or not resolved_database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("ME_YOU_DATABASE_URL must use postgresql+asyncpg in production")
    resolved_origins = cors_origins if cors_origins is not None else CORS_ORIGINS
    if not resolved_origins or "*" in resolved_origins:
        raise ValueError("ME_YOU_CORS_ORIGINS must contain explicit origins in production")
    resolved_storage_backend = storage_backend or os.getenv("STORAGE_BACKEND", "local").lower()
    if resolved_storage_backend != "s3":
        raise ValueError("STORAGE_BACKEND must be s3 in production")
    if not (s3_bucket if s3_bucket is not None else os.getenv("S3_BUCKET", "me-you-media")):
        raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
    if not (
        s3_access_key if s3_access_key is not None else os.getenv("AWS_ACCESS_KEY_ID")
    ) or not (
        s3_secret_key if s3_secret_key is not None else os.getenv("AWS_SECRET_ACCESS_KEY")
    ):
        raise ValueError("S3 credentials must be supplied through environment variables")
    resolved_endpoint = (
        s3_endpoint_url if s3_endpoint_url is not None else os.getenv("S3_ENDPOINT_URL")
    )
    if resolved_endpoint and resolved_endpoint.startswith("http://"):
        raise ValueError("S3_ENDPOINT_URL must use HTTPS in production")


APP_NAME = "Me&You"
VERSION = "1.0"
DATABASE_URL = "sqlite:///./me_you.db"
POSTGRESQL_DATABASE_URL = os.getenv("ME_YOU_DATABASE_URL")
JWT_SECRET_KEY = validate_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
TRUSTED_PROXY_COUNT = max(0, int(os.getenv("TRUSTED_PROXY_COUNT", "0")))
LOGIN_PAIR_FAILURE_LIMIT = int(os.getenv("LOGIN_PAIR_FAILURE_LIMIT", "5"))
LOGIN_PAIR_WINDOW_SECONDS = int(os.getenv("LOGIN_PAIR_WINDOW_SECONDS", "900"))
LOGIN_IP_ATTEMPT_LIMIT = int(os.getenv("LOGIN_IP_ATTEMPT_LIMIT", "30"))
LOGIN_IP_WINDOW_SECONDS = int(os.getenv("LOGIN_IP_WINDOW_SECONDS", "900"))
LOGIN_EMAIL_FAILURE_LIMIT = int(os.getenv("LOGIN_EMAIL_FAILURE_LIMIT", "50"))
LOGIN_EMAIL_WINDOW_SECONDS = int(os.getenv("LOGIN_EMAIL_WINDOW_SECONDS", "3600"))
REGISTRATION_IP_LIMIT = int(os.getenv("REGISTRATION_IP_LIMIT", "5"))
REGISTRATION_WINDOW_SECONDS = int(os.getenv("REGISTRATION_WINDOW_SECONDS", "3600"))
PASSWORD_CHANGE_IP_LIMIT = int(os.getenv("PASSWORD_CHANGE_IP_LIMIT", "5"))
PASSWORD_CHANGE_WINDOW_SECONDS = int(os.getenv("PASSWORD_CHANGE_WINDOW_SECONDS", "3600"))
API_IP_LIMIT = int(os.getenv("API_IP_LIMIT", "120"))
API_WINDOW_SECONDS = int(os.getenv("API_WINDOW_SECONDS", "60"))
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
SECURITY_EVENT_RETENTION_DAYS = int(os.getenv("SECURITY_EVENT_RETENTION_DAYS", "365"))
APP_PUBLIC_BASE_URL = os.getenv("ME_YOU_PUBLIC_BASE_URL", "http://localhost:3000").rstrip("/")
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
if STORAGE_BACKEND not in {"local", "s3"}:
    raise ValueError("STORAGE_BACKEND must be local or s3")
STORAGE_LOCAL_DIR = Path(
    os.getenv("STORAGE_LOCAL_DIR", str(Path(__file__).resolve().parents[1] / ".media"))
).expanduser()
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None
S3_BUCKET = os.getenv("S3_BUCKET", "me-you-media")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
STORAGE_SIGNED_URL_LIFETIME_SECONDS = int(
    os.getenv("STORAGE_SIGNED_URL_LIFETIME_SECONDS", "300")
)
MEDIA_USER_QUOTA_BYTES = int(os.getenv("MEDIA_USER_QUOTA_BYTES", "2000000000"))
MEDIA_ORPHAN_UPLOAD_HOURS = int(os.getenv("MEDIA_ORPHAN_UPLOAD_HOURS", "24"))
if STORAGE_SIGNED_URL_LIFETIME_SECONDS < 1 or STORAGE_SIGNED_URL_LIFETIME_SECONDS > 604800:
    raise ValueError("STORAGE_SIGNED_URL_LIFETIME_SECONDS must be between 1 and 604800")
if MEDIA_USER_QUOTA_BYTES < 1:
    raise ValueError("MEDIA_USER_QUOTA_BYTES must be positive")
if MEDIA_ORPHAN_UPLOAD_HOURS < 1:
    raise ValueError("MEDIA_ORPHAN_UPLOAD_HOURS must be positive")

RATE_LIMITS = {
    "login_pair": (LOGIN_PAIR_FAILURE_LIMIT, LOGIN_PAIR_WINDOW_SECONDS),
    "login_ip": (LOGIN_IP_ATTEMPT_LIMIT, LOGIN_IP_WINDOW_SECONDS),
    "login_email": (LOGIN_EMAIL_FAILURE_LIMIT, LOGIN_EMAIL_WINDOW_SECONDS),
    "registration_ip": (REGISTRATION_IP_LIMIT, REGISTRATION_WINDOW_SECONDS),
    "password_change_ip": (PASSWORD_CHANGE_IP_LIMIT, PASSWORD_CHANGE_WINDOW_SECONDS),
    "api_ip": (API_IP_LIMIT, API_WINDOW_SECONDS),
}