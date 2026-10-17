from datetime import datetime, timezone

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import APP_ENV, S3_ENDPOINT_URL, STORAGE_SIGNED_URL_LIFETIME_SECONDS
from ..database import get_postgres_session
from ..models import Follow, MediaAsset, Post, Profile, User
from ..pagination import descending_time_uuid_clause, time_uuid_cursor
from ..privacy import can_view_profile, visible_post_clause
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..schemas import CreateProfile, FeedResponse, MediaAvatarSet, ProfileDiscoveryResponse, ProfileResponse, UpdateProfile
from ..security import get_current_postgres_user, get_optional_postgres_user
from .media import validate_provider_url
from .posts import post_responses


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

    count_visibility = (
        visible_post_clause(current_user)
        if current_user is not None
        else (Post.visibility == "PUBLIC") & Post.is_hidden.is_(False)
    )
    post_count = await database.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_id == user_id,
            Post.post_type == "POST",
            count_visibility,
        )
    )
    reel_count = await database.scalar(
        select(func.count()).select_from(Post).where(
            Post.author_id == user_id,
            Post.post_type == "REEL",
            count_visibility,
        )
    )
    follower_count = await database.scalar(
        select(func.count()).select_from(Follow).where(Follow.following_id == user_id)
    )
    following_count = await database.scalar(
        select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)
    )
    is_following = False
    if current_user is not None:
        is_following = (
            await database.scalar(
                select(Follow.follower_id).where(
                    Follow.follower_id == current_user.id,
                    Follow.following_id == user_id,
                )
            )
        ) is not None
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
        "username": target_user.username,
        "joined_at": target_user.created_at,
        "post_count": post_count or 0,
        "reel_count": reel_count or 0,
        "follower_count": follower_count or 0,
        "following_count": following_count or 0,
        "is_following": is_following,
    }


@router.get(
    "/users/{user_id}/posts",
    response_model=FeedResponse,
    summary="List a visible user's posts or reels",
)
async def list_user_posts(
    user_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
    post_type: str = Query(default="POST", pattern="^(POST|REEL)$"),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
):
    target_user = await database.scalar(select(User).where(User.id == user_id))
    profile = await database.scalar(select(Profile).where(Profile.user_id == user_id))
    if (
        target_user is None
        or profile is None
        or not await can_view_profile(target_user, profile.visibility, current_user, database)
    ):
        raise HTTPException(status_code=404, detail="Profile not found")
    visibility_clause = (
        visible_post_clause(current_user)
        if current_user is not None
        else (Post.visibility == "PUBLIC") & Post.is_hidden.is_(False)
    )
    statement = (
        select(Post)
        .where(Post.author_id == user_id, Post.post_type == post_type, visibility_clause)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        statement = statement.where(descending_time_uuid_clause(Post.created_at, Post.id, cursor))
    items = list((await database.scalars(statement)).all())
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = time_uuid_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return {
        "items": await post_responses(items, current_user, database, providers, request),
        "offset": 0,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": next_cursor,
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