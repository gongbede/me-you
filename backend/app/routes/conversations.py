import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Conversation, ConversationMember, Message, User
from ..schemas import (
    AddConversationMember,
    ConversationMemberResponse,
    ConversationResponse,
    CreateDirectConversation,
    CreateGroupConversation,
    TransferConversationOwnership,
    UserSummary,
)
from ..security import get_current_postgres_user


router = APIRouter(prefix="/conversations", tags=["conversations"])


def summary_user(user: User) -> dict:
    return {"id": str(user.id), "username": user.username}


def conversation_response(
    conversation: Conversation,
    *,
    last_message: Message | None = None,
    unread_count: int = 0,
) -> dict:
    return {
        "id": str(conversation.id),
        "type": conversation.type,
        "name": conversation.name,
        "description": conversation.description,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "members": [
            {"user": summary_user(member.user), "joined_at": member.joined_at, "last_read_at": member.last_read_at}
            for member in conversation.members[:100]
        ],
        "last_message_preview": (
            last_message.content[:200] if last_message is not None else None
        ),
        "last_message_at": last_message.created_at if last_message is not None else None,
        "unread_count": unread_count,
    }


async def member_for(conversation_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> ConversationMember | None:
    return await database.scalar(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id, ConversationMember.user_id == user_id))


async def require_member(conversation_id: uuid.UUID, user_id: uuid.UUID, database: AsyncSession) -> ConversationMember:
    membership = await member_for(conversation_id, user_id, database)
    if membership is None:
        exists = await database.scalar(select(Conversation.id).where(Conversation.id == conversation_id))
        if exists is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conversation membership required")
    return membership


async def load_conversation(conversation_id: uuid.UUID, database: AsyncSession) -> Conversation:
    conversation = await database.scalar(select(Conversation).options(selectinload(Conversation.members).selectinload(ConversationMember.user)).where(Conversation.id == conversation_id))
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


async def conversation_details(
    conversation: Conversation,
    user_id: uuid.UUID,
    database: AsyncSession,
) -> dict:
    membership = await member_for(conversation.id, user_id, database)
    if membership is None:
        raise HTTPException(status_code=403, detail="Conversation membership required")
    last_message = await database.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    unread_statement = select(func.count(Message.id)).where(
        Message.conversation_id == conversation.id,
        Message.sender_id != user_id,
        Message.deleted_at.is_(None),
    )
    if membership.last_read_at is not None:
        unread_statement = unread_statement.where(Message.created_at > membership.last_read_at)
    unread_count = await database.scalar(unread_statement)
    return conversation_response(
        conversation,
        last_message=last_message,
        unread_count=int(unread_count or 0),
    )


async def require_group_owner(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    database: AsyncSession,
) -> Conversation:
    await require_member(conversation_id, user_id, database)
    conversation = await database.scalar(
        select(Conversation).where(Conversation.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.type != "GROUP":
        raise HTTPException(status_code=409, detail="Membership management is only available for groups")
    if conversation.created_by_id != user_id:
        raise HTTPException(status_code=403, detail="Group owner access required")
    return conversation


@router.post("/direct", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED, summary="Create or reuse a direct conversation")
async def create_direct(data: CreateDirectConversation, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    try:
        target_id = uuid.UUID(data.target_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="target_user_id must be a UUID") from None
    if target_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create a conversation with yourself")
    target = await database.scalar(
        select(User).where(User.id == target_id, User.is_active.is_(True))
    )
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    direct_key = ":".join(sorted((str(current_user.id), str(target.id))))
    existing = await database.scalar(select(Conversation).where(Conversation.direct_key == direct_key))
    if existing is not None:
        return conversation_response(await load_conversation(existing.id, database))
    conversation = Conversation(type="DIRECT", direct_key=direct_key, created_by_id=current_user.id, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(conversation)
    await database.flush()
    database.add_all([ConversationMember(conversation_id=conversation.id, user_id=current_user.id), ConversationMember(conversation_id=conversation.id, user_id=target.id)])
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        existing = await database.scalar(select(Conversation).where(Conversation.direct_key == direct_key))
        if existing is None:
            raise HTTPException(status_code=409, detail="Direct conversation could not be created") from None
        return conversation_response(await load_conversation(existing.id, database))
    return conversation_response(await load_conversation(conversation.id, database))


@router.post("/group", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED, summary="Create a group conversation")
async def create_group(data: CreateGroupConversation, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    try:
        member_ids = {uuid.UUID(value) for value in data.member_ids}
    except ValueError:
        raise HTTPException(status_code=422, detail="member_ids must contain UUIDs") from None
    member_ids.add(current_user.id)
    if len(member_ids) > 100:
        raise HTTPException(status_code=422, detail="Groups may have at most 100 members")
    users = list(
        (
            await database.scalars(
                select(User).where(
                    User.id.in_(member_ids),
                    User.is_active.is_(True),
                )
            )
        ).all()
    )
    if len(users) != len(member_ids):
        raise HTTPException(status_code=404, detail="One or more users not found")
    conversation = Conversation(type="GROUP", name=data.name, description=data.description, created_by_id=current_user.id, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(conversation)
    await database.flush()
    database.add_all([ConversationMember(conversation_id=conversation.id, user_id=user.id) for user in users])
    await database.commit()
    return conversation_response(await load_conversation(conversation.id, database))


@router.get("", response_model=list[ConversationResponse], summary="List your conversations")
async def list_conversations(current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=100)):
    conversations = list((await database.scalars(select(Conversation).join(ConversationMember).options(selectinload(Conversation.members).selectinload(ConversationMember.user)).where(ConversationMember.user_id == current_user.id).order_by(Conversation.updated_at.desc(), Conversation.id.desc()).offset(offset).limit(limit))).unique().all())
    return [await conversation_details(conversation, current_user.id, database) for conversation in conversations]


@router.get("/{conversation_id}", response_model=ConversationResponse, summary="Get conversation details")
async def get_conversation(conversation_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await require_member(conversation_id, current_user.id, database)
    conversation = await load_conversation(conversation_id, database)
    return await conversation_details(conversation, current_user.id, database)


@router.post("/{conversation_id}/members", response_model=ConversationMemberResponse, status_code=201, summary="Add a member to a group")
async def add_group_member(conversation_id: uuid.UUID, data: AddConversationMember, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    conversation = await require_group_owner(conversation_id, current_user.id, database)
    try:
        target_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a UUID") from None
    target = await database.scalar(select(User).where(User.id == target_id, User.is_active.is_(True)))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if await member_for(conversation_id, target_id, database) is not None:
        raise HTTPException(status_code=409, detail="User is already a conversation member")
    member_count = await database.scalar(
        select(func.count(ConversationMember.user_id)).where(
            ConversationMember.conversation_id == conversation_id
        )
    )
    if int(member_count or 0) >= 100:
        raise HTTPException(status_code=409, detail="Groups may have at most 100 members")
    membership = ConversationMember(conversation_id=conversation_id, user_id=target_id, user=target)
    database.add(membership)
    conversation.updated_at = datetime.now(timezone.utc)
    try:
        await database.commit()
        await database.refresh(membership)
    except IntegrityError:
        await database.rollback()
        raise HTTPException(status_code=409, detail="User is already a conversation member") from None
    return {"user": summary_user(target), "joined_at": membership.joined_at, "last_read_at": membership.last_read_at}


@router.delete("/{conversation_id}/members/{user_id}", status_code=204, summary="Remove a group member or leave a group")
async def remove_group_member(conversation_id: uuid.UUID, user_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await require_member(conversation_id, current_user.id, database)
    conversation = await database.scalar(
        select(Conversation).where(Conversation.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.type != "GROUP":
        raise HTTPException(status_code=409, detail="Membership management is only available for groups")
    if user_id != current_user.id and conversation.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Group owner access required")
    if user_id == conversation.created_by_id:
        raise HTTPException(status_code=409, detail="Transfer group ownership before leaving or removing the owner")
    membership = await member_for(conversation_id, user_id, database)
    if membership is None:
        raise HTTPException(status_code=404, detail="Conversation member not found")
    await database.delete(membership)
    conversation.updated_at = datetime.now(timezone.utc)
    await database.commit()


@router.patch("/{conversation_id}/owner", response_model=ConversationResponse, summary="Transfer group ownership")
async def transfer_group_owner(conversation_id: uuid.UUID, data: TransferConversationOwnership, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    conversation = await require_group_owner(conversation_id, current_user.id, database)
    try:
        target_id = uuid.UUID(data.user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a UUID") from None
    if await member_for(conversation_id, target_id, database) is None:
        raise HTTPException(status_code=404, detail="Target must be a conversation member")
    conversation.created_by_id = target_id
    conversation.updated_at = datetime.now(timezone.utc)
    await database.commit()
    return await conversation_details(
        await load_conversation(conversation_id, database), target_id, database
    )
