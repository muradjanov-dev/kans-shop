from pydantic import BaseModel, Field

from app.db.models.enums import AdminRole


class TelegramAuthIn(BaseModel):
    init_data: str


class BotCodeAuthIn(BaseModel):
    code: str


class AdminCodeAuthIn(BaseModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class AdminCodeRequestIn(BaseModel):
    # Telegram user ID (digits) or Telegram username, with or without "@".
    identifier: str = Field(min_length=2, max_length=64)


class AdminCodeRequestOut(BaseModel):
    expires_in: int
    resend_after: int


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
