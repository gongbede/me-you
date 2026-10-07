import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..activity import record_activity
from ..config import STORAGE_SIGNED_URL_LIFETIME_SECONDS
from ..database import get_postgres_session
from ..models import (
    Comment,
    Follow,
    InstitutionMembership,
    MediaAsset,
    Post,
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
        "created_at": post.created_at,
        "updated_at": post.updated_at,
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
    like_counts = dict(
        (
            await database.execute(
                select(PostLike.post_id, func.count())
                .where(PostLike.post_id.in_(post_ids))
                .group_by(PostLike.post_id)
            )
        ).all()
    )
    comment_counts = dict(
        (
            await database.execute(
                select(Comment.post_id, func.count())
                .where(Comment.post_id.in_(post_ids))
                .group_by(Comment.post_id)
            )
        ).all()
    )

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

    responses = []
    for post in posts:
        response = post_response(post, author_summaries.get(post.author_id))
        response["like_count"] = like_counts.get(post.id, 0)
        response["comment_count"] = comment_counts.get(post.id, 0)
        response["liked_by_me"] = post.id in liked_post_ids
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
    post = Post(
        author_id=current_user.id,
        author=current_user,
        content=post_data.content,
        visibility=post_data.visibility,
    )
    database.add(post)
    await database.flush()
    await record_activity(
        database,
        event_type="social.post.created",
        actor_id=current_user.id,
        target_type="post",
        target_id=post.id,
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
):
    followed_user_ids = select(Follow.following_id).where(Follow.follower_id == current_user.id)
    statement = (
        select(Post)
        .join(User, User.id == Post.author_id)
        .where(
            or_(Post.author_id == current_user.id, Post.author_id.in_(followed_user_ids)),
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
    if "visibility" in post_data.model_fields_set:
        post.visibility = post_data.visibility
    post.updated_at = datetime.now(timezone.utc)
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
):
    post = await get_post(post_id, database, current_user)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post")

    await database.delete(post)
    await database.commit()


