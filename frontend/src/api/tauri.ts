import type { CommitPlanItem, CommitRenameItemResult } from "./types";

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function renameByTauri(plan: CommitPlanItem[]): Promise<CommitRenameItemResult[]> {
  if (!isTauriRuntime()) {
    throw new Error("not_tauri_runtime");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  const results = await invoke<CommitRenameItemResult[]>("rename_files", {
    plan_items: plan,
  });
  return results;
}
