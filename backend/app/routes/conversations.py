import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Conversation, ConversationMember, User
from ..schemas import ConversationMemberResponse, ConversationResponse, CreateDirectConversation, CreateGroupConversation, UserSummary
from ..security import get_current_postgres_user


router = APIRouter(prefix="/conversations", tags=["conversations"])


def summary_user(user: User) -> dict:
    return {"id": str(user.id), "username": user.username}


def conversation_response(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "type": conversation.type,
        "name": conversation.name,
        "description": conversation.description,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "members": [
            {"user": summary_user(member.user), "joined_at": member.joined_at, "last_read_at": member.last_read_at}
            for member in conversation.members
        ],
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


@router.post("/direct", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED, summary="Create or reuse a direct conversation")
async def create_direct(data: CreateDirectConversation, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    try:
        target_id = uuid.UUID(data.target_user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="target_user_id must be a UUID") from None
    if target_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create a conversation with yourself")
    target = await database.scalar(select(User).where(User.id == target_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    direct_key = ":".join(sorted((str(current_user.id), str(target.id))))
    existing = await database.scalar(select(Conversation).where(Conversation.direct_key == direct_key))
    if existing is not None:
        return conversation_response(await load_conversation(existing.id, database))
    conversation = Conversation(type="DIRECT", direct_key=direct_key, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
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
    users = list((await database.scalars(select(User).where(User.id.in_(member_ids)))).all())
    if len(users) != len(member_ids):
        raise HTTPException(status_code=404, detail="One or more users not found")
    conversation = Conversation(type="GROUP", name=data.name, description=data.description, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    database.add(conversation)
    await database.flush()
    database.add_all([ConversationMember(conversation_id=conversation.id, user_id=user.id) for user in users])
    await database.commit()
    return conversation_response(await load_conversation(conversation.id, database))


@router.get("", response_model=list[ConversationResponse], summary="List your conversations")
async def list_conversations(current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    conversations = list((await database.scalars(select(Conversation).join(ConversationMember).options(selectinload(Conversation.members).selectinload(ConversationMember.user)).where(ConversationMember.user_id == current_user.id).order_by(Conversation.updated_at.desc()))).unique().all())
    return [conversation_response(conversation) for conversation in conversations]


@router.get("/{conversation_id}", response_model=ConversationResponse, summary="Get conversation details")
async def get_conversation(conversation_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await require_member(conversation_id, current_user.id, database)
    return conversation_response(await load_conversation(conversation_id, database))
