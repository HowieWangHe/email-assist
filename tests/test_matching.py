from app.models import SentMessage
from app.services.matching import ReplyMatcher


def test_matches_reply_by_thread_headers_with_high_confidence():
    sent = [
        SentMessage(
            id="s1",
            campaign_id="c1",
            recipient_id="r1",
            recipient_email="vendor@example.com",
            subject="RFQ",
            message_id="<original@example.com>",
        )
    ]

    result = ReplyMatcher().match(
        from_email="other@example.com",
        subject="Re: unrelated subject",
        in_reply_to="<original@example.com>",
        references=[],
        sent_messages=sent,
    )

    assert result.recipient_id == "r1"
    assert result.confidence == "high"
    assert result.needs_review is False


def test_matches_reply_by_sender_and_campaign_subject_with_medium_confidence():
    sent = [
        SentMessage(
            id="s1",
            campaign_id="c1",
            recipient_id="r1",
            recipient_email="vendor@example.com",
            subject="RFQ",
            message_id="<original@example.com>",
        )
    ]

    result = ReplyMatcher().match(
        from_email="vendor@example.com",
        subject="Re: RFQ",
        in_reply_to=None,
        references=[],
        sent_messages=sent,
    )

    assert result.recipient_id == "r1"
    assert result.confidence == "medium"
    assert result.needs_review is False


def test_matches_legacy_marker_subject_with_chinese_reply_prefix():
    sent = [
        SentMessage(
            id="s1",
            campaign_id="e74e41aaa42b4e6c85183f427bb1a8ea",
            recipient_id="r1",
            recipient_email="vendor@example.com",
            subject="[EA-e74e41aaa42b4e6c85183f427bb1a8ea] 调研-测试",
            message_id="<original@example.com>",
        )
    ]

    result = ReplyMatcher().match(
        from_email="vendor@example.com",
        subject="回复：[EA-e74e41aaa42b4e6c85183f427bb1a8ea] 调研-测试",
        in_reply_to=None,
        references=[],
        sent_messages=sent,
    )

    assert result.recipient_id == "r1"
    assert result.confidence == "medium"


def test_unmatched_reply_requires_review():
    result = ReplyMatcher().match(
        from_email="unknown@example.com",
        subject="Re: RFQ",
        in_reply_to=None,
        references=[],
        sent_messages=[],
    )

    assert result.recipient_id is None
    assert result.confidence == "low"
    assert result.needs_review is True
