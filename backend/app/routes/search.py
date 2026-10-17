import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, Uuid, and_, exists, func, literal, or_, select, tuple_, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import (
    Course, Department, Faculty, Institution, InstitutionMembership,
    Post, Profile, User, UserBlock,
)
from ..pagination import decode_cursor, encode_cursor
from ..privacy import visible_post_clause
from ..rate_limit import RateLimitStore, get_rate_limit_store
from ..schemas import SearchResponse
from ..security import get_current_postgres_user


router = APIRouter(prefix="/search", tags=["search"])


def normalize_search_query(query: str) -> str:
    return " ".join(query.split()).casefold()


def escape_search_query(query: str) -> str:
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("", response_model=SearchResponse, summary="Search resources in your institutions")
async def global_search(
    query: str = Query(min_length=2, max_length=100),
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    limiter: RateLimitStore | None = Depends(get_rate_limit_store),
):
    normalized = normalize_search_query(query)
    if len(normalized) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query must contain at least 2 non-whitespace characters",
        )
    escaped_query = escape_search_query(normalized)
    pattern = f"%{escaped_query}%"
    if limiter is None:
        raise HTTPException(status_code=503, detail="Rate limiting is unavailable")
    count, retry_after = await limiter.increment("search_user", str(current_user.id), 60)
    if count > 60:
        raise HTTPException(
            status_code=429, detail="Search limit reached",
            headers={"Retry-After": str(retry_after)},
        )

    institution_results = select(
        literal("institution").label("resource_type"),
        Institution.id.label("id"),
        Institution.name.label("name"),
        literal(None, type_=String()).label("code"),
        literal(None, type_=Uuid(as_uuid=True)).label("institution_id"),
    ).join(
        InstitutionMembership,
        InstitutionMembership.institution_id == Institution.id,
    ).where(
        InstitutionMembership.user_id == current_user.id,
        Institution.name.ilike(pattern, escape="\\"),
    )
    course_results = select(
        literal("course").label("resource_type"),
        Course.id.label("id"),
        Course.name.label("name"),
        Course.code.label("code"),
        Faculty.institution_id.label("institution_id"),
    ).join(
        Department,
        Department.id == Course.department_id,
    ).join(
        Faculty,
        Faculty.id == Department.faculty_id,
    ).join(
        InstitutionMembership,
        InstitutionMembership.institution_id == Faculty.institution_id,
    ).where(
        InstitutionMembership.user_id == current_user.id,
        or_(
            Course.name.ilike(pattern, escape="\\"),
            Course.code.ilike(pattern, escape="\\"),
        ),
    )

    shared_profile_membership = exists(
        select(1).where(
            InstitutionMembership.user_id == User.id,
            InstitutionMembership.institution_id.in_(
                select(InstitutionMembership.institution_id).where(
                    InstitutionMembership.user_id == current_user.id
                )
            ),
        )
    )
    blocked_person = exists(
        select(1).where(
            ((UserBlock.blocker_id == current_user.id) & (UserBlock.blocked_id == User.id))
            | ((UserBlock.blocker_id == User.id) & (UserBlock.blocked_id == current_user.id))
        )
    )
    people_results = select(
        literal("person").label("resource_type"),
        User.id.label("id"),
        func.coalesce(Profile.display_name, User.username).label("name"),
        User.username.label("code"),
        literal(None, type_=Uuid(as_uuid=True)).label("institution_id"),
    ).outerjoin(Profile, Profile.user_id == User.id).where(
        User.is_active.is_(True),
        ~blocked_person,
        or_(
            User.username.ilike(pattern, escape="\\"),
            Profile.display_name.ilike(pattern, escape="\\"),
        ),
        or_(
            User.id == current_user.id,
            Profile.visibility.in_(("PUBLIC", "AUTHENTICATED")),
            and_(Profile.visibility == "NETWORK", shared_profile_membership),
        ),
    )
    post_results = select(
        literal("post").label("resource_type"),
        Post.id.label("id"),
        func.left(Post.content, 160).label("name"),
        literal(None, type_=String()).label("code"),
        literal(None, type_=Uuid(as_uuid=True)).label("institution_id"),
    ).where(
        Post.content.ilike(pattern, escape="\\"),
        visible_post_clause(current_user),
    )
    school_results = select(
        literal("school").label("resource_type"),
        Institution.id.label("id"),
        Institution.name.label("name"),
        literal(None, type_=String()).label("code"),
        Institution.id.label("institution_id"),
    ).where(
        Institution.is_listed.is_(True),
        Institution.name.ilike(pattern, escape="\\"),
    )

    results = union_all(
        institution_results, course_results, people_results, post_results, school_results
    ).subquery()
    statement = (
        select(
            results.c.resource_type,
            results.c.id,
            results.c.name,
            results.c.code,
            results.c.institution_id,
        )
    )
    if cursor is not None:
        cursor_name, cursor_type, cursor_id_value = decode_cursor(cursor, 3)
        try:
            cursor_id = uuid.UUID(cursor_id_value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid pagination cursor",
            ) from None
        statement = statement.where(
            tuple_(
                func.lower(results.c.name),
                results.c.resource_type,
                results.c.id,
            )
            > tuple_(cursor_name.casefold(), cursor_type, cursor_id)
        )
    else:
        statement = statement.offset(offset)
    statement = statement.order_by(
        func.lower(results.c.name), results.c.resource_type, results.c.id
    ).limit(limit + 1)
    rows = list((await database.execute(statement)).mappings().all())
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = [
        {
            "id": str(row["id"]),
            "resource_type": row["resource_type"],
            "name": row["name"],
            "code": row["code"],
            "institution_id": str(row["institution_id"]) if row["institution_id"] else None,
        }
        for row in page_rows
    ]
    next_cursor = (
        encode_cursor(
            str(page_rows[-1]["name"]),
            str(page_rows[-1]["resource_type"]),
            str(page_rows[-1]["id"]),
        )
        if has_more and page_rows
        else None
    )
    return {
        "query": normalized,
        "items": items,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": next_cursor,
    }
