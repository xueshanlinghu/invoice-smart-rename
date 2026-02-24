from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    ClearItemsRequest,
    CommitPlanRequest,
    CommitPlanResponse,
    CommitResultsSyncRequest,
    CommitRenameRequest,
    CommitRenameResponse,
    ImportRequest,
    InvoiceItem,
    InvoicePatchRequest,
    PreviewRequest,
    RecognizeRequest,
    RemoveItemsRequest,
    SettingsResponse,
    SettingsUpdateRequest,
    SyncItemsRequest,
    TaskState,
    TaskSummary,
)
from app.services.importer import collect_invoice_files
from app.services.naming import apply_name_preview, build_rename_plan
from app.services.ocr.pipeline import OcrPipeline
from app.services.rename import execute_rename_plan
from app.services.settings_store import load_runtime_settings, save_runtime_settings
from app.storage import InMemoryTaskStore


app = FastAPI(title="Invoice Smart Rename API", version="0.1.0")
store = InMemoryTaskStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _load_settings() -> dict:
    return load_runtime_settings()


def _to_settings_response(data: dict) -> SettingsResponse:
    return SettingsResponse(
        siliconflow_base_url=str(data["siliconflow_base_url"]),
        siliconflow_model=str(data["siliconflow_model"]),
        siliconflow_models=list(data["siliconflow_models"]),
        api_key_configured=bool(data["api_key_configured"]),
        filename_template=str(data["filename_template"]),
        category_mapping=dict(data["category_mapping"]),
    )


def _new_pipeline(settings_data: dict, *, api_key_override: str | None = None) -> OcrPipeline:
    api_key = (api_key_override or "").strip() or str(settings_data["siliconflow_api_key"])
    return OcrPipeline(
        base_url=str(settings_data["siliconflow_base_url"]),
        api_key=api_key,
        model=str(settings_data["siliconflow_model"]),
    )


def _save_task(task: TaskState) -> TaskState:
    task.updated_at = _utcnow()
    task.summary = _build_summary(task.items)
    store.save_task(task)
    return task


def _build_summary(items: list[InvoiceItem]) -> TaskSummary:
    summary = TaskSummary(total=len(items))
    for item in items:
        if item.status == "pending":
            summary.pending += 1
        elif item.status == "ok":
            summary.ok += 1
        elif item.status == "failed":
            summary.failed += 1

        if item.conflict_type != "none":
            summary.conflict += 1
        if item.action == "rename":
            summary.rename_ready += 1
        if item.result == "renamed":
            summary.renamed += 1
        if item.result == "skipped":
            summary.skipped += 1
    return summary


def _must_task(task_id: str) -> TaskState:
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return task


def _item_index(task: TaskState) -> dict[str, InvoiceItem]:
    return {item.id: item for item in task.items}


@app.get("/api/health")
def health() -> dict:
    settings_data = _load_settings()
    return {
        "status": "ok",
        "time": _utcnow().isoformat(),
        "cloud_configured": bool(settings_data["api_key_configured"]),
        "model": settings_data["siliconflow_model"],
        "base_url": settings_data["siliconflow_base_url"],
    }


@app.post("/api/import", response_model=TaskState)
def import_invoices(request: ImportRequest) -> TaskState:
    files = collect_invoice_files(request.paths)
    if not files:
        raise HTTPException(status_code=400, detail="No supported invoice files found")

    settings_data = _load_settings()
    task = TaskState(id=str(uuid4()), template=str(settings_data["filename_template"]))
    task.items = [
        InvoiceItem(
            source_path=str(file_path),
            old_name=file_path.name,
            file_ext=file_path.suffix.lower(),
        )
        for file_path in files
    ]
    return _save_task(task)


@app.get("/api/tasks/{task_id}", response_model=TaskState)
def get_task(task_id: str) -> TaskState:
    task = _must_task(task_id)
    return _save_task(task)


@app.post("/api/recognize", response_model=TaskState)
def recognize_items(request: RecognizeRequest) -> TaskState:
    task = _must_task(request.task_id)
    target_ids = set(request.item_ids or [item.id for item in task.items])
    settings_data = _load_settings()
    mapping = dict(settings_data["category_mapping"])
    pipeline = _new_pipeline(settings_data, api_key_override=request.session_api_key)

    for item in task.items:
        if item.id not in target_ids:
            continue
        updated = pipeline.recognize_item(item=item, category_mapping=mapping)
        updated.updated_at = _utcnow()

    apply_name_preview(task.items, template=task.template)
    return _save_task(task)


@app.post("/api/preview-names", response_model=TaskState)
def preview_names(request: PreviewRequest) -> TaskState:
    task = _must_task(request.task_id)
    template = request.template or task.template
    task.template = template

    target_ids = set(request.item_ids or [item.id for item in task.items])
    target_items = [item for item in task.items if item.id in target_ids]
    apply_name_preview(target_items, template=template)
    for item in target_items:
        item.updated_at = _utcnow()
    return _save_task(task)


@app.post("/api/commit-plan", response_model=CommitPlanResponse)
def commit_plan(request: CommitPlanRequest) -> CommitPlanResponse:
    task = _must_task(request.task_id)
    plan = build_rename_plan(task.items, set(request.item_ids) if request.item_ids else None)

    index = _item_index(task)
    for plan_item in plan:
        item = index[plan_item.item_id]
        item.action = plan_item.action
        item.conflict_type = plan_item.conflict_type
        item.updated_at = _utcnow()

    _save_task(task)
    return CommitPlanResponse(task_id=task.id, dry_run=request.dry_run, plan=plan)


@app.post("/api/commit-rename", response_model=CommitRenameResponse)
def commit_rename(request: CommitRenameRequest) -> CommitRenameResponse:
    task = _must_task(request.task_id)
    plan = build_rename_plan(task.items, set(request.item_ids) if request.item_ids else None)
    results = execute_rename_plan(plan)

    index = _item_index(task)
    for result in results:
        item = index[result.item_id]
        item.result = result.result
        item.result_message = result.message
        if result.result == "renamed":
            item.source_path = result.target_path
            item.old_name = Path(result.target_path).name
        item.updated_at = _utcnow()

    _save_task(task)
    return CommitRenameResponse(task_id=task.id, results=results)


@app.post("/api/commit-results", response_model=CommitRenameResponse)
def commit_results(request: CommitResultsSyncRequest) -> CommitRenameResponse:
    task = _must_task(request.task_id)
    index = _item_index(task)
    for result in request.results:
        if result.item_id not in index:
            continue
        item = index[result.item_id]
        item.result = result.result
        item.result_message = result.message
        if result.result == "renamed":
            item.source_path = result.target_path
            item.old_name = Path(result.target_path).name
        item.updated_at = _utcnow()

    _save_task(task)
    return CommitRenameResponse(task_id=task.id, results=request.results)


@app.post("/api/sync-items", response_model=TaskState)
def sync_items(request: SyncItemsRequest) -> TaskState:
    task = _must_task(request.task_id)
    if not request.items:
        return _save_task(task)

    index = _item_index(task)
    for patch in request.items:
        item = index.get(patch.item_id)
        if not item:
            continue
        item.invoice_date = patch.invoice_date
        item.amount = patch.amount
        item.category = patch.category
        item.updated_at = _utcnow()

    apply_name_preview(task.items, template=task.template)
    return _save_task(task)


@app.patch("/api/items/{task_id}/{item_id}", response_model=TaskState)
def patch_item(task_id: str, item_id: str, request: InvoicePatchRequest) -> TaskState:
    task = _must_task(task_id)
    index = _item_index(task)
    if item_id not in index:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    item = index[item_id]
    patch = request.model_dump(exclude_unset=True)
    for key, value in patch.items():
        setattr(item, key, value)
    item.updated_at = _utcnow()
    preview_related_fields = {"invoice_date", "category", "amount", "manual_name", "item_name", "status"}
    if any(field in patch for field in preview_related_fields):
        apply_name_preview(task.items, template=task.template)
    return _save_task(task)


@app.post("/api/remove-items", response_model=TaskState)
def remove_items(request: RemoveItemsRequest) -> TaskState:
    task = _must_task(request.task_id)
    if not request.item_ids:
        return _save_task(task)

    target_ids = set(request.item_ids)
    task.items = [item for item in task.items if item.id not in target_ids]
    apply_name_preview(task.items, template=task.template)
    for item in task.items:
        item.updated_at = _utcnow()
    return _save_task(task)


@app.post("/api/clear-items", response_model=TaskState)
def clear_items(request: ClearItemsRequest) -> TaskState:
    task = _must_task(request.task_id)
    task.items = []
    return _save_task(task)


@app.get("/api/settings", response_model=SettingsResponse)
def get_settings() -> SettingsResponse:
    return _to_settings_response(_load_settings())


@app.put("/api/settings", response_model=SettingsResponse)
def put_settings(request: SettingsUpdateRequest) -> SettingsResponse:
    updated = save_runtime_settings(
        siliconflow_base_url=request.siliconflow_base_url,
        siliconflow_model=request.siliconflow_model,
        siliconflow_models=request.siliconflow_models,
        siliconflow_api_key=request.siliconflow_api_key,
        filename_template=request.filename_template,
        category_mapping=request.category_mapping,
    )
    return _to_settings_response(updated)
