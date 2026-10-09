from pydantic import BaseModel, Field

from app.db.models.enums import AdminRole


class TelegramAuthIn(BaseModel):
    init_data: str


class BotCodeAuthIn(BaseModel):
    code: str


class AdminCodeAuthIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class AdminSessionOut(BaseModel):
    admin_id: int
    full_name: str
    role: AdminRole
    csrf_token: str


class CustomerCodeAuthIn(BaseModel):
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_admin: bool = False
