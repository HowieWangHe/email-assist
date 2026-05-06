from email.utils import parseaddr
import re

from app.models import MatchResult, SentMessage


class ReplyMatcher:
    def match(
        self,
        *,
        from_email: str,
        subject: str,
        in_reply_to: str | None,
        references: list[str],
        sent_messages: list[SentMessage],
    ) -> MatchResult:
        thread_ids = {value.strip() for value in references}
        if in_reply_to:
            thread_ids.add(in_reply_to.strip())

        for sent in sent_messages:
            if sent.message_id.strip() in thread_ids:
                return MatchResult(sent.campaign_id, sent.recipient_id, "high", False, "thread_header")

        normalized_sender = parseaddr(from_email)[1].lower()
        normalized_subject = _normalize_subject(subject)
        for sent in sent_messages:
            if (
                sent.recipient_email.lower() == normalized_sender
                and _normalize_subject(sent.subject) == normalized_subject
            ):
                return MatchResult(sent.campaign_id, sent.recipient_id, "medium", False, "sender_subject")

        return MatchResult(None, None, "low", True, "unmatched")


def _normalize_subject(value: str) -> str:
    normalized = value.strip().lower()
    while True:
        next_value = re.sub(r"^(re|fw|fwd|回复|答复|转发)\s*[:：]\s*", "", normalized).strip()
        next_value = re.sub(r"^\[ea-[0-9a-f-]+\]\s*", "", next_value).strip()
        if next_value == normalized:
            return normalized
        normalized = next_value
