from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationType(str, Enum):
    COMMENT = "COMMENT"
    FOLLOW = "FOLLOW"
    LIKE = "LIKE"
    MESSAGE = "MESSAGE"
    CLASS_ANNOUNCEMENT = "CLASS_ANNOUNCEMENT"
    EXERCISE_SUBMISSION = "EXERCISE_SUBMISSION"
    EXERCISE_REVIEWED = "EXERCISE_REVIEWED"
    NEW_VIDEO = "NEW_VIDEO"
    VIDEO_COMMENT = "VIDEO_COMMENT"
    VIDEO_LIKE = "VIDEO_LIKE"
    NEW_TRACK = "NEW_TRACK"
    MENTION = "MENTION"
    COMMENT_LIKE = "COMMENT_LIKE"


class UserSummary(BaseModel):
    id: str
    username: str


class PostAuthorSummary(UserSummary):
    display_name: str
    avatar_url: str | None


class PostAttachmentInput(BaseModel):
    media_asset_id: str = Field(min_length=36, max_length=36)
    alt_text: str = Field(default="", max_length=200)


class CreatePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"] = "PUBLIC"
    attachments: list[PostAttachmentInput] = Field(default_factory=list, max_length=4)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class CreateReel(BaseModel):
    media_asset_id: str
    content: str = Field(min_length=1, max_length=10000)
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"] = "PUBLIC"

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class UpdatePost(BaseModel):
    content: str = Field(min_length=1, max_length=10000)
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"] | None = None
    attachments: list[PostAttachmentInput] | None = Field(default=None, max_length=4)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be blank")
        return value


class PostAttachmentResponse(BaseModel):
    id: str
    media_asset_id: str
    image_url: str
    alt_text: str
    position: int


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    author_id: str
    author: PostAuthorSummary
    content: str
    visibility: Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"]
    post_type: Literal["POST", "REEL"] = "POST"
    media_asset_id: str | None = None
    video_url: str | None = None
    created_at: datetime
    updated_at: datetime
    edited: bool = False
    attachments: list["PostAttachmentResponse"] = Field(default_factory=list)
    like_count: int
    comment_count: int
    liked_by_me: bool


class CreateComment(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    parent_id: str | None = Field(default=None, min_length=36, max_length=36)

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
    parent_id: str | None = None
    author: UserSummary
    content: str
    created_at: datetime
    updated_at: datetime
    like_count: int = 0
    liked_by_me: bool = False


class LikeResponse(BaseModel):
    user_id: str
    created_at: datetime


class CommentLikeResponse(LikeResponse):
    pass


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


class NotificationPreferencesResponse(BaseModel):
    preferences: dict[NotificationType, bool]


class NotificationPreferencesUpdate(BaseModel):
    preferences: dict[NotificationType, bool] = Field(min_length=1)


class FeedResponse(BaseModel):
    items: list[PostResponse]
    offset: int
    limit: int
    has_more: bool
    next_cursor: str | None = None
