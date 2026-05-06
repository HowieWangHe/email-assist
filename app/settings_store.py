from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


SecurityMode = Literal["ssl", "starttls", "none"]


@dataclass(slots=True)
class MailServerConfig:
    host: str = ""
    port: int = 0
    security: SecurityMode = "ssl"
    username: str = ""
    password: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MailServerConfig":
        data = data or {}
        return cls(
            host=str(data.get("host") or ""),
            port=int(data.get("port") or 0),
            security=_security_mode(data.get("security")),
            username=str(data.get("username") or ""),
            password=str(data.get("password") or ""),
        )

    def masked(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "security": self.security,
            "username": self.username,
            "password_configured": bool(self.password),
        }


@dataclass(slots=True)
class AiProviderConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AiProviderConfig":
        data = data or {}
        return cls(
            base_url=str(data.get("base_url") or ""),
            api_key=str(data.get("api_key") or ""),
            model=str(data.get("model") or ""),
        )

    def masked(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
        }


@dataclass(slots=True)
class AppLocalConfig:
    smtp: MailServerConfig = field(default_factory=MailServerConfig)
    imap: MailServerConfig = field(default_factory=MailServerConfig)
    ai: AiProviderConfig = field(default_factory=AiProviderConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AppLocalConfig":
        data = data or {}
        return cls(
            smtp=MailServerConfig.from_dict(data.get("smtp")),
            imap=MailServerConfig.from_dict(data.get("imap")),
            ai=AiProviderConfig.from_dict(data.get("ai")),
        )

    def masked(self) -> dict[str, Any]:
        return {"smtp": self.smtp.masked(), "imap": self.imap.masked(), "ai": self.ai.masked()}


class SettingsStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> AppLocalConfig:
        if not self.path.exists():
            return AppLocalConfig()
        return AppLocalConfig.from_dict(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, config: AppLocalConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _security_mode(value: Any) -> SecurityMode:
    if value in {"ssl", "starttls", "none"}:
        return value
    return "ssl"
