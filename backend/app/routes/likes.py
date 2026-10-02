import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Notification, Post, PostLike, User
from ..schemas import LikeResponse
from ..security import get_current_postgres_user


router = APIRouter(tags=["likes"])


async def require_post(post_id: uuid.UUID, database: AsyncSession) -> Post:
    post = await database.scalar(select(Post).where(Post.id == post_id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.post(
    "/posts/{post_id}/like",
    response_model=LikeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Like a post",
)
async def like_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    post = await require_post(post_id, database)
    existing_like = await database.scalar(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.user_id == current_user.id,
        )
    )
    if existing_like is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Post already liked")

    like = PostLike(post_id=post_id, user_id=current_user.id)
    database.add(like)
    if post.author_id != current_user.id:
        database.add(
            Notification(
                recipient_id=post.author_id,
                actor_id=current_user.id,
                type="LIKE",
                title="New like",
                post_id=post_id,
                target_type="post",
                target_id=post_id,
            )
        )
    try:
        await database.commit()
        await database.refresh(like)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Post already liked") from None

    return {"user_id": str(like.user_id), "created_at": like.created_at}


@router.delete(
    "/posts/{post_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlike a post",
)
async def unlike_post(
    post_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    await require_post(post_id, database)
    like = await database.scalar(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.user_id == current_user.id,
        )
    )
    if like is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Like not found")

    await database.delete(like)
    await database.commit()


@router.get(
    "/posts/{post_id}/likes",
    response_model=list[LikeResponse],
    summary="List post likes",
)
async def list_likes(
    post_id: uuid.UUID,
    database: AsyncSession = Depends(get_postgres_session),
):
    await require_post(post_id, database)
    likes = list(
        (
            await database.scalars(
                select(PostLike)
                .where(PostLike.post_id == post_id)
                .order_by(PostLike.created_at.asc(), PostLike.user_id.asc())
            )
        ).all()
    )
    return [{"user_id": str(like.user_id), "created_at": like.created_at} for like in likes]
