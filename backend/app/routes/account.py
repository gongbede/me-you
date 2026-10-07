import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..account_tokens import (
    invalidate_account_email_tokens,
    issue_account_email_token,
    lock_valid_account_token,
)
from ..database import get_postgres_session
from ..models import (
    AccountEmailToken,
    AssessmentResult,
    AssessmentSubmission,
    Comment,
    ExerciseSubmission,
    Message,
    Post,
    Profile,
    Student,
    User,
)
from ..permissions import ensure_account_can_be_deactivated
from ..providers import ProviderRegistry, get_provider_registry, provider_or_503
from ..schemas import (
    AccountLifecycleResponse,
    EmailTokenConfirm,
    PasswordChangeRequest,
    PasswordChangeResponse,
    PasswordConfirmationRequest,
    PasswordRecoveryConfirm,
    PasswordRecoveryRequest,
    UserResponse,
)
from ..security import get_current_postgres_user, password_hash
from ..security_audit import record_security_event


router = APIRouter(tags=["account"])


@router.get(
    "/account/me",
    response_model=UserResponse,
    summary="Get the current account",
)
async def get_my_account(
    current_user: User = Depends(get_current_postgres_user),
    _database: AsyncSession = Depends(get_postgres_session),
):
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "created_at": current_user.created_at,
    }


@router.put(
    "/account/password",
    response_model=PasswordChangeResponse,
    summary="Change the current user's password",
)
async def change_my_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    if not password_hash.verify(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must differ from the current password",
        )

    current_user.password_hash = password_hash.hash(data.new_password)
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await invalidate_account_email_tokens(database, current_user.id)
        if request is not None:
            record_security_event(
                database,
                event_type="account.password_changed",
                outcome="SUCCESS",
                request=request,
                actor_user_id=current_user.id,
                target_user_id=current_user.id,
            )
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Password updated"}


async def confirm_current_password(data: PasswordConfirmationRequest, current_user: User) -> None:
    if not password_hash.verify(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )


@router.post(
    "/account/sessions/revoke",
    response_model=AccountLifecycleResponse,
    summary="Revoke all current account sessions",
)
async def revoke_account_sessions(
    data: PasswordConfirmationRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    await confirm_current_password(data, current_user)
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await invalidate_account_email_tokens(database, current_user.id)
        if request is not None:
            record_security_event(
                database,
                event_type="account.sessions_revoked",
                outcome="SUCCESS",
                request=request,
                actor_user_id=current_user.id,
                target_user_id=current_user.id,
            )
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "All account sessions have been revoked"}


@router.post(
    "/account/logout",
    response_model=AccountLifecycleResponse,
    summary="Log out and revoke the current account's tokens",
)
async def logout_account(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    await invalidate_account_email_tokens(database, current_user.id)
    if request is not None:
        record_security_event(
            database,
            event_type="account.sessions_revoked",
            outcome="SUCCESS",
            request=request,
            actor_user_id=current_user.id,
            target_user_id=current_user.id,
            details={"source": "logout"},
        )
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Logged out"}


@router.post(
    "/account/email-verification",
    response_model=AccountLifecycleResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send an email verification token",
)
async def request_email_verification(
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    provider = provider_or_503(providers, "email")
    await issue_account_email_token(database, provider, current_user, "EMAIL_VERIFICATION")
    return {"message": "If the account is eligible, a verification message will be sent"}


@router.post(
    "/account/email-verification/confirm",
    response_model=AccountLifecycleResponse,
    summary="Verify the account email address",
)
async def confirm_email_verification(
    data: EmailTokenConfirm,
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    token, user = await lock_valid_account_token(
        database, data.token, "EMAIL_VERIFICATION"
    )
    now = datetime.now(timezone.utc)
    token.consumed_at = now
    user.email_verified_at = now
    if request is not None:
        record_security_event(
            database,
            event_type="account.email_verified",
            outcome="SUCCESS",
            request=request,
            actor_user_id=user.id,
            target_user_id=user.id,
        )
    await database.commit()
    return {"message": "Email verified"}


@router.post(
    "/account/password-recovery",
    response_model=AccountLifecycleResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password recovery email",
)
async def request_password_recovery(
    data: PasswordRecoveryRequest,
    database: AsyncSession = Depends(get_postgres_session),
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    provider = provider_or_503(providers, "email")
    user = await database.scalar(
        select(User).where(
            User.email == data.email,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if user is not None:
        await issue_account_email_token(database, provider, user, "PASSWORD_RESET")
    return {"message": "If the account is eligible, a recovery message will be sent"}


@router.post(
    "/account/password-recovery/confirm",
    response_model=PasswordChangeResponse,
    summary="Set a new password using a recovery token",
)
async def confirm_password_recovery(
    data: PasswordRecoveryConfirm,
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    token, user = await lock_valid_account_token(database, data.token, "PASSWORD_RESET")
    now = datetime.now(timezone.utc)
    token.consumed_at = now
    user.password_hash = password_hash.hash(data.new_password)
    user.token_version = (getattr(user, "token_version", 0) or 0) + 1
    await invalidate_account_email_tokens(database, user.id)
    if request is not None:
        record_security_event(
            database,
            event_type="account.password_recovered",
            outcome="SUCCESS",
            request=request,
            actor_user_id=user.id,
            target_user_id=user.id,
        )
    await database.commit()
    return {"message": "Password updated"}


@router.post(
    "/account/deactivate",
    response_model=AccountLifecycleResponse,
    summary="Deactivate the current account",
)
async def deactivate_account(
    data: PasswordConfirmationRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    await confirm_current_password(data, current_user)
    await ensure_account_can_be_deactivated(
        current_user.id,
        database,
        is_platform_admin=bool(getattr(current_user, "is_platform_admin", False)),
    )
    current_user.is_active = False
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    try:
        await invalidate_account_email_tokens(database, current_user.id)
        if request is not None:
            record_security_event(
                database,
                event_type="account.deactivated",
                outcome="SUCCESS",
                request=request,
                actor_user_id=current_user.id,
                target_user_id=current_user.id,
            )
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Account deactivated"}


@router.delete(
    "/account/me",
    response_model=AccountLifecycleResponse,
    summary="Anonymize and deactivate the current account",
)
async def delete_account(
    data: PasswordConfirmationRequest,
    current_user: User = Depends(get_current_postgres_user),
    database: AsyncSession = Depends(get_postgres_session),
    request: Request = None,
):
    await confirm_current_password(data, current_user)
    await ensure_account_can_be_deactivated(
        current_user.id,
        database,
        is_platform_admin=bool(getattr(current_user, "is_platform_admin", False)),
    )
    now = datetime.now(timezone.utc)
    anonymous_id = uuid.uuid4().hex
    current_user.username = f"deleted-{anonymous_id}"
    current_user.email = f"deleted+{anonymous_id}@deleted.invalid"
    current_user.password_hash = password_hash.hash(secrets.token_urlsafe(48))
    current_user.is_active = False
    current_user.email_verified_at = None
    current_user.deleted_at = now
    current_user.token_version = (getattr(current_user, "token_version", 0) or 0) + 1
    await database.execute(delete(Profile).where(Profile.user_id == current_user.id))
    await database.execute(delete(Post).where(Post.author_id == current_user.id))
    await database.execute(delete(Comment).where(Comment.author_id == current_user.id))
    await database.execute(
        update(Message)
        .where(Message.sender_id == current_user.id, Message.deleted_at.is_(None))
        .values(content="[deleted]", deleted_at=now, updated_at=now)
    )
    student_ids = select(Student.id).where(Student.user_id == current_user.id)
    await database.execute(
        update(ExerciseSubmission)
        .where(ExerciseSubmission.student_id.in_(student_ids))
        .values(answer_text="[deleted]", feedback=None)
    )
    submission_ids = select(AssessmentSubmission.id).where(
        AssessmentSubmission.student_id.in_(student_ids)
    )
    await database.execute(
        update(AssessmentSubmission)
        .where(AssessmentSubmission.id.in_(submission_ids))
        .values(answer_text="[deleted]")
    )
    await database.execute(
        update(AssessmentResult)
        .where(AssessmentResult.submission_id.in_(submission_ids))
        .values(feedback=None)
    )
    await database.execute(
        delete(AccountEmailToken).where(AccountEmailToken.user_id == current_user.id)
    )
    if request is not None:
        record_security_event(
            database,
            event_type="account.deleted",
            outcome="SUCCESS",
            request=request,
            actor_user_id=current_user.id,
            target_user_id=current_user.id,
            details={"policy": "anonymized_retention"},
        )
    try:
        await database.commit()
    except BaseException:
        await database.rollback()
        raise
    return {"message": "Account deleted"}