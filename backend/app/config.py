from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str
    secret_encryption_key: str
    svix_admin_username: str
    svix_admin_password: str
    jwt_expire_minutes: int = 15
    refresh_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    cookie_secure: bool = True
    rate_limit_per_minute: int = 10

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
