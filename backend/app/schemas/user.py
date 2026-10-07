from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeResponse(BaseModel):
    message: str


class PasswordConfirmationRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)


class PasswordRecoveryRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordRecoveryConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class EmailTokenConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class AccountLifecycleResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    message: str
    access_token: str
    token_type: str
    id: str
    username: str
    email: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    email_verified_at: datetime | None = None
    created_at: datetime
