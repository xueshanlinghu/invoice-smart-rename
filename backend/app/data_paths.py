from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "InvoiceSmartRename"


def app_data_dir() -> Path:
    override = os.getenv("INVOICE_APP_DATA_DIR", "").strip()
    if override:
        target = Path(override).expanduser()
    elif sys.platform == "win32":
        target = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_DIR_NAME
    elif sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        target = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    return app_data_dir() / "invoice-smart-rename.sqlite3"
