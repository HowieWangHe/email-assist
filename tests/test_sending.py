from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

from app.models import Campaign, CampaignRecipient, RecipientStatus, ReminderStrategy
from app.services.sending import CampaignSendService
from app.services.mail import MailboxFetchService
from app.settings_store import MailServerConfig


class FakeSMTP:
    sent_messages = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

    def login(self, username, password):
        self.username = username
        self.password = password

    def send_message(self, message, from_addr, to_addrs):
        self.sent_messages.append((message, from_addr, to_addrs))

    def quit(self):
        pass


def test_campaign_send_service_sends_one_message_per_draft_recipient_and_records_tracking():
    FakeSMTP.sent_messages = []
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Hello {company}, please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        cc=["team@example.com"],
        bcc=["archive@example.com"],
    )
    recipients = [
        CampaignRecipient(
            id="r1",
            campaign_id="c1",
            email="vendor@example.com",
            company="Vendor",
            status=RecipientStatus.DRAFT,
        ),
        CampaignRecipient(
            id="r2",
            campaign_id="c1",
            email="sent@example.com",
            company="Already Sent",
            status=RecipientStatus.SENT,
        ),
    ]
    service = CampaignSendService(smtp_ssl_factory=FakeSMTP)

    result = service.send_campaign(
        campaign,
        recipients,
        MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        ),
    )

    assert result.sent_count == 1
    assert result.failed_count == 0
    assert recipients[0].status == RecipientStatus.SENT
    assert recipients[0].sent_at is not None
    assert result.sent_messages[0].recipient_id == "r1"
    sent_message, from_addr, to_addrs = FakeSMTP.sent_messages[0]
    assert sent_message["To"] == "vendor@example.com"
    assert sent_message["Cc"] == "team@example.com"
    assert sent_message["Subject"] == "RFQ"
    assert "[EA-" not in sent_message["Subject"]
    assert "archive@example.com" not in sent_message.as_string()
    assert from_addr == "buyer@example.com"
    assert to_addrs == ["vendor@example.com", "team@example.com", "archive@example.com"]
    assert "Hello Vendor" in sent_message.get_content()


def test_campaign_send_service_attaches_campaign_files_without_subject_marker(tmp_path):
    FakeSMTP.sent_messages = []
    attachment = tmp_path / "quote.xlsx"
    attachment.write_bytes(b"fake workbook")
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.DRAFT)
    ]

    result = CampaignSendService(smtp_ssl_factory=FakeSMTP).send_campaign(
        campaign,
        recipients,
        MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        ),
        attachments=[attachment],
    )

    sent_message = FakeSMTP.sent_messages[0][0]
    parsed = BytesParser(policy=policy.default).parsebytes(sent_message.as_bytes())
    attachment_parts = list(parsed.iter_attachments())

    assert result.sent_messages[0].subject == "RFQ"
    assert attachment_parts[0].get_filename() == "quote.xlsx"


def test_campaign_send_service_marks_failed_recipient_and_continues():
    class PartiallyFailingSMTP(FakeSMTP):
        sent_messages = []

        def send_message(self, message, from_addr, to_addrs):
            if message["To"] == "bad@example.com":
                raise RuntimeError("mailbox rejected")
            self.sent_messages.append((message, from_addr, to_addrs))

    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="bad@example.com", status=RecipientStatus.DRAFT),
        CampaignRecipient(id="r2", campaign_id="c1", email="ok@example.com", status=RecipientStatus.DRAFT),
    ]
    service = CampaignSendService(smtp_ssl_factory=PartiallyFailingSMTP)

    result = service.send_campaign(
        campaign,
        recipients,
        MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        ),
    )

    assert result.sent_count == 1
    assert result.failed_count == 1
    assert recipients[0].status == RecipientStatus.FAILED
    assert recipients[0].error == "mailbox rejected"
    assert recipients[1].status == RecipientStatus.SENT


def test_campaign_send_service_sends_reminders_to_due_recipients():
    FakeSMTP.sent_messages = []
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=now + timedelta(hours=2),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        cc=["team@example.com"],
    )
    recipients = [
        CampaignRecipient(id="r1", campaign_id="c1", email="due@example.com", status=RecipientStatus.SENT),
        CampaignRecipient(id="r2", campaign_id="c1", email="done@example.com", status=RecipientStatus.REPLIED),
    ]

    result = CampaignSendService(smtp_ssl_factory=FakeSMTP).send_reminders(
        campaign,
        recipients,
        MailServerConfig(
            host="smtp.example.com",
            port=465,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        ),
        now=now,
    )

    assert result.sent_count == 1
    assert recipients[0].status == RecipientStatus.REMINDED
    assert recipients[0].reminded_at is not None
    message = FakeSMTP.sent_messages[0][0]
    assert message["To"] == "due@example.com"
    assert message["Subject"] == "提醒：RFQ"
    assert "截止时间" in message.get_content()


def test_mailbox_fetch_service_fetches_unseen_rfc822_messages():
    class FakeIMAP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def login(self, username, password):
            self.username = username
            self.password = password

        def select(self, mailbox):
            self.mailbox = mailbox

        def search(self, charset, criterion):
            return "OK", [b"1 2"]

        def fetch(self, message_id, query):
            assert query == "(BODY.PEEK[])"
            return "OK", [(b"1 (RFC822 {5}", b"raw-" + message_id)]

        def logout(self):
            pass

    messages = MailboxFetchService(imap_ssl_factory=FakeIMAP).fetch_unseen(
        MailServerConfig(
            host="imap.example.com",
            port=993,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        )
    )

    assert messages == [b"raw-1", b"raw-2"]


def test_mailbox_fetch_service_fetches_recent_messages_even_if_read():
    class FakeIMAP:
        def __init__(self, host, port, timeout):
            pass

        def login(self, username, password):
            pass

        def select(self, mailbox):
            pass

        def search(self, charset, criterion):
            assert criterion == "ALL"
            return "OK", [b"1 2 3"]

        def fetch(self, message_id, query):
            assert query == "(BODY.PEEK[])"
            return "OK", [(b"1 (RFC822 {5}", b"raw-" + message_id)]

        def logout(self):
            pass

    messages = MailboxFetchService(imap_ssl_factory=FakeIMAP).fetch_recent(
        MailServerConfig(
            host="imap.example.com",
            port=993,
            security="ssl",
            username="buyer@example.com",
            password="secret",
        ),
        limit=2,
    )

    assert messages == [b"raw-2", b"raw-3"]
