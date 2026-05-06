from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from app.models import Campaign, CampaignRecipient, RecipientStatus, ReminderStrategy, SentMessage
from app.services.receiving import ReplyIngestService


def _reply_message() -> bytes:
    message = EmailMessage()
    message["From"] = "vendor@example.com"
    message["To"] = "buyer@example.com"
    message["Subject"] = "Re: RFQ"
    message["Message-ID"] = "<reply@example.com>"
    message["In-Reply-To"] = "<sent@example.com>"
    message.set_content("Here is our quote.")
    message.add_attachment(b"price,10\n", maintype="text", subtype="csv", filename="quote.csv")
    return message.as_bytes()


def _long_reply_message() -> bytes:
    message = EmailMessage()
    message["From"] = "vendor@example.com"
    message["To"] = "buyer@example.com"
    message["Subject"] = "Re: RFQ"
    message["Message-ID"] = "<long-reply@example.com>"
    message["In-Reply-To"] = "<sent@example.com>"
    message.set_content(
        """
        Dear buyer,

        We can provide model A at 10 USD per unit.
        The lead time is 14 days after PO confirmation.
        Please see the attached quotation for payment terms.
        This extra line should not be part of the short summary.
        """
    )
    return message.as_bytes()


def test_reply_ingest_matches_reply_archives_body_and_attachment(tmp_path):
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(
        id="r1",
        campaign_id="c1",
        email="vendor@example.com",
        status=RecipientStatus.SENT,
    )
    sent = SentMessage(
        id="s1",
        campaign_id="c1",
        recipient_id="r1",
        recipient_email="vendor@example.com",
        subject="RFQ",
        message_id="<sent@example.com>",
    )

    result = ReplyIngestService(tmp_path).ingest(
        raw_messages=[_reply_message()],
        campaigns=[campaign],
        recipients=[recipient],
        sent_messages=[sent],
    )

    assert result.replied_count == 1
    assert recipient.status == RecipientStatus.REPLIED
    assert recipient.replied_at is not None
    assert result.received_messages[0].recipient_id == "r1"
    assert result.received_messages[0].body_path.read_text().strip() == "Here is our quote."
    assert result.received_messages[0].body_summary == "Here is our quote."
    assert result.attachments[0].filename == "quote.csv"
    assert result.attachments[0].path.exists()


def test_reply_ingest_creates_short_body_summary(tmp_path):
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(
        id="r1",
        campaign_id="c1",
        email="vendor@example.com",
        status=RecipientStatus.SENT,
    )
    sent = SentMessage(
        id="s1",
        campaign_id="c1",
        recipient_id="r1",
        recipient_email="vendor@example.com",
        subject="RFQ",
        message_id="<sent@example.com>",
    )

    result = ReplyIngestService(tmp_path).ingest(
        raw_messages=[_long_reply_message()],
        campaigns=[campaign],
        recipients=[recipient],
        sent_messages=[sent],
    )

    assert (
        result.received_messages[0].body_summary
        == "Dear buyer, / We can provide model A at 10 USD per unit. / The lead time is 14 days after PO confirmation."
    )
