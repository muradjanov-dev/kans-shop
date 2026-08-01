from pydantic import BaseModel


class TelegramAuthIn(BaseModel):
    init_data: str


class BotCodeAuthIn(BaseModel):
    code: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    is_admin: bool = False
