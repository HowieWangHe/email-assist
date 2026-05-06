from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.database import Database
from app.settings_store import SettingsStore
from app.web import router


def create_app(data_dir: Path | str | None = None) -> FastAPI:
    settings = Settings()
    if data_dir is not None:
        settings.data_dir = Path(data_dir)

    database = Database(settings.database_path)
    database.initialize()

    app = FastAPI(title="Email Assist")
    app.state.settings = settings
    app.state.database = database
    app.state.settings_store = SettingsStore(settings.local_settings_path)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(router)
    return app


app = create_app(data_dir=Path("data"))
