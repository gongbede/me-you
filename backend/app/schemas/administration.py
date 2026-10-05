from datetime import datetime

from pydantic import BaseModel


class PlatformAdminUserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime