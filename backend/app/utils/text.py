from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


INVALID_FILENAME_CHARS = r'<>:"/\|?*'
INVALID_FILENAME_PATTERN = re.compile(r"[<>:\"/\\|?*\x00-\x1F]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_spaces(value: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def sanitize_component(value: str, fallback: str = "未命名") -> str:
    text = normalize_spaces(value)
    text = INVALID_FILENAME_PATTERN.sub("-", text)
    text = text.rstrip(". ")
    if not text:
        return fallback
    return text


def format_amount_to_yuan(amount: str | float | Decimal) -> str:
    if isinstance(amount, Decimal):
        decimal_value = amount
    else:
        try:
            decimal_value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            return "0.00元"
    quantized = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized}元"


def parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    # tolerant extraction for Markdown fenced code or mixed text.
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        maybe = raw[start : end + 1]
        try:
            data = json.loads(maybe)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

