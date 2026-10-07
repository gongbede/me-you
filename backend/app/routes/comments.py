import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Comment, Notification, Post, User
from ..pagination import ascending_time_uuid_clause, time_uuid_cursor
from ..privacy import require_post_visibility
from ..schemas import CommentResponse, CreateComment, UpdateComment
from ..security import get_current_postgres_user, get_optional_postgres_user
from .posts import user_summary


router = APIRouter(tags=["comments"])


def comment_response(comment: Comment) -> dict:
    return {
        "id": str(comment.id),
        "post_id": str(comment.post_id),
        "author_id": str(comment.author_id),
        "author": user_summary(comment.author),
        "content": comment.content,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
    }


async def get_comment(comment_id: uuid.UUID, database: AsyncSession) -> Comment:
    comment = await database.scalar(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.id == comment_id)
    )
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a post",
)
async def create_comment(
    post_id: uuid.UUID,
    comment_data: CreateComment,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    post = await database.scalar(select(Post).where(Post.id == post_id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await require_post_visibility(post, current_user, database)

    comment = Comment(
        post_id=post_id,
        author_id=current_user.id,
        author=current_user,
        content=comment_data.content,
    )
    database.add(comment)
    if post.author_id != current_user.id:
        database.add(
            Notification(
                recipient_id=post.author_id,
                actor_id=current_user.id,
                type="COMMENT",
                title="New comment",
                post_id=post.id,
                comment=comment,
                target_type="comment",
                target_id=comment.id,
            )
        )
    await database.commit()
    await database.refresh(comment)
    return comment_response(comment)


@router.get(
    "/posts/{post_id}/comments",
    response_model=list[CommentResponse],
    summary="List post comments",
)
async def list_comments(
    post_id: uuid.UUID,
    current_user: User | None = Depends(get_optional_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    response: Response = None,
):
    post = await database.scalar(select(Post).where(Post.id == post_id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await require_post_visibility(post, current_user, database)

    statement = (
        select(Comment)
        .options(selectinload(Comment.author))
        .join(User, User.id == Comment.author_id)
        .where(Comment.post_id == post_id, User.is_active.is_(True))
    )
    if cursor is not None:
        statement = statement.where(
            ascending_time_uuid_clause(Comment.created_at, Comment.id, cursor)
        )
    comments = list(
        (
            await database.scalars(
                statement.order_by(Comment.created_at.asc(), Comment.id.asc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(comments) > limit
    page = comments[:limit]
    if response is not None and has_more and page:
        response.headers["X-Next-Cursor"] = time_uuid_cursor(
            page[-1].created_at, page[-1].id
        )
    return [comment_response(comment) for comment in page]


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Update your comment",
)
async def update_comment(
    comment_id: uuid.UUID,
    comment_data: UpdateComment,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    comment = await get_comment(comment_id, database)
    if comment.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to modify this comment")

    comment.content = comment_data.content
    comment.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(comment)
    return comment_response(comment)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your comment",
)
async def delete_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    comment = await get_comment(comment_id, database)
    if comment.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this comment")

    await database.delete(comment)
    await database.commit()
