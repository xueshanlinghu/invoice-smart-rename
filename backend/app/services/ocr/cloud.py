from __future__ import annotations

import base64
import mimetypes
import re
from datetime import datetime
import io
from pathlib import Path
from typing import Any

import httpx

from app.utils.text import parse_json_object


STRUCTURED_PROMPT = (
    "请从发票中提取以下字段，并且只输出一个JSON对象，不要输出任何其他文字或markdown。"
    "字段和定位要求："
    "invoice_date(开票日期，发票右上角，格式YYYY-MM-DD或null), "
    "item_name(项目名称，中间表格“项目名称”列，若有多行取第一条有效项目名，字符串或null), "
    "amount(价税合计小写金额，即“(小写)”右侧金额，纯数字字符串如26.80或null)。"
)

DATE_PATTERN = re.compile(r"(20\d{2})[^\d]?(\d{1,2})[^\d]?(\d{1,2})")
AMOUNT_PATTERN = re.compile(r"^\d+(?:\.\d{1,2})?$")


def _normalize_date(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    matched = DATE_PATTERN.search(text)
    if not matched:
        return None
    year, month, day = matched.group(1), matched.group(2), matched.group(3)
    try:
        dt = datetime(int(year), int(month), int(day))
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")


def _normalize_amount(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().replace("￥", "").replace("¥", "").replace(",", "")
    if not text:
        return None
    if not AMOUNT_PATTERN.match(text):
        try:
            value = float(text)
        except ValueError:
            return None
        return f"{value:.2f}"
    try:
        value = float(text)
    except ValueError:
        return None
    return f"{value:.2f}"


def _normalize_item_name(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return text.splitlines()[0].strip() or None


def _pdf_page_to_png_data_url(file_path: Path, page: int = 1, dpi: int = 220) -> str | None:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception:
        return None

    if page < 1:
        page = 1
    if dpi < 72:
        dpi = 72

    try:
        pdf = pdfium.PdfDocument(str(file_path))
        if len(pdf) < page:
            return None
        page_obj = pdf[page - 1]
        bitmap = page_obj.render(scale=dpi / 72.0)
        image = bitmap.to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except Exception:
        return None
    content = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{content}"


def _to_data_url(file_path: Path) -> str | None:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_page_to_png_data_url(file_path)

    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        return None
    data = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content or "")


class SiliconFlowClient:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip())

    def extract_fields(
        self,
        file_path: Path,
        timeout_seconds: int = 45,
    ) -> dict[str, Any]:
        if not self.is_configured:
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data_url = _to_data_url(file_path)
        if not data_url:
            return {}

        content_parts: list[dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            {"type": "text", "text": STRUCTURED_PROMPT},
        ]

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = parse_json_object(_extract_message_text(content))
        if not parsed:
            return {}

        invoice_date = _normalize_date(parsed.get("invoice_date"))
        item_name = _normalize_item_name(parsed.get("item_name"))
        amount = _normalize_amount(parsed.get("amount"))
        confidence_raw = parsed.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else 0.9
        except (TypeError, ValueError):
            confidence = 0.9
        confidence = min(1.0, max(0.0, confidence))

        return {
            "invoice_date": invoice_date,
            "item_name": item_name,
            "amount": amount,
            "confidence": confidence,
        }
