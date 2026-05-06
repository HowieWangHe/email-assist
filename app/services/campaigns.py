from datetime import datetime, timezone

from app.models import Campaign, CampaignRecipient, RecipientStatus


class CampaignService:
    def refresh_campaign_status(
        self,
        campaign: Campaign,
        recipients: list[CampaignRecipient],
        now: datetime | None = None,
    ) -> Campaign:
        now = now or datetime.now(timezone.utc)
        deadline = _aware(campaign.deadline)
        required = [
            recipient
            for recipient in recipients
            if not recipient.excluded_from_required_reply and recipient.status != RecipientStatus.FAILED
        ]
        if _aware(now) > deadline:
            for recipient in required:
                if recipient.status in {RecipientStatus.SENT, RecipientStatus.REMINDED}:
                    recipient.status = RecipientStatus.OVERDUE
        if required and all(recipient.status == RecipientStatus.REPLIED for recipient in required):
            campaign.status = "all_replied"
        elif any(recipient.status == RecipientStatus.OVERDUE for recipient in required):
            campaign.status = "overdue"
        elif any(
            recipient.status in {RecipientStatus.SENT, RecipientStatus.REMINDED, RecipientStatus.REPLIED}
            for recipient in recipients
        ) or campaign.status in {"tracking", "overdue", "all_replied"}:
            campaign.status = "tracking"
        return campaign


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
