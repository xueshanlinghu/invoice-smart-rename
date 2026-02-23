from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def collect_invoice_files(paths: list[str]) -> list[Path]:
    files: dict[str, Path] = {}

    for raw_path in paths:
        candidate = Path(raw_path).expanduser()
        if not candidate.exists():
            continue

        if candidate.is_file():
            if candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                files[str(candidate.resolve())] = candidate.resolve()
            continue

        for child in candidate.rglob("*"):
            if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                files[str(child.resolve())] = child.resolve()

    return sorted(files.values(), key=lambda p: p.name.lower())

