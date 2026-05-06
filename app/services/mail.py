from __future__ import annotations

from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
import imaplib
import mimetypes
from typing import Any, Callable

from app.settings_store import MailServerConfig


def build_inquiry_message(
    *,
    sender: str,
    recipient: str,
    cc: list[str],
    bcc: list[str],
    subject: str,
    body: str,
    attachments: list[Path],
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    for attachment in attachments:
        content_type, _ = mimetypes.guess_type(attachment)
        maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
        message.add_attachment(
            attachment.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment.name,
        )
    return message


class MailboxFetchService:
    def __init__(
        self,
        *,
        imap_factory: Callable[..., Any] = imaplib.IMAP4,
        imap_ssl_factory: Callable[..., Any] = imaplib.IMAP4_SSL,
        timeout: int = 20,
    ):
        self.imap_factory = imap_factory
        self.imap_ssl_factory = imap_ssl_factory
        self.timeout = timeout

    def fetch_unseen(self, config: MailServerConfig, mailbox: str = "INBOX") -> list[bytes]:
        return self._fetch_by_search(config, mailbox, "UNSEEN")

    def fetch_recent(self, config: MailServerConfig, mailbox: str = "INBOX", limit: int = 50) -> list[bytes]:
        return self._fetch_by_search(config, mailbox, "ALL", limit=limit)

    def _fetch_by_search(
        self,
        config: MailServerConfig,
        mailbox: str,
        criterion: str,
        limit: int | None = None,
    ) -> list[bytes]:
        if not config.host or not config.port or not config.username:
            raise ValueError("IMAP host, port, and username are required")
        client = self._connect(config)
        try:
            if config.security == "starttls":
                client.starttls()
            client.login(config.username, config.password)
            client.select(mailbox)
            status, data = client.search(None, criterion)
            if status != "OK":
                return []
            raw_messages: list[bytes] = []
            ids = data[0].split() if data and data[0] else []
            if limit is not None:
                ids = ids[-limit:]
            for message_id in ids:
                fetch_status, fetched = client.fetch(message_id, "(BODY.PEEK[])")
                if fetch_status != "OK":
                    continue
                for item in fetched:
                    if isinstance(item, tuple) and len(item) >= 2:
                        raw_messages.append(item[1])
            return raw_messages
        finally:
            client.logout()

    def _connect(self, config: MailServerConfig):
        if config.security == "ssl":
            return self.imap_ssl_factory(config.host, config.port, timeout=self.timeout)
        return self.imap_factory(config.host, config.port, timeout=self.timeout)
