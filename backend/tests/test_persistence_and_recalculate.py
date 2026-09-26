from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app import main
from app.schemas import InvoiceItem, TaskState
from app.services.naming import build_rename_plan
from app.storage import SqliteTaskStore


def _write_png(path: Path, color: str = "white") -> None:
    Image.new("RGB", (2, 2), color).save(path, format="PNG")


def _settings() -> dict:
    return {
        "siliconflow_base_url": "https://example.invalid/v1",
        "siliconflow_model": "test-model",
        "siliconflow_models": ["test-model"],
        "siliconflow_api_key": "test-key",
        "api_key_configured": True,
        "filename_template": "{date}-{category}-{amount}",
        "category_mapping": {"交通": ["机票"], "餐饮": ["餐饮"]},
    }


def test_sqlite_store_survives_new_instance(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite3"
    first = SqliteTaskStore(db_path)
    task = TaskState(id="task-1", items=[InvoiceItem(source_path="a.pdf", old_name="a.pdf", file_ext=".pdf")])
    first.save_task(task)
    first.save_cache(
        cache_key="cache-1",
        file_sha256="abc",
        provider="siliconflow",
        model="test-model",
        prompt_version="v1",
        result={"invoice_date": "20260101", "item_name": "机票", "amount": "10"},
    )

    second = SqliteTaskStore(db_path)
    assert second.get_recent_task() is not None
    assert second.get_task("task-1").items[0].old_name == "a.pdf"  # type: ignore[union-attr]
    assert second.get_cache("cache-1")["item_name"] == "机票"  # type: ignore[index]


def test_recent_task_skips_empty_task(tmp_path: Path) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    filled = TaskState(id="filled", items=[InvoiceItem(source_path="a.pdf", old_name="a.pdf", file_ext=".pdf")])
    empty = TaskState(id="empty")
    empty.updated_at = filled.updated_at.replace(year=filled.updated_at.year + 1)
    store.save_task(filled)
    store.save_task(empty)

    assert store.get_recent_task().id == "filled"  # type: ignore[union-attr]


def test_recalculate_category_without_cloud_call(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    task = TaskState(
        id="task-1",
        items=[
            InvoiceItem(
                source_path=str(tmp_path / "invoice.pdf"),
                old_name="invoice.pdf",
                file_ext=".pdf",
                invoice_date="20260101",
                item_name="代订机票产品",
                amount="88",
                category="其他",
                status="ok",
            )
        ],
    )
    store.save_task(task)
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    monkeypatch.setattr(main, "_new_pipeline", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud called")))

    response = TestClient(main.app).post(
        "/api/tasks/task-1/recalculate",
        json={"operations": ["category", "name"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["category"] == "交通"
    assert item["suggested_name"] == "20260101-交通-88元.pdf"


def test_import_appends_and_deduplicates_by_hash(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    first_file = tmp_path / "first.png"
    duplicate_file = tmp_path / "copy.png"
    _write_png(first_file)
    duplicate_file.write_bytes(first_file.read_bytes())
    client = TestClient(main.app)

    first = client.post("/api/import", json={"paths": [str(first_file)]})
    task_id = first.json()["id"]
    second = client.post("/api/import", json={"paths": [str(duplicate_file)], "task_id": task_id})

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1


def test_cache_is_used_unless_force_refresh(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    invoice = tmp_path / "invoice.png"
    _write_png(invoice)
    file_hash = main._file_sha256(invoice)
    item = InvoiceItem(
        source_path=str(invoice),
        old_name=invoice.name,
        file_ext=".png",
        file_sha256=file_hash,
    )
    task = TaskState(id="task-1", items=[item])
    store.save_task(task)
    store.save_cache(
        cache_key=main._cache_key(file_hash, "test-model"),
        file_sha256=file_hash,
        provider="siliconflow",
        model="test-model",
        prompt_version=main.PROMPT_VERSION,
        result={"invoice_date": "20260101", "item_name": "机票", "amount": "10"},
    )

    calls = 0

    class FakePipeline:
        def recognize_item(self, item: InvoiceItem, category_mapping: dict) -> InvoiceItem:
            nonlocal calls
            calls += 1
            item.invoice_date = "20260202"
            item.item_name = "餐饮服务"
            item.amount = "20"
            item.category = "餐饮"
            item.status = "ok"
            item.recognition_source = "cloud"
            return item

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    monkeypatch.setattr(main, "_new_pipeline", lambda *_args, **_kwargs: FakePipeline())
    client = TestClient(main.app)

    cached = client.post("/api/recognize", json={"task_id": "task-1", "item_ids": [item.id]})
    refreshed = client.post(
        "/api/recognize",
        json={"task_id": "task-1", "item_ids": [item.id], "force_refresh": True},
    )

    assert cached.json()["items"][0]["recognition_source"] == "cache"
    assert refreshed.json()["items"][0]["recognition_source"] == "cloud"
    assert calls == 1


def test_changed_or_missing_file_never_uses_old_cache(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    invoice = tmp_path / "invoice.png"
    _write_png(invoice)
    old_hash = main._file_sha256(invoice)
    item = InvoiceItem(source_path=str(invoice), old_name=invoice.name, file_ext=".png", file_sha256=old_hash)
    store.save_task(TaskState(id="task-1", items=[item]))
    store.save_cache(
        cache_key=main._cache_key(old_hash, "test-model"),
        file_sha256=old_hash,
        provider="siliconflow",
        model="test-model",
        prompt_version=main.PROMPT_VERSION,
        result={"invoice_date": "20260101", "item_name": "旧发票", "amount": "10"},
    )

    calls = 0

    class FakePipeline:
        def recognize_item(self, item: InvoiceItem, category_mapping: dict) -> InvoiceItem:
            nonlocal calls
            calls += 1
            item.invoice_date = "20260202"
            item.item_name = "新发票"
            item.amount = "20"
            item.status = "ok"
            item.recognition_source = "cloud"
            return item

    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    monkeypatch.setattr(main, "_new_pipeline", lambda *_args, **_kwargs: FakePipeline())
    client = TestClient(main.app)

    _write_png(invoice, "black")
    changed = client.post("/api/recognize", json={"task_id": "task-1", "item_ids": [item.id]})
    assert changed.status_code == 200
    assert changed.json()["items"][0]["item_name"] == "新发票"
    assert changed.json()["items"][0]["file_sha256"] == main._file_sha256(invoice)
    assert calls == 1

    invoice.unlink()
    missing = client.post("/api/recognize", json={"task_id": "task-1", "item_ids": [item.id]})
    assert missing.status_code == 200
    assert missing.json()["items"][0]["status"] == "failed"
    assert missing.json()["items"][0]["failure_reason"] == "file_not_found"
    assert calls == 1


def test_reimport_replaced_path_and_rename_plan_detects_change(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    invoice = tmp_path / "invoice.png"
    _write_png(invoice)
    client = TestClient(main.app)
    imported = client.post("/api/import", json={"paths": [str(invoice)]}).json()
    prior = store.get_task(imported["id"])
    assert prior is not None
    prior.items[0].status = "ok"
    prior.items[0].invoice_date = "20260101"
    prior.items[0].item_name = "旧发票"
    prior.items[0].amount = "10"
    prior.items[0].manual_name = "旧名称.png"
    store.save_task(prior)

    _write_png(invoice, "black")
    updated = client.post(
        "/api/import", json={"paths": [str(invoice)], "task_id": imported["id"]}
    ).json()
    assert len(updated["items"]) == 1
    assert updated["items"][0]["file_sha256"] == main._file_sha256(invoice)
    assert updated["items"][0]["status"] == "pending"
    assert updated["items"][0]["item_name"] is None
    assert updated["items"][0]["manual_name"] is None

    row = InvoiceItem.model_validate(updated["items"][0])
    row.status = "ok"
    row.suggested_name = "new.png"
    _write_png(invoice, "red")
    plan = build_rename_plan([row], {row.id})
    assert plan[0].action == "skip"
    assert plan[0].reason == "source_changed"


def test_invalid_image_is_rejected_before_cloud_call(tmp_path: Path, monkeypatch) -> None:
    store = SqliteTaskStore(tmp_path / "state.sqlite3")
    invoice = tmp_path / "broken.png"
    invoice.write_bytes(b"not-an-image")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(main, "_load_settings", _settings)
    monkeypatch.setattr(main, "_new_pipeline", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("cloud called")))
    client = TestClient(main.app)

    imported = client.post("/api/import", json={"paths": [str(invoice)]})
    assert imported.status_code == 200
    row = imported.json()["items"][0]
    assert row["status"] == "failed"
    assert row["failure_reason"] == "invalid_image"
    retried = client.post("/api/recognize", json={"task_id": imported.json()["id"], "item_ids": [row["id"]]})
    assert retried.status_code == 200
    assert retried.json()["items"][0]["failure_reason"] == "invalid_image"


def test_packaged_tauri_origin_can_reach_token_protected_api(monkeypatch) -> None:
    monkeypatch.setenv("INVOICE_SESSION_TOKEN", "test-session-token")
    monkeypatch.setattr(main, "_load_settings", _settings)
    client = TestClient(main.app)
    origin = "http://tauri.localhost"

    preflight = client.options(
        "/api/settings",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-app-token",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin

    unauthorized = client.get("/api/settings", headers={"Origin": origin})
    assert unauthorized.status_code == 401
    assert unauthorized.headers["access-control-allow-origin"] == origin

    authorized = client.get(
        "/api/settings",
        headers={"Origin": origin, "X-App-Token": "test-session-token"},
    )
    assert authorized.status_code == 200
    assert authorized.headers["access-control-allow-origin"] == origin
