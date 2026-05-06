from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import smtplib
from typing import Any, Callable
from uuid import uuid4

from app.models import Campaign, CampaignRecipient, RecipientStatus, SentMessage
from app.services.mail import build_inquiry_message
from app.services.reminders import ReminderService
from app.settings_store import MailServerConfig


@dataclass(slots=True)
class CampaignSendResult:
    sent_count: int = 0
    failed_count: int = 0
    sent_messages: list[SentMessage] = field(default_factory=list)


class CampaignSendService:
    def __init__(
        self,
        *,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
        timeout: int = 20,
    ):
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory
        self.timeout = timeout

    def send_campaign(
        self,
        campaign: Campaign,
        recipients: list[CampaignRecipient],
        smtp_config: MailServerConfig,
        attachments: list[Path] | None = None,
    ) -> CampaignSendResult:
        result = CampaignSendResult()
        if not smtp_config.host or not smtp_config.port or not smtp_config.username:
            raise ValueError("SMTP host, port, and username are required")

        client = self._connect(smtp_config)
        try:
            if smtp_config.username:
                client.login(smtp_config.username, smtp_config.password)
            for recipient in recipients:
                if recipient.status != RecipientStatus.DRAFT:
                    continue
                self._send_one(client, campaign, recipient, smtp_config, result, attachments or [])
        finally:
            client.quit()
        return result

    def send_reminders(
        self,
        campaign: Campaign,
        recipients: list[CampaignRecipient],
        smtp_config: MailServerConfig,
        now: datetime | None = None,
    ) -> CampaignSendResult:
        result = CampaignSendResult()
        if not smtp_config.host or not smtp_config.port or not smtp_config.username:
            raise ValueError("SMTP host, port, and username are required")
        reminder_time = now or datetime.now(timezone.utc)
        due = ReminderService().due_recipients(campaign, recipients, reminder_time)
        if not due:
            return result

        client = self._connect(smtp_config)
        try:
            if smtp_config.username:
                client.login(smtp_config.username, smtp_config.password)
            for item in due:
                self._send_reminder_one(client, campaign, item.recipient, smtp_config, result, reminder_time)
        finally:
            client.quit()
        return result

    def _connect(self, smtp_config: MailServerConfig):
        if smtp_config.security == "ssl":
            return self.smtp_ssl_factory(smtp_config.host, smtp_config.port, timeout=self.timeout)
        client = self.smtp_factory(smtp_config.host, smtp_config.port, timeout=self.timeout)
        if smtp_config.security == "starttls":
            client.starttls()
        return client

    def _send_one(
        self,
        client,
        campaign: Campaign,
        recipient: CampaignRecipient,
        smtp_config: MailServerConfig,
        result: CampaignSendResult,
        attachments: list[Path],
    ) -> None:
        subject = campaign.subject
        body = _render_body(campaign.body_template, recipient)
        message = build_inquiry_message(
            sender=smtp_config.username,
            recipient=recipient.email,
            cc=campaign.cc,
            bcc=campaign.bcc,
            subject=subject,
            body=body,
            attachments=attachments,
        )
        envelope_recipients = [recipient.email, *campaign.cc, *campaign.bcc]
        try:
            client.send_message(message, from_addr=smtp_config.username, to_addrs=envelope_recipients)
            recipient.status = RecipientStatus.SENT
            recipient.sent_at = datetime.now(timezone.utc)
            recipient.error = None
            result.sent_count += 1
            result.sent_messages.append(
                SentMessage(
                    id=uuid4().hex,
                    campaign_id=campaign.id,
                    recipient_id=recipient.id,
                    recipient_email=recipient.email,
                    subject=subject,
                    message_id=message["Message-ID"],
                )
            )
        except Exception as exc:
            recipient.status = RecipientStatus.FAILED
            recipient.error = str(exc)
            result.failed_count += 1

    def _send_reminder_one(
        self,
        client,
        campaign: Campaign,
        recipient: CampaignRecipient,
        smtp_config: MailServerConfig,
        result: CampaignSendResult,
        now: datetime,
    ) -> None:
        subject = f"提醒：{campaign.subject}"
        body = (
            f"您好，\n\n"
            f"此前发送的调研/询价邮件尚未收到您的回复。\n"
            f"任务：{campaign.name}\n"
            f"主题：{campaign.subject}\n"
            f"截止时间：{campaign.deadline.isoformat()}\n\n"
            f"如已回复，请忽略本提醒；如尚未回复，烦请在截止时间前反馈。\n"
        )
        message = build_inquiry_message(
            sender=smtp_config.username,
            recipient=recipient.email,
            cc=campaign.cc,
            bcc=campaign.bcc,
            subject=subject,
            body=body,
            attachments=[],
        )
        envelope_recipients = [recipient.email, *campaign.cc, *campaign.bcc]
        try:
            client.send_message(message, from_addr=smtp_config.username, to_addrs=envelope_recipients)
            recipient.status = RecipientStatus.REMINDED
            recipient.reminded_at = now
            recipient.error = None
            result.sent_count += 1
            result.sent_messages.append(
                SentMessage(
                    id=uuid4().hex,
                    campaign_id=campaign.id,
                    recipient_id=recipient.id,
                    recipient_email=recipient.email,
                    subject=subject,
                    message_id=message["Message-ID"],
                )
            )
        except Exception as exc:
            recipient.error = str(exc)
            result.failed_count += 1


def _render_body(template: str, recipient: CampaignRecipient) -> str:
    values = {
        "email": recipient.email,
        "name": recipient.name or "",
        "company": recipient.company or "",
    }
    try:
        return template.format_map(_SafeFormatDict(values))
    except ValueError:
        return template


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"
