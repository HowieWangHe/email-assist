from datetime import datetime, timedelta, timezone

from app.models import Campaign, CampaignRecipient, ReminderStrategy, RecipientStatus
from app.services.reminders import ReminderService


def test_selects_unreplied_recipients_inside_six_hour_reminder_window():
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=now + timedelta(hours=5, minutes=30),
        reminder_strategy=ReminderStrategy.AUTO_SEND,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.SENT),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.REPLIED),
    ]

    due = ReminderService().due_recipients(campaign, recipients, now)

    assert [item.recipient.id for item in due] == ["r1"]
    assert due[0].action == "auto_send"


def test_manual_confirm_strategy_creates_pending_reminder_action():
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=now + timedelta(hours=2),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.SENT)

    due = ReminderService().due_recipients(campaign, [recipient], now)

    assert due[0].action == "manual_confirm"


def test_does_not_remind_twice_or_after_deadline():
    now = datetime(2026, 5, 3, 8, 0, tzinfo=timezone.utc)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=now - timedelta(minutes=1),
        reminder_strategy=ReminderStrategy.AUTO_SEND,
    )
    recipients = [
        CampaignRecipient(
            id="r1",
            campaign_id="c1",
            email="a@example.com",
            status=RecipientStatus.SENT,
            reminded_at=now - timedelta(hours=1),
        ),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.SENT),
    ]

    assert ReminderService().due_recipients(campaign, recipients, now) == []
