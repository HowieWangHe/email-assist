from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.config import default_data_dir
from app.main import create_app
from app.services.connectivity import ConnectivityTester
from app.settings_store import (
    AiProviderConfig,
    AppLocalConfig,
    MailServerConfig,
    SettingsStore,
)
from scripts.run_macos_app import find_port


def test_default_data_dir_uses_macos_application_support():
    assert default_data_dir(Path("/Users/alice")) == Path(
        "/Users/alice/Library/Application Support/Email Assist"
    )


def test_macos_launcher_finds_available_local_port():
    port = find_port(start=9876, end=9880)

    assert 9876 <= port <= 9880


def test_settings_store_round_trips_local_config(tmp_path):
    store = SettingsStore(tmp_path / "config.json")
    config = AppLocalConfig(
        smtp=MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="smtp-secret",
        ),
        imap=MailServerConfig(
            host="imap.example.com",
            port=993,
            security="ssl",
            username="buyer@example.com",
            password="imap-secret",
        ),
        ai=AiProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="ai-secret",
            model="quote-model",
        ),
    )

    store.save(config)
    loaded = store.load()

    assert loaded.smtp.host == "smtp.example.com"
    assert loaded.smtp.password == "smtp-secret"
    assert loaded.ai.model == "quote-model"


def test_masked_config_does_not_return_stored_secrets(tmp_path):
    store = SettingsStore(tmp_path / "config.json")
    store.save(
        AppLocalConfig(
            smtp=MailServerConfig(host="smtp.example.com", port=465, password="secret"),
            ai=AiProviderConfig(base_url="https://api.example.com/v1", api_key="api-secret", model="m"),
        )
    )

    masked = store.load().masked()

    assert masked["smtp"]["password_configured"] is True
    assert "secret" not in str(masked)
    assert masked["ai"]["api_key_configured"] is True


def test_smtp_connectivity_uses_ssl_and_login():
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(("connect", host, port, timeout))

        def login(self, username, password):
            events.append(("login", username, password))

        def quit(self):
            events.append(("quit",))

    tester = ConnectivityTester(smtp_ssl_factory=FakeSMTP)

    result = tester.test_smtp(
        MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        )
    )

    assert result.ok is True
    assert events == [
        ("connect", "smtp.example.com", 465, 10),
        ("login", "buyer@example.com", "secret"),
        ("quit",),
    ]


def test_ai_connectivity_posts_minimal_ping_to_openai_compatible_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    tester = ConnectivityTester(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    result = tester.test_ai(
        AiProviderConfig(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model="quote-model",
        )
    )

    assert result.ok is True
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert "ping" in captured["body"]


def test_settings_api_saves_config_and_returns_masked_payload(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/settings",
        json={
            "smtp": {
                "host": "smtp.example.com",
                "port": 465,
                "security": "ssl",
                "username": "buyer@example.com",
                "password": "smtp-secret",
            },
            "imap": {
                "host": "imap.example.com",
                "port": 993,
                "security": "ssl",
                "username": "buyer@example.com",
                "password": "imap-secret",
            },
            "ai": {
                "base_url": "https://api.example.com/v1",
                "api_key": "ai-secret",
                "model": "quote-model",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["smtp"]["password_configured"] is True
    assert "smtp-secret" not in response.text

    saved = SettingsStore(tmp_path / "config" / "local_settings.json").load()
    assert saved.imap.host == "imap.example.com"
