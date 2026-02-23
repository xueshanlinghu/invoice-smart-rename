from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from app.schemas import InvoiceItem, RenamePlanItem
from app.utils.text import format_amount_to_yuan, sanitize_component


DEFAULT_TEMPLATE = "{date}-{category}-{amount}"


@dataclass(slots=True)
class NamingTokens:
    date: str
    category: str
    amount: str
    ext: str


def _format_date(date_value: str | None) -> str:
    if not date_value:
        return "19700101"
    return date_value.replace("-", "")


def _format_amount(amount: str | None) -> str:
    if not amount:
        return "0.00元"
    try:
        decimal_value = Decimal(amount)
    except InvalidOperation:
        return "0.00元"
    return format_amount_to_yuan(decimal_value)


def _render_template(template: str, tokens: NamingTokens) -> str:
    result = template
    result = result.replace("{date}", tokens.date)
    result = result.replace("{category}", tokens.category)
    result = result.replace("{amount}", tokens.amount)
    result = result.replace("{ext}", tokens.ext)
    return result


EXT_SUFFIX_PATTERN = re.compile(r"\.[A-Za-z0-9]{1,12}$")


def _normalize_base_name(value: str, ext: str) -> str:
    base = sanitize_component(value, fallback="未命名")
    ext_value = f".{ext.lower()}"
    if base.lower().endswith(ext_value):
        base = base[: -len(ext_value)]
    elif EXT_SUFFIX_PATTERN.search(base):
        base = EXT_SUFFIX_PATTERN.sub("", base)
    return sanitize_component(base, fallback="未命名")


def _build_final_name(base_name: str, ext: str) -> str:
    return f"{base_name}.{ext.lower()}"


def apply_name_preview(items: list[InvoiceItem], template: str | None = None) -> list[InvoiceItem]:
    template = template or DEFAULT_TEMPLATE
    counters: dict[tuple[str, str, str], int] = defaultdict(int)

    ordered_items = sorted(items, key=lambda item: (item.invoice_date or "", item.old_name.lower()))
    for item in ordered_items:
        item.action = "skip"
        item.conflict_type = "none"
        if item.status in {"pending", "failed"}:
            item.suggested_name = None
            item.action = "manual_edit_required"
            continue

        group_key = (item.invoice_date or "", item.category or "其他", item.amount or "0.00")
        counters[group_key] += 1
        index = counters[group_key]

        category = item.category or "其他"
        if index > 1:
            category = f"{category}{index}"

        ext = item.file_ext.lstrip(".").lower()
        tokens = NamingTokens(
            date=_format_date(item.invoice_date),
            category=sanitize_component(category, fallback="其他"),
            amount=sanitize_component(_format_amount(item.amount), fallback="0.00元"),
            ext=ext,
        )
        rendered = _render_template(template, tokens)
        base_name = _normalize_base_name(rendered, ext=ext)
        item.suggested_name = _build_final_name(base_name, ext=ext)
        item.action = "rename"

    return items


def build_rename_plan(items: list[InvoiceItem], selected_ids: set[str] | None = None) -> list[RenamePlanItem]:
    selected_ids = selected_ids or {item.id for item in items if item.selected}
    used_targets: set[str] = set()
    plan: list[RenamePlanItem] = []

    for item in items:
        ext = item.file_ext.lstrip(".").lower()
        chosen_name_raw = item.manual_name or item.suggested_name
        chosen_name = None
        if chosen_name_raw:
            base_name = _normalize_base_name(chosen_name_raw, ext=ext)
            chosen_name = _build_final_name(base_name, ext=ext)
        source = Path(item.source_path)
        target_name = chosen_name or item.old_name
        target_path = source.with_name(target_name)

        action = "rename"
        reason = None
        conflict_type = "none"

        if item.id not in selected_ids:
            action = "skip"
            reason = "not_selected"
        elif item.status == "failed":
            action = "skip"
            reason = "recognition_failed"
            conflict_type = "none"
        elif not chosen_name:
            action = "skip"
            reason = "missing_suggested_name"
            conflict_type = "none"
        elif target_name == item.old_name:
            action = "skip"
            reason = "same_name"
            conflict_type = "same_name"
        elif str(target_path).lower() in used_targets:
            action = "skip"
            reason = "duplicate_in_batch"
            conflict_type = "exists_other"
        elif target_path.exists() and target_path.resolve() != source.resolve():
            action = "skip"
            reason = "target_exists"
            conflict_type = "exists_other"

        if action == "rename":
            used_targets.add(str(target_path).lower())

        plan.append(
            RenamePlanItem(
                item_id=item.id,
                source_path=str(source),
                target_path=str(target_path),
                old_name=item.old_name,
                target_name=target_name,
                action=action,
                conflict_type=conflict_type,
                reason=reason,
            )
        )

    return plan
