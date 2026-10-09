from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.bot.utils.helpers import is_valid_uz_phone, normalize_uz_phone


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    display_name: str
    phone: str | None
    language: Literal["uz", "ru"]


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    phone: str | None = None
    language: Literal["uz", "ru"] | None = None

    @field_validator("display_name")
    @classmethod
    def _trim_display_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("display_name cannot be null")
        normalized = value.strip()
        if not 1 <= len(normalized) <= 128:
            raise ValueError("display_name must contain 1 to 128 characters")
        return normalized

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_uz_phone(value)
        if not is_valid_uz_phone(normalized):
            raise ValueError(f"Invalid Uzbek phone number: {value}")
        return normalized

    @field_validator("language")
    @classmethod
    def _require_language(cls, value: Literal["uz", "ru"] | None) -> Literal["uz", "ru"]:
        if value is None:
            raise ValueError("language cannot be null")
        return value


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    address_text: str
    address_comment: str | None
    is_default: bool


class AddressCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    address_text: str
    address_comment: str | None = None

    @field_validator("label")
    @classmethod
    def _trim_label(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 60:
            raise ValueError("label must contain 1 to 60 characters")
        return normalized

    @field_validator("address_text")
    @classmethod
    def _trim_address_text(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 1000:
            raise ValueError("address_text must contain 1 to 1000 characters")
        return normalized

    @field_validator("address_comment")
    @classmethod
    def _trim_address_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) > 500:
            raise ValueError("address_comment must contain at most 500 characters")
        return normalized or None


class AddressPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    address_text: str | None = None
    address_comment: str | None = None

    @field_validator("label")
    @classmethod
    def _trim_label(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("label cannot be null")
        normalized = value.strip()
        if not 1 <= len(normalized) <= 60:
            raise ValueError("label must contain 1 to 60 characters")
        return normalized

    @field_validator("address_text")
    @classmethod
    def _trim_address_text(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("address_text cannot be null")
        normalized = value.strip()
        if not 1 <= len(normalized) <= 1000:
            raise ValueError("address_text must contain 1 to 1000 characters")
        return normalized

    @field_validator("address_comment")
    @classmethod
    def _trim_address_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) > 500:
            raise ValueError("address_comment must contain at most 500 characters")
        return normalized or None
