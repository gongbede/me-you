from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def username_must_not_contain_whitespace(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("username must not contain whitespace")
        return value

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


class EmailChangeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    current_password: str = Field(min_length=8, max_length=128)


class AccountLifecycleResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    message: str
    access_token: str | None = None
    token_type: str | None = None
    id: str
    username: str
    email: str
    csrf_token: str | None = None


class AuthSessionResponse(BaseModel):
    id: str
    username: str
    email: str
    csrf_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    email_verified_at: datetime | None = None
    created_at: datetime
