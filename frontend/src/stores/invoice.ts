import { defineStore } from "pinia";
import {
  buildCommitPlan,
  clearItems,
  commitRename,
  fetchTask,
  getSettings,
  importPaths,
  patchItem,
  previewNames,
  recognizeTask,
  removeItems,
  syncCommitResults,
  updateSettings,
} from "../api/client";
import { isTauriRuntime, renameByTauri } from "../api/tauri";
import type {
  AppSettings,
  AppSettingsUpdate,
  CommitPlanResponse,
  CommitRenameResponse,
  InvoiceItem,
  TaskState,
} from "../api/types";

interface InvoiceState {
  task: TaskState | null;
  loading: boolean;
  message: string;
  settings: AppSettings | null;
  lastPlan: CommitPlanResponse | null;
  lastRename: CommitRenameResponse | null;
}

export const useInvoiceStore = defineStore("invoice", {
  state: (): InvoiceState => ({
    task: null,
    loading: false,
    message: "",
    settings: null,
    lastPlan: null,
    lastRename: null,
  }),
  getters: {
    selectedIds(state): string[] {
      return (state.task?.items ?? []).filter((item) => item.selected).map((item) => item.id);
    },
    hasTask(state): boolean {
      return !!state.task?.id;
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
      this.task = nextTask;
    },
    handleError(error: unknown) {
      const maybeAxios = error as { response?: { data?: { detail?: string } }; message?: string };
      this.message = maybeAxios?.response?.data?.detail ?? maybeAxios?.message ?? "请求失败";
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
      this.message = "命名模板已保存";
    },
    async importByPaths(paths: string[]) {
      this.loading = true;
      try {
        this.task = await importPaths(paths);
        this.lastPlan = null;
        this.lastRename = null;
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
      } catch (error) {
        this.handleError(error);
      }
    },
    async recognize(itemIds?: string[]) {
      if (!this.task?.id) return;
      const targetIds = itemIds ?? this.selectedIds;
      if (!targetIds.length) {
        this.message = "请先勾选需要识别的发票";
        return;
      }
      this.loading = true;
      try {
        const selection = this.selectionSnapshot();
        const nextTask = await recognizeTask(this.task.id, targetIds);
        this.applyTask(nextTask, selection);
        this.message = "识别完成";
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async preview(template?: string) {
      if (!this.task?.id) return;
      this.loading = true;
      try {
        const appliedTemplate = template || this.settings?.filename_template || this.task.template;
        const selection = this.selectionSnapshot();
        const nextTask = await previewNames(this.task.id, appliedTemplate, this.selectedIds);
        this.applyTask(nextTask, selection);
        this.message = "命名预览已生成";
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
      }
    },
    async patchItem(itemId: string, patch: Partial<InvoiceItem>) {
      if (!this.task?.id) return;
      try {
        const selection = this.selectionSnapshot();
        if (Object.prototype.hasOwnProperty.call(patch, "selected")) {
          selection[itemId] = Boolean(patch.selected);
        }
        const nextTask = await patchItem(this.task.id, itemId, patch);
        this.applyTask(nextTask, selection);
        this.message = "已更新";
      } catch (error) {
        this.handleError(error);
      }
    },
    setItemSelected(itemId: string, nextValue: boolean) {
      const item = this.task?.items.find((row) => row.id === itemId);
      if (!item) return;
      item.selected = nextValue;
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
        this.lastPlan = null;
        this.lastRename = null;
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
      try {
        const selection = this.selectionSnapshot();
        if (isTauriRuntime()) {
          this.lastPlan = await buildCommitPlan(this.task.id, this.selectedIds);
          const tauriResults = await renameByTauri(this.lastPlan.plan);
          this.lastRename = await syncCommitResults(this.task.id, tauriResults);
        } else {
          this.lastRename = await commitRename(this.task.id, this.selectedIds);
        }
        const nextTask = await fetchTask(this.task.id);
        this.applyTask(nextTask, selection);
        this.message = "改名执行完成";
      } catch (error) {
        this.handleError(error);
      } finally {
        this.loading = false;
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
