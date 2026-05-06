from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir(home: Path | None = None) -> Path:
    user_home = home or Path.home()
    return user_home / "Library" / "Application Support" / "Email Assist"


class Settings(BaseSettings):
    data_dir: Path = default_data_dir()
    database_name: str = "email_assist.sqlite3"
    poll_interval_seconds: int = 300

    model_config = SettingsConfigDict(env_prefix="EMAIL_ASSIST_", env_file=".env", extra="ignore")

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name

    @property
    def local_settings_path(self) -> Path:
        return self.data_dir / "config" / "local_settings.json"
