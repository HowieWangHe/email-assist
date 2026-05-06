from __future__ import annotations

import re
from pathlib import Path

from app.models import ArchiveResult


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:\0]+", "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    return cleaned or "item"


class CampaignStorage:
    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)

    def campaign_dir(self, campaign_id: str) -> Path:
        return self.data_dir / "campaigns" / safe_name(campaign_id)

    def save_outgoing_attachment(self, campaign_id: str, filename: str, content: bytes) -> Path:
        attachment_dir = self.campaign_dir(campaign_id) / "outgoing" / "original_attachments"
        attachment_dir.mkdir(parents=True, exist_ok=True)
        target = attachment_dir / safe_name(filename)
        target.write_bytes(content)
        return target

    def archive_reply(
        self,
        *,
        campaign_id: str,
        recipient_id: str,
        message_id: str,
        body: str,
        raw_email: str,
        attachments: dict[str, bytes],
    ) -> ArchiveResult:
        reply_dir = (
            self.campaign_dir(campaign_id)
            / "recipients"
            / safe_name(recipient_id)
            / "replies"
            / safe_name(message_id)
        )
        attachment_dir = reply_dir / "attachments"
        attachment_dir.mkdir(parents=True, exist_ok=True)

        body_path = reply_dir / "body.txt"
        raw_path = reply_dir / "raw.eml"
        body_path.write_text(body, encoding="utf-8")
        raw_path.write_text(raw_email, encoding="utf-8")

        saved: list[Path] = []
        for filename, content in attachments.items():
            target = attachment_dir / safe_name(filename)
            target.write_bytes(content)
            saved.append(target)
        return ArchiveResult(body_path, raw_path, saved)
