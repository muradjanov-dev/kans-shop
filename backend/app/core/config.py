from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    bot_token: str = Field(alias="BOT_TOKEN")
    bot_username: str = Field(alias="BOT_USERNAME")
    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_secret: str = Field(alias="WEBHOOK_SECRET")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    error_channel_id: int | None = Field(default=None, alias="ERROR_CHANNEL_ID")
    orders_channel_id: int | None = Field(default=None, alias="ORDERS_CHANNEL_ID")

    # --- Database ---
    database_url: str = Field(alias="DATABASE_URL")
    database_url_sync: str = Field(alias="DATABASE_URL_SYNC")

    # --- Redis ---
    redis_url: str = Field(alias="REDIS_URL")

    # --- Auth ---
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: int = Field(default=30, alias="JWT_ACCESS_TTL_MINUTES")
    jwt_refresh_ttl_days: int = Field(default=7, alias="JWT_REFRESH_TTL_DAYS")

    # --- Web / API ---
    webapp_url: str = Field(default="http://localhost:5173", alias="WEBAPP_URL")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")
    media_root: str = Field(default="./media", alias="MEDIA_ROOT")
    media_base_url: str = Field(default="http://localhost:8000/media", alias="MEDIA_BASE_URL")

    # --- Misc ---
    default_language: str = Field(default="uz", alias="DEFAULT_LANGUAGE")
    timezone: str = Field(default="Asia/Tashkent", alias="TIMEZONE")
    currency: str = Field(default="UZS", alias="CURRENCY")
    debug: bool = Field(default=False, alias="DEBUG")

    @field_validator("error_channel_id", "orders_channel_id", mode="before")
    @classmethod
    def _blank_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def admin_ids_list(self) -> list[int]:
        return [int(x) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def media_root_path(self) -> Path:
        path = Path(self.media_root)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
