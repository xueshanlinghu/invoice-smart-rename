from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.data_paths import database_path
from app.schemas import TaskState


class SqliteTaskStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at DESC);
                CREATE TABLE IF NOT EXISTS ocr_cache (
                    cache_key TEXT PRIMARY KEY,
                    file_sha256 TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )

    def save_task(self, task: TaskState) -> None:
        payload = task.model_dump_json()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks(id, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
                """,
                (task.id, payload, task.created_at.isoformat(), task.updated_at.isoformat()),
            )

    def get_task(self, task_id: str) -> TaskState | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT state_json FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return TaskState.model_validate_json(row["state_json"]) if row else None

    def get_recent_task(self) -> TaskState | None:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT state_json FROM tasks ORDER BY updated_at DESC"
            ).fetchall()
        for row in rows:
            task = TaskState.model_validate_json(row["state_json"])
            if task.items:
                return task
        return None

    def get_cache(self, cache_key: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM ocr_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def save_cache(
        self,
        *,
        cache_key: str,
        file_sha256: str,
        provider: str,
        model: str,
        prompt_version: str,
        result: dict[str, Any],
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ocr_cache
                (cache_key, file_sha256, provider, model, prompt_version, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    file_sha256,
                    provider,
                    model,
                    prompt_version,
                    json.dumps(result, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                ),
            )

    def load_settings(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            rows = connection.execute("SELECT key, value_json FROM settings").fetchall()
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def save_settings(self, values: dict[str, Any]) -> None:
        with self._lock, self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO settings(key, value_json) VALUES (?, ?)",
                [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()],
            )


# Compatibility alias for existing imports and third-party usage.
InMemoryTaskStore = SqliteTaskStore
