from functools import lru_cache
import base64
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr
    secret_key: SecretStr
    secret_encryption_key: SecretStr
    credential_master_key: SecretStr
    svix_admin_username: str
    svix_admin_password: SecretStr
    jwt_expire_minutes: int = 15
    refresh_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = True
    rate_limit_per_minute: int = 10
    data_provider: Literal["IBKR", "FUTU"] = "IBKR"
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = Field(default=7497, ge=1, le=65535)
    ibkr_client_id: int = Field(default=19, ge=0)
    futu_host: str = "127.0.0.1"
    futu_port: int = Field(default=11111, ge=1, le=65535)

    @field_validator("data_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return str(value).strip().upper()

    @field_validator("secret_encryption_key", "credential_master_key", mode="before")
    @classmethod
    def validate_aes_key(cls, value: str) -> str:
        encoded = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        try:
            decoded = base64.b64decode(encoded.encode(), altchars=b"-_", validate=True)
        except Exception as exc:
            raise ValueError("must be URL-safe Base64 encoded") from exc
        if len(decoded) != 32:
            raise ValueError("must decode to exactly 32 bytes for AES-256-GCM")
        return encoded

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
