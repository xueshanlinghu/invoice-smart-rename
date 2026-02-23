import { defineStore } from "pinia";
import {
  buildCommitPlan,
  commitRename,
  fetchTask,
  getSettings,
  importPaths,
  patchItem,
  previewNames,
  recognizeTask,
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
      try {
        this.task = await fetchTask(this.task.id);
      } catch (error) {
        this.handleError(error);
      }
    },
    async recognize(itemIds?: string[]) {
      if (!this.task?.id) return;
      this.loading = true;
      try {
        this.task = await recognizeTask(this.task.id, itemIds);
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
        this.task = await previewNames(this.task.id, appliedTemplate, this.selectedIds);
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
        this.task = await patchItem(this.task.id, itemId, patch);
      } catch (error) {
        this.handleError(error);
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
      this.loading = true;
      try {
        if (isTauriRuntime()) {
          this.lastPlan = await buildCommitPlan(this.task.id, this.selectedIds);
          const tauriResults = await renameByTauri(this.lastPlan.plan);
          this.lastRename = await syncCommitResults(this.task.id, tauriResults);
        } else {
          this.lastRename = await commitRename(this.task.id, this.selectedIds);
        }
        this.task = await fetchTask(this.task.id);
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
