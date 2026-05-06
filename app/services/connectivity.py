from __future__ import annotations

from dataclasses import dataclass
import imaplib
import smtplib
from typing import Any, Callable

import httpx

from app.settings_store import AiProviderConfig, MailServerConfig


@dataclass(slots=True)
class ConnectionTestResult:
    ok: bool
    message: str


class ConnectivityTester:
    def __init__(
        self,
        *,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
        imap_factory: Callable[..., Any] = imaplib.IMAP4,
        imap_ssl_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
        http_client: httpx.Client | None = None,
        timeout: int = 10,
    ):
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory
        self.imap_factory = imap_factory
        self.imap_ssl_factory = imap_ssl_factory
        self.http_client = http_client or httpx.Client(timeout=timeout)
        self.timeout = timeout

    def test_smtp(self, config: MailServerConfig) -> ConnectionTestResult:
        try:
            if not config.host or not config.port:
                return ConnectionTestResult(False, "SMTP host and port are required")
            client = (
                self.smtp_ssl_factory(config.host, config.port, timeout=self.timeout)
                if config.security == "ssl"
                else self.smtp_factory(config.host, config.port, timeout=self.timeout)
            )
            try:
                if config.security == "starttls":
                    client.starttls()
                if config.username:
                    client.login(config.username, config.password)
            finally:
                client.quit()
            return ConnectionTestResult(True, "SMTP connection succeeded")
        except Exception as exc:
            return ConnectionTestResult(False, f"SMTP connection failed: {exc}")

    def test_imap(self, config: MailServerConfig) -> ConnectionTestResult:
        try:
            if not config.host or not config.port:
                return ConnectionTestResult(False, "IMAP host and port are required")
            client = (
                self.imap_ssl_factory(config.host, config.port, timeout=self.timeout)
                if config.security == "ssl"
                else self.imap_factory(config.host, config.port, timeout=self.timeout)
            )
            try:
                if config.security == "starttls":
                    client.starttls()
                if config.username:
                    client.login(config.username, config.password)
            finally:
                client.logout()
            return ConnectionTestResult(True, "IMAP connection succeeded")
        except Exception as exc:
            return ConnectionTestResult(False, f"IMAP connection failed: {exc}")

    def test_ai(self, config: AiProviderConfig) -> ConnectionTestResult:
        try:
            if not config.base_url or not config.api_key or not config.model:
                return ConnectionTestResult(False, "AI base_url, api_key, and model are required")
            response = self.http_client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 8,
                },
            )
            response.raise_for_status()
            return ConnectionTestResult(True, "AI API connection succeeded")
        except Exception as exc:
            return ConnectionTestResult(False, f"AI API connection failed: {exc}")
