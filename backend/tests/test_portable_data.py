from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data_paths import DATABASE_FILENAME
from app.portable_data import migrate_legacy_database
from app.schemas import InvoiceItem, TaskState
from app.storage import SqliteTaskStore


def test_migrates_legacy_wal_snapshot_without_overwriting_portable_data(tmp_path: Path) -> None:
    legacy_dir = tmp_path / "legacy"
    portable_dir = tmp_path / "portable"
    legacy_store = SqliteTaskStore(legacy_dir / DATABASE_FILENAME)
    legacy_store.save_settings(
        {"siliconflow_api_key": "fake-key", "category_mapping": {"交通": ["机票"]}}
    )
    legacy_store.save_task(
        TaskState(
            id="task-1",
            items=[InvoiceItem(source_path="a.pdf", old_name="a.pdf", file_ext=".pdf")],
        )
    )
    legacy_store.save_cache(
        cache_key="cache-1",
        file_sha256="abc",
        provider="siliconflow",
        model="test-model",
        prompt_version="v1",
        result={"item_name": "机票"},
    )

    keeper = sqlite3.connect(legacy_dir / DATABASE_FILENAME)
    try:
        keeper.execute(
            "INSERT OR REPLACE INTO settings(key, value_json) VALUES (?, ?)",
            ("filename_template", '"{date}-{amount}"'),
        )
        keeper.commit()
        assert (legacy_dir / f"{DATABASE_FILENAME}-wal").stat().st_size > 0

        assert migrate_legacy_database(portable_dir, legacy_dir)
        portable_store = SqliteTaskStore(portable_dir / DATABASE_FILENAME)
        assert portable_store.load_settings() == {
            "siliconflow_api_key": "fake-key",
            "category_mapping": {"交通": ["机票"]},
            "filename_template": "{date}-{amount}",
        }
        assert portable_store.get_task("task-1") is not None
        assert portable_store.get_cache("cache-1") == {"item_name": "机票"}

        legacy_store.save_settings({"siliconflow_api_key": "newer-fake-key"})
        assert not migrate_legacy_database(portable_dir, legacy_dir)
        assert portable_store.load_settings()["siliconflow_api_key"] == "fake-key"
    finally:
        keeper.close()
