from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://nexora:local-development-only@localhost:5432/nexora"
    app_env: str = "development"
    web_origin: str = "http://localhost:3000"
    storage_root: Path = Path("/data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024
    session_hours: int = 12
    seed_demo: bool = False
    demo_password: str = ""


@lru_cache
def settings() -> Settings:
    return Settings()
