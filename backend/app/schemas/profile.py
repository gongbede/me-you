from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateProfile(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    profile_picture_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=2048)


class UpdateProfile(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=2000)
    profile_picture_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=2048)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    display_name: str
    bio: str | None
    profile_picture_url: str | None
    location: str | None
    website: str | None
    created_at: datetime
    updated_at: datetime