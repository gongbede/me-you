from contextlib import asynccontextmanager
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import APP_ENV, APP_NAME, CORS_ORIGINS, RATE_LIMITS, RATE_LIMIT_ENABLED, VERSION, validate_production_config
from .database import init_mongodb
from .rate_limit import client_ip, get_rate_limit_store
from .routes.general import router as general_router
from .routes.health import router as health_router
from .routes.account import router as account_router
from .routes.auth_google import router as auth_google_router
from .routes.auth_phone import router as auth_phone_router
from .routes.comments import router as comments_router
from .routes.classrooms import router as classrooms_router
from .routes.conversations import router as conversations_router
from .routes.education import router as education_router
from .routes.education_learning import router as education_learning_router
from .routes.follows import router as follows_router
from .routes.institutions import router as institutions_router
from .routes.login import router as login_router
from .routes.media import router as media_router
from .routes.likes import router as likes_router
from .routes.me import router as me_router
from .routes.messages import router as messages_router
from .routes.notifications import router as notifications_router
from .routes.posts import router as posts_router
from .routes.profile import router as profile_router
from .routes.platform_admin import router as platform_admin_router
from .routes.registration import router as registration_router
from .routes.search import router as search_router
from .routes.security_events import router as security_events_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_production_config()
    await init_mongodb()
    yield


app = FastAPI(title=APP_NAME, version=VERSION, lifespan=lifespan)
class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in ("request_id", "exception_type"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"))


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO if APP_ENV == "production" else logging.DEBUG)
if not root_logger.handlers:
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(log_handler)
logger = logging.getLogger("me_you.api")

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Next-Cursor"],
    )

routers = (
    general_router,
    registration_router,
    login_router,
    me_router,
    profile_router,
    account_router,
    auth_google_router,
    auth_phone_router,
    posts_router,
    comments_router,
    classrooms_router,
    likes_router,
    follows_router,
    notifications_router,
    conversations_router,
    messages_router,
    education_router,
    education_learning_router,
    institutions_router,
    search_router,
    platform_admin_router,
    media_router,
    health_router,
    security_events_router,
)
for route_group in routers:
    app.include_router(route_group)
    app.include_router(route_group, prefix="/api/v1")


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, error: HTTPException):
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content={
            "detail": error.detail,
            "code": f"http_{error.status_code}",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError):
    details = [
        {
            "loc": list(item.get("loc", ())),
            "msg": item.get("msg", "Invalid value"),
            "type": item.get("type", "value_error"),
        }
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "detail": details,
            "code": "validation_error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.middleware("http")
async def add_request_and_security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = None
    try:
        if RATE_LIMIT_ENABLED:
            path = request.url.path.removeprefix("/api/v1") or "/"
            if path not in {"/health/live", "/health/ready", "/login"}:
                if path == "/register":
                    scope, limit_name = "registration:ip", "registration_ip"
                elif path == "/account/password":
                    scope, limit_name = "password_change:ip", "password_change_ip"
                else:
                    scope, limit_name = "api:ip", "api_ip"
                limiter = get_rate_limit_store()
                if limiter is not None:
                    limit, window_seconds = RATE_LIMITS[limit_name]
                    count, retry_after = await limiter.increment(
                        scope, client_ip(request), window_seconds
                    )
                    if count > limit:
                        response = JSONResponse(
                            status_code=429,
                            headers={"Retry-After": str(retry_after)},
                            content={
                                "detail": "Too many requests; try again later",
                                "code": "http_429",
                                "request_id": request_id,
                            },
                        )
        if response is None:
            response = await call_next(request)
    except Exception as error:
        logger.error(
            "unhandled_request_error",
            extra={"request_id": request_id, "exception_type": type(error).__name__},
        )
        response = JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "code": "internal_error",
                "request_id": request_id,
            },
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def main():
    print("Me&You backend has started.")
    print(f"Application: {APP_NAME}")
    print(f"Version: {VERSION}")


if __name__ == "__main__":
    main()