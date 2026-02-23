from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


InvoiceStatus = Literal["pending", "ok", "needs_review", "failed"]
RenameAction = Literal["rename", "skip", "manual_edit_required"]
ConflictType = Literal["none", "same_name", "exists_other"]
CommitResultStatus = Literal["pending", "renamed", "skipped", "failed"]


def now_utc() -> datetime:
    return datetime.utcnow()


class TaskSummary(BaseModel):
    total: int = 0
    pending: int = 0
    ok: int = 0
    needs_review: int = 0
    failed: int = 0
    conflict: int = 0
    rename_ready: int = 0
    renamed: int = 0
    skipped: int = 0


class InvoiceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_path: str
    old_name: str
    file_ext: str

    invoice_date: str | None = None
    item_name: str | None = None
    amount: str | None = None
    category: str | None = None
    vendor_name: str | None = None

    fields_confidence: dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0

    extracted_text: str | None = None

    status: InvoiceStatus = "pending"
    failure_reason: str | None = None

    suggested_name: str | None = None
    manual_name: str | None = None

    selected: bool = True
    action: RenameAction | None = None
    conflict_type: ConflictType = "none"

    result: CommitResultStatus = "pending"
    result_message: str | None = None

    updated_at: datetime = Field(default_factory=now_utc)


class TaskState(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    template: str = "{date}-{category}-{amount}"
    summary: TaskSummary = Field(default_factory=TaskSummary)
    items: list[InvoiceItem] = Field(default_factory=list)


class ImportRequest(BaseModel):
    paths: list[str]


class RecognizeRequest(BaseModel):
    task_id: str
    item_ids: list[str] | None = None


class PreviewRequest(BaseModel):
    task_id: str
    template: str | None = None
    item_ids: list[str] | None = None


class CommitPlanRequest(BaseModel):
    task_id: str
    item_ids: list[str] | None = None
    dry_run: bool = True


class RenamePlanItem(BaseModel):
    item_id: str
    source_path: str
    target_path: str
    old_name: str
    target_name: str
    action: RenameAction
    conflict_type: ConflictType = "none"
    reason: str | None = None


class CommitPlanResponse(BaseModel):
    task_id: str
    dry_run: bool
    plan: list[RenamePlanItem]


class CommitRenameRequest(BaseModel):
    task_id: str
    item_ids: list[str] | None = None


class CommitRenameItemResult(BaseModel):
    item_id: str
    source_path: str
    target_path: str
    result: CommitResultStatus
    message: str | None = None


class CommitRenameResponse(BaseModel):
    task_id: str
    results: list[CommitRenameItemResult]


class CommitResultsSyncRequest(BaseModel):
    task_id: str
    results: list[CommitRenameItemResult]


class InvoicePatchRequest(BaseModel):
    invoice_date: str | None = None
    item_name: str | None = None
    amount: str | None = None
    category: str | None = None
    vendor_name: str | None = None
    manual_name: str | None = None
    selected: bool | None = None


class SettingsResponse(BaseModel):
    siliconflow_base_url: str
    siliconflow_model: str
    siliconflow_models: list[str]
    api_key_configured: bool
    filename_template: str
    category_mapping: dict[str, list[str]]


class SettingsUpdateRequest(BaseModel):
    siliconflow_base_url: str | None = None
    siliconflow_model: str | None = None
    siliconflow_models: list[str] | None = None
    siliconflow_api_key: str | None = None
    filename_template: str | None = None
    category_mapping: dict[str, list[str]] | None = None


class ApiError(BaseModel):
    detail: str
    extra: dict[str, Any] | None = None
