from datetime import datetime, timezone

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import APP_ENV, S3_ENDPOINT_URL, STORAGE_SIGNED_URL_LIFETIME_SECONDS
from ..database import get_postgres_session
from ..models import MediaAsset, Profile, User
from ..privacy import can_view_profile
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..schemas import CreateProfile, MediaAvatarSet, ProfileDiscoveryResponse, ProfileResponse, UpdateProfile
from ..security import get_current_postgres_user, get_optional_postgres_user
from .media import validate_provider_url


router = APIRouter(tags=["profile"])


def profile_response(profile: Profile) -> dict:
    return {
        "user_id": str(profile.user_id),
        "display_name": profile.display_name,
        "bio": profile.bio,
        "profile_picture_url": profile.profile_picture_url,
        "location": profile.location,
        "website": profile.website,
        "visibility": getattr(profile, "visibility", "NETWORK"),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


async def profile_avatar_url(
    profile: Profile,
    database: AsyncSession,
    providers: ProviderRegistry,
    request: Request | None,
) -> str | None:
    if profile.avatar_asset_id is None:
        return profile.profile_picture_url
    asset = await database.scalar(
        select(MediaAsset).where(
            MediaAsset.id == profile.avatar_asset_id,
            MediaAsset.owner_id == profile.user_id,
            MediaAsset.purpose == "PROFILE_IMAGE",
            MediaAsset.status == "READY",
        )
    )
    if asset is None:
        return None
    storage = provider_or_503(providers, "storage")
    value = await storage.create_download_url(
        asset.storage_key,
        expires_in_seconds=STORAGE_SIGNED_URL_LIFETIME_SECONDS,
    )
    return validate_provider_url(value, "avatar", request)


@router.post(
    "/profile",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the current user's profile",
)
async def create_profile(
    profile_data: CreateProfile,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    existing_profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if existing_profile is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists",
        )

    profile = Profile(user_id=current_user.id, **profile_data.model_dump())
    database.add(profile)
    try:
        await database.commit()
        await database.refresh(profile)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists",
        ) from None

    result = profile_response(profile)
    result["profile_picture_url"] = await profile_avatar_url(
        profile, database, providers, request
    )
    return result


@router.get(
    "/profile/me",
    response_model=ProfileResponse,
    summary="Get the current user's profile",
)
async def get_my_profile(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    result = profile_response(profile)
    result["profile_picture_url"] = await profile_avatar_url(
        profile, database, providers, request
    )
    return result


@router.patch(
    "/profile/me",
    response_model=ProfileResponse,
    summary="Update the current user's profile",
)
async def update_my_profile(
    profile_data: UpdateProfile,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    updates = profile_data.model_dump(exclude_unset=True)
    if updates.get("display_name") is None and "display_name" in updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="display_name cannot be null",
        )

    for field, value in updates.items():
        setattr(profile, field, value)
    profile.updated_at = datetime.now(timezone.utc)

    await database.commit()
    await database.refresh(profile)
    result = profile_response(profile)
    result["profile_picture_url"] = await profile_avatar_url(
        profile, database, providers, request
    )
    return result


@router.get(
    "/users/{user_id}/profile",
    response_model=ProfileDiscoveryResponse,
    summary="Get a profile in your institution network",
)
async def get_user_profile(
    user_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    target_user = await database.scalar(select(User).where(User.id == user_id))
    if target_user is None or target_user.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    profile = await database.scalar(select(Profile).where(Profile.user_id == user_id))
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    if not await can_view_profile(
        target_user,
        getattr(profile, "visibility", None) or "NETWORK",
        current_user,
        database,
    ):
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "user_id": str(profile.user_id),
        "display_name": profile.display_name,
        "bio": profile.bio,
        "profile_picture_url": await profile_avatar_url(
            profile, database, providers, request
        ),
        "location": profile.location,
        "website": profile.website,
        "visibility": getattr(profile, "visibility", None) or "NETWORK",
    }


@router.put("/profile/me/avatar", response_model=ProfileResponse)
async def set_my_profile_avatar(
    data: MediaAvatarSet,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    try:
        asset_id = uuid.UUID(data.asset_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="asset_id must be a UUID") from None
    asset = await database.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.owner_id == current_user.id,
            MediaAsset.purpose == "PROFILE_IMAGE",
            MediaAsset.status == "READY",
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Completed avatar asset not found")
    profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.avatar_asset_id = asset.id
    profile.profile_picture_url = None
    profile.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(profile)
    result = profile_response(profile)
    result["profile_picture_url"] = await profile_avatar_url(
        profile, database, providers, request
    )
    return result


@router.delete("/profile/me/avatar", response_model=ProfileResponse)
async def clear_my_profile_avatar(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile.avatar_asset_id = None
    profile.profile_picture_url = None
    profile.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(profile)
    return profile_response(profile)