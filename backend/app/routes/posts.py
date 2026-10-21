import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import record_activity
from ..config import STORAGE_SIGNED_URL_LIFETIME_SECONDS
from ..database import get_postgres_session
from ..mentions import notify_mentions
from ..models import (
    Comment,
    Follow,
    InstitutionMembership,
    MediaAsset,
    Post,
    PostAttachment,
    PostLike,
    Profile,
    User,
)
from ..pagination import descending_time_uuid_clause, time_uuid_cursor
from ..privacy import require_post_visibility, visible_post_clause
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..schemas import CreatePost, FeedResponse, PostResponse, UpdatePost
from ..security import get_current_postgres_user, get_optional_postgres_user
from .media import validate_provider_url


router = APIRouter(prefix="/posts", tags=["posts"])


def user_summary(user: User) -> dict:
    return {"id": str(user.id), "username": user.username}


def post_response(post: Post, author_summary: dict | None = None) -> dict:
    author = post.__dict__.get("author")
    if author_summary is None:
        username = author.username if author is not None else ""
        author_summary = {
            "id": str(post.author_id),
            "username": username,
            "display_name": username,
            "avatar_url": None,
        }
    return {
        "id": str(post.id),
        "author_id": str(post.author_id),
        "author": author_summary,
        "content": post.content,
        "visibility": getattr(post, "visibility", None) or "PUBLIC",
        "post_type": getattr(post, "post_type", "POST") or "POST",
        "media_asset_id": str(post.media_asset_id) if getattr(post, "media_asset_id", None) else None,
        "video_url": None,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "edited": getattr(post, "edited", False),
        "attachments": [],
        "like_count": 0,
        "comment_count": 0,
        "liked_by_me": False,
    }


async def post_responses(
    posts: list[Post],
    viewer: User | None,
    database: AsyncSession,
    providers: ProviderRegistry,
    request: Request | None,
) -> list[dict]:
    if not posts:
        return []

    post_ids = [post.id for post in posts]
    author_ids = {post.author_id for post in posts}
    likes_by_post = (
        select(PostLike.post_id.label("post_id"), func.count().label("like_count"))
        .where(PostLike.post_id.in_(post_ids))
        .group_by(PostLike.post_id)
        .subquery()
    )
    comments_by_post = (
        select(Comment.post_id.label("post_id"), func.count().label("comment_count"))
        .where(Comment.post_id.in_(post_ids))
        .group_by(Comment.post_id)
        .subquery()
    )
    engagement_counts = (
        await database.execute(
            select(
                Post.id,
                func.coalesce(likes_by_post.c.like_count, 0),
                func.coalesce(comments_by_post.c.comment_count, 0),
            )
            .outerjoin(likes_by_post, likes_by_post.c.post_id == Post.id)
            .outerjoin(comments_by_post, comments_by_post.c.post_id == Post.id)
            .where(Post.id.in_(post_ids))
        )
    ).all()
    like_counts = {post_id: count for post_id, count, _ in engagement_counts}
    comment_counts = {post_id: count for post_id, _, count in engagement_counts}

    liked_post_ids = set()
    if viewer is not None:
        liked_post_ids = set(
            (
                await database.scalars(
                    select(PostLike.post_id).where(
                        PostLike.post_id.in_(post_ids),
                        PostLike.user_id == viewer.id,
                    )
                )
            ).all()
        )

    viewer_can_view_restricted_profiles = (
        viewer is not None
        and viewer.is_active is not False
        and getattr(viewer, "deleted_at", None) is None
    )
    author_visibility = []
    if viewer is None:
        author_visibility.append(Profile.visibility == "PUBLIC")
    elif viewer_can_view_restricted_profiles:
        author_visibility.extend(
            [
                Profile.visibility == "PUBLIC",
                User.id == viewer.id,
                Profile.visibility == "AUTHENTICATED",
                and_(
                    Profile.visibility == "FOLLOWERS",
                    exists(
                        select(1).where(
                            Follow.follower_id == viewer.id,
                            Follow.following_id == User.id,
                        )
                    ),
                ),
                and_(
                    Profile.visibility == "NETWORK",
                    exists(
                        select(1).where(
                            InstitutionMembership.user_id == User.id,
                            InstitutionMembership.institution_id.in_(
                                select(InstitutionMembership.institution_id).where(
                                    InstitutionMembership.user_id == viewer.id
                                )
                            ),
                        )
                    ),
                ),
            ]
        )
    profile_visible = and_(
        User.is_active.is_(True),
        or_(False, *author_visibility),
    )
    asset_join = and_(
        MediaAsset.id == Profile.avatar_asset_id,
        MediaAsset.owner_id == User.id,
        MediaAsset.purpose == "PROFILE_IMAGE",
        MediaAsset.status == "READY",
    )
    author_rows = (
        await database.execute(
            select(User, Profile, MediaAsset, profile_visible)
            .outerjoin(Profile, Profile.user_id == User.id)
            .outerjoin(MediaAsset, asset_join)
            .where(User.id.in_(author_ids))
        )
    ).all()

    author_summaries = {}
    for author, profile, avatar_asset, can_view_profile in author_rows:
        display_name = author.username
        avatar_url = None
        if profile is not None and can_view_profile:
            display_name = profile.display_name
            if profile.avatar_asset_id is None:
                avatar_url = profile.profile_picture_url
            elif avatar_asset is not None:
                storage = provider_or_503(providers, "storage")
                value = await storage.create_download_url(
                    avatar_asset.storage_key,
                    expires_in_seconds=STORAGE_SIGNED_URL_LIFETIME_SECONDS,
                )
                avatar_url = validate_provider_url(value, "avatar", request)
        author_summaries[author.id] = {
            "id": str(author.id),
            "username": author.username,
            "display_name": display_name,
            "avatar_url": avatar_url,
        }

    reel_assets_by_id = {}
    reel_posts = [post for post in posts if getattr(post, "post_type", "POST") == "REEL"]
    if reel_posts:
        asset_ids = [post.media_asset_id for post in reel_posts if post.media_asset_id is not None]
        reel_assets = list((await database.scalars(
            select(MediaAsset).where(
                MediaAsset.id.in_(asset_ids),
                MediaAsset.owner_id.in_(author_ids),
                MediaAsset.purpose == "REEL",
                MediaAsset.status == "READY",
            )
        )).all()) if asset_ids else []
        reel_assets_by_id = {asset.id: asset for asset in reel_assets}

    attachment_rows = (
        await database.execute(
            select(PostAttachment, MediaAsset)
            .join(MediaAsset, MediaAsset.id == PostAttachment.media_asset_id)
            .where(
                PostAttachment.post_id.in_(post_ids),
                MediaAsset.owner_id.in_(author_ids),
                MediaAsset.purpose == "POST_IMAGE",
                MediaAsset.status == "READY",
            )
            .order_by(PostAttachment.position.asc())
        )
    ).all()
    attachments_by_post: dict[uuid.UUID, list[dict]] = {}
    post_author_ids = {post.id: post.author_id for post in posts}
    for attachment, asset in attachment_rows:
        if asset.owner_id != post_author_ids.get(attachment.post_id):
            continue
        storage = provider_or_503(providers, "storage")
        image_url = validate_provider_url(
            await storage.create_download_url(
                asset.storage_key, expires_in_seconds=STORAGE_SIGNED_URL_LIFETIME_SECONDS
            ),
            "post image",
            request,
        )
        attachments_by_post.setdefault(attachment.post_id, []).append(
            {
                "id": str(attachment.id),
                "media_asset_id": str(asset.id),
                "image_url": image_url,
                "alt_text": attachment.alt_text,
                "position": attachment.position,
            }
        )

    responses = []
    for post in posts:
        response = post_response(post, author_summaries.get(post.author_id))
        response["like_count"] = like_counts.get(post.id, 0)
        response["comment_count"] = comment_counts.get(post.id, 0)
        response["liked_by_me"] = post.id in liked_post_ids
        response["attachments"] = attachments_by_post.get(post.id, [])
        asset = reel_assets_by_id.get(getattr(post, "media_asset_id", None))
        if (
            getattr(post, "post_type", "POST") == "REEL"
            and asset is not None
            and asset.owner_id == post.author_id
        ):
            storage = provider_or_503(providers, "storage")
            response["video_url"] = validate_provider_url(
                await storage.create_download_url(
                    asset.storage_key,
                    expires_in_seconds=STORAGE_SIGNED_URL_LIFETIME_SECONDS,
                ),
                "reel video",
                request,
            )
        responses.append(response)
    return responses


async def get_post(
    post_id: uuid.UUID,
    database: AsyncSession,
    viewer: User | None = None,
) -> Post:
    post = await database.scalar(
        select(Post).where(Post.id == post_id)
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await require_post_visibility(post, viewer, database)
    return post


async def get_owned_post_images(
    attachment_data: list,
    current_user: User,
    database: AsyncSession,
) -> list[MediaAsset]:
    asset_ids = []
    for attachment in attachment_data:
        try:
            asset_ids.append(uuid.UUID(attachment.media_asset_id))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid image asset id") from None
    if len(set(asset_ids)) != len(asset_ids):
        raise HTTPException(status_code=422, detail="An image cannot be attached more than once")
    if not asset_ids:
        return []
    assets = list(
        (
            await database.scalars(
                select(MediaAsset).where(
                    MediaAsset.id.in_(asset_ids),
                    MediaAsset.owner_id == current_user.id,
                    MediaAsset.purpose == "POST_IMAGE",
                    MediaAsset.status == "READY",
                )
            )
        ).all()
    )
    assets_by_id = {asset.id: asset for asset in assets}
    if len(assets_by_id) != len(asset_ids):
        raise HTTPException(
            status_code=422,
            detail="Images must be completed POST_IMAGE uploads owned by you",
        )
    return [assets_by_id[asset_id] for asset_id in asset_ids]


@router.post(
    "",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a post",
)
async def create_post(
    post_data: CreatePost,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    attachment_assets = await get_owned_post_images(
        post_data.attachments, current_user, database
    )
    post = Post(
        author_id=current_user.id,
        author=current_user,
        content=post_data.content,
        visibility=post_data.visibility,
    )
    database.add(post)
    await database.flush()
    for position, (attachment_data, asset) in enumerate(
        zip(post_data.attachments, attachment_assets, strict=True)
    ):
        database.add(
            PostAttachment(
                post_id=post.id,
                media_asset_id=asset.id,
                position=position,
                alt_text=attachment_data.alt_text,
            )
        )
    await record_activity(
        database,
        event_type="social.post.created",
        actor_id=current_user.id,
        target_type="post",
        target_id=post.id,
    )
    await notify_mentions(
        post.content, actor_id=current_user.id, post_id=post.id, database=database
    )
    await database.commit()
    await database.refresh(post)
    return (await post_responses([post], current_user, database, providers, request))[0]


@router.get(
    "/feed",
    response_model=FeedResponse,
    summary="Get your feed",
)
async def get_feed(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    mode: str = Query(default="FOLLOWING", pattern="^(FOLLOWING|LATEST)$"),
):
    followed_user_ids = select(Follow.following_id).where(Follow.follower_id == current_user.id)
    author_scope = (
        or_(Post.author_id == current_user.id, Post.author_id.in_(followed_user_ids))
        if mode == "FOLLOWING"
        else True
    )
    statement = (
        select(Post)
        .join(User, User.id == Post.author_id)
        .where(
            Post.post_type == "POST",
            author_scope,
            User.is_active.is_(True),
            visible_post_clause(current_user),
        )
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        statement = statement.where(
            descending_time_uuid_clause(Post.created_at, Post.id, cursor)
        )
    else:
        statement = statement.offset(offset)
    posts = list((await database.scalars(statement)).all())
    has_more = len(posts) > limit
    posts = posts[:limit]
    next_cursor = (
        time_uuid_cursor(posts[-1].created_at, posts[-1].id)
        if has_more and posts
        else None
    )
    return {
        "items": await post_responses(posts, current_user, database, providers, request),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="Get a post",
)
async def get_post_by_id(
    post_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    post = await get_post(post_id, database, current_user)
    return (await post_responses([post], current_user, database, providers, request))[0]


@router.patch(
    "/{post_id}",
    response_model=PostResponse,
    summary="Update your post",
)
async def update_post(
    post_id: uuid.UUID,
    post_data: UpdatePost,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
    request: Request = None,
):
    post = await get_post(post_id, database, current_user)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this post")

    post.content = post_data.content
    if post_data.visibility is not None:
        post.visibility = post_data.visibility
    if post_data.attachments is not None:
        replacement_assets = await get_owned_post_images(
            post_data.attachments, current_user, database
        )
        current_attachments = list(
            (await database.scalars(
                select(PostAttachment).where(PostAttachment.post_id == post.id)
            )).all()
        )
        new_asset_ids = {asset.id for asset in replacement_assets}
        removed_asset_ids = {
            attachment.media_asset_id
            for attachment in current_attachments
            if attachment.media_asset_id not in new_asset_ids
        }
        for attachment in current_attachments:
            await database.delete(attachment)
        await database.flush()
        storage = provider_or_503(providers, "storage") if removed_asset_ids else None
        for attachment in current_attachments:
            if attachment.media_asset_id not in new_asset_ids:
                asset = await database.get(MediaAsset, attachment.media_asset_id)
                if asset is not None:
                    assert storage is not None
                    await storage.delete_object(asset.storage_key)
                    await database.delete(asset)
        for position, (attachment_data, asset) in enumerate(
            zip(post_data.attachments, replacement_assets, strict=True)
        ):
            database.add(
                PostAttachment(
                    post_id=post.id,
                    media_asset_id=asset.id,
                    position=position,
                    alt_text=attachment_data.alt_text,
                )
            )
    post.updated_at = datetime.now(timezone.utc)
    post.edited = True
    await database.commit()
    await database.refresh(post)
    return (await post_responses([post], current_user, database, providers, request))[0]


@router.delete(
    "/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your post",
)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    post = await get_post(post_id, database, current_user)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post")
    if getattr(post, "post_type", "POST") == "REEL":
        raise HTTPException(status_code=409, detail="Use the reel delete endpoint to remove this video")

    attachments = list(
        (await database.scalars(
            select(PostAttachment).where(PostAttachment.post_id == post.id)
        )).all()
    )
    assets = [await database.get(MediaAsset, attachment.media_asset_id) for attachment in attachments]
    storage = provider_or_503(providers, "storage") if any(assets) else None
    for attachment in attachments:
        await database.delete(attachment)
    await database.flush()
    for asset in assets:
        if asset is not None:
            assert storage is not None
            await storage.delete_object(asset.storage_key)
            await database.delete(asset)

    await database.delete(post)
    await database.commit()

