"""Application settings, loaded from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

PLACEHOLDER_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    # Look for .env in the repo root first, then backend/, so the same file
    # works whether the app is started from either directory.
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # docker-compose overrides this with the Postgres URL.
    database_url: str = "sqlite:///./manas.db"

    models_dir: Path = BASE_DIR / "models"

    environment: str = "development"

    jwt_secret: str = PLACEHOLDER_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    admin_username: str = "admin"
    admin_password: str = "admin123"
    viewer_username: str = "viewer"
    viewer_password: str = "viewer123"

    max_batch_rows: int = 1000
    max_upload_bytes: int = 5 * 1024 * 1024

    # The training set was a balanced 50/50 split.
    drift_baseline_positive_rate: float = 0.5
    drift_window: int = 200
    drift_threshold: float = 0.15

    @property
    def uses_placeholder_secret(self) -> bool:
        return self.jwt_secret == PLACEHOLDER_SECRET


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
