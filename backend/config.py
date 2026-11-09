from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    environment: Literal["local", "test", "production"] = "local"
    database_url: SecretStr = SecretStr("sqlite:///./deploylens.sqlite3")
    database_sslmode: Literal["require", "disable"] = "require"
    database_schema: str = Field(default="public", pattern=r"^[a-z_][a-z0-9_]{0,40}$")
    admin_token: SecretStr = SecretStr("")
    github_repository: str = Field(
        default="Gauravwakle96/deploylens", pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
    )
    monitor_url: str = "https://module3-feedback-board.onrender.com/health"
    monitor_name: str = "Feedback Board"
    check_interval_seconds: int = Field(default=60, ge=10, le=3600)
    github_interval_seconds: int = Field(default=300, ge=60, le=3600)
    collector_enabled: bool = True
    github_poll_enabled: bool = True
    app_version: str = "local"
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    render_external_hostname: str = ""

    @model_validator(mode="after")
    def validate_environment(self) -> Self:
        url = urlsplit(self.monitor_url)
        if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password:
            raise ValueError("MONITOR_URL must be an HTTP(S) URL without credentials")
        if self.environment == "production":
            if not self.database_url.get_secret_value().startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if self.database_sslmode != "require":
                raise ValueError("Production requires database TLS")
            if len(self.admin_token.get_secret_value()) < 32:
                raise ValueError("Production ADMIN_TOKEN must contain at least 32 characters")
            if url.scheme != "https":
                raise ValueError("Production monitoring requires HTTPS")
        return self
