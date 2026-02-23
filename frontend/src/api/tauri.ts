import type { CommitPlanItem, CommitRenameItemResult } from "./types";

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function pickFilesFromSystem(): Promise<string[]> {
  if (!isTauriRuntime()) {
    return [];
  }
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: true,
    directory: false,
    filters: [
      { name: "Invoices", extensions: ["pdf", "png", "jpg", "jpeg"] },
    ],
  });

  if (!selected) {
    return [];
  }
  if (Array.isArray(selected)) {
    return selected.map((v) => String(v));
  }
  return [String(selected)];
}

export async function pickFolderFromSystem(): Promise<string[]> {
  if (!isTauriRuntime()) {
    return [];
  }
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({
    multiple: false,
    directory: true,
  });
  if (!selected) {
    return [];
  }
  return [String(selected)];
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
