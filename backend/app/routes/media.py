import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import (
    APP_ENV,
    MEDIA_USER_QUOTA_BYTES,
    S3_ENDPOINT_URL,
    STORAGE_SIGNED_URL_LIFETIME_SECONDS,
)
from ..database import get_postgres_session
from ..models import InstitutionMembership, MediaAsset, Profile, User
from ..privacy import can_view_profile
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..providers.storage import (
    LocalDiskStorageProvider,
    StorageObjectTooLarge,
    StorageTokenError,
)
from ..schemas import (
    MediaAssetResponse,
    MediaAvatarSet,
    MediaDownloadResponse,
    MediaUploadIntentCreate,
    MediaUploadIntentResponse,
)
from ..security import get_current_postgres_user, get_optional_postgres_user


router = APIRouter(prefix="/media", tags=["media"])
UPLOAD_INTENT_TTL_SECONDS = 600
DOWNLOAD_URL_TTL_SECONDS = 300
CONTENT_TYPES_BY_PURPOSE = {
    "PROFILE_IMAGE": {"image/jpeg", "image/png", "image/webp"},
    "POST_MEDIA": {
        "image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "audio/mpeg", "audio/ogg",
    },
    "COURSE_MEDIA": {
        "image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "audio/mpeg", "audio/ogg", "application/pdf",
    },
    "REEL": {"video/mp4", "video/webm"},
    "MESSAGE_ATTACHMENT": {
        "image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm", "audio/mpeg", "audio/ogg", "application/pdf",
    },
}
MAX_BYTES_BY_PURPOSE = {
    "PROFILE_IMAGE": 5_000_000,
    "POST_MEDIA": 250_000_000,
    "COURSE_MEDIA": 500_000_000,
    "REEL": 1_000_000_000,
    "MESSAGE_ATTACHMENT": 50_000_000,
}


def media_asset_response(asset: MediaAsset) -> dict:
    return {
        "id": str(asset.id),
        "purpose": asset.purpose,
        "institution_id": str(asset.institution_id) if asset.institution_id else None,
        "status": asset.status,
        "content_type": asset.content_type,
        "byte_size": asset.byte_size,
        "original_filename": asset.original_filename,
        "checksum_sha256": asset.checksum_sha256,
        "created_at": asset.created_at,
    }


def require_https_url(value: str, label: str) -> str:
    if urlparse(value).scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Storage provider returned an invalid {label} URL",
        )
    return value


def validate_provider_url(value: str, label: str, request: Request | None) -> str:
    if value.startswith("/api/v1/media/local-"):
        return value
    parsed = urlparse(value)
    if parsed.scheme == "https":
        return value
    endpoint = urlparse(S3_ENDPOINT_URL or "")
    if (
        APP_ENV != "production"
        and parsed.scheme == "http"
        and endpoint.scheme == "http"
        and (parsed.hostname, parsed.port) == (endpoint.hostname, endpoint.port)
    ):
        return value
    return require_https_url(value, label)


async def owned_asset_or_404(
    asset_id: uuid.UUID,
    owner_id: uuid.UUID,
    database: AsyncSession,
) -> MediaAsset:
    asset = await database.scalar(
        select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == owner_id)
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


@router.post("/upload-intents", response_model=MediaUploadIntentResponse, status_code=201)
async def create_media_upload_intent(
    data: MediaUploadIntentCreate,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    if data.content_type not in CONTENT_TYPES_BY_PURPOSE[data.purpose]:
        raise HTTPException(status_code=422, detail="Content type is not allowed for this media purpose")
    max_bytes = MAX_BYTES_BY_PURPOSE[data.purpose]
    if data.byte_size > max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds the size limit for this media purpose")
    if data.institution_id is not None and data.purpose != "COURSE_MEDIA":
        raise HTTPException(status_code=422, detail="Only course media can be institution-scoped")
    institution_id = None
    if data.institution_id is not None:
        try:
            institution_id = uuid.UUID(data.institution_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="institution_id must be a UUID") from None
        membership = await database.scalar(
            select(InstitutionMembership.id).where(
                InstitutionMembership.user_id == current_user.id,
                InstitutionMembership.institution_id == institution_id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="Institution not found")
    await database.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    current_usage = await database.scalar(
        select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
            MediaAsset.owner_id == current_user.id,
            MediaAsset.status != "FAILED",
        )
    )
    if int(current_usage or 0) + data.byte_size > MEDIA_USER_QUOTA_BYTES:
        raise HTTPException(status_code=413, detail="User media storage quota exceeded")
    storage = provider_or_503(providers, "storage")
    asset_id = uuid.uuid4()
    storage_key = f"users/{current_user.id}/{asset_id}"
    intent = await storage.create_upload_intent(
        object_key=storage_key,
        content_type=data.content_type,
        max_bytes=data.byte_size,
        expires_in_seconds=UPLOAD_INTENT_TTL_SECONDS,
    )
    upload_url = validate_provider_url(intent.upload_url, "upload", request)
    if intent.object_key != storage_key:
        raise HTTPException(status_code=502, detail="Storage provider returned an unexpected object key")
    now = datetime.now(timezone.utc)
    if intent.expires_at <= now or intent.expires_at > now + timedelta(seconds=UPLOAD_INTENT_TTL_SECONDS + 30):
        raise HTTPException(status_code=502, detail="Storage provider returned an invalid upload expiry")

    asset = MediaAsset(
        id=asset_id,
        owner_id=current_user.id,
        institution_id=institution_id,
        purpose=data.purpose,
        status="UPLOAD_PENDING",
        storage_provider=getattr(storage, "name", providers.settings.storage or type(storage).__name__),
        storage_key=storage_key,
        content_type=data.content_type,
        byte_size=data.byte_size,
        original_filename=data.original_filename,
        upload_expires_at=intent.expires_at,
        created_at=now,
        updated_at=now,
    )
    database.add(asset)
    try:
        await database.commit()
        await database.refresh(asset)
    except BaseException:
        await database.rollback()
        raise
    return {
        "asset": media_asset_response(asset),
        "upload_url": upload_url,
        "required_headers": intent.required_headers,
        "expires_at": intent.expires_at,
    }


@router.post("/{asset_id}/complete", response_model=MediaAssetResponse)
async def complete_media_upload(
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    asset = await owned_asset_or_404(asset_id, current_user.id, database)
    if asset.status == "READY":
        return media_asset_response(asset)
    if asset.status != "UPLOAD_PENDING":
        raise HTTPException(status_code=409, detail="Media asset cannot be completed")
    if asset.upload_expires_at <= datetime.now(timezone.utc):
        storage = provider_or_503(providers, "storage")
        await storage.delete_object(asset.storage_key)
        asset.status = "FAILED"
        await database.commit()
        raise HTTPException(status_code=410, detail="Upload intent has expired")

    storage = provider_or_503(providers, "storage")
    metadata = await storage.inspect_object(asset.storage_key)
    if metadata is None:
        raise HTTPException(status_code=409, detail="Uploaded object is not available yet")
    if (
        metadata.object_key != asset.storage_key
        or metadata.content_type != asset.content_type
        or metadata.byte_size != asset.byte_size
        or metadata.byte_size > MAX_BYTES_BY_PURPOSE[asset.purpose]
        or metadata.detected_content_type != asset.content_type
    ):
        await storage.delete_object(asset.storage_key)
        asset.status = "FAILED"
        asset.updated_at = datetime.now(timezone.utc)
        await database.commit()
        raise HTTPException(status_code=422, detail="Uploaded object metadata does not match the request")
    if metadata.checksum_sha256 and (
        len(metadata.checksum_sha256) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in metadata.checksum_sha256)
    ):
        raise HTTPException(status_code=502, detail="Storage provider returned an invalid checksum")
    asset.checksum_sha256 = metadata.checksum_sha256.lower() if metadata.checksum_sha256 else None
    asset.status = "READY"
    asset.updated_at = datetime.now(timezone.utc)
    try:
        await database.commit()
        await database.refresh(asset)
    except BaseException:
        await database.rollback()
        raise
    return media_asset_response(asset)


@router.put("/local-upload/{token}", status_code=204)
async def receive_local_upload(
    token: str,
    request: Request,
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    storage = providers.storage
    if not isinstance(storage, LocalDiskStorageProvider):
        raise HTTPException(status_code=404, detail="Local upload endpoint is unavailable")
    try:
        await storage.accept_upload(
            token,
            request.headers.get("content-type", ""),
            request.stream(),
        )
    except StorageObjectTooLarge as error:
        raise HTTPException(status_code=413, detail=str(error)) from None
    except StorageTokenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None


@router.get("/local-download/{token}")
async def serve_local_download(
    token: str,
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    storage = providers.storage
    if not isinstance(storage, LocalDiskStorageProvider):
        raise HTTPException(status_code=404, detail="Local download endpoint is unavailable")
    try:
        path, metadata = await storage.resolve_download(token)
    except StorageTokenError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stored object not found") from None
    return FileResponse(
        path,
        media_type=metadata.content_type,
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("", response_model=list[MediaAssetResponse])
async def list_my_media_assets(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    assets = list(
        (
            await database.scalars(
                select(MediaAsset)
                .where(MediaAsset.owner_id == current_user.id)
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return [media_asset_response(asset) for asset in assets]


@router.get("/{asset_id}/download", response_model=MediaDownloadResponse)
async def create_media_download_url(
    asset_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    asset = await database.scalar(select(MediaAsset).where(MediaAsset.id == asset_id))
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    if asset.status != "READY":
        raise HTTPException(status_code=409, detail="Media asset is not ready for download")
    authorized = current_user is not None and asset.owner_id == current_user.id
    if not authorized and asset.purpose == "PROFILE_IMAGE":
        profile = await database.scalar(
            select(Profile).where(Profile.avatar_asset_id == asset.id)
        )
        owner = await database.scalar(select(User).where(User.id == asset.owner_id))
        authorized = bool(
            profile is not None
            and owner is not None
            and await can_view_profile(
                owner, profile.visibility, current_user, database
            )
        )
    if not authorized and current_user is not None and asset.institution_id is not None:
        authorized = (
            await database.scalar(
                select(InstitutionMembership.id).where(
                    InstitutionMembership.user_id == current_user.id,
                    InstitutionMembership.institution_id == asset.institution_id,
                )
            )
            is not None
        )
    if not authorized:
        raise HTTPException(status_code=404, detail="Media asset not found")
    storage = provider_or_503(providers, "storage")
    download_url = validate_provider_url(
        await storage.create_download_url(
            asset.storage_key,
            expires_in_seconds=STORAGE_SIGNED_URL_LIFETIME_SECONDS,
        ),
        "download",
        request,
    )
    return {
        "asset": media_asset_response(asset),
        "download_url": download_url,
        "expires_in_seconds": STORAGE_SIGNED_URL_LIFETIME_SECONDS,
    }


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_asset(
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    asset = await owned_asset_or_404(asset_id, current_user.id, database)
    storage = provider_or_503(providers, "storage")
    await storage.delete_object(asset.storage_key)
    await database.delete(asset)
    await database.commit()