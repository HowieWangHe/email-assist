from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import json

from app.models import (
    Campaign,
    CampaignAttachment,
    CampaignRecipient,
    ExtractionRecord,
    ReceivedAttachment,
    ReceivedMessage,
    RecipientStatus,
    ReminderStrategy,
    SentMessage,
)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                create table if not exists campaigns (
                    id text primary key,
                    name text not null,
                    subject text not null,
                    body_template text not null,
                    deadline text not null,
                    reminder_strategy text not null,
                    status text not null,
                    cc text not null default '[]',
                    bcc text not null default '[]',
                    attachment_ai_enabled integer not null default 0,
                    created_at text not null default current_timestamp,
                    archived_at text,
                    status_before_archive text
                );

                create table if not exists campaign_recipients (
                    id text primary key,
                    campaign_id text not null references campaigns(id),
                    email text not null,
                    name text,
                    company text,
                    status text not null,
                    sent_at text,
                    replied_at text,
                    reminded_at text,
                    error text,
                    excluded_from_required_reply integer not null default 0
                );

                create table if not exists sent_messages (
                    id text primary key,
                    campaign_id text not null references campaigns(id),
                    recipient_id text not null references campaign_recipients(id),
                    recipient_email text not null,
                    subject text not null,
                    message_id text not null,
                    sent_at text not null default current_timestamp
                );

                create table if not exists campaign_attachments (
                    id text primary key,
                    campaign_id text not null references campaigns(id),
                    filename text not null,
                    path text not null,
                    content_type text not null
                );

                create table if not exists received_messages (
                    id text primary key,
                    campaign_id text,
                    recipient_id text,
                    from_email text not null,
                    subject text not null,
                    message_id text not null,
                    body_path text not null,
                    raw_path text not null,
                    confidence text not null,
                    body_summary text not null default '',
                    needs_review integer not null default 0
                );

                create table if not exists received_attachments (
                    id text primary key,
                    campaign_id text,
                    recipient_id text,
                    message_id text not null,
                    filename text not null,
                    path text not null,
                    content_type text not null
                );

                create table if not exists extraction_results (
                    id text primary key,
                    campaign_id text not null,
                    attachment_id text not null,
                    filename text not null,
                    status text not null,
                    result_json text not null,
                    error text not null default ''
                );
                """
            )
            self._ensure_column(connection, "campaigns", "cc", "text not null default '[]'")
            self._ensure_column(connection, "campaigns", "bcc", "text not null default '[]'")
            self._ensure_column(connection, "campaigns", "created_at", "text")
            self._ensure_column(connection, "campaigns", "archived_at", "text")
            self._ensure_column(connection, "campaigns", "status_before_archive", "text")
            self._ensure_column(connection, "received_messages", "body_summary", "text not null default ''")
            connection.execute(
                "update campaigns set created_at = ? where created_at is null or created_at = ''",
                (datetime.now(timezone.utc).isoformat(),),
            )
            self._backfill_archive_metadata(connection)
            self._backfill_received_message_summaries(connection)

    def save_campaign(self, campaign: Campaign) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into campaigns (
                    id, name, subject, body_template, deadline,
                    reminder_strategy, status, cc, bcc, attachment_ai_enabled,
                    created_at, archived_at, status_before_archive
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    name = excluded.name,
                    subject = excluded.subject,
                    body_template = excluded.body_template,
                    deadline = excluded.deadline,
                    reminder_strategy = excluded.reminder_strategy,
                    status = excluded.status,
                    cc = excluded.cc,
                    bcc = excluded.bcc,
                    attachment_ai_enabled = excluded.attachment_ai_enabled,
                    created_at = coalesce(campaigns.created_at, excluded.created_at),
                    archived_at = excluded.archived_at,
                    status_before_archive = excluded.status_before_archive
                """,
                (
                    campaign.id,
                    campaign.name,
                    campaign.subject,
                    campaign.body_template,
                    campaign.deadline.isoformat(),
                    campaign.reminder_strategy.value,
                    campaign.status,
                    json.dumps(campaign.cc),
                    json.dumps(campaign.bcc),
                    int(campaign.attachment_ai_enabled),
                    campaign.created_at.isoformat(),
                    campaign.archived_at.isoformat() if campaign.archived_at else None,
                    campaign.status_before_archive,
                ),
            )

    def save_recipients(self, recipients: list[CampaignRecipient]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                insert into campaign_recipients (
                    id, campaign_id, email, name, company, status,
                    sent_at, replied_at, reminded_at, error, excluded_from_required_reply
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    email = excluded.email,
                    name = excluded.name,
                    company = excluded.company,
                    status = excluded.status,
                    sent_at = excluded.sent_at,
                    replied_at = excluded.replied_at,
                    reminded_at = excluded.reminded_at,
                    error = excluded.error,
                    excluded_from_required_reply = excluded.excluded_from_required_reply
                """,
                [
                    (
                        recipient.id,
                        recipient.campaign_id,
                        recipient.email,
                        recipient.name,
                        recipient.company,
                        recipient.status.value,
                        recipient.sent_at.isoformat() if recipient.sent_at else None,
                        recipient.replied_at.isoformat() if recipient.replied_at else None,
                        recipient.reminded_at.isoformat() if recipient.reminded_at else None,
                        recipient.error,
                        int(recipient.excluded_from_required_reply),
                    )
                    for recipient in recipients
                ],
            )

    def save_sent_message(self, message: SentMessage) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into sent_messages (
                    id, campaign_id, recipient_id, recipient_email, subject, message_id
                )
                values (?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    recipient_email = excluded.recipient_email,
                    subject = excluded.subject,
                    message_id = excluded.message_id
                """,
                (
                    message.id,
                    message.campaign_id,
                    message.recipient_id,
                    message.recipient_email,
                    message.subject,
                    message.message_id,
                ),
            )

    def save_campaign_attachments(self, attachments: list[CampaignAttachment]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                insert into campaign_attachments (id, campaign_id, filename, path, content_type)
                values (?, ?, ?, ?, ?)
                on conflict(id) do update set
                    filename = excluded.filename,
                    path = excluded.path,
                    content_type = excluded.content_type
                """,
                [
                    (
                        attachment.id,
                        attachment.campaign_id,
                        attachment.filename,
                        str(attachment.path),
                        attachment.content_type,
                    )
                    for attachment in attachments
                ],
            )

    def save_received_messages(self, messages: list[ReceivedMessage]) -> None:
        with self.connect() as connection:
            for message in messages:
                connection.execute(
                    """
                    insert into received_messages (
                        id, campaign_id, recipient_id, from_email, subject, message_id,
                        body_path, raw_path, confidence, body_summary, needs_review
                    )
                    select ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    where not exists (
                        select 1 from received_messages where message_id = ?
                    )
                    """,
                    (
                        message.id,
                        message.campaign_id,
                        message.recipient_id,
                        message.from_email,
                        message.subject,
                        message.message_id,
                        str(message.body_path),
                        str(message.raw_path),
                        message.confidence,
                        message.body_summary,
                        int(message.needs_review),
                        message.message_id,
                    ),
                )

    def save_received_attachments(self, attachments: list[ReceivedAttachment]) -> None:
        with self.connect() as connection:
            for attachment in attachments:
                connection.execute(
                    """
                    insert into received_attachments (
                        id, campaign_id, recipient_id, message_id, filename, path, content_type
                    )
                    select ?, ?, ?, ?, ?, ?, ?
                    where not exists (
                        select 1 from received_attachments
                        where message_id = ? and filename = ?
                    )
                    """,
                    (
                        attachment.id,
                        attachment.campaign_id,
                        attachment.recipient_id,
                        attachment.message_id,
                        attachment.filename,
                        str(attachment.path),
                        attachment.content_type,
                        attachment.message_id,
                        attachment.filename,
                    ),
                )

    def save_extraction_records(self, records: list[ExtractionRecord]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                insert into extraction_results (
                    id, campaign_id, attachment_id, filename, status, result_json, error
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    status = excluded.status,
                    result_json = excluded.result_json,
                    error = excluded.error
                """,
                [
                    (
                        record.id,
                        record.campaign_id,
                        record.attachment_id,
                        record.filename,
                        record.status,
                        record.result_json,
                        record.error,
                    )
                    for record in records
                ],
            )

    def get_campaign(self, campaign_id: str) -> Campaign | None:
        with self.connect() as connection:
            row = connection.execute("select * from campaigns where id = ?", (campaign_id,)).fetchone()
        return self._campaign_from_row(row) if row else None

    def archive_campaign(self, campaign_id: str) -> Campaign | None:
        with self.connect() as connection:
            row = connection.execute("select * from campaigns where id = ?", (campaign_id,)).fetchone()
            if row is None:
                return None
            if row["status"] != "archived":
                connection.execute(
                    """
                    update campaigns
                    set status = 'archived', archived_at = ?, status_before_archive = ?
                    where id = ?
                    """,
                    (datetime.now(timezone.utc).isoformat(), row["status"], campaign_id),
                )
            row = connection.execute("select * from campaigns where id = ?", (campaign_id,)).fetchone()
        return self._campaign_from_row(row) if row else None

    def unarchive_campaign(self, campaign_id: str) -> Campaign | None:
        with self.connect() as connection:
            row = connection.execute("select * from campaigns where id = ?", (campaign_id,)).fetchone()
            if row is None:
                return None
            if row["status"] == "archived":
                restored_status = row["status_before_archive"] or self._infer_campaign_status(connection, campaign_id)
                connection.execute(
                    """
                    update campaigns
                    set status = ?, archived_at = null, status_before_archive = null
                    where id = ?
                    """,
                    (restored_status, campaign_id),
                )
            row = connection.execute("select * from campaigns where id = ?", (campaign_id,)).fetchone()
        return self._campaign_from_row(row) if row else None

    def _infer_campaign_status(self, connection: sqlite3.Connection, campaign_id: str) -> str:
        rows = connection.execute(
            """
            select status, excluded_from_required_reply
            from campaign_recipients
            where campaign_id = ?
            """,
            (campaign_id,),
        ).fetchall()
        required = [
            row
            for row in rows
            if not bool(row["excluded_from_required_reply"]) and row["status"] != RecipientStatus.FAILED.value
        ]
        if required and all(row["status"] == RecipientStatus.REPLIED.value for row in required):
            return "all_replied"
        if any(row["status"] in {RecipientStatus.SENT.value, RecipientStatus.REMINDED.value} for row in rows):
            return "tracking"
        return "draft"

    def delete_campaign(self, campaign_id: str) -> bool:
        with self.connect() as connection:
            exists = connection.execute("select 1 from campaigns where id = ?", (campaign_id,)).fetchone()
            if exists is None:
                return False
            for table in (
                "extraction_results",
                "received_attachments",
                "received_messages",
                "campaign_attachments",
                "sent_messages",
                "campaign_recipients",
            ):
                connection.execute(f"delete from {table} where campaign_id = ?", (campaign_id,))
            connection.execute("delete from campaigns where id = ?", (campaign_id,))
        return True

    def _backfill_archive_metadata(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            select id, archived_at, status_before_archive
            from campaigns
            where status = 'archived'
            and (archived_at is null or archived_at = '' or status_before_archive is null or status_before_archive = '')
            """
        ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        for row in rows:
            connection.execute(
                """
                update campaigns
                set archived_at = coalesce(nullif(archived_at, ''), ?),
                    status_before_archive = coalesce(nullif(status_before_archive, ''), ?)
                where id = ?
                """,
                (now, self._infer_campaign_status(connection, row["id"]), row["id"]),
            )

    def _backfill_received_message_summaries(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            select id, body_path
            from received_messages
            where body_summary is null or body_summary = ''
            """
        ).fetchall()
        for row in rows:
            body_path = Path(row["body_path"])
            if not body_path.exists():
                continue
            summary = _summarize_text(body_path.read_text(encoding="utf-8", errors="replace"))
            if summary:
                connection.execute(
                    "update received_messages set body_summary = ? where id = ?",
                    (summary, row["id"]),
                )

    def list_campaigns(self) -> list[Campaign]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from campaigns where status != 'archived' order by deadline asc"
            ).fetchall()
        return [self._campaign_from_row(row) for row in rows]

    def list_archived_campaigns(self) -> list[Campaign]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from campaigns where status = 'archived' order by archived_at desc, deadline asc"
            ).fetchall()
        return [self._campaign_from_row(row) for row in rows]

    def list_recipients(self, campaign_id: str) -> list[CampaignRecipient]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from campaign_recipients where campaign_id = ? order by email asc",
                (campaign_id,),
            ).fetchall()
        return [self._recipient_from_row(row) for row in rows]

    def list_sent_messages(self, campaign_id: str) -> list[SentMessage]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from sent_messages where campaign_id = ? order by sent_at asc",
                (campaign_id,),
            ).fetchall()
        return [self._sent_message_from_row(row) for row in rows]

    def list_campaign_attachments(self, campaign_id: str) -> list[CampaignAttachment]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from campaign_attachments where campaign_id = ? order by filename asc",
                (campaign_id,),
            ).fetchall()
        return [self._campaign_attachment_from_row(row) for row in rows]

    def list_received_messages(self, campaign_id: str) -> list[ReceivedMessage]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from received_messages
                where campaign_id = ?
                and rowid in (
                    select min(rowid) from received_messages
                    where campaign_id = ?
                    group by message_id
                )
                order by rowid asc
                """,
                (campaign_id, campaign_id),
            ).fetchall()
        return [self._received_message_from_row(row) for row in rows]

    def list_review_messages(self, campaign_id: str, limit: int = 50) -> list[ReceivedMessage]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from received_messages
                where needs_review = 1 and (campaign_id is null or campaign_id = ?)
                and rowid in (
                    select min(rowid) from received_messages
                    where needs_review = 1 and (campaign_id is null or campaign_id = ?)
                    group by message_id
                )
                order by rowid desc
                limit ?
                """,
                (campaign_id, campaign_id, limit),
            ).fetchall()
        return [self._received_message_from_row(row) for row in rows]

    def list_received_message_ids(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("select message_id from received_messages").fetchall()
        return {row["message_id"] for row in rows}

    def claim_received_message(
        self,
        message_row_id: str,
        *,
        campaign_id: str,
        recipient_id: str,
    ) -> ReceivedMessage | None:
        with self.connect() as connection:
            row = connection.execute(
                "select * from received_messages where id = ?",
                (message_row_id,),
            ).fetchone()
            if row is None:
                return None
            message_id = row["message_id"]
            connection.execute(
                """
                update received_messages
                set campaign_id = ?, recipient_id = ?, confidence = 'manual', needs_review = 0
                where message_id = ? and needs_review = 1
                """,
                (campaign_id, recipient_id, message_id),
            )
            connection.execute(
                """
                update received_attachments
                set campaign_id = ?, recipient_id = ?
                where message_id = ? and campaign_id is null
                """,
                (campaign_id, recipient_id, message_id),
            )
            claimed = connection.execute(
                "select * from received_messages where id = ?",
                (message_row_id,),
            ).fetchone()
        return self._received_message_from_row(claimed) if claimed else None

    def list_received_attachments(self, campaign_id: str) -> list[ReceivedAttachment]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from received_attachments
                where campaign_id = ?
                and rowid in (
                    select min(rowid) from received_attachments
                    where campaign_id = ?
                    group by message_id, filename
                )
                order by filename asc
                """,
                (campaign_id, campaign_id),
            ).fetchall()
        return [self._received_attachment_from_row(row) for row in rows]

    def list_extraction_records(self, campaign_id: str) -> list[ExtractionRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "select * from extraction_results where campaign_id = ? order by filename asc",
                (campaign_id,),
            ).fetchall()
        return [self._extraction_record_from_row(row) for row in rows]

    def _campaign_from_row(self, row: sqlite3.Row) -> Campaign:
        return Campaign(
            id=row["id"],
            name=row["name"],
            subject=row["subject"],
            body_template=row["body_template"],
            deadline=datetime.fromisoformat(row["deadline"]),
            reminder_strategy=ReminderStrategy(row["reminder_strategy"]),
            status=row["status"],
            cc=json.loads(row["cc"] or "[]"),
            bcc=json.loads(row["bcc"] or "[]"),
            attachment_ai_enabled=bool(row["attachment_ai_enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc),
            archived_at=datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
            status_before_archive=row["status_before_archive"],
        )

    def _recipient_from_row(self, row: sqlite3.Row) -> CampaignRecipient:
        return CampaignRecipient(
            id=row["id"],
            campaign_id=row["campaign_id"],
            email=row["email"],
            name=row["name"],
            company=row["company"],
            status=RecipientStatus(row["status"]),
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
            replied_at=datetime.fromisoformat(row["replied_at"]) if row["replied_at"] else None,
            reminded_at=datetime.fromisoformat(row["reminded_at"]) if row["reminded_at"] else None,
            error=row["error"],
            excluded_from_required_reply=bool(row["excluded_from_required_reply"]),
        )

    def _sent_message_from_row(self, row: sqlite3.Row) -> SentMessage:
        return SentMessage(
            id=row["id"],
            campaign_id=row["campaign_id"],
            recipient_id=row["recipient_id"],
            recipient_email=row["recipient_email"],
            subject=row["subject"],
            message_id=row["message_id"],
        )

    def _campaign_attachment_from_row(self, row: sqlite3.Row) -> CampaignAttachment:
        return CampaignAttachment(
            id=row["id"],
            campaign_id=row["campaign_id"],
            filename=row["filename"],
            path=Path(row["path"]),
            content_type=row["content_type"],
        )

    def _received_message_from_row(self, row: sqlite3.Row) -> ReceivedMessage:
        return ReceivedMessage(
            id=row["id"],
            campaign_id=row["campaign_id"],
            recipient_id=row["recipient_id"],
            from_email=row["from_email"],
            subject=row["subject"],
            message_id=row["message_id"],
            body_path=Path(row["body_path"]),
            raw_path=Path(row["raw_path"]),
            confidence=row["confidence"],
            body_summary=row["body_summary"] or "",
            needs_review=bool(row["needs_review"]),
        )

    def _received_attachment_from_row(self, row: sqlite3.Row) -> ReceivedAttachment:
        return ReceivedAttachment(
            id=row["id"],
            campaign_id=row["campaign_id"],
            recipient_id=row["recipient_id"],
            message_id=row["message_id"],
            filename=row["filename"],
            path=Path(row["path"]),
            content_type=row["content_type"],
        )

    def _extraction_record_from_row(self, row: sqlite3.Row) -> ExtractionRecord:
        return ExtractionRecord(
            id=row["id"],
            campaign_id=row["campaign_id"],
            attachment_id=row["attachment_id"],
            filename=row["filename"],
            status=row["status"],
            result_json=row["result_json"],
            error=row["error"],
        )

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, spec: str) -> None:
        columns = {row["name"] for row in connection.execute(f"pragma table_info({table})")}
        if column not in columns:
            connection.execute(f"alter table {table} add column {column} {spec}")


def _summarize_text(value: str, *, max_lines: int = 3, max_chars: int = 280) -> str:
    lines = []
    for raw_line in value.splitlines():
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
