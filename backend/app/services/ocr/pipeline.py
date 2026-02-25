from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.schemas import InvoiceItem
from app.services.ocr.cloud import SiliconFlowClient
from app.services.settings_store import infer_category


class OcrPipeline:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self.cloud_client = SiliconFlowClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

    def recognize_item(self, item: InvoiceItem, category_mapping: dict[str, list[str]]) -> InvoiceItem:
        if not self.cloud_client.is_configured:
            item.status = "failed"
            item.failure_reason = "api_key_not_configured"
            return item

        file_path = Path(item.source_path)
        if not file_path.exists():
            item.status = "failed"
            item.failure_reason = "file_not_found"
            return item

        try:
            extracted = self.cloud_client.extract_fields(file_path=file_path)
        except Exception:
            item.status = "failed"
            item.failure_reason = "cloud_request_failed"
            return item

        item.invoice_date = extracted.get("invoice_date")
        item.item_name = extracted.get("item_name")
        item.amount = extracted.get("amount")
        item.category = infer_category(item.item_name, item.old_name, category_mapping)
        item.vendor_name = None
        item.extracted_text = None
        item.updated_at = datetime.utcnow()

        required_ready = bool(item.invoice_date and item.item_name and item.amount)
        if not required_ready:
            item.status = "failed"
            item.failure_reason = "missing_required_fields"
            return item

        item.status = "ok"
        item.failure_reason = None
        return item
