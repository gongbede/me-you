from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .social import UserSummary


ConversationType = Literal["DIRECT", "GROUP"]


def non_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("value must not be blank")
    return value


class CreateDirectConversation(BaseModel):
    target_user_id: str


class CreateGroupConversation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    member_ids: list[str] = Field(default_factory=list, max_length=100)

    _name_not_blank = field_validator("name")(non_blank)


class AddConversationMember(BaseModel):
    user_id: str


class TransferConversationOwnership(BaseModel):
    user_id: str


class ConversationMemberResponse(BaseModel):
    user: UserSummary
    joined_at: datetime
    last_read_at: datetime | None


class ConversationResponse(BaseModel):
    id: str
    type: ConversationType
    name: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime
    members: list[ConversationMemberResponse]
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class CreateMessage(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    _content_not_blank = field_validator("content")(non_blank)


class UpdateMessage(CreateMessage):
    pass


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender: UserSummary
    content: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ReadStateResponse(BaseModel):
    conversation_id: str
    last_read_at: datetime
    unread_count: int
