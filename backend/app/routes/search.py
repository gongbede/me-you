from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import Course, Department, Faculty, Institution, InstitutionMembership, User
from ..schemas import SearchResponse
from ..security import get_current_postgres_user


router = APIRouter(prefix="/search", tags=["search"])


def normalize_search_query(query: str) -> str:
    return " ".join(query.split()).casefold()


@router.get("", response_model=SearchResponse, summary="Search resources in your institutions")
async def global_search(
    query: str = Query(min_length=1, max_length=100),
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    normalized = normalize_search_query(query)
    if len(normalized) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Search query must contain at least 2 non-whitespace characters",
        )
    escaped_query = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped_query}%"

    institution_results = select(
        literal("institution").label("resource_type"),
        Institution.id.label("id"),
        Institution.name.label("name"),
        literal(None, type_=String()).label("code"),
        literal(None, type_=String()).label("institution_id"),
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

    results = union_all(institution_results, course_results).subquery()
    statement = (
        select(
            results.c.resource_type,
            results.c.id,
            results.c.name,
            results.c.code,
            results.c.institution_id,
        )
        .order_by(func.lower(results.c.name), results.c.resource_type, results.c.id)
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list((await database.execute(statement)).mappings().all())
    has_more = len(rows) > limit
    items = [
        {
            "id": str(row["id"]),
            "resource_type": row["resource_type"],
            "name": row["name"],
            "code": row["code"],
            "institution_id": str(row["institution_id"]) if row["institution_id"] else None,
        }
        for row in rows[:limit]
    ]
    return {
        "query": normalized,
        "items": items,
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
    }
