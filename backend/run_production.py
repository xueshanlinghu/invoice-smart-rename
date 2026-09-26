from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoice Smart Rename backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--legacy-data-dir", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.token:
        os.environ["INVOICE_SESSION_TOKEN"] = args.token
    if args.data_dir:
        os.environ["INVOICE_APP_DATA_DIR"] = args.data_dir
        if args.legacy_data_dir:
            from app.portable_data import migrate_legacy_database

            migrate_legacy_database(Path(args.data_dir), Path(args.legacy_data_dir))

    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=False,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
