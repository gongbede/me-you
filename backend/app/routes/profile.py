from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Profile, User
from ..schemas import CreateProfile, ProfileResponse, UpdateProfile
from ..security import get_current_postgres_user


router = APIRouter(prefix="/profile", tags=["profile"])


def profile_response(profile: Profile) -> dict:
    return {
        "user_id": str(profile.user_id),
        "display_name": profile.display_name,
        "bio": profile.bio,
        "profile_picture_url": profile.profile_picture_url,
        "location": profile.location,
        "website": profile.website,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the current user's profile",
)
async def create_profile(
    profile_data: CreateProfile,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
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

    return profile_response(profile)


@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get the current user's profile",
)
async def get_my_profile(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    profile = await database.scalar(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return profile_response(profile)


@router.patch(
    "/me",
    response_model=ProfileResponse,
    summary="Update the current user's profile",
)
async def update_my_profile(
    profile_data: UpdateProfile,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
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
    return profile_response(profile)