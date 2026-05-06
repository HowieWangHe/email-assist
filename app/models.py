from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class ReminderStrategy(StrEnum):
    AUTO_SEND = "auto_send"
    MANUAL_CONFIRM = "manual_confirm"


class RecipientStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    REPLIED = "replied"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    OVERDUE = "overdue"
    REMINDED = "reminded"


@dataclass(slots=True)
class Campaign:
    id: str
    name: str
    subject: str
    body_template: str
    deadline: datetime
    reminder_strategy: ReminderStrategy
    status: str = "draft"
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    attachment_ai_enabled: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    archived_at: datetime | None = None
    status_before_archive: str | None = None


@dataclass(slots=True)
class CampaignRecipient:
    id: str
    campaign_id: str
    email: str
    status: RecipientStatus
    name: str | None = None
    company: str | None = None
    sent_at: datetime | None = None
    replied_at: datetime | None = None
    reminded_at: datetime | None = None
    error: str | None = None
    excluded_from_required_reply: bool = False


@dataclass(slots=True)
class SentMessage:
    id: str
    campaign_id: str
    recipient_id: str
    recipient_email: str
    subject: str
    message_id: str


@dataclass(slots=True)
class CampaignAttachment:
    id: str
    campaign_id: str
    filename: str
    path: Path
    content_type: str = "application/octet-stream"


@dataclass(slots=True)
class ReceivedMessage:
    id: str
    campaign_id: str | None
    recipient_id: str | None
    from_email: str
    subject: str
    message_id: str
    body_path: Path
    raw_path: Path
    confidence: str
    body_summary: str = ""
    needs_review: bool = False


@dataclass(slots=True)
class ReceivedAttachment:
    id: str
    campaign_id: str | None
    recipient_id: str | None
    message_id: str
    filename: str
    path: Path
    content_type: str = "application/octet-stream"


@dataclass(slots=True)
class ExtractionRecord:
    id: str
    campaign_id: str
    attachment_id: str
    filename: str
    status: str
    result_json: str
    error: str = ""


@dataclass(slots=True)
class MatchResult:
    campaign_id: str | None
    recipient_id: str | None
    confidence: str
    needs_review: bool
    reason: str


@dataclass(slots=True)
class ReminderDue:
    campaign_id: str
    recipient: CampaignRecipient
    action: str


@dataclass(slots=True)
class ArchiveResult:
    body_path: Path
    raw_path: Path
    attachment_paths: list[Path]


@dataclass(slots=True)
class ExtractionResult:
    status: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    text: str | None = None
    message: str = ""
