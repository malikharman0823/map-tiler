from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env.local"


class Settings(BaseSettings):
    session_storage_dir: Path = Path(__file__).resolve().parent / "temp" / "sessions"
    session_inactivity_timeout_seconds: int = 3600  # 1 hour
    session_max_lifetime_seconds: int = 86400  # 24 hours
    cleanup_interval_seconds: int = 600  # 10 minutes

    max_upload_size_mb: int = Field(default=500, gt=0)
    max_storage_per_session_bytes: int = 500 * 1024 * 1024  # 500 MB per session
    max_total_temporary_storage_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB total

    export_retention_seconds: int = 3600  # 1 hour
    restore_sessions_on_startup: bool = True

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
