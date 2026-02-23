from __future__ import annotations

from app.schemas import InvoiceItem
from app.services.naming import apply_name_preview, build_rename_plan


def _item(name: str, date: str, category: str, amount: str) -> InvoiceItem:
    return InvoiceItem(
        source_path=f"E:/tmp/{name}",
        old_name=name,
        file_ext=".pdf",
        invoice_date=date,
        category=category,
        amount=amount,
        status="ok",
    )


def test_group_suffix_is_applied_from_second_item() -> None:
    items = [
        _item("a.pdf", "2025-12-05", "餐饮", "23.31"),
        _item("b.pdf", "2025-12-05", "餐饮", "23.31"),
        _item("c.pdf", "2025-12-05", "餐饮", "23.31"),
    ]

    apply_name_preview(items, template="{date}-{category}-{amount}.{ext}")

    assert items[0].suggested_name == "20251205-餐饮-23.31元.pdf"
    assert items[1].suggested_name == "20251205-餐饮2-23.31元.pdf"
    assert items[2].suggested_name == "20251205-餐饮3-23.31元.pdf"


def test_same_name_is_skipped() -> None:
    item = _item("20251205-餐饮-23.31元.pdf", "2025-12-05", "餐饮", "23.31")
    apply_name_preview([item], template="{date}-{category}-{amount}.{ext}")
    plan = build_rename_plan([item])
    assert plan[0].action == "skip"
    assert plan[0].conflict_type == "same_name"

