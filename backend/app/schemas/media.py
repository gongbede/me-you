from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


MediaPurpose = Literal[
    "PROFILE_IMAGE",
    "POST_MEDIA",
    "COURSE_MEDIA",
    "REEL",
    "MESSAGE_ATTACHMENT",
]
MediaStatus = Literal["UPLOAD_PENDING", "READY", "FAILED"]


class MediaUploadIntentCreate(BaseModel):
    purpose: MediaPurpose
    institution_id: str | None = Field(default=None, min_length=36, max_length=36)
    content_type: str = Field(min_length=1, max_length=120)
    byte_size: int = Field(gt=0, le=1_000_000_000)
    original_filename: str = Field(min_length=1, max_length=255)

    @field_validator("content_type")
    @classmethod
    def normalize_content_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("original_filename")
    @classmethod
    def filename_must_be_a_single_safe_name(cls, value: str) -> str:
        value = value.strip()
        if (
            not value
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("original_filename must be a safe filename")
        return value


class MediaAssetResponse(BaseModel):
    id: str
    purpose: MediaPurpose
    institution_id: str | None = None
    status: MediaStatus
    content_type: str
    byte_size: int
    original_filename: str
    checksum_sha256: str | None
    created_at: datetime


class MediaUploadIntentResponse(BaseModel):
    asset: MediaAssetResponse
    upload_url: str
    required_headers: dict[str, str]
    expires_at: datetime


class MediaDownloadResponse(BaseModel):
    asset: MediaAssetResponse
    download_url: str
    expires_in_seconds: int


class MediaAvatarSet(BaseModel):
    asset_id: str = Field(min_length=36, max_length=36)