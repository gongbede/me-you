import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Follow, Post, User
from ..schemas import CreatePost, FeedResponse, PostResponse, UpdatePost
from ..security import get_current_postgres_user


router = APIRouter(prefix="/posts", tags=["posts"])


def user_summary(user: User) -> dict:
    return {"id": str(user.id), "username": user.username}


def post_response(post: Post) -> dict:
    author = post.author
    return {
        "id": str(post.id),
        "author_id": str(post.author_id),
        "author": user_summary(author),
        "content": post.content,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


async def get_post(post_id: uuid.UUID, database: AsyncSession) -> Post:
    post = await database.scalar(
        select(Post)
        .options(selectinload(Post.author))
        .where(Post.id == post_id)
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
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
):
    post = Post(author_id=current_user.id, author=current_user, content=post_data.content)
    database.add(post)
    await database.commit()
    await database.refresh(post)
    return post_response(post)


@router.get(
    "/feed",
    response_model=FeedResponse,
    summary="Get your feed",
)
async def get_feed(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    followed_user_ids = select(Follow.following_id).where(Follow.follower_id == current_user.id)
    statement = (
        select(Post)
        .options(selectinload(Post.author))
        .where(or_(Post.author_id == current_user.id, Post.author_id.in_(followed_user_ids)))
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    posts = list((await database.scalars(statement)).all())
    has_more = len(posts) > limit
    posts = posts[:limit]
    return {
        "items": [post_response(post) for post in posts],
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
    }


@router.get(
    "/{post_id}",
    response_model=PostResponse,
    summary="Get a post",
)
async def get_post_by_id(
    post_id: uuid.UUID,
    database: AsyncSession = Depends(get_postgres_session),
):
    return post_response(await get_post(post_id, database))


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
):
    post = await get_post(post_id, database)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this post")

    post.content = post_data.content
    post.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(post)
    return post_response(post)


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
    post = await get_post(post_id, database)
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this post")

    await database.delete(post)
    await database.commit()


