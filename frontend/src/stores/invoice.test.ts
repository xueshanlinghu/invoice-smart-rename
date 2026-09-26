import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import type { InvoiceItem, TaskState } from "../api/types";

const apiMocks = vi.hoisted(() => ({
  recognizeTask: vi.fn(),
  recalculateTask: vi.fn(),
  syncItems: vi.fn(),
  exportTask: vi.fn(),
}));

vi.mock("../api/client", () => ({
  buildCommitPlan: vi.fn(),
  clearItems: vi.fn(),
  commitRename: vi.fn(),
  exportTask: apiMocks.exportTask,
  fetchRecentTask: vi.fn(),
  fetchTask: vi.fn(),
  getSettings: vi.fn(),
  importPaths: vi.fn(),
  importTaskBackup: vi.fn(),
  recalculateTask: apiMocks.recalculateTask,
  recognizeTask: apiMocks.recognizeTask,
  removeItems: vi.fn(),
  syncCommitResults: vi.fn(),
  syncItems: apiMocks.syncItems,
  updateSettings: vi.fn(),
}));

vi.mock("../api/tauri", () => ({
  isTauriRuntime: () => false,
  renameByTauri: vi.fn(),
}));

import { useInvoiceStore } from "./invoice";

function item(id: string, status: InvoiceItem["status"]): InvoiceItem {
  return {
    id,
    source_path: `C:\\tmp\\${id}.pdf`,
    old_name: `${id}.pdf`,
    file_ext: ".pdf",
    invoice_date: status === "ok" ? "20260101" : null,
    item_name: status === "ok" ? "餐饮服务" : null,
    amount: status === "ok" ? "10" : null,
    category: status === "ok" ? "餐饮" : null,
    vendor_name: null,
    extracted_text: null,
    file_sha256: null,
    recognition_source: status === "ok" ? "cloud" : "pending",
    recognized_at: null,
    recognition_model: null,
    prompt_version: null,
    cloud_call_count: status === "ok" ? 1 : 0,
    status,
    failure_reason: null,
    suggested_name: null,
    manual_name: null,
    selected: true,
    action: null,
    conflict_type: "none",
    result: "pending",
    result_message: null,
    updated_at: "2026-01-01T00:00:00",
  };
}

function task(items: InvoiceItem[]): TaskState {
  return {
    id: "task-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    template: "{date}-{category}-{amount}",
    summary: {
      total: items.length,
      pending: items.filter((row) => row.status === "pending").length,
      ok: items.filter((row) => row.status === "ok").length,
      failed: items.filter((row) => row.status === "failed").length,
      conflict: 0,
      rename_ready: 0,
      renamed: 0,
      skipped: 0,
    },
    items,
  };
}

describe("invoice store recognition safeguards", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("recognizes pending rows without reprocessing successful rows", async () => {
    const store = useInvoiceStore();
    store.task = task([item("pending", "pending"), item("success", "ok")]);
    apiMocks.recognizeTask.mockResolvedValue(store.task);

    await store.recognizePending();

    expect(apiMocks.recognizeTask).toHaveBeenCalledTimes(1);
    expect(apiMocks.recognizeTask).toHaveBeenCalledWith("task-1", ["pending"], undefined, false);
  });

  it("stops before sending the next queued recognition request", async () => {
    const store = useInvoiceStore();
    store.task = task([item("first", "pending"), item("second", "pending")]);
    apiMocks.recognizeTask.mockImplementation(async () => {
      store.stopRecognizing();
      return store.task;
    });

    await store.recognizePending();

    expect(apiMocks.recognizeTask).toHaveBeenCalledTimes(1);
    expect(store.message).toContain("已停止识别");
  });

  it("applies category and name recalculation through the zero-cost endpoint", async () => {
    const store = useInvoiceStore();
    store.task = task([item("success", "ok")]);
    apiMocks.recalculateTask.mockResolvedValue(store.task);

    const count = await store.recalculate(["category", "name"]);

    expect(apiMocks.recalculateTask).toHaveBeenCalledWith("task-1", ["category", "name"]);
    expect(count).toBe(1);
  });

  it("saves manual edits before exporting a backup", async () => {
    const store = useInvoiceStore();
    store.task = task([item("success", "ok")]);
    const saved = task([{ ...item("success", "ok"), amount: "25", recognition_source: "manual" }]);
    apiMocks.syncItems.mockResolvedValue(saved);
    apiMocks.exportTask.mockResolvedValue({ format: "invoice-smart-rename-task", version: 1, task: saved });

    store.setItemAmount("success", "25");
    const backup = await store.createBackup();

    expect(apiMocks.syncItems).toHaveBeenCalledWith("task-1", [{
      item_id: "success", invoice_date: "20260101", amount: "25", category: "餐饮",
    }]);
    expect(apiMocks.exportTask.mock.invocationCallOrder[0]).toBeGreaterThan(
      apiMocks.syncItems.mock.invocationCallOrder[0],
    );
    expect(backup?.task.items[0].amount).toBe("25");
    expect(store.hasPendingEdits).toBe(false);
  });

  it("preserves a newer edit made while an earlier save is pending", async () => {
    const store = useInvoiceStore();
    store.task = task([item("success", "ok")]);
    let completeFirst!: (value: TaskState) => void;
    apiMocks.syncItems
      .mockImplementationOnce(() => new Promise<TaskState>((resolve) => { completeFirst = resolve; }))
      .mockResolvedValueOnce(task([{ ...item("success", "ok"), amount: "30" }]));

    store.setItemAmount("success", "20");
    const saving = store.syncEditableItems(true);
    await vi.waitFor(() => expect(apiMocks.syncItems).toHaveBeenCalledTimes(1));
    store.setItemAmount("success", "30");
    completeFirst(task([{ ...item("success", "ok"), amount: "20" }]));
    await saving;

    expect(apiMocks.syncItems).toHaveBeenCalledTimes(2);
    expect(apiMocks.syncItems).toHaveBeenLastCalledWith("task-1", [{
      item_id: "success", invoice_date: "20260101", amount: "30", category: "餐饮",
    }]);
    expect(store.task?.items[0].amount).toBe("30");
    expect(store.hasPendingEdits).toBe(false);
  });
});
