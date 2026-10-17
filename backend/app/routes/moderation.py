import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_postgres_session
from ..models import (
    Comment,
    ConversationMember,
    Message,
    Post,
    Video,
    Track,
    Profile,
    Report,
    User,
    UserBlock,
)
from ..permissions import require_platform_admin
from ..privacy import can_view_profile, require_post_visibility
from ..rate_limit import RateLimitStore, get_rate_limit_store
from ..schemas import (
    BlockedUserResponse,
    BlockResponse,
    ReportCreate,
    ReportResponse,
    ReportStatusUpdate,
)
from ..security import get_current_postgres_user
from ..security_audit import record_security_event
from .platform_admin import set_account_active


router = APIRouter(tags=["moderation"])


def parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid target id") from None


async def check_report_target(
    data: ReportCreate, reporter: User, database: AsyncSession
) -> uuid.UUID:
    target_id = parse_uuid(data.target_id)
    if data.target_type in {"POST", "REEL"}:
        target = await database.get(Post, target_id)
        if target is None or (
            data.target_type == "REEL" and target.post_type != "REEL"
        ) or (data.target_type == "POST" and target.post_type == "REEL"):
            raise HTTPException(status_code=404, detail="Report target not found")
        await require_post_visibility(target, reporter, database)
        if target.author_id == reporter.id:
            raise HTTPException(status_code=400, detail="You cannot report your own content")
    elif data.target_type in {"VIDEO", "TRACK"}:
        target_model = Video if data.target_type == "VIDEO" else Track
        target = await database.get(target_model, target_id)
        if target is None or target.is_hidden or target.owner_id == reporter.id:
            raise HTTPException(status_code=404, detail="Report target not found")
        from ..privacy import can_view_profile
        from ..models import User
        owner = await database.get(User, target.owner_id)
        if owner is None or not await can_view_profile(owner, target.visibility, reporter, database):
            raise HTTPException(status_code=404, detail="Report target not found")
    elif data.target_type == "COMMENT":
        target = await database.get(Comment, target_id)
        if target is None or target.is_hidden:
            raise HTTPException(status_code=404, detail="Report target not found")
        if target.author_id == reporter.id:
            raise HTTPException(status_code=400, detail="You cannot report your own content")
        post = await database.get(Post, target.post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="Report target not found")
        await require_post_visibility(post, reporter, database)
    elif data.target_type == "USER":
        target = await database.get(User, target_id)
        if target is None or target.id == reporter.id:
            raise HTTPException(status_code=400, detail="Invalid user report target")
        profile = await database.get(Profile, target.id)
        if profile is None or not await can_view_profile(
            target, profile.visibility, reporter, database
        ):
            raise HTTPException(status_code=404, detail="Report target not found")
    else:
        target = await database.get(Message, target_id)
        if target is None or target.deleted_at is not None or target.sender_id == reporter.id:
            raise HTTPException(status_code=404, detail="Report target not found")
        membership = await database.scalar(
            select(ConversationMember.id).where(
                ConversationMember.conversation_id == target.conversation_id,
                ConversationMember.user_id == reporter.id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="Report target not found")
    return target_id


@router.post("/reports", response_model=ReportResponse, status_code=201)
async def create_report(
    data: ReportCreate,
    request: Request,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    limiter: RateLimitStore | None = Depends(get_rate_limit_store),
):
    if limiter is None:
        raise HTTPException(status_code=503, detail="Rate limiting is unavailable")
    count, retry_after = await limiter.increment("report_user", str(current_user.id), 3600)
    if count > 10:
        raise HTTPException(
            status_code=429, detail="Report limit reached", headers={"Retry-After": str(retry_after)}
        )
    target_id = await check_report_target(data, current_user, database)
    report = Report(
        reporter_id=current_user.id,
        target_type=data.target_type,
        target_id=target_id,
        reason=data.reason,
        details=data.details,
    )
    database.add(report)
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="An open report for this target already exists") from None
    await database.refresh(report)
    return report_response(report)


def report_response(report: Report) -> dict:
    return {
        "id": str(report.id),
        "target_type": report.target_type,
        "target_id": str(report.target_id),
        "reason": report.reason,
        "details": report.details,
        "status": report.status,
        "created_at": report.created_at,
        "reviewer_id": str(report.reviewer_id) if report.reviewer_id else None,
    }


@router.post("/users/{user_id}/block", response_model=BlockResponse)
async def block_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")
    target = await database.scalar(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    existing = await database.scalar(
        select(UserBlock.id).where(
            UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == user_id
        )
    )
    if existing is None:
        database.add(UserBlock(blocker_id=current_user.id, blocked_id=user_id))
        await database.commit()
    return {"blocked": True}


@router.delete("/users/{user_id}/block", response_model=BlockResponse)
async def unblock_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    block = await database.scalar(
        select(UserBlock).where(
            UserBlock.blocker_id == current_user.id, UserBlock.blocked_id == user_id
        )
    )
    if block is not None:
        await database.delete(block)
        await database.commit()
    return {"blocked": False}


@router.get("/blocks", response_model=list[BlockedUserResponse])
async def list_blocked_users(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    rows = (
        await database.execute(
            select(User.id, User.username)
            .join(UserBlock, UserBlock.blocked_id == User.id)
            .where(UserBlock.blocker_id == current_user.id)
            .order_by(UserBlock.created_at.desc(), UserBlock.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [{"id": str(row.id), "username": row.username} for row in rows]


@router.get("/admin/reports", response_model=list[ReportResponse])
async def list_reports(
    status_filter: str = Query(default="OPEN", alias="status", pattern="^(OPEN|REVIEWED|DISMISSED|ACTIONED)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    require_platform_admin(current_user)
    reports = list(
        (await database.scalars(
            select(Report).where(Report.status == status_filter)
            .order_by(Report.created_at.asc(), Report.id.asc())
            .offset(offset).limit(limit)
        )).all()
    )
    return [report_response(report) for report in reports]


@router.patch("/admin/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    report_id: uuid.UUID,
    data: ReportStatusUpdate,
    request: Request,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    require_platform_admin(current_user)
    report = await database.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = data.status
    report.reviewer_id = current_user.id
    report.updated_at = datetime.now(timezone.utc)
    record_security_event(
        database,
        event_type="moderation.report_status_changed",
        outcome="SUCCESS",
        request=request,
        actor_user_id=current_user.id,
        target_user_id=report.reporter_id,
    )
    await database.commit()
    await database.refresh(report)
    return report_response(report)


@router.patch("/admin/content/{target_type}/{target_id}")
async def set_content_hidden(
    target_type: str,
    target_id: uuid.UUID,
    hidden: bool = Query(),
    request: Request = None,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
):
    require_platform_admin(current_user)
    model = {"POST": Post, "REEL": Post, "COMMENT": Comment}.get(target_type.upper())
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported content type")
    item = await database.get(model, target_id)
    if item is None or (
        target_type.upper() == "REEL" and item.post_type != "REEL"
    ) or (target_type.upper() == "POST" and item.post_type == "REEL"):
        raise HTTPException(status_code=404, detail="Content not found")
    item.is_hidden = hidden
    record_security_event(
        database,
        event_type="moderation.content_hidden" if hidden else "moderation.content_unhidden",
        outcome="SUCCESS",
        request=request,
        actor_user_id=current_user.id,
    )
    await database.commit()
    return {"hidden": hidden}


@router.post("/admin/users/{user_id}/suspend")
async def suspend_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    return await set_account_active(user_id, False, current_user, database, request)


@router.post("/admin/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    return await set_account_active(user_id, True, current_user, database, request)
