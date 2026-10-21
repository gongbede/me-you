import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..mentions import notify_mentions
from ..models import Comment, CommentLike, Notification, Post, User, UserBlock
from ..notification_preferences import add_notification
from ..pagination import ascending_time_uuid_clause, time_uuid_cursor
from ..privacy import require_post_visibility
from ..schemas import CommentLikeResponse, CommentResponse, CreateComment, UpdateComment
from ..security import get_current_postgres_user, get_optional_postgres_user
from .posts import user_summary


router = APIRouter(tags=["comments"])


def comment_response(comment: Comment) -> dict:
    return {
        "id": str(comment.id),
        "post_id": str(comment.post_id),
        "author_id": str(comment.author_id),
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "author": user_summary(comment.author),
        "content": comment.content,
        "created_at": comment.created_at,
        "updated_at": comment.updated_at,
        "like_count": getattr(comment, "like_count", 0),
        "liked_by_me": getattr(comment, "liked_by_me", False),
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


async def visible_comment_or_404(
    comment_id: uuid.UUID,
    current_user: User,
    database: AsyncSession,
) -> Comment:
    comment = await get_comment(comment_id, database)
    post = await database.scalar(select(Post).where(Post.id == comment.post_id))
    if post is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    await require_post_visibility(post, current_user, database)
    if comment.is_hidden:
        raise HTTPException(status_code=404, detail="Comment not found")
    blocked = await database.scalar(
        select(UserBlock.id).where(
            ((UserBlock.blocker_id == current_user.id) & (UserBlock.blocked_id == comment.author_id))
            | ((UserBlock.blocker_id == comment.author_id) & (UserBlock.blocked_id == current_user.id))
        )
    )
    if blocked is not None:
        raise HTTPException(status_code=404, detail="Comment not found")
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
    if comment_data.parent_id:
        try:
            parent_id = uuid.UUID(comment_data.parent_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid parent comment id") from None
        parent = await database.scalar(
            select(Comment).where(
                Comment.id == parent_id,
                Comment.post_id == post_id,
                Comment.parent_id.is_(None),
                Comment.is_hidden.is_(False),
            )
        )
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        blocked_parent = await database.scalar(
            select(UserBlock.id).where(
                ((UserBlock.blocker_id == current_user.id) & (UserBlock.blocked_id == parent.author_id))
                | ((UserBlock.blocker_id == parent.author_id) & (UserBlock.blocked_id == current_user.id))
            )
        )
        if blocked_parent is not None:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        comment.parent_id = parent.id
    database.add(comment)
    if post.author_id != current_user.id:
        await add_notification(
            database,
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
    await notify_mentions(
        comment.content,
        actor_id=current_user.id,
        post_id=post.id,
        comment_id=comment.id,
        database=database,
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

    like_count = (
        select(func.count())
        .where(CommentLike.comment_id == Comment.id)
        .correlate(Comment)
        .scalar_subquery()
    )
    liked_by_me = (
        exists(
            select(1).where(
                CommentLike.comment_id == Comment.id,
                CommentLike.user_id == current_user.id,
            )
        )
        if current_user is not None
        else False
    )
    statement = (
        select(Comment, like_count, liked_by_me)
        .options(selectinload(Comment.author))
        .join(User, User.id == Comment.author_id)
        .where(Comment.post_id == post_id, User.is_active.is_(True))
    )
    if current_user is None or not getattr(current_user, "is_platform_admin", False):
        statement = statement.where(Comment.is_hidden.is_(False))
        if current_user is not None:
            blocked_author = select(UserBlock.id).where(
                ((UserBlock.blocker_id == current_user.id) & (UserBlock.blocked_id == Comment.author_id))
                | ((UserBlock.blocker_id == Comment.author_id) & (UserBlock.blocked_id == current_user.id))
            )
            statement = statement.where(~blocked_author.exists())
    if cursor is not None:
        statement = statement.where(
            ascending_time_uuid_clause(Comment.created_at, Comment.id, cursor)
        )
    rows = list(
        (
            await database.execute(
                statement.order_by(Comment.created_at.asc(), Comment.id.asc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    if response is not None and has_more and page:
        response.headers["X-Next-Cursor"] = time_uuid_cursor(
            page[-1][0].created_at, page[-1][0].id
        )
    for comment, comment_like_count, is_liked in page:
        comment.like_count = comment_like_count
        comment.liked_by_me = is_liked
    return [comment_response(comment) for comment, _, _ in page]


@router.post(
    "/comments/{comment_id}/like",
    response_model=CommentLikeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Like a comment",
)
async def like_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    comment = await visible_comment_or_404(comment_id, current_user, database)
    existing = await database.scalar(
        select(CommentLike).where(
            CommentLike.comment_id == comment.id,
            CommentLike.user_id == current_user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Comment already liked")
    like = CommentLike(comment_id=comment.id, user_id=current_user.id)
    database.add(like)
    if comment.author_id != current_user.id:
        await add_notification(
            database,
            Notification(
                recipient_id=comment.author_id,
                actor_id=current_user.id,
                type="COMMENT_LIKE",
                title="New comment like",
                post_id=comment.post_id,
                comment_id=comment.id,
                target_type="comment",
                target_id=comment.id,
            ),
        )
    try:
        await database.commit()
        await database.refresh(like)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="Comment already liked") from None
    return {"user_id": str(like.user_id), "created_at": like.created_at}


@router.delete(
    "/comments/{comment_id}/like",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlike a comment",
)
async def unlike_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    comment = await visible_comment_or_404(comment_id, current_user, database)
    like = await database.scalar(
        select(CommentLike).where(
            CommentLike.comment_id == comment.id,
            CommentLike.user_id == current_user.id,
        )
    )
    if like is None:
        raise HTTPException(status_code=404, detail="Comment like not found")
    await database.delete(like)
    await database.commit()


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
