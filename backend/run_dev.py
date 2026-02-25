from __future__ import annotations

import uvicorn

from app.config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        reload_excludes=[
            ".env",
            "*.env",
            ".venv/*",
            "backend/.venv/*",
            "src-tauri/target/*",
            "node_modules/*",
        ],
    )


if __name__ == "__main__":
    main()
