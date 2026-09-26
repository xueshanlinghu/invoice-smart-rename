from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from app.data_paths import DATABASE_FILENAME


def migrate_legacy_database(data_dir: Path, legacy_data_dir: Path) -> bool:
    """Copy a complete SQLite snapshot into a new portable data directory once."""
    target = data_dir / DATABASE_FILENAME
    source = legacy_data_dir / DATABASE_FILENAME
    if target.exists() or not source.is_file():
        return False

    data_dir.mkdir(parents=True, exist_ok=True)
    temporary = data_dir / f".{DATABASE_FILENAME}.{uuid4().hex}.tmp"
    try:
        with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as old_db:
            with closing(sqlite3.connect(temporary)) as new_db:
                old_db.backup(new_db)
                if new_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("migrated_database_integrity_check_failed")

        if target.exists():
            return False
        temporary.rename(target)
        return True
    finally:
        temporary.unlink(missing_ok=True)
