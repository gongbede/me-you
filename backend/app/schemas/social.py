from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


NotificationType = str


class UserSummary(BaseModel):
    id: str
    username: str


class CreatePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"] = "PUBLIC"

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class UpdatePost(CreatePost):
    pass


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_id: str
    author: UserSummary
    content: str
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"]
    created_at: datetime
    updated_at: datetime


class CreateComment(BaseModel):
    content: str = Field(min_length=1, max_length=5000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class UpdateComment(CreateComment):
    pass


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    post_id: str
    author_id: str
    author: UserSummary
    content: str
    created_at: datetime
    updated_at: datetime


class LikeResponse(BaseModel):
    user_id: str
    created_at: datetime


class FollowUserResponse(BaseModel):
    id: str
    username: str


class NotificationResponse(BaseModel):
    id: str
    type: NotificationType
    title: str
    payload: dict[str, Any] | None
    target_type: str | None
    target_id: str | None
    actor: UserSummary | None
    post_id: str | None
    comment_id: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class FeedResponse(BaseModel):
    items: list[PostResponse]
    offset: int
    limit: int
    has_more: bool
    next_cursor: str | None = None
