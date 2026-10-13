import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import record_activity
from ..config import REEL_MAX_BYTES
from ..database import get_postgres_session
from ..models import Follow, MediaAsset, Post, User
from ..pagination import descending_time_uuid_clause, time_uuid_cursor
from ..privacy import visible_post_clause
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..schemas import CreateReel, FeedResponse, PostResponse
from ..security import get_current_postgres_user
from .posts import post_responses


router = APIRouter(prefix="/reels", tags=["reels"])


async def owned_reel_asset(asset_id: str, current_user: User, database: AsyncSession) -> MediaAsset:
    try:
        parsed_asset_id = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="media_asset_id must be a UUID") from None
    asset = await database.scalar(
        select(MediaAsset).where(
            MediaAsset.id == parsed_asset_id,
            MediaAsset.owner_id == current_user.id,
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="REEL media asset not found")
    if asset.purpose != "REEL":
        raise HTTPException(status_code=422, detail="Media asset purpose must be REEL")
    if asset.status != "READY":
        raise HTTPException(status_code=409, detail="REEL media asset must be completed before publishing")
    if asset.content_type not in {"video/mp4", "video/webm"}:
        raise HTTPException(status_code=422, detail="REEL video must be MP4 or WebM")
    if asset.byte_size > REEL_MAX_BYTES:
        raise HTTPException(status_code=413, detail="REEL video exceeds the configured size limit")
    return asset


@router.post("", response_model=PostResponse, status_code=status.HTTP_201_CREATED, summary="Create a reel")
async def create_reel(
    data: CreateReel,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    asset = await owned_reel_asset(data.media_asset_id, current_user, database)
    reel = Post(
        author_id=current_user.id,
        author=current_user,
        content=data.content,
        visibility=data.visibility,
        post_type="REEL",
        media_asset_id=asset.id,
    )
    database.add(reel)
    await database.flush()
    await record_activity(
        database,
        event_type="social.reel.created",
        actor_id=current_user.id,
        target_type="post",
        target_id=reel.id,
    )
    await database.commit()
    await database.refresh(reel)
    return (await post_responses([reel], current_user, database, providers, request))[0]


@router.get("/feed", response_model=FeedResponse, summary="Get visible reels")
async def get_reels_feed(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=20),
    cursor: str | None = None,
):
    followed_user_ids = select(Follow.following_id).where(Follow.follower_id == current_user.id)
    statement = (
        select(Post)
        .join(User, User.id == Post.author_id)
        .where(
            Post.post_type == "REEL",
            User.is_active.is_(True),
            or_(Post.author_id == current_user.id, Post.author_id.in_(followed_user_ids)),
            visible_post_clause(current_user),
        )
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if cursor is None:
        statement = statement.offset(offset)
    else:
        statement = statement.where(
            descending_time_uuid_clause(Post.created_at, Post.id, cursor)
        )
    reels = list((await database.scalars(statement)).all())
    has_more = len(reels) > limit
    reels = reels[:limit]
    next_cursor = time_uuid_cursor(reels[-1].created_at, reels[-1].id) if has_more and reels else None
    return {
        "items": await post_responses(reels, current_user, database, providers, request),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.delete("/{reel_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete your reel")
async def delete_reel(
    reel_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    reel = await database.scalar(
        select(Post).where(
            Post.id == reel_id,
            Post.author_id == current_user.id,
            Post.post_type == "REEL",
        )
    )
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    asset = await database.scalar(
        select(MediaAsset).where(
            MediaAsset.id == reel.media_asset_id,
            MediaAsset.owner_id == current_user.id,
            MediaAsset.purpose == "REEL",
        )
    )
    if asset is None:
        raise HTTPException(status_code=409, detail="Reel video asset is unavailable")
    storage = provider_or_503(providers, "storage")
    await storage.delete_object(asset.storage_key)
    await database.delete(reel)
    await database.flush()
    await database.delete(asset)
    await database.commit()