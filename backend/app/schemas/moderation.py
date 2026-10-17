from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ReportCreate(BaseModel):
    target_type: Literal["POST", "COMMENT", "REEL", "USER", "MESSAGE"]
    target_id: str
    reason: Literal["SPAM", "HARASSMENT", "INAPPROPRIATE", "MISINFORMATION", "OTHER"]
    details: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    reason: str
    details: str | None
    status: str
    created_at: datetime
    reviewer_id: str | None = None


class ReportStatusUpdate(BaseModel):
    status: Literal["REVIEWED", "DISMISSED", "ACTIONED"]


class BlockedUserResponse(BaseModel):
    id: str
    username: str


class BlockResponse(BaseModel):
    blocked: bool
