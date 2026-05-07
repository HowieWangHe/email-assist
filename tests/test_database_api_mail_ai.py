from datetime import datetime, timedelta, timezone
import json

import httpx
from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app
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
from app.services.sending import CampaignSendResult
from app.settings_store import AppLocalConfig, MailServerConfig
from app.services.extraction import OpenAICompatibleClient
from app.services.mail import build_inquiry_message


def test_database_initializes_schema_and_persists_campaign(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )

    db.save_campaign(campaign)
    loaded = db.get_campaign("c1")

    assert loaded is not None
    assert loaded.name == "May inquiry"
    assert loaded.created_at is not None


def test_database_archives_and_deletes_campaign_records(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.DRAFT)
    db.save_campaign(campaign)
    db.save_recipients([recipient])

    campaign.status = "all_replied"
    db.save_campaign(campaign)

    archived = db.archive_campaign("c1")
    loaded = db.get_campaign("c1")

    assert archived is not None
    assert loaded.status == "archived"
    assert loaded.status_before_archive == "all_replied"
    assert loaded.archived_at is not None
    assert db.list_campaigns() == []
    assert db.list_archived_campaigns()[0].id == "c1"

    unarchived = db.unarchive_campaign("c1")

    assert unarchived.status == "all_replied"
    assert unarchived.status_before_archive is None
    assert unarchived.archived_at is None
    assert db.list_campaigns()[0].id == "c1"

    assert db.delete_campaign("c1") is True
    assert db.get_campaign("c1") is None
    assert db.list_recipients("c1") == []


def test_database_unarchives_legacy_archived_campaign_from_recipient_state(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="Legacy archived",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        status="archived",
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.REPLIED)
    db.save_campaign(campaign)
    db.save_recipients([recipient])

    unarchived = db.unarchive_campaign("c1")

    assert unarchived.status == "all_replied"


def test_database_persists_campaign_recipients(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipients = [
        CampaignRecipient(
            id="r1",
            campaign_id="c1",
            email="vendor@example.com",
            company="Vendor",
            status=RecipientStatus.DRAFT,
        )
    ]

    db.save_campaign(campaign)
    db.save_recipients(recipients)
    loaded = db.list_recipients("c1")

    assert len(loaded) == 1
    assert loaded[0].email == "vendor@example.com"
    assert loaded[0].company == "Vendor"


def test_database_persists_sent_messages_and_updates_recipients(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        cc=["team@example.com"],
        bcc=["archive@example.com"],
    )
    recipient = CampaignRecipient(
        id="r1",
        campaign_id="c1",
        email="vendor@example.com",
        company="Vendor",
        status=RecipientStatus.DRAFT,
    )
    sent = SentMessage(
        id="s1",
        campaign_id="c1",
        recipient_id="r1",
        recipient_email="vendor@example.com",
        subject="[EA-c1] RFQ",
        message_id="<m@example.com>",
    )

    db.save_campaign(campaign)
    db.save_recipients([recipient])
    recipient.status = RecipientStatus.SENT
    recipient.sent_at = datetime.now(timezone.utc)
    db.save_recipients([recipient])
    db.save_sent_message(sent)

    loaded_campaign = db.get_campaign("c1")
    loaded_recipient = db.list_recipients("c1")[0]
    sent_messages = db.list_sent_messages("c1")

    assert loaded_campaign.cc == ["team@example.com"]
    assert loaded_campaign.bcc == ["archive@example.com"]
    assert loaded_recipient.status == RecipientStatus.SENT
    assert sent_messages[0].message_id == "<m@example.com>"


def test_database_persists_campaign_attachments(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    attachment_path = tmp_path / "quote.xlsx"
    attachment_path.write_bytes(b"content")

    db.save_campaign(campaign)
    db.save_campaign_attachments(
        [
            CampaignAttachment(
                id="a1",
                campaign_id="c1",
                filename="quote.xlsx",
                path=attachment_path,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ]
    )

    loaded = db.list_campaign_attachments("c1")

    assert loaded[0].filename == "quote.xlsx"
    assert loaded[0].path == attachment_path


def test_database_persists_received_messages_and_attachments(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    body_path = tmp_path / "body.txt"
    raw_path = tmp_path / "raw.eml"
    attachment_path = tmp_path / "quote.csv"
    body_path.write_text("reply")
    raw_path.write_text("raw")
    attachment_path.write_text("price,10")

    db.save_received_messages(
        [
            ReceivedMessage(
                id="m1",
                campaign_id="c1",
                recipient_id="r1",
                from_email="vendor@example.com",
                subject="Re: RFQ",
                message_id="<reply@example.com>",
                body_path=body_path,
                raw_path=raw_path,
                confidence="high",
                body_summary="reply summary",
            )
        ]
    )
    db.save_received_attachments(
        [
            ReceivedAttachment(
                id="a1",
                campaign_id="c1",
                recipient_id="r1",
                message_id="<reply@example.com>",
                filename="quote.csv",
                path=attachment_path,
                content_type="text/csv",
            )
        ]
    )

    assert db.list_received_messages("c1")[0].body_path == body_path
    assert db.list_received_messages("c1")[0].body_summary == "reply summary"
    assert db.list_received_attachments("c1")[0].filename == "quote.csv"


def test_database_persists_extraction_records(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()

    db.save_extraction_records(
        [
            ExtractionRecord(
                id="x1",
                campaign_id="c1",
                attachment_id="a1",
                filename="quote.csv",
                status="parsed",
                result_json="{\"rows\": []}",
            )
        ]
    )

    assert db.list_extraction_records("c1")[0].filename == "quote.csv"


def test_database_claims_review_message_and_attachments(tmp_path):
    db = Database(tmp_path / "email_assist.db")
    db.initialize()
    body_path = tmp_path / "body.txt"
    raw_path = tmp_path / "raw.eml"
    attachment_path = tmp_path / "quote.csv"
    body_path.write_text("reply")
    raw_path.write_text("raw")
    attachment_path.write_text("item,price\nA,10\n")
    db.save_received_messages(
        [
            ReceivedMessage(
                id="m1",
                campaign_id=None,
                recipient_id=None,
                from_email="vendor@example.com",
                subject="Re: unexpected subject",
                message_id="<reply@example.com>",
                body_path=body_path,
                raw_path=raw_path,
                confidence="low",
                needs_review=True,
            )
        ]
    )
    db.save_received_attachments(
        [
            ReceivedAttachment(
                id="a1",
                campaign_id=None,
                recipient_id=None,
                message_id="<reply@example.com>",
                filename="quote.csv",
                path=attachment_path,
                content_type="text/csv",
            )
        ]
    )

    claimed = db.claim_received_message("m1", campaign_id="c1", recipient_id="r1")

    assert claimed is not None
    assert db.list_received_messages("c1")[0].recipient_id == "r1"
    assert db.list_received_attachments("c1")[0].recipient_id == "r1"


def test_fastapi_health_and_campaign_create_list(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}

    response = client.post(
        "/api/campaigns",
        json={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-08T08:00:00+00:00",
            "recipients": [{"email": "vendor@example.com", "company": "Vendor"}],
        },
    )

    assert response.status_code == 201
    listing = client.get("/api/campaigns").json()
    assert listing[0]["name"] == "May inquiry"
    assert listing[0]["created_at"]

    detail = client.get(f"/api/campaigns/{response.json()['id']}").json()
    assert detail["recipients"][0]["email"] == "vendor@example.com"


def test_fastapi_renders_index_and_settings_pages(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    index = client.get("/")
    settings = client.get("/settings")

    assert index.status_code == 200
    assert "调研任务" in index.text
    assert "/static/mail-workflow.png" in index.text
    assert "创建时间" in index.text
    assert "归档" in index.text
    assert "删除" in index.text
    assert "<span>创建调研任务</span>" not in index.text
    assert "<span>连接配置</span>" not in index.text
    assert settings.status_code == 200
    assert "连接配置" in settings.text


def test_fastapi_index_separates_active_and_archived_campaigns(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    active = client.post(
        "/api/campaigns",
        json={
            "name": "Active inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients": [{"email": "active@example.com"}],
        },
    ).json()
    archived = client.post(
        "/api/campaigns",
        json={
            "name": "Archived inquiry",
            "subject": "Old RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients": [{"email": "archive@example.com"}],
        },
    ).json()
    client.post(f"/api/campaigns/{archived['id']}/archive", json={"confirm": "ARCHIVE"})

    page = client.get("/")

    assert "活跃任务" in page.text
    assert "已归档" in page.text
    assert "取消归档" in page.text
    assert page.text.index("Active inquiry") < page.text.index("Archived inquiry")


def test_fastapi_renders_new_campaign_and_campaign_detail_pages(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    created = client.post(
        "/api/campaigns",
        json={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-08T08:00:00+00:00",
            "recipients": [{"email": "vendor@example.com", "company": "Vendor"}],
        },
    ).json()
    body_path = tmp_path / "body.txt"
    raw_path = tmp_path / "raw.eml"
    body_path.write_text("reply body")
    raw_path.write_text("raw")
    recipient_id = app.state.database.list_recipients(created["id"])[0].id
    app.state.database.save_received_messages(
        [
            ReceivedMessage(
                id="m1",
                campaign_id=created["id"],
                recipient_id=recipient_id,
                from_email="vendor@example.com",
                subject="Re: RFQ",
                message_id="<reply@example.com>",
                body_path=body_path,
                raw_path=raw_path,
                confidence="high",
                body_summary="reply summary",
            )
        ]
    )

    new_page = client.get("/campaigns/new")
    detail = client.get(f"/campaigns/{created['id']}")

    assert new_page.status_code == 200
    assert "创建调研任务" in new_page.text
    assert "导入收件人文件" in new_page.text
    assert detail.status_code == 200
    assert "vendor@example.com" in detail.text
    assert "reply summary" in detail.text
    assert "发送与追踪" in detail.text
    assert "资料工作台" in detail.text
    assert "解析所有回复附件" in detail.text
    assert "AI 识别待处理附件" in detail.text
    assert "生成 Excel + ZIP" in detail.text
    assert "本地解析附件" not in detail.text


def test_fastapi_previews_downloads_and_reveals_reply_files(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    body_path = tmp_path / "campaigns" / "c1" / "recipients" / "r1" / "replies" / "m1" / "body.txt"
    raw_path = body_path.with_name("raw.eml")
    attachment_path = body_path.parent / "attachments" / "quote.txt"
    attachment_path.parent.mkdir(parents=True)
    body_path.write_text("Line one\nLine two", encoding="utf-8")
    raw_path.write_text("raw", encoding="utf-8")
    attachment_path.write_text("quoted delivery date: Friday", encoding="utf-8")
    app.state.database.save_campaign(campaign)
    app.state.database.save_received_messages(
        [
            ReceivedMessage(
                id="m1",
                campaign_id="c1",
                recipient_id="r1",
                from_email="vendor@example.com",
                subject="Re: RFQ",
                message_id="<reply@example.com>",
                body_path=body_path,
                raw_path=raw_path,
                confidence="high",
                body_summary="Line one",
            )
        ]
    )
    app.state.database.save_received_attachments(
        [
            ReceivedAttachment(
                id="a1",
                campaign_id="c1",
                recipient_id="r1",
                message_id="<reply@example.com>",
                filename="quote.txt",
                path=attachment_path,
                content_type="text/plain",
            )
        ]
    )
    captured = {}

    def fake_run(command, check=False):
        captured["command"] = command
        captured["check"] = check

    monkeypatch.setattr("app.web.subprocess.run", fake_run)

    body = client.get("/api/campaigns/c1/received-messages/m1/body")
    preview = client.get("/api/campaigns/c1/received-attachments/a1/preview")
    download = client.get("/api/campaigns/c1/received-attachments/a1/download")
    reveal = client.post("/api/campaigns/c1/received-attachments/a1/reveal")

    assert body.status_code == 200
    assert body.json()["body"] == "Line one\nLine two"
    assert preview.status_code == 200
    assert preview.json()["kind"] == "text"
    assert "quoted delivery date" in preview.json()["text"]
    assert download.status_code == 200
    assert download.text == "quoted delivery date: Friday"
    assert reveal.status_code == 200
    assert captured["command"] == ["open", "-R", str(attachment_path)]


def test_fastapi_archives_and_deletes_campaign(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    created = client.post(
        "/api/campaigns",
        json={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients": [{"email": "vendor@example.com", "company": "Vendor"}],
        },
    ).json()
    campaign_dir = tmp_path / "campaigns" / created["id"]
    export_dir = tmp_path / "exports" / created["id"]
    campaign_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    (campaign_dir / "note.txt").write_text("campaign data")
    (export_dir / "package.zip").write_text("export data")

    unconfirmed = client.post(f"/api/campaigns/{created['id']}/archive", json={})
    archive = client.post(f"/api/campaigns/{created['id']}/archive", json={"confirm": "ARCHIVE"})
    archived = client.get(f"/api/campaigns/{created['id']}").json()

    assert unconfirmed.status_code == 400
    assert archive.status_code == 200
    assert archived["status"] == "archived"
    assert archived["status_before_archive"] == "draft"
    assert archived["archived_at"]

    blocked_send = client.post(f"/api/campaigns/{created['id']}/send")
    unarchive = client.post(f"/api/campaigns/{created['id']}/unarchive")
    restored = client.get(f"/api/campaigns/{created['id']}").json()

    assert blocked_send.status_code == 409
    assert unarchive.status_code == 200
    assert restored["status"] == "draft"
    assert restored["status_before_archive"] is None
    assert restored["archived_at"] is None

    client.post(f"/api/campaigns/{created['id']}/archive", json={"confirm": "ARCHIVE"})

    unconfirmed_delete = client.request("DELETE", f"/api/campaigns/{created['id']}", json={})
    delete = client.request("DELETE", f"/api/campaigns/{created['id']}", json={"confirm": "DELETE"})

    assert unconfirmed_delete.status_code == 400
    assert delete.status_code == 200
    assert client.get(f"/api/campaigns/{created['id']}").status_code == 404
    assert not campaign_dir.exists()
    assert not export_dir.exists()


def test_campaign_form_uploads_attachment_to_campaign_detail(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/campaigns",
        data={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients_text": "vendor@example.com,Vendor",
            "cc": "",
            "bcc": "",
        },
        files={"attachments": ("quote.txt", b"attachment body", "text/plain")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    detail = client.get(response.headers["location"])

    assert "quote.txt" in detail.text
    assert app.state.database.list_campaign_attachments(response.headers["location"].split("/")[-1])[0].path.exists()


def test_campaign_form_imports_recipient_file_and_dedupes_with_pasted_rows(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)

    response = client.post(
        "/campaigns",
        data={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients_text": "vendor@example.com,Pasted Vendor,Li",
            "cc": "",
            "bcc": "",
        },
        files={
            "recipients_file": (
                "recipients.csv",
                b"email,company,name\nvendor@example.com,CSV Vendor,Wang\nsecond@example.com,Second Vendor,Zhang\n",
                "text/csv",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    campaign_id = response.headers["location"].split("/")[-1]
    recipients = app.state.database.list_recipients(campaign_id)

    assert [recipient.email for recipient in recipients] == ["second@example.com", "vendor@example.com"]
    assert {recipient.email: recipient.company for recipient in recipients} == {
        "vendor@example.com": "Pasted Vendor",
        "second@example.com": "Second Vendor",
    }


def test_fastapi_exports_campaign_summary_and_package(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    response = client.post(
        "/api/campaigns",
        json={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-04T08:00:00+00:00",
            "recipients": [{"email": "vendor@example.com", "company": "Vendor"}],
        },
    )

    export = client.post(f"/api/campaigns/{response.json()['id']}/export").json()

    assert export["summary"].endswith("campaign_summary.xlsx")
    assert export["package"].endswith("campaign_package.zip")


def test_fastapi_send_campaign_endpoint_updates_status_and_sent_messages(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    app.state.settings_store.save(
        AppLocalConfig(
            smtp=MailServerConfig(
                host="smtp.example.com",
                port=465,
                security="ssl",
                username="buyer@example.com",
                password="secret",
            )
        )
    )
    client = TestClient(app)
    created = client.post(
        "/api/campaigns",
        json={
            "name": "May inquiry",
            "subject": "RFQ",
            "body_template": "Please quote.",
            "deadline": "2026-05-08T08:00:00+00:00",
            "recipients": [{"email": "vendor@example.com", "company": "Vendor"}],
        },
    ).json()

    class FakeSendService:
        def send_campaign(self, campaign, recipients, smtp_config, attachments=None):
            recipients[0].status = RecipientStatus.SENT
            recipients[0].sent_at = datetime.now(timezone.utc)
            return CampaignSendResult(
                sent_count=1,
                failed_count=0,
                sent_messages=[
                    SentMessage(
                        id="s1",
                        campaign_id=campaign.id,
                        recipient_id=recipients[0].id,
                        recipient_email=recipients[0].email,
                        subject=campaign.subject,
                        message_id="<m@example.com>",
                    )
                ],
            )

    monkeypatch.setattr("app.web.CampaignSendService", FakeSendService)

    response = client.post(f"/api/campaigns/{created['id']}/send")
    detail = client.get(f"/api/campaigns/{created['id']}").json()

    assert response.status_code == 200
    assert response.json()["sent_count"] == 1
    assert detail["status"] == "tracking"
    assert detail["recipients"][0]["status"] == "sent"
    assert app.state.database.list_sent_messages(created["id"])[0].message_id == "<m@example.com>"


def test_fastapi_campaign_detail_shows_and_sends_due_reminders(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    app.state.settings_store.save(
        AppLocalConfig(
            smtp=MailServerConfig(
                host="smtp.example.com",
                port=465,
                security="ssl",
                username="buyer@example.com",
                password="secret",
            )
        )
    )
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(hours=2),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        status="tracking",
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.SENT)
    app.state.database.save_campaign(campaign)
    app.state.database.save_recipients([recipient])

    class FakeSendService:
        def send_reminders(self, campaign, recipients, smtp_config, now=None):
            recipients[0].status = RecipientStatus.REMINDED
            recipients[0].reminded_at = datetime.now(timezone.utc)
            return CampaignSendResult(sent_count=1, failed_count=0, sent_messages=[])

    monkeypatch.setattr("app.web.CampaignSendService", FakeSendService)

    detail_page = client.get("/campaigns/c1")
    index_page = client.get("/")
    response = client.post("/api/campaigns/c1/reminders/send")
    detail = client.get("/api/campaigns/c1").json()

    assert "待提醒收件人" in detail_page.text
    assert "vendor@example.com" in detail_page.text
    assert "待提醒 1" in index_page.text
    assert response.status_code == 200
    assert response.json()["sent_count"] == 1
    assert detail["recipients"][0]["status"] == "reminded"
    assert detail["recipients"][0]["reminded_at"] is not None


def test_fastapi_archived_campaign_rejects_reminders(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(hours=2),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        status="archived",
    )
    app.state.database.save_campaign(campaign)

    response = client.post("/api/campaigns/c1/reminders/send")

    assert response.status_code == 409
    assert response.json()["error"] == "campaign_archived"


def test_fastapi_refresh_campaign_endpoint_ingests_replies(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.SENT)
    sent = SentMessage(
        id="s1",
        campaign_id="c1",
        recipient_id="r1",
        recipient_email="vendor@example.com",
        subject="RFQ",
        message_id="<sent@example.com>",
    )
    app.state.database.save_campaign(campaign)
    app.state.database.save_recipients([recipient])
    app.state.database.save_sent_message(sent)

    class FakeMailbox:
        def fetch_recent(self, config, limit=80):
            from email.message import EmailMessage

            message = EmailMessage()
            message["From"] = "vendor@example.com"
            message["To"] = "buyer@example.com"
            message["Subject"] = "Re: RFQ"
            message["Message-ID"] = "<reply@example.com>"
            message["In-Reply-To"] = "<sent@example.com>"
            message.set_content("Reply body")
            return [message.as_bytes()]

    monkeypatch.setattr("app.web.MailboxFetchService", FakeMailbox)

    response = client.post("/api/campaigns/c1/refresh")
    detail = client.get("/api/campaigns/c1").json()

    assert response.status_code == 200
    assert response.json()["replied_count"] == 1
    assert detail["status"] == "all_replied"
    assert detail["recipients"][0]["status"] == "replied"
    assert app.state.database.list_received_messages("c1")[0].from_email == "vendor@example.com"
    assert "Reply body" in app.state.database.list_received_messages("c1")[0].body_summary


def test_fastapi_refresh_campaign_endpoint_is_idempotent_for_same_message(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.SENT)
    sent = SentMessage(
        id="s1",
        campaign_id="c1",
        recipient_id="r1",
        recipient_email="vendor@example.com",
        subject="RFQ",
        message_id="<sent@example.com>",
    )
    app.state.database.save_campaign(campaign)
    app.state.database.save_recipients([recipient])
    app.state.database.save_sent_message(sent)

    class FakeMailbox:
        def fetch_recent(self, config, limit=80):
            from email.message import EmailMessage

            message = EmailMessage()
            message["From"] = "vendor@example.com"
            message["To"] = "buyer@example.com"
            message["Subject"] = "Re: RFQ"
            message["Message-ID"] = "<reply@example.com>"
            message["In-Reply-To"] = "<sent@example.com>"
            message.set_content("Reply body")
            message.add_attachment(b"item,price\nA,10\n", maintype="text", subtype="csv", filename="quote.csv")
            return [message.as_bytes()]

    monkeypatch.setattr("app.web.MailboxFetchService", FakeMailbox)

    first = client.post("/api/campaigns/c1/refresh").json()
    second = client.post("/api/campaigns/c1/refresh").json()

    assert first["replied_count"] == 1
    assert second["replied_count"] == 0
    assert second["skipped_existing_count"] == 1
    assert len(app.state.database.list_received_messages("c1")) == 1
    assert len(app.state.database.list_received_attachments("c1")) == 1


def test_fastapi_claim_review_message_marks_recipient_replied(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    campaign = Campaign(
        id="c1",
        name="May inquiry",
        subject="RFQ",
        body_template="Please quote.",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
    )
    recipient = CampaignRecipient(id="r1", campaign_id="c1", email="vendor@example.com", status=RecipientStatus.SENT)
    body_path = tmp_path / "body.txt"
    raw_path = tmp_path / "raw.eml"
    body_path.write_text("reply")
    raw_path.write_text("raw")
    app.state.database.save_campaign(campaign)
    app.state.database.save_recipients([recipient])
    app.state.database.save_received_messages(
        [
            ReceivedMessage(
                id="m1",
                campaign_id=None,
                recipient_id=None,
                from_email="vendor@example.com",
                subject="Re: unexpected subject",
                message_id="<reply@example.com>",
                body_path=body_path,
                raw_path=raw_path,
                confidence="low",
                needs_review=True,
            )
        ]
    )

    response = client.post("/api/campaigns/c1/review-messages/m1/claim", json={"recipient_id": "r1"})
    detail = client.get("/api/campaigns/c1").json()

    assert response.status_code == 200
    assert response.json()["recipient_status"] == "replied"
    assert detail["status"] == "all_replied"
    assert detail["recipients"][0]["status"] == "replied"


def test_fastapi_process_attachments_endpoint_saves_extraction_records(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    attachment_path = tmp_path / "quote.csv"
    attachment_path.write_text("item,price\nA,10\n")
    app.state.database.save_campaign(
        Campaign(
            id="c1",
            name="May inquiry",
            subject="RFQ",
            body_template="Please quote.",
            deadline=datetime.now(timezone.utc) + timedelta(days=1),
            reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        )
    )
    app.state.database.save_received_attachments(
        [
            ReceivedAttachment(
                id="a1",
                campaign_id="c1",
                recipient_id="r1",
                message_id="<reply@example.com>",
                filename="quote.csv",
                path=attachment_path,
                content_type="text/csv",
            )
        ]
    )

    response = client.post("/api/campaigns/c1/process-attachments")

    assert response.status_code == 200
    assert response.json()["processed_count"] == 1
    assert app.state.database.list_extraction_records("c1")[0].status == "parsed"


def test_fastapi_process_attachments_with_ai_requires_ai_config(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    app.state.database.save_campaign(
        Campaign(
            id="c1",
            name="May inquiry",
            subject="RFQ",
            body_template="Please quote.",
            deadline=datetime.now(timezone.utc) + timedelta(days=1),
            reminder_strategy=ReminderStrategy.MANUAL_CONFIRM,
        )
    )

    response = client.post("/api/campaigns/c1/process-attachments?use_ai=true")

    assert response.status_code == 400
    assert response.json()["error"] == "ai_config_required"


def test_builds_one_message_per_external_recipient_with_cc_bcc_and_tracking_headers():
    message = build_inquiry_message(
        sender="buyer@example.com",
        recipient="vendor@example.com",
        cc=["team@example.com"],
        bcc=["archive@example.com"],
        subject="[EA-c1] RFQ",
        body="Please quote.",
        attachments=[],
    )

    assert message["To"] == "vendor@example.com"
    assert message["Cc"] == "team@example.com"
    assert "archive@example.com" not in message.as_string()
    assert message["Message-ID"]


def test_openai_compatible_client_builds_expected_request_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["json"] = request.read().decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\": true}"}}]})

    client = OpenAICompatibleClient(
        base_url="https://api.example.com/v1",
        api_key="secret",
        model="quote-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.extract("Extract fields", "Attachment text")

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer secret"
    assert result == {"ok": True}


def test_openai_compatible_client_builds_image_request_payload(tmp_path):
    captured = {}
    image_path = tmp_path / "quote.jpg"
    image_path.write_bytes(b"image")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.read().decode())
        captured["content"] = payload["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"ok\": true}"}}]})

    client = OpenAICompatibleClient(
        base_url="https://api.example.com/v1",
        api_key="secret",
        model="quote-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.extract_file("Extract fields", image_path, "image/jpeg")

    assert result == {"ok": True}
    assert captured["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
