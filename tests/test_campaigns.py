from datetime import datetime, timedelta, timezone

from app.models import Campaign, CampaignRecipient, ReminderStrategy, RecipientStatus
from app.services.campaigns import CampaignService


def test_marks_campaign_all_replied_when_every_required_recipient_replied():
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.REPLIED),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.REPLIED),
    ]

    updated = CampaignService().refresh_campaign_status(campaign, recipients)

    assert updated.status == "all_replied"


def test_failed_and_excluded_recipients_do_not_block_all_replied():
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.AUTO_SEND,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.REPLIED),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.FAILED),
        CampaignRecipient(
            id="r3",
            campaign_id="c1",
            email="c@example.com",
            status=RecipientStatus.SENT,
            excluded_from_required_reply=True,
        ),
    ]

    updated = CampaignService().refresh_campaign_status(campaign, recipients)

    assert updated.status == "all_replied"


def test_sent_required_recipient_keeps_campaign_tracking():
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.REPLIED),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.SENT),
    ]

    updated = CampaignService().refresh_campaign_status(campaign, recipients)

    assert updated.status == "tracking"


def test_draft_recipients_keep_campaign_draft_when_viewed():
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        status="draft",
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.DRAFT),
    ]

    updated = CampaignService().refresh_campaign_status(campaign, recipients)

    assert updated.status == "draft"
    assert recipients[0].status == RecipientStatus.DRAFT


def test_marks_unreplied_sent_recipients_overdue_after_deadline():
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) - timedelta(hours=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        status="tracking",
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="a@example.com", status=RecipientStatus.REPLIED),
        CampaignRecipient(id="r2", campaign_id="c1", email="b@example.com", status=RecipientStatus.SENT),
        CampaignRecipient(id="r3", campaign_id="c1", email="c@example.com", status=RecipientStatus.REMINDED),
        CampaignRecipient(id="r4", campaign_id="c1", email="d@example.com", status=RecipientStatus.DRAFT),
    ]

    updated = CampaignService().refresh_campaign_status(
        campaign,
        recipients,
        now=datetime.now(timezone.utc),
    )

    assert updated.status == "overdue"
    assert recipients[1].status == RecipientStatus.OVERDUE
    assert recipients[2].status == RecipientStatus.OVERDUE
    assert recipients[3].status == RecipientStatus.DRAFT
