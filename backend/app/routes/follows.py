import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Follow, Notification, User
from ..schemas import FollowUserResponse
from ..security import get_current_postgres_user


router = APIRouter(tags=["follows"])


async def require_user(user_id: uuid.UUID, database: AsyncSession) -> User:
    user = await database.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post(
    "/users/{user_id}/follow",
    response_model=FollowUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Follow a user",
)
async def follow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    target = await require_user(user_id, database)
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

    existing_follow = await database.scalar(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == target.id,
        )
    )
    if existing_follow is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following user")

    follow = Follow(follower_id=current_user.id, following_id=target.id)
    database.add(follow)
    database.add(
        Notification(
            recipient_id=target.id,
            actor_id=current_user.id,
            type="FOLLOW",
            title="New follower",
            target_type="user",
            target_id=current_user.id,
        )
    )
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following user") from None

    return {"id": str(target.id), "username": target.username}


@router.delete(
    "/users/{user_id}/follow",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unfollow a user",
)
async def unfollow_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    await require_user(user_id, database)
    follow = await database.scalar(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.following_id == user_id,
        )
    )
    if follow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow not found")

    await database.delete(follow)
    await database.commit()


@router.get(
    "/users/{user_id}/followers",
    response_model=list[FollowUserResponse],
    summary="List a user's followers",
)
async def list_followers(
    user_id: uuid.UUID,
    database: AsyncSession = Depends(get_postgres_session),
):
    await require_user(user_id, database)
    users = list(
        (
            await database.scalars(
                select(User)
                .join(Follow, Follow.follower_id == User.id)
                .where(Follow.following_id == user_id)
                .order_by(User.username.asc())
            )
        ).all()
    )
    return [{"id": str(user.id), "username": user.username} for user in users]


@router.get(
    "/users/{user_id}/following",
    response_model=list[FollowUserResponse],
    summary="List users followed by a user",
)
async def list_following(
    user_id: uuid.UUID,
    database: AsyncSession = Depends(get_postgres_session),
):
    await require_user(user_id, database)
    users = list(
        (
            await database.scalars(
                select(User)
                .join(Follow, Follow.following_id == User.id)
                .where(Follow.follower_id == user_id)
                .order_by(User.username.asc())
            )
        ).all()
    )
    return [{"id": str(user.id), "username": user.username} for user in users]
