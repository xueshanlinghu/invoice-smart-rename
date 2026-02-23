from __future__ import annotations

from pathlib import Path

from app.schemas import CommitRenameItemResult, RenamePlanItem


def execute_rename_plan(plan: list[RenamePlanItem]) -> list[CommitRenameItemResult]:
    results: list[CommitRenameItemResult] = []
    for item in plan:
        if item.action != "rename":
            results.append(
                CommitRenameItemResult(
                    item_id=item.item_id,
                    source_path=item.source_path,
                    target_path=item.target_path,
                    result="skipped",
                    message=item.reason or "skipped",
                )
            )
            continue

        source = Path(item.source_path)
        target = Path(item.target_path)
        if not source.exists():
            results.append(
                CommitRenameItemResult(
                    item_id=item.item_id,
                    source_path=item.source_path,
                    target_path=item.target_path,
                    result="failed",
                    message="source_not_found",
                )
            )
            continue

        try:
            source.rename(target)
            result = CommitRenameItemResult(
                item_id=item.item_id,
                source_path=item.source_path,
                target_path=item.target_path,
                result="renamed",
                message=None,
            )
        except OSError as exc:
            result = CommitRenameItemResult(
                item_id=item.item_id,
                source_path=item.source_path,
                target_path=item.target_path,
                result="failed",
                message=str(exc),
            )
        results.append(result)
    return results

