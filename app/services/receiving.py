from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from uuid import uuid4

from app.models import (
    Campaign,
    CampaignRecipient,
    ReceivedAttachment,
    ReceivedMessage,
    RecipientStatus,
    SentMessage,
)
from app.services.matching import ReplyMatcher
from app.services.storage import CampaignStorage


@dataclass(slots=True)
class ReplyIngestResult:
    replied_count: int = 0
    review_count: int = 0
    skipped_existing_count: int = 0
    received_messages: list[ReceivedMessage] = field(default_factory=list)
    attachments: list[ReceivedAttachment] = field(default_factory=list)


class ReplyIngestService:
    def __init__(self, data_dir: Path | str):
        self.storage = CampaignStorage(data_dir)
        self.matcher = ReplyMatcher()

    def ingest(
        self,
        *,
        raw_messages: list[bytes],
        campaigns: list[Campaign],
        recipients: list[CampaignRecipient],
        sent_messages: list[SentMessage],
        known_message_ids: set[str] | None = None,
    ) -> ReplyIngestResult:
        campaigns_by_id = {campaign.id: campaign for campaign in campaigns}
        recipients_by_id = {recipient.id: recipient for recipient in recipients}
        seen_message_ids = set(known_message_ids or set())
        result = ReplyIngestResult()

        for raw in raw_messages:
            parsed = BytesParser(policy=policy.default).parsebytes(raw)
            message_id = parsed.get("Message-ID", uuid4().hex)
            if message_id in seen_message_ids:
                result.skipped_existing_count += 1
                continue
            seen_message_ids.add(message_id)
            match = self.matcher.match(
                from_email=parsed.get("From", ""),
                subject=parsed.get("Subject", ""),
                in_reply_to=parsed.get("In-Reply-To"),
                references=_split_references(parsed.get("References", "")),
                sent_messages=sent_messages,
            )
            campaign_id = match.campaign_id or (campaigns[0].id if len(campaigns) == 1 else "unmatched")
            recipient_id = match.recipient_id or "unmatched"
            body = _extract_text_body(parsed)
            attachments = _extract_attachments(parsed)
            archive = self.storage.archive_reply(
                campaign_id=campaign_id,
                recipient_id=recipient_id,
                message_id=message_id,
                body=body,
                raw_email=raw.decode("utf-8", errors="replace"),
                attachments={name: content for name, content, _ in attachments},
            )

            received = ReceivedMessage(
                id=uuid4().hex,
                campaign_id=match.campaign_id,
                recipient_id=match.recipient_id,
                from_email=parseaddr(parsed.get("From", ""))[1],
                subject=parsed.get("Subject", ""),
                message_id=message_id,
                body_path=archive.body_path,
                raw_path=archive.raw_path,
                confidence=match.confidence,
                body_summary=_summarize_body(body),
                needs_review=match.needs_review,
            )
            result.received_messages.append(received)

            for index, (filename, _, content_type) in enumerate(attachments):
                result.attachments.append(
                    ReceivedAttachment(
                        id=uuid4().hex,
                        campaign_id=match.campaign_id,
                        recipient_id=match.recipient_id,
                        message_id=received.message_id,
                        filename=filename,
                        path=archive.attachment_paths[index],
                        content_type=content_type,
                    )
                )

            if match.recipient_id and match.recipient_id in recipients_by_id:
                recipient = recipients_by_id[match.recipient_id]
                recipient.status = RecipientStatus.REPLIED
                recipient.replied_at = datetime.now(timezone.utc)
                result.replied_count += 1
            elif match.needs_review:
                result.review_count += 1

            if match.campaign_id and match.campaign_id in campaigns_by_id:
                campaigns_by_id[match.campaign_id].status = "tracking"

        return result


def _split_references(value: str) -> list[str]:
    return [item.strip() for item in value.split() if item.strip()]


def _extract_text_body(message: EmailMessage) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                return str(part.get_content())
        return ""
    if message.get_content_type() == "text/plain":
        return str(message.get_content())
    return ""


def _extract_attachments(message: EmailMessage) -> list[tuple[str, bytes, str]]:
    attachments: list[tuple[str, bytes, str]] = []
    for part in message.walk():
        if part.get_content_disposition() != "attachment":
            continue
        filename = part.get_filename() or f"attachment-{len(attachments) + 1}"
        payload = part.get_payload(decode=True) or b""
        attachments.append((filename, payload, part.get_content_type()))
    return attachments


def _summarize_body(body: str, *, max_lines: int = 3, max_chars: int = 280) -> str:
    lines = []
    for raw_line in body.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line or line.startswith(">"):
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    summary = " / ".join(lines)
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 1].rstrip() + "..."
