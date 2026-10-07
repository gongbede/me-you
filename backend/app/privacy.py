import uuid

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import InstitutionMembership, Post, User
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
    if visibility == "PUBLIC":
        return True
    if viewer is None:
        return False
    if visibility == "AUTHENTICATED":
        return True
    if visibility == "NETWORK":
        return await shares_active_institution(viewer.id, owner.id, database)
    return False


async def require_post_visibility(
    post: Post,
    viewer: User | None,
    database: AsyncSession,
) -> None:
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

    return or_(
        public_posts,
        authenticated_posts,
        own_posts,
        and_(network_posts, shared_membership),
        and_(private_posts, own_posts),
    )