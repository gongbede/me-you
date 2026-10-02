import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_postgres_session
from ..models import Conversation, ConversationMember, Message, Notification, User
from ..schemas import CreateMessage, MessageResponse, ReadStateResponse, UpdateMessage
from ..security import get_current_postgres_user
from .conversations import require_member


router = APIRouter(tags=["messages"])


def message_response(message: Message) -> dict:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "sender": {"id": str(message.sender.id), "username": message.sender.username},
        "content": None if message.deleted_at else message.content,
        "created_at": message.created_at,
        "updated_at": message.updated_at,
        "deleted_at": message.deleted_at,
    }


async def get_message(message_id: uuid.UUID, database: AsyncSession) -> Message:
    message = await database.scalar(select(Message).options(selectinload(Message.sender)).where(Message.id == message_id))
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED, summary="Send a message")
async def send_message(conversation_id: uuid.UUID, data: CreateMessage, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    await require_member(conversation_id, current_user.id, database)
    conversation = await database.scalar(select(Conversation).where(Conversation.id == conversation_id))
    message = Message(conversation_id=conversation_id, sender_id=current_user.id, sender=current_user, content=data.content)
    database.add(message)
    member_ids = list((await database.scalars(select(ConversationMember.user_id).where(ConversationMember.conversation_id == conversation_id, ConversationMember.user_id != current_user.id))).all())
    for recipient_id in member_ids:
        database.add(Notification(recipient_id=recipient_id, actor_id=current_user.id, type="MESSAGE", title="New message", target_type="conversation", target_id=conversation_id))
    conversation.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(message)
    return message_response(message)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse], summary="List message history")
async def list_messages(conversation_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    await require_member(conversation_id, current_user.id, database)
    messages = list((await database.scalars(select(Message).options(selectinload(Message.sender)).where(Message.conversation_id == conversation_id).order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit))).all())
    return [message_response(message) for message in messages]


@router.post("/conversations/{conversation_id}/read", response_model=ReadStateResponse, summary="Mark a conversation as read")
async def mark_read(conversation_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    membership = await require_member(conversation_id, current_user.id, database)
    previous_read_at = membership.last_read_at
    unread = await database.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation_id,
            Message.sender_id != current_user.id,
            Message.deleted_at.is_(None),
            Message.created_at > previous_read_at if previous_read_at is not None else True,
        )
    )
    now = datetime.now(timezone.utc)
    membership.last_read_at = now
    await database.commit()
    return {"conversation_id": str(conversation_id), "last_read_at": membership.last_read_at, "unread_count": int(unread or 0)}


@router.patch("/messages/{message_id}", response_model=MessageResponse, summary="Edit your message")
async def edit_message(message_id: uuid.UUID, data: UpdateMessage, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    message = await get_message(message_id, database)
    await require_member(message.conversation_id, current_user.id, database)
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this message")
    if message.deleted_at:
        raise HTTPException(status_code=409, detail="Deleted messages cannot be edited")
    message.content = data.content
    message.updated_at = datetime.now(timezone.utc)
    await database.commit()
    await database.refresh(message)
    return message_response(message)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete your message")
async def delete_message(message_id: uuid.UUID, current_user: User = Depends(get_current_postgres_user), database: AsyncSession = Depends(get_postgres_session)):
    message = await get_message(message_id, database)
    await require_member(message.conversation_id, current_user.id, database)
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this message")
    if message.deleted_at is None:
        message.deleted_at = datetime.now(timezone.utc)
        await database.commit()
