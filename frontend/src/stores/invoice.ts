import { defineStore } from "pinia";
import {
  buildCommitPlan,
  clearItems,
  commitRename,
  fetchTask,
  getSettings,
  importPaths,
  recognizeTask,
  removeItems,
  syncCommitResults,
  syncItems,
  updateSettings,
} from "../api/client";
import { isTauriRuntime, renameByTauri } from "../api/tauri";
import type {
  AppSettings,
  AppSettingsUpdate,
  CommitPlanResponse,
  CommitRenameItemResult,
  CommitRenameResponse,
  InvoiceItem,
  SyncItemPatch,
  TaskState,
} from "../api/types";
import { applyNamePreviewLocal } from "../utils/naming";

interface InvoiceState {
  task: TaskState | null;
  loading: boolean;
  message: string;
  settings: AppSettings | null;
  lastPlan: CommitPlanResponse | null;
  lastRename: CommitRenameResponse | null;
  isRecognizing: boolean;
  recognizeTotal: number;
  recognizeDone: number;
  isRenaming: boolean;
  renameTotal: number;
  renameDone: number;
  sessionApiKey: string;
  localEdits: Record<string, { invoice_date: string | null; amount: string | null; category: string | null }>;
}

const DEFAULT_TEMPLATE = "{date}-{category}-{amount}";
const INVALID_FILENAME_CHAR_PATTERN = /[<>:"/\\|?*\x00-\x1F]/g;

export const useInvoiceStore = defineStore("invoice", {
  state: (): InvoiceState => ({
    task: null,
    loading: false,
    message: "",
    settings: null,
    lastPlan: null,
    lastRename: null,
    isRecognizing: false,
    recognizeTotal: 0,
    recognizeDone: 0,
    isRenaming: false,
    renameTotal: 0,
    renameDone: 0,
    sessionApiKey: "",
    localEdits: {},
  }),
  getters: {
    selectedIds(state): string[] {
      return (state.task?.items ?? []).filter((item) => item.selected).map((item) => item.id);
    },
    hasTask(state): boolean {
      return !!state.task?.id;
    },
    recognizePercent(state): number {
      if (!state.recognizeTotal) return 0;
      return Math.min(100, Math.round((state.recognizeDone / state.recognizeTotal) * 100));
    },
    renamePercent(state): number {
      if (!state.renameTotal) return 0;
      return Math.min(100, Math.round((state.renameDone / state.renameTotal) * 100));
    },
  },
  actions: {
    selectionSnapshot(): Record<string, boolean> {
      const snapshot: Record<string, boolean> = {};
      for (const item of this.task?.items ?? []) {
        snapshot[item.id] = item.selected;
      }
      return snapshot;
    },
    applyTask(nextTask: TaskState, selection?: Record<string, boolean>) {
      if (selection) {
        for (const item of nextTask.items) {
          if (Object.prototype.hasOwnProperty.call(selection, item.id)) {
            item.selected = selection[item.id];
          }
        }
      }
      for (const item of nextTask.items) {
        const localEdit = this.localEdits[item.id];
        if (!localEdit) continue;
        item.invoice_date = localEdit.invoice_date;
        item.amount = localEdit.amount;
        item.category = localEdit.category;
      }
      const aliveItemIds = new Set(nextTask.items.map((item) => item.id));
      for (const itemId of Object.keys(this.localEdits)) {
        if (!aliveItemIds.has(itemId)) {
          delete this.localEdits[itemId];
        }
      }
      this.task = nextTask;
    },
    currentTemplate(): string {
      return this.task?.template || this.settings?.filename_template || DEFAULT_TEMPLATE;
    },
    recomputePreviewLocally(template?: string) {
      if (!this.task) return;
      const appliedTemplate = template || this.currentTemplate();
      this.task.template = appliedTemplate;
      applyNamePreviewLocal(this.task.items, appliedTemplate);
    },
    normalizeNullableText(value: string | null | undefined): string | null {
      const text = (value ?? "").trim();
      return text || null;
    },
    sanitizeCategoryText(value: string | null | undefined): string | null {
      const text = (value ?? "").replace(INVALID_FILENAME_CHAR_PATTERN, "");
      return this.normalizeNullableText(text);
    },
    setSessionApiKey(value: string | null | undefined) {
      this.sessionApiKey = (value ?? "").trim();
    },
    handleError(error: unknown) {
      const maybeAxios = error as { response?: { data?: { detail?: string } }; message?: string };
      const detail = maybeAxios?.response?.data?.detail;
      const message = maybeAxios?.message ?? "";
      const raw = `${detail ?? ""} ${message}`.toLowerCase();
      if (raw.includes("rename_files") && raw.includes("unknown command")) {
        this.message = "桌面改名命令未加载，请重启 `npm run tauri:dev` 后重试";
        return;
      }
      if (raw.includes("missing required key") && raw.includes("plan")) {
        this.message = "改名参数传递失败，请重启 `npm run tauri:dev` 后重试";
        return;
      }
      this.message = detail ?? maybeAxios?.message ?? "请求失败";
    },
    summarizeRenameResults(results: CommitRenameItemResult[]): string {
      let renamed = 0;
      let failed = 0;
      let skipped = 0;
      for (const item of results) {
        if (item.result === "renamed") {
          renamed += 1;
        } else if (item.result === "failed") {
          failed += 1;
        } else if (item.result === "skipped") {
          skipped += 1;
        }
      }
      return `改名完成：成功 ${renamed}，失败 ${failed}，跳过 ${skipped}`;
    },
    async loadSettings() {
      try {
        this.settings = await getSettings();
      } catch (error) {
        this.handleError(error);
      }
    },
    async saveSettings(update: AppSettingsUpdate) {
      try {
        this.settings = await updateSettings(update);
        return this.settings;
      } catch (error) {
        this.handleError(error);
        throw error;
      }
    },
    async saveMapping(nextMapping: Record<string, string[]>) {
      await this.saveSettings({ category_mapping: nextMapping });
      this.message = "关键词映射已保存";
    },
    async saveTemplate(template: string) {
      await this.saveSettings({ filename_template: template });
      this.recomputePreviewLocally(template);
      this.message = "命名模板已保存";
    },
    async importByPaths(paths: string[]) {
      this.loading = true;
      try {
        this.task = await importPaths(paths);
        this.localEdits = {};
        this.lastPlan = null;
        this.lastRename = null;
        this.isRenaming = false;
        this.renameTotal = 0;
        this.renameDone = 0;
        this.recomputePreviewLocally();
        this.message = `已导入 ${this.task.summary.total} 个文件`;
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async refreshTask() {
      if (!this.task?.id) return;
      const selection = this.selectionSnapshot();
      try {
        const nextTask = await fetchTask(this.task.id);
        this.applyTask(nextTask, selection);
        this.recomputePreviewLocally();
      } catch (error) {
        this.handleError(error);
      }
    },
    setItemSelected(itemId: string, nextValue: boolean) {
      const item = this.task?.items.find((row) => row.id === itemId);
      if (!item) return;
      item.selected = nextValue;
    },
    setItemInvoiceDate(itemId: string, invoiceDate: string | null) {
      const item = this.task?.items.find((row) => row.id === itemId);
      if (!item) return;
      item.invoice_date = invoiceDate;
      this.localEdits[itemId] = {
        invoice_date: item.invoice_date ?? null,
        amount: item.amount ?? null,
        category: item.category ?? null,
      };
      this.recomputePreviewLocally();
    },
    setItemCategory(itemId: string, category: string | null) {
      const item = this.task?.items.find((row) => row.id === itemId);
      if (!item) return;
      item.category = this.sanitizeCategoryText(category);
      this.localEdits[itemId] = {
        invoice_date: item.invoice_date ?? null,
        amount: item.amount ?? null,
        category: item.category ?? null,
      };
      this.recomputePreviewLocally();
    },
    setItemAmount(itemId: string, amount: string | null) {
      const item = this.task?.items.find((row) => row.id === itemId);
      if (!item) return;
      item.amount = this.normalizeNullableText(amount);
      this.localEdits[itemId] = {
        invoice_date: item.invoice_date ?? null,
        amount: item.amount ?? null,
        category: item.category ?? null,
      };
      this.recomputePreviewLocally();
    },
    async recognize(itemIds?: string[]) {
      if (!this.task?.id) return;
      const targetIds = itemIds ?? this.selectedIds;
      if (!targetIds.length) {
        this.message = "请先勾选需要识别的发票";
        return;
      }

      this.loading = true;
      this.isRecognizing = true;
      this.recognizeTotal = targetIds.length;
      this.recognizeDone = 0;
      for (const itemId of targetIds) {
        delete this.localEdits[itemId];
      }

      try {
        const selection = this.selectionSnapshot();
        for (const itemId of targetIds) {
          const nextTask = await recognizeTask(this.task.id, [itemId], this.sessionApiKey || undefined);
          this.applyTask(nextTask, selection);
          this.recomputePreviewLocally();
          this.recognizeDone += 1;
        }
        this.message = `识别完成（${this.recognizeDone}/${this.recognizeTotal}）`;
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
        this.isRecognizing = false;
      }
    },
    preview(template?: string) {
      this.recomputePreviewLocally(template);
      this.message = "命名预览已更新";
    },
    async syncEditableItems(silent = false) {
      if (!this.task?.id) return;
      const patches: SyncItemPatch[] = Object.entries(this.localEdits).map(([itemId, value]) => ({
        item_id: itemId,
        invoice_date: value.invoice_date,
        amount: value.amount,
        category: value.category,
      }));
      if (!patches.length) return;
      const selection = this.selectionSnapshot();
      const nextTask = await syncItems(this.task.id, patches);
      for (const patch of patches) {
        delete this.localEdits[patch.item_id];
      }
      this.applyTask(nextTask, selection);
      this.recomputePreviewLocally();
      if (!silent) {
        this.message = "已同步编辑内容";
      }
    },
    async removeSelectedItemsFromList() {
      if (!this.task?.id) return;
      const targetIds = this.selectedIds;
      if (!targetIds.length) {
        this.message = "请先勾选要移除的发票";
        return;
      }
      this.loading = true;
      try {
        const selection = this.selectionSnapshot();
        const nextTask = await removeItems(this.task.id, targetIds);
        this.applyTask(nextTask, selection);
        this.recomputePreviewLocally();
        this.lastPlan = null;
        this.lastRename = null;
        this.message = `已从列表移除 ${targetIds.length} 项`;
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async clearTaskItems() {
      if (!this.task?.id) return;
      this.loading = true;
      try {
        this.task = await clearItems(this.task.id);
        this.localEdits = {};
        this.lastPlan = null;
        this.lastRename = null;
        this.recognizeTotal = 0;
        this.recognizeDone = 0;
        this.isRenaming = false;
        this.renameTotal = 0;
        this.renameDone = 0;
        this.message = "列表已清空";
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async buildPlan() {
      if (!this.task?.id) return;
      this.loading = true;
      try {
        await this.syncEditableItems(true);
        this.lastPlan = await buildCommitPlan(this.task.id, this.selectedIds);
        this.message = `计划生成完成：${this.lastPlan.plan.length} 项`;
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async executeRename() {
      if (!this.task?.id) return;
      const selectedItems = (this.task.items ?? []).filter((item) => item.selected);
      if (!selectedItems.length) {
        this.message = "请先勾选要改名的发票";
        return;
      }
      const hasEmptyNewName = selectedItems.some((item) => !(item.suggested_name ?? "").trim());
      if (hasEmptyNewName) {
        this.message = "选中项存在新文件名为空，请先识别后再改名";
        return;
      }
      this.loading = true;
      this.isRenaming = true;
      this.renameDone = 0;
      this.renameTotal = selectedItems.length;
      try {
        const selection = this.selectionSnapshot();
        await this.syncEditableItems(true);

        if (isTauriRuntime()) {
          this.lastPlan = await buildCommitPlan(this.task.id, this.selectedIds);
          const plan = this.lastPlan.plan;
          this.renameTotal = plan.length;
          this.renameDone = 0;

          const tauriResults: CommitRenameItemResult[] = [];
          for (const planItem of plan) {
            const results = await renameByTauri([planItem]);
            const first = results[0] ?? {
              item_id: planItem.item_id,
              source_path: planItem.source_path,
              target_path: planItem.target_path,
              result: "failed",
              message: "tauri_result_empty",
            };
            tauriResults.push(first);
            this.renameDone += 1;
          }
          this.lastRename = await syncCommitResults(this.task.id, tauriResults);
        } else {
          this.lastRename = await commitRename(this.task.id, this.selectedIds);
          this.renameTotal = this.lastRename.results.length;
          this.renameDone = this.renameTotal;
        }
        const nextTask = await fetchTask(this.task.id);
        this.applyTask(nextTask, selection);
        this.recomputePreviewLocally();
        this.message = this.summarizeRenameResults(this.lastRename?.results ?? []);
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
        this.isRenaming = false;
      }
    },
    toggleSelectAll(nextValue: boolean) {
      if (!this.task) return;
      this.task.items.forEach((item) => {
        item.selected = nextValue;
      });
    },
  },
});
