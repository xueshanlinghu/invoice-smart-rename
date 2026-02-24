import type { CommitPlanItem, CommitRenameItemResult, PreviewPayload } from "./types";

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

export async function readPreviewFile(sourcePath: string): Promise<PreviewPayload> {
  if (!isTauriRuntime()) {
    throw new Error("not_tauri_runtime");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  const payload = await invoke<PreviewPayload>("read_preview_file", {
    // Keep both key styles for compatibility with different invoke arg mapping behaviors.
    source_path: sourcePath,
    sourcePath,
  });
  return payload;
}
