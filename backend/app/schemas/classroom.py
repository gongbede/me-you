from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .education_learning import non_blank


ClassSessionStatus = Literal["SCHEDULED", "LIVE", "ENDED", "CANCELLED"]
ClassAttendanceStatus = Literal["PRESENT", "LATE", "ABSENT"]
ClassSessionMessageType = Literal["CHAT", "ANNOUNCEMENT"]


class ClassSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    starts_at: datetime
    ends_at: datetime
    _title_not_blank = field_validator("title")(non_blank)

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Session times must include a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ClassSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    _title_not_blank = field_validator("title")(lambda value: non_blank(value) if value is not None else value)


class ClassSessionResponse(BaseModel):
    id: str
    course_id: str
    created_by_id: str
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    status: ClassSessionStatus
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ClassSessionAttendanceResponse(BaseModel):
    session_id: str
    user_id: str
    username: str
    status: ClassAttendanceStatus
    joined_at: datetime | None
    updated_at: datetime


class ClassSessionAttendanceUpdate(BaseModel):
    user_id: str
    status: ClassAttendanceStatus


class ClassSessionJoinResponse(BaseModel):
    session_id: str
    user_id: str
    status: ClassAttendanceStatus
    joined_at: datetime


class ClassSessionMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5000)
    message_type: ClassSessionMessageType = "CHAT"
    _content_not_blank = field_validator("content")(non_blank)


class ClassSessionMessageResponse(BaseModel):
    id: str
    session_id: str
    sender_id: str
    sender_name: str
    message_type: ClassSessionMessageType
    content: str
    created_at: datetime