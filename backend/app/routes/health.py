import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from ..database import postgres_engine


router = APIRouter(tags=["operations"])
logger = logging.getLogger(__name__)


@router.get("/health/live", summary="Check process liveness")
async def live():
    return {"status": "alive"}


@router.get("/health/ready", summary="Check backend readiness")
async def ready():
    if postgres_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured",
        )
    try:
        async with postgres_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        logger.warning("database_readiness_failed error_type=%s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from None
    return {"status": "ready", "database": "available"}