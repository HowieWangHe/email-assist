from __future__ import annotations

import json
from uuid import uuid4

from app.models import ExtractionRecord, ReceivedAttachment
from app.services.extraction import AttachmentExtractor, OpenAICompatibleClient


AI_EXTRACTION_INSTRUCTION = (
    "You extract procurement inquiry reply attachment data. "
    "Return valid JSON with keys summary, fields, tables, and confidence. "
    "Keep values faithful to the attachment and do not invent missing data."
)


class AttachmentProcessingService:
    def __init__(self, extractor: AttachmentExtractor | None = None):
        self.extractor = extractor or AttachmentExtractor()

    def process(
        self,
        campaign_id: str,
        attachments: list[ReceivedAttachment],
        ai_client: OpenAICompatibleClient | None = None,
    ) -> list[ExtractionRecord]:
        records: list[ExtractionRecord] = []
        for attachment in attachments:
            try:
                result = self.extractor.extract_local(attachment.path)
                if ai_client is not None:
                    if result.status == "parsed":
                        ai_payload = {
                            "filename": attachment.filename,
                            "rows": result.rows,
                            "text": result.text,
                        }
                        ai_result = ai_client.extract(
                            AI_EXTRACTION_INSTRUCTION,
                            json.dumps(ai_payload, ensure_ascii=False, default=str),
                        )
                        records.append(
                            ExtractionRecord(
                                id=uuid4().hex,
                                campaign_id=campaign_id,
                                attachment_id=attachment.id,
                                filename=attachment.filename,
                                status="ai_processed",
                                result_json=json.dumps(ai_result, ensure_ascii=False, default=str),
                            )
                        )
                        continue
                    if result.status == "needs_ai":
                        ai_result = ai_client.extract_file(
                            AI_EXTRACTION_INSTRUCTION,
                            attachment.path,
                            attachment.content_type,
                        )
                        records.append(
                            ExtractionRecord(
                                id=uuid4().hex,
                                campaign_id=campaign_id,
                                attachment_id=attachment.id,
                                filename=attachment.filename,
                                status="ai_processed",
                                result_json=json.dumps(ai_result, ensure_ascii=False, default=str),
                            )
                        )
                        continue
            except Exception as exc:
                records.append(
                    ExtractionRecord(
                        id=uuid4().hex,
                        campaign_id=campaign_id,
                        attachment_id=attachment.id,
                        filename=attachment.filename,
                        status="failed",
                        result_json=json.dumps({"filename": attachment.filename}, ensure_ascii=False),
                        error=str(exc),
                    )
                )
                continue

            if result.status == "parsed":
                payload = {
                    "filename": attachment.filename,
                    "rows": result.rows,
                    "text": result.text,
                }
                records.append(
                    ExtractionRecord(
                        id=uuid4().hex,
                        campaign_id=campaign_id,
                        attachment_id=attachment.id,
                        filename=attachment.filename,
                        status="parsed",
                        result_json=json.dumps(payload, ensure_ascii=False, default=str),
                    )
                )
            else:
                records.append(
                    ExtractionRecord(
                        id=uuid4().hex,
                        campaign_id=campaign_id,
                        attachment_id=attachment.id,
                        filename=attachment.filename,
                        status=result.status,
                        result_json=json.dumps({"filename": attachment.filename}, ensure_ascii=False),
                        error=result.message,
                    )
                )
        return records
