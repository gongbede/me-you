import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Follow, InstitutionMembership, Post, User, UserBlock
from .permissions import list_user_institution_ids


async def shares_active_institution(
    viewer_id: uuid.UUID,
    owner_id: uuid.UUID,
    database: AsyncSession,
) -> bool:
    viewer_institutions = await list_user_institution_ids(viewer_id, database)
    if not viewer_institutions:
        return False
    owner_institutions = await list_user_institution_ids(owner_id, database)
    return not viewer_institutions.isdisjoint(owner_institutions)


def require_authenticated(viewer: User | None) -> User:
    if viewer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return viewer


async def can_view_profile(
    owner: User,
    visibility: str,
    viewer: User | None,
    database: AsyncSession,
) -> bool:
    if viewer is not None and (
        viewer.is_active is False or getattr(viewer, "deleted_at", None) is not None
    ):
        return False
    if owner.is_active is False:
        return False
    if viewer is not None and viewer.id == owner.id:
        return True
    if viewer is not None:
        blocked = await database.scalar(
            select(UserBlock.id).where(
                ((UserBlock.blocker_id == viewer.id) & (UserBlock.blocked_id == owner.id))
                | ((UserBlock.blocker_id == owner.id) & (UserBlock.blocked_id == viewer.id))
            )
        )
        if blocked is not None:
            return False
    if visibility == "PUBLIC":
        return True
    if viewer is None:
        return False
    if visibility == "AUTHENTICATED":
        return True
    if visibility == "NETWORK":
        return await shares_active_institution(viewer.id, owner.id, database)
    if visibility == "FOLLOWERS":
        return await database.scalar(
            select(Follow.follower_id).where(
                Follow.follower_id == viewer.id,
                Follow.following_id == owner.id,
            )
        ) is not None
    return False


async def require_post_visibility(
    post: Post,
    viewer: User | None,
    database: AsyncSession,
) -> None:
    if getattr(post, "is_hidden", False) and not (
        viewer is not None and getattr(viewer, "is_platform_admin", False)
    ):
        raise HTTPException(status_code=404, detail="Post not found")
    if viewer is not None and viewer.id != post.author_id:
        blocked = await database.scalar(
            select(UserBlock.id).where(
                ((UserBlock.blocker_id == viewer.id) & (UserBlock.blocked_id == post.author_id))
                | ((UserBlock.blocker_id == post.author_id) & (UserBlock.blocked_id == viewer.id))
            )
        )
        if blocked is not None:
            raise HTTPException(status_code=404, detail="Post not found")
    visibility = getattr(post, "visibility", None) or "PUBLIC"
    owner_is_active = await database.scalar(
        select(User.is_active).where(User.id == post.author_id)
    )
    if owner_is_active is not True:
        raise HTTPException(status_code=404, detail="Post not found")
    if viewer is not None and viewer.id == post.author_id:
        return
    if visibility == "PUBLIC":
        return
    if viewer is None:
        require_authenticated(viewer)
    if visibility == "AUTHENTICATED":
        return
    if visibility == "NETWORK" and await shares_active_institution(
        viewer.id, post.author_id, database
    ):
        return
    raise HTTPException(status_code=404, detail="Post not found")


def visible_post_clause(viewer: User):
    own_posts = Post.author_id == viewer.id
    public_posts = Post.visibility == "PUBLIC"
    authenticated_posts = Post.visibility == "AUTHENTICATED"
    network_posts = Post.visibility == "NETWORK"
    private_posts = Post.visibility == "PRIVATE"
    own_institution_ids = select(InstitutionMembership.institution_id).where(
        InstitutionMembership.user_id == viewer.id
    )
    shared_membership = exists(
        select(1).where(
            InstitutionMembership.user_id == Post.author_id,
            InstitutionMembership.institution_id.in_(own_institution_ids),
        )
    )
    from sqlalchemy import and_, or_

    blocked_pair = exists(
        select(1).where(
            ((UserBlock.blocker_id == viewer.id) & (UserBlock.blocked_id == Post.author_id))
            | ((UserBlock.blocker_id == Post.author_id) & (UserBlock.blocked_id == viewer.id))
        )
    )
    visible = or_(
        public_posts,
        authenticated_posts,
        own_posts,
        and_(network_posts, shared_membership),
        and_(private_posts, own_posts),
    )
    if getattr(viewer, "is_platform_admin", False):
        return and_(visible, ~blocked_pair)
    return and_(visible, Post.is_hidden.is_(False), ~blocked_pair)