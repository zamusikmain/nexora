from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "postgresql+psycopg://nexora:local-development-only@localhost:5432/nexora"
    app_env: Literal["development", "production"] = "development"
    web_origin: str = "http://localhost:3000"
    storage_root: Path = Path("/data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024
    session_hours: int = 12
    seed_demo: bool = False
    demo_password: str = ""
    malware_scanner: Literal["disabled-development", "clamav"] = "disabled-development"
    clamav_host: str = "clamav"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    scan_timeout_seconds: int = Field(default=30, ge=1, le=60)

    @model_validator(mode="after")
    def production_controls(self):
        if self.app_env == "production":
            if self.seed_demo or self.demo_password or self.malware_scanner != "clamav":
                raise ValueError("Production requires scanning and disables demo data")
            origin = urlsplit(self.web_origin)
            if (
                origin.scheme != "https"
                or not origin.hostname
                or origin.path not in {"", "/"}
                or origin.username
                or origin.password
                or origin.query
                or origin.fragment
            ):
                raise ValueError("Production requires an HTTPS origin")
            if "local-development-only" in self.database_url:
                raise ValueError("Production requires a non-demo database credential")
        self.web_origin = self.web_origin.rstrip("/")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
