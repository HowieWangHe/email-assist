from datetime import datetime, timedelta, timezone

from app.models import Campaign, CampaignRecipient, RecipientStatus, ReminderDue, ReminderStrategy


class ReminderService:
    def due_recipients(
        self,
        campaign: Campaign,
        recipients: list[CampaignRecipient],
        now: datetime,
    ) -> list[ReminderDue]:
        now = _as_aware(now)
        deadline = _as_aware(campaign.deadline)
        if now >= deadline:
            return []
        if deadline - now > timedelta(hours=6):
            return []

        action = "auto_send" if campaign.reminder_strategy == ReminderStrategy.AUTO_SEND else "manual_confirm"
        due: list[ReminderDue] = []
        for recipient in recipients:
            if recipient.status != RecipientStatus.SENT:
                continue
            if recipient.reminded_at is not None:
                continue
            if recipient.excluded_from_required_reply:
                continue
            due.append(ReminderDue(campaign.id, recipient, action))
        return due


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
