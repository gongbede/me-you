from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProfileVisibility = Literal["PUBLIC", "AUTHENTICATED", "NETWORK", "PRIVATE"]


class CreateProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    profile_picture_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=2048)
    visibility: ProfileVisibility = "NETWORK"


class UpdateProfile(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    profile_picture_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=2048)
    visibility: ProfileVisibility | None = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    display_name: str
    bio: str | None
    profile_picture_url: str | None
    location: str | None
    website: str | None
    visibility: ProfileVisibility
    created_at: datetime
    updated_at: datetime


class ProfileDiscoveryResponse(BaseModel):
    user_id: str
    display_name: str
    bio: str | None
    profile_picture_url: str | None
    location: str | None
    website: str | None
    visibility: ProfileVisibility