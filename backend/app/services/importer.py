from __future__ import annotations

from pathlib import Path
import warnings

from PIL import Image


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_INVOICE_FILE_SIZE = 25 * 1024 * 1024
MAX_PDF_PAGES = 20


def validate_invoice_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_INVOICE_FILE_SIZE:
            return "file_too_large"
    except OSError:
        return "file_not_found"
    if path.suffix.lower() == ".pdf":
        try:
            import pypdfium2 as pdfium  # type: ignore

            document = pdfium.PdfDocument(str(path))
            try:
                if len(document) > MAX_PDF_PAGES:
                    return "pdf_too_many_pages"
            finally:
                document.close()
        except Exception:
            return "invalid_pdf"
    elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        try:
            expected_format = "PNG" if path.suffix.lower() == ".png" else "JPEG"
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.format != expected_format or image.size[0] < 1 or image.size[1] < 1:
                        return "invalid_image"
                    image.verify()
        except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return "invalid_image"
    return None


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
