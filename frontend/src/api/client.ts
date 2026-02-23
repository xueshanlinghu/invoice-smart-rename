import axios from "axios";
import type {
  AppSettings,
  AppSettingsUpdate,
  CommitPlanResponse,
  CommitRenameResponse,
  TaskState,
} from "./types";

const defaultApiBase = import.meta.env.VITE_API_BASE_URL || __APP_DEFAULT_API_BASE__ || "http://127.0.0.1:8765";

const api = axios.create({
  baseURL: defaultApiBase,
  timeout: 120000,
});

export async function importPaths(paths: string[]): Promise<TaskState> {
  const { data } = await api.post<TaskState>("/api/import", { paths });
  return data;
}

export async function recognizeTask(taskId: string, itemIds?: string[]): Promise<TaskState> {
  const { data } = await api.post<TaskState>("/api/recognize", {
    task_id: taskId,
    item_ids: itemIds,
  });
  return data;
}

export async function previewNames(taskId: string, template: string, itemIds?: string[]): Promise<TaskState> {
  const { data } = await api.post<TaskState>("/api/preview-names", {
    task_id: taskId,
    template,
    item_ids: itemIds,
  });
  return data;
}

export async function fetchTask(taskId: string): Promise<TaskState> {
  const { data } = await api.get<TaskState>(`/api/tasks/${taskId}`);
  return data;
}

export async function patchItem(
  taskId: string,
  itemId: string,
  patch: Record<string, unknown>,
): Promise<TaskState> {
  const { data } = await api.patch<TaskState>(`/api/items/${taskId}/${itemId}`, patch);
  return data;
}

export async function getSettings(): Promise<AppSettings> {
  const { data } = await api.get<AppSettings>("/api/settings");
  return data;
}

export async function updateSettings(update: AppSettingsUpdate): Promise<AppSettings> {
  const { data } = await api.put<AppSettings>("/api/settings", update);
  return data;
}

export async function buildCommitPlan(taskId: string, itemIds?: string[]): Promise<CommitPlanResponse> {
  const { data } = await api.post<CommitPlanResponse>("/api/commit-plan", {
    task_id: taskId,
    item_ids: itemIds,
    dry_run: true,
  });
  return data;
}

export async function commitRename(taskId: string, itemIds?: string[]): Promise<CommitRenameResponse> {
  const { data } = await api.post<CommitRenameResponse>("/api/commit-rename", {
    task_id: taskId,
    item_ids: itemIds,
  });
  return data;
}

export async function syncCommitResults(
  taskId: string,
  results: CommitRenameResponse["results"],
): Promise<CommitRenameResponse> {
  const { data } = await api.post<CommitRenameResponse>("/api/commit-results", {
    task_id: taskId,
    results,
  });
  return data;
}
