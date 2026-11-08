from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_OPERATION_KEY_SECRET = "development-only-operation-key-secret-do-not-use"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "postgresql+psycopg://nexora:local-development-only@localhost:5432/nexora"
    app_env: Literal["development", "production"] = "development"
    web_origin: str = "http://localhost:3000"
    storage_root: Path = Path("/data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024
    session_hours: int = 12
    # Comma-separated CIDRs/addresses/hostnames whose X-Forwarded-For is honoured for throttling.
    trusted_proxies: str = ""
    # Signed retry keys (app.operation_keys). Keep the secret and epoch outside database dumps.
    operation_key_secret: str = DEV_OPERATION_KEY_SECRET
    operation_key_ttl_days: int = Field(default=30, ge=1, le=365)
    operation_key_epoch: int = Field(default=1, ge=1)
    # Client UUID keys are refused from this instant; unset accepts them (development only).
    legacy_operation_keys_until: datetime | None = None
    # Email copies of notifications (python -m app.notification_dispatch). Empty host disables email.
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True
    # ЭЦП verification. "ncanode" verifies CMS, certificate chain and OCSP through an NCANode
    # service (Kalkan); "none" stores signatures as UNVERIFIED and is refused in production.
    signature_verifier: Literal["none", "ncanode"] = "none"
    ncanode_url: str = ""
    signature_timeout_seconds: int = Field(default=30, ge=1, le=120)
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
            if self.operation_key_secret == DEV_OPERATION_KEY_SECRET or len(self.operation_key_secret) < 32:
                raise ValueError("Production requires OPERATION_KEY_SECRET of at least 32 characters")
            if self.legacy_operation_keys_until is None:
                raise ValueError("Production requires LEGACY_OPERATION_KEYS_UNTIL (end of legacy key retries)")
            if self.smtp_host and not self.smtp_starttls:
                raise ValueError("Production email requires SMTP_STARTTLS")
        if self.signature_verifier == "ncanode" and urlsplit(self.ncanode_url).scheme not in {"http", "https"}:
            raise ValueError("SIGNATURE_VERIFIER=ncanode requires NCANODE_URL")
        if self.smtp_host and "@" not in self.smtp_from:
            raise ValueError("SMTP_FROM must be an email address when SMTP_HOST is set")
        self.web_origin = self.web_origin.rstrip("/")
        if self.legacy_operation_keys_until and self.legacy_operation_keys_until.tzinfo is None:
            self.legacy_operation_keys_until = self.legacy_operation_keys_until.replace(tzinfo=UTC)
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
