import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Follow, Notification, Profile, User
from ..pagination import ascending_username_uuid_clause, username_uuid_cursor
from ..privacy import can_view_profile
from ..schemas import FollowUserResponse
from ..security import get_current_postgres_user, get_optional_postgres_user


router = APIRouter(tags=["follows"])


async def require_user(user_id: uuid.UUID, database: AsyncSession) -> User:
    user = await database.scalar(select(User).where(User.id == user_id))
    if user is None or user.is_active is False:
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
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    response: Response = None,
):
    owner = await require_user(user_id, database)
    profile = await database.scalar(select(Profile).where(Profile.user_id == user_id))
    if not await can_view_profile(
        owner,
        getattr(profile, "visibility", None) or "NETWORK",
        current_user,
        database,
    ):
        raise HTTPException(status_code=404, detail="User not found")
    statement = (
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.following_id == user_id, User.is_active.is_(True))
    )
    if cursor is not None:
        statement = statement.where(
            ascending_username_uuid_clause(User.username, User.id, cursor)
        )
    users = list(
        (
            await database.scalars(
                statement.order_by(User.username.asc(), User.id.asc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(users) > limit
    page = users[:limit]
    if response is not None and has_more and page:
        response.headers["X-Next-Cursor"] = username_uuid_cursor(
            page[-1].username, page[-1].id
        )
    return [{"id": str(user.id), "username": user.username} for user in page]


@router.get(
    "/users/{user_id}/following",
    response_model=list[FollowUserResponse],
    summary="List users followed by a user",
)
async def list_following(
    user_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    response: Response = None,
):
    owner = await require_user(user_id, database)
    profile = await database.scalar(select(Profile).where(Profile.user_id == user_id))
    if not await can_view_profile(
        owner,
        getattr(profile, "visibility", None) or "NETWORK",
        current_user,
        database,
    ):
        raise HTTPException(status_code=404, detail="User not found")
    statement = (
        select(User)
        .join(Follow, Follow.following_id == User.id)
        .where(Follow.follower_id == user_id, User.is_active.is_(True))
    )
    if cursor is not None:
        statement = statement.where(
            ascending_username_uuid_clause(User.username, User.id, cursor)
        )
    users = list(
        (
            await database.scalars(
                statement.order_by(User.username.asc(), User.id.asc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(users) > limit
    page = users[:limit]
    if response is not None and has_more and page:
        response.headers["X-Next-Cursor"] = username_uuid_cursor(
            page[-1].username, page[-1].id
        )
    return [{"id": str(user.id), "username": user.username} for user in page]
